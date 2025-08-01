# glens.py
import io
import logging
import random
import time
import math
import re
from typing import Optional, Tuple, List
from dataclasses import dataclass
import requests
from PIL import Image
from src.ocr.lens_betterproto import LensOverlayServerResponse, LensOverlayServerRequest, CenterRotatedBox
from src.config.config import config

JAPANESE_REGEX = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]')

@dataclass(frozen=True)
class ProcessedWord:
    text: str; separator: str; box: CenterRotatedBox

@dataclass(frozen=True)
class ProcessedParagraph:
    full_text: str; writing_direction: int; words: List[ProcessedWord]; bounding_box: CenterRotatedBox

logger = logging.getLogger(__name__) # Get the logger

class GoogleLensOcr:
    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            'Content-Type': 'application/x-protobuf', 'X-Goog-Api-Key': 'AIzaSyDr2UxVnv_U85AbhhY8XSHSIavUW0DC-sY',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        })

    def _process_image_for_upload(self, image: Image.Image) -> Tuple[bytes, int, int]:
        if config.quality_mode == 'fast':
            scale_factor = math.sqrt(0.5)
            new_width = int(image.width * scale_factor)
            new_height = int(image.height * scale_factor)
            processed_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            processed_image = processed_image.convert('L').quantize(colors=16)
            with io.BytesIO() as bio:
                processed_image.save(bio, format='PNG')
                return bio.getvalue(), new_width, new_height
        elif config.quality_mode == 'balanced':
            processed_image = image.convert('RGB')
            with io.BytesIO() as bio:
                processed_image.save(bio, format='JPEG', quality=90)
                return bio.getvalue(), image.width, image.height
        else:
            processed_image = image.convert('RGB')
            with io.BytesIO() as bio:
                processed_image.save(bio, format='PNG')
                return bio.getvalue(), image.width, image.height

    def scan_and_process(self, image: Image.Image) -> Optional[List[ProcessedParagraph]]:
        start_time = time.perf_counter()
        image_bytes, final_width, final_height = self._process_image_for_upload(image)
        request = LensOverlayServerRequest()
        request.objects_request.request_context.request_id.uuid = random.randint(0, 2**64 - 1)
        request.objects_request.image_data.payload.image_bytes = image_bytes
        request.objects_request.image_data.image_metadata.width = final_width
        request.objects_request.image_data.image_metadata.height = final_height

        try:
            request_duration = time.perf_counter() - start_time
            logger.debug(f"Request created in {request_duration:.2f}s. Sending screenshot for OCR...")
            start_time = time.perf_counter()
            response = self._session.post(
                'https://lensfrontend-pa.googleapis.com/v1/crupload',
                data=request.SerializeToString(), timeout=10
            )
            network_duration = time.perf_counter() - start_time
            response.raise_for_status()
            logger.debug(f"OCR response received in {network_duration:.2f}s. Processing...")

            last_response = LensOverlayServerResponse().FromString(response.content)
            processed_paragraphs = []
            if last_response.objects_response.text.text_layout:
                for para in last_response.objects_response.text.text_layout.paragraphs:
                    para_has_japanese = any(JAPANESE_REGEX.search(w.plain_text) for l in para.lines for w in l.words)
                    if not para_has_japanese: continue
                    words_in_para = []
                    full_para_text = ""
                    for line in para.lines:
                        for word in line.words:
                            clean_word_text = word.plain_text.replace(' ', '')
                            separator = word.text_separator or ""
                            words_in_para.append(ProcessedWord(text=clean_word_text, separator=separator, box=word.geometry.bounding_box))
                            full_para_text += clean_word_text + separator
                    if full_para_text:
                        processed_paragraphs.append(ProcessedParagraph(full_text=full_para_text, writing_direction=para.writing_direction.value, words=words_in_para, bounding_box=para.geometry.bounding_box))

            if processed_paragraphs:
                full_text_preview = processed_paragraphs[0].full_text[:30]
                logger.info("OCR complete in %.2fs. Found %d paragraphs. (e.g., \"%s...\")",network_duration, len(processed_paragraphs), full_text_preview)
            else:
                logger.info("OCR complete in %.2fs. No Japanese text found.", network_duration)

            return processed_paragraphs

        except requests.RequestException as e:
            logger.error("OCR Request Failed: %s", e)
            return None