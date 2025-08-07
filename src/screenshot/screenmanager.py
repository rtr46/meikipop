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
            try:
                screen_idx = int(config.scan_region)
                self.set_scan_screen(screen_idx)
            except (ValueError, IndexError):
                logger.warning(f"Invalid screen '{config.scan_region}' in config, defaulting to screen 1.")
                self.set_scan_screen(1)

    def run(self):
        logger.debug("Screenshot thread started.")
        while self.shared_state.running:
            try:
                if config.auto_scan_mode and not config.is_enabled:
                    logger.debug(f"paused while auto mode")
                    self._sleep_and_handle_loop_exit(1)
                    continue
                self.shared_state.screenshot_trigger_event.wait()
                self.shared_state.screenshot_trigger_event.clear()
                if not self.shared_state.running: break
                logger.debug("Screenshot: Triggered!")

                logger.debug("screenmanager acquiring lock...")
                with self.shared_state.screen_lock:
                    logger.debug("...successfully acquired lock by screenmanager")
                    start_time = time.perf_counter()
                    screenshot = self.take_screenshot()
                logger.debug("...successfully released lock by screenmanager")
                processing_duration = time.perf_counter() - start_time
                logger.debug(f"Screenshot {screenshot.size} complete in {processing_duration:.2f}s")

                if self.last_screenshot and self.last_screenshot == screenshot:
                    logger.debug(f"Screen content didnt change... skipping ocr")
                    self._sleep_and_handle_loop_exit(0.1)
                    continue

                self.last_screenshot = screenshot
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
        if scan_rect:
            logger.info(f"Set scan area to region {scan_rect}")
            self.monitor = {"top": scan_rect.y(), "left": scan_rect.x(), "width": scan_rect.width(),
                            "height": scan_rect.height()}
            return True
        else:
            logger.info("Region selection cancelled.")
            return False

    def set_scan_screen(self, screen_index):
        logger.info(f"Set scan area to screen {screen_index}")
        with mss.mss() as sct:
            if screen_index < len(sct.monitors):
                logger.info(f"Set scan area to screen {screen_index}")
                self.monitor = sct.monitors[screen_index]
            else:
                logger.error(f"Cannot set scan screen: index {screen_index} is out of bounds.")

    def get_scan_geometry(self):
        if not self.monitor:
            return 0, 0, 0, 0
        return self.monitor["left"], self.monitor["top"], self.monitor["width"], self.monitor["height"]

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