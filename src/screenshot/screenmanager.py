# src/screenshot/screenmanager.py
import logging
import threading
import time

import mss
from PIL import Image

from src.config.config import config
from src.gui.region_selector import RegionSelector

logger = logging.getLogger(__name__) # Get the logger

# todo doesnt work when monitors change
class ScreenManager(threading.Thread):
    def __init__(self, shared_state):
        super().__init__(daemon=True, name="ScreenManager")
        self.shared_state = shared_state
        self.monitor = None
        if config.scan_region == "region":
            self.set_scan_region()
        else:
            self.set_scan_screen(1)

    def run(self):
        # print("Screenshot thread started.")
        while self.shared_state.running:
            with self.shared_state.lock:
                self.shared_state.cv_screenshot.wait_for(lambda: self.shared_state.trigger_screenshot)
                if not self.shared_state.running: break

                #print("Screenshot: Triggered!")
                start_time = time.perf_counter()
                self.take_screenshot()
                processing_duration = time.perf_counter() - start_time
                logger.debug(f"Screenshot {self.shared_state.screenshot_data.size} complete in {processing_duration:.2f}s")

                # Reset trigger and notify next thread
                self.shared_state.trigger_screenshot = False
                self.shared_state.trigger_ocr = True
                self.shared_state.cv_ocr.notify()
        # print("Screenshot thread stopped.")

    def take_screenshot(self):
        with mss.mss() as sct:
            sct_img = sct.grab(self.monitor)
            self.shared_state.screenshot_data = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

    def set_scan_region(self):
        scan_rect = RegionSelector.get_region()
        logger.info(f"Set scan area to region {scan_rect}")
        self.monitor = {"top": scan_rect.y(), "left": scan_rect.x(), "width": scan_rect.width(), "height": scan_rect.height()}
        self.shared_state.mouse_offset = (self.monitor["left"], self.monitor["top"])

    def set_scan_screen(self, screen_index):
        logger.info(f"Set scan area to screen {screen_index}")
        with mss.mss() as sct:
            self.monitor = sct.monitors[screen_index]
        self.shared_state.mouse_offset = (self.monitor["left"], self.monitor["top"])

    @staticmethod
    def get_screens():
        with mss.mss() as sct:
            return sct.monitors