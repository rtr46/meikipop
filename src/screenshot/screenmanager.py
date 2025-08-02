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
        self.last_screenshot = None
        if config.scan_region == "region":
            self.set_scan_region()
        else:
            self.set_scan_screen(1)

    def run(self):
        logger.debug("Screenshot thread started.")
        while self.shared_state.running:
            try:
                self.shared_state.screenshot_trigger_event.wait()
                self.shared_state.screenshot_trigger_event.clear()
                if not self.shared_state.running: break
                logger.debug("Screenshot: Triggered!")

                with self.shared_state.screen_lock:
                    start_time = time.perf_counter()
                    screenshot = self.take_screenshot()
                processing_duration = time.perf_counter() - start_time
                logger.debug(f"Screenshot {screenshot.size} complete in {processing_duration:.2f}s")

                if self.last_screenshot and self.last_screenshot == screenshot:
                    logger.debug(f"Screen content didnt change... skipping ocr")
                    self._sleep_and_handle_loop_exit(0.1)
                    continue

                self.last_screenshot = screenshot
                self.shared_state.screenshot_data = screenshot  # todo remove eventually... currently needed by hit_scan
                self.shared_state.ocr_queue.put(screenshot)
            except:
                logger.exception("An unexpected error occurred in the screenshot loop. Continuing...")
                self._sleep_and_handle_loop_exit(1)
        logger.debug("Screenshot thread stopped.")

    def take_screenshot(self):
        with mss.mss() as sct:
            sct_img = sct.grab(self.monitor)
            return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

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

    def _sleep_and_handle_loop_exit(self, interval):
        if config.auto_scan_mode:
            time.sleep(interval)
            self.shared_state.screenshot_trigger_event.set()
        else:
            self.shared_state.hit_scan_queue.put((False, None))

    @staticmethod
    def get_screens():
        with mss.mss() as sct:
            return sct.monitors