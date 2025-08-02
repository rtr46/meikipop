# src/ocr/ocr.py
import logging
import threading

from src.config.config import config
from src.ocr.glens import GoogleLensOcr

logger = logging.getLogger(__name__)  # Get the logger

class OcrProcessor(threading.Thread):
    def __init__(self, shared_state):
        super().__init__(daemon=True, name="OcrProcessor")
        self.shared_state = shared_state
        self.glens = GoogleLensOcr()

    def run(self):
        logger.debug("OCR thread started.")
        while self.shared_state.running:
            try:
                screenshot = self.shared_state.ocr_queue.get()
                if not self.shared_state.running: break

                logger.debug("OCR: Triggered!")
                ocr_result = self.ocr(screenshot)
                # todo keep last ocr result?

                # Reset trigger and notify next thread
                self.shared_state.hit_scan_queue.put((True, ocr_result))
            except:
                logger.exception("An unexpected error occurred in the ocr loop. Continuing...")
            finally:
                if config.auto_scan_mode:
                    self.shared_state.screenshot_trigger_event.set()
        logger.debug("OCR thread stopped.")

    def ocr(self, screenshot):
        return self.glens.scan_and_process(screenshot)
