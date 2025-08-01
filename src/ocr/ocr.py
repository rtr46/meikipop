# src/ocr/ocr.py
import threading

from src.ocr.glens import GoogleLensOcr


class OcrProcessor(threading.Thread):
    def __init__(self, shared_state):
        super().__init__(daemon=True, name="OcrProcessor")
        self.shared_state = shared_state
        self.glens = GoogleLensOcr()

    def run(self):
        #print("OCR thread started.")
        while self.shared_state.running:
            with self.shared_state.lock: # todo here and at screenmanager it is blocking
                self.shared_state.cv_ocr.wait_for(lambda: self.shared_state.trigger_ocr)
                if not self.shared_state.running: break

                #print("OCR: Triggered!")
                self.ocr()

                # Reset trigger and notify next thread
                self.shared_state.trigger_ocr = False
                self.shared_state.trigger_hit_detection = True
                self.shared_state.cv_hit_detector.notify()
        #print("OCR thread stopped.")

    def ocr(self):
        self.shared_state.ocr_results = self.glens.scan_and_process(self.shared_state.screenshot_data)
