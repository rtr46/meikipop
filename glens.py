# glens.py
import io
import random
import time
import math
import re
from typing import Optional, Tuple, List
from multiprocessing import Process, Queue
import atexit
from dataclasses import dataclass

import requests
from PIL import Image

from lens_betterproto import LensOverlayServerResponse, LensOverlayServerRequest, CenterRotatedBox, WritingDirection
from settings import settings

JAPANESE_REGEX = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]')

@dataclass(frozen=True)
class ProcessedWord:
    text: str; separator: str; box: CenterRotatedBox
@dataclass(frozen=True)
class ProcessedParagraph:
    full_text: str; writing_direction: int; words: List[ProcessedWord]; bounding_box: CenterRotatedBox

def ocr_worker_main(request_queue: Queue, result_queue: Queue):
    """Processes OCR response bytes in a separate process."""
    while True:
        try:
            # The queue now only sends response bytes or None to terminate.
            response_bytes = request_queue.get()
            if response_bytes is None:
                break

            last_response = LensOverlayServerResponse().FromString(response_bytes)
            processed_paragraphs = []
            if last_response.objects_response.text.text_layout:
                for para in last_response.objects_response.text.text_layout.paragraphs:
                    # ... (rest of the processing logic is identical)
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
            result_queue.put(processed_paragraphs)

        except (KeyboardInterrupt, EOFError):
            break
        except Exception as e:
            result_queue.put(f"WORKER_ERROR: {e}")

class GoogleLensOcr:
    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            'Content-Type': 'application/x-protobuf', 'X-Goog-Api-Key': 'AIzaSyDr2UxVnv_U85AbhhY8XSHSIavUW0DC-sY',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        })
        
        self.request_queue = Queue()
        self.result_queue = Queue()
        self.worker_process = Process(target=ocr_worker_main, args=(self.request_queue, self.result_queue), daemon=True)
        self.worker_process.start()
        atexit.register(self.stop_worker)

    def stop_worker(self):
        if self.worker_process.is_alive():
            self.worker_process.terminate()

    def _process_image_for_upload(self, image: Image.Image) -> Tuple[bytes, int, int]:
        # Unchanged
        if settings.quality_mode == 'fast':
            scale_factor = math.sqrt(0.5)
            new_width = int(image.width * scale_factor)
            new_height = int(image.height * scale_factor)
            processed_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            processed_image = processed_image.convert('L').quantize(colors=16)
            with io.BytesIO() as bio:
                processed_image.save(bio, format='PNG')
                return bio.getvalue(), new_width, new_height
        elif settings.quality_mode == 'balanced':
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
        image_bytes, final_width, final_height = self._process_image_for_upload(image)
        request = LensOverlayServerRequest()
        request.objects_request.request_context.request_id.uuid = random.randint(0, 2**64 - 1)
        request.objects_request.image_data.payload.image_bytes = image_bytes
        request.objects_request.image_data.image_metadata.width = final_width
        request.objects_request.image_data.image_metadata.height = final_height
        try:
            settings.user_log("Sending screenshot for OCR...")
            start_time = time.perf_counter()
            response = self._session.post(
                'https://lensfrontend-pa.googleapis.com/v1/crupload',
                data=request.SerializeToString(), timeout=10
            )
            network_duration = time.perf_counter() - start_time
            response.raise_for_status()
            
            settings.user_log(f"OCR response received in {network_duration:.2f}s. Processing in background...")
            
            # Send the normal process command
            self.request_queue.put(response.content)
            result = self.result_queue.get()

            if isinstance(result, str) and result.startswith("WORKER_ERROR:"):
                settings.user_log(f"ERROR: {result}")
                return None
            
            settings.user_log("Processing complete. Caching result.")
            return result
            
        except requests.RequestException as e:
            settings.user_log(f"OCR Request Failed: {e}")
            return None