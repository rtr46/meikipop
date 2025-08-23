# glensv2/provider.py
import io
import logging
import math
import random
import re
import time
from typing import Optional, List, Tuple

import requests
from PIL import Image

from src.config.config import config
from src.ocr.interface import OcrProvider, Paragraph, Word, BoundingBox
from src.ocr.providers.glens.lens_betterproto import LensOverlayServerRequest, WritingDirection, \
    LensOverlayServerResponse
from src.ocr.providers.postprocessing import group_lines_into_paragraphs  # Import the new function

JAPANESE_REGEX = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]')

logger = logging.getLogger(__name__)


class GoogleLensOcrV2(OcrProvider):
    NAME = "Google Lens v2-beta (better vertical text support)"

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

    def scan(self, image: Image.Image) -> Optional[List[Paragraph]]:
        start_time = time.perf_counter()
        image_bytes, final_width, final_height = self._process_image_for_upload(image)
        request = LensOverlayServerRequest()
        request.objects_request.request_context.request_id.uuid = random.randint(0, 2 ** 64 - 1)
        request.objects_request.image_data.payload.image_bytes = image_bytes
        request.objects_request.image_data.image_metadata.width = final_width
        request.objects_request.image_data.image_metadata.height = final_height

        try:
            request_duration = time.perf_counter() - start_time
            logger.debug(f"Request created in {request_duration:.2f}s. Sending screenshot for OCR...")
            start_time_req = time.perf_counter()
            response = self._session.post(
                'https://lensfrontend-pa.googleapis.com/v1/crupload',
                data=request.SerializeToString(), timeout=10
            )
            network_duration = time.perf_counter() - start_time_req
            response.raise_for_status()
            logger.debug(f"OCR response received in {network_duration:.2f}s. Processing...")

            glens_response = LensOverlayServerResponse().FromString(response.content)

            raw_lines = []
            if glens_response.objects_response.text.text_layout:
                for para in glens_response.objects_response.text.text_layout.paragraphs:
                    is_vertical = para.writing_direction == WritingDirection.TOP_TO_BOTTOM

                    for line in para.lines:
                        line_has_japanese = any(JAPANESE_REGEX.search(w.plain_text) for w in line.words)
                        if not line_has_japanese:
                            continue

                        words_in_line = []
                        full_line_text = ""
                        for word in line.words:
                            clean_word_text = word.plain_text.replace(' ', '')
                            separator = word.text_separator or ""

                            w_box = BoundingBox(
                                center_x=word.geometry.bounding_box.center_x,
                                center_y=word.geometry.bounding_box.center_y,
                                width=word.geometry.bounding_box.width,
                                height=word.geometry.bounding_box.height,
                            )
                            words_in_line.append(Word(text=clean_word_text, separator=separator, box=w_box))
                            full_line_text += clean_word_text + separator

                        if full_line_text:
                            l_box = BoundingBox(
                                center_x=line.geometry.bounding_box.center_x,
                                center_y=line.geometry.bounding_box.center_y,
                                width=line.geometry.bounding_box.width,
                                height=line.geometry.bounding_box.height,
                            )
                            # Create a temporary Paragraph object for each line
                            raw_lines.append(
                                Paragraph(full_text=full_line_text.strip(), words=words_in_line, box=l_box,
                                          is_vertical=is_vertical)
                            )

            processed_paragraphs = group_lines_into_paragraphs(raw_lines)

            total_duration = time.perf_counter() - start_time
            if processed_paragraphs:
                full_text_preview = processed_paragraphs[0].full_text[:30]
                logger.info("OCR complete in %.2fs. Found %d paragraphs. (e.g., \"%s...\")", total_duration,
                            len(processed_paragraphs), full_text_preview)
            else:
                logger.info("OCR complete in %.2fs. No Japanese text found.", total_duration)

            return processed_paragraphs

        except requests.RequestException as e:
            logger.error("OCR Request Failed: %s", e)
            return None
