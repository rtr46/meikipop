# meikipop/screenshot/screenmanager.py
import logging
import threading
import time

from PIL import Image

from meikipop.config.config import config, IS_WAYLAND
from meikipop.gui.region_selector import RegionSelector

if IS_WAYLAND:
    from . import wayland_mss_shim

    mss = wayland_mss_shim.MSSModuleShim()
else:
    import mss

logger = logging.getLogger(__name__)  # Get the logger


# todo doesnt work when monitors change
class ScreenManager(threading.Thread):
    def __init__(self, shared_state, input_loop):
        super().__init__(daemon=True, name="ScreenManager")
        self.shared_state = shared_state
        self.monitor = None
        self.last_ocr_put_time = 0.0
        self.last_screenshots = {}  # geometry -> last screenshot taken of that area (skip unchanged content)
        self.last_mouse_pos = None
        self.input_loop = input_loop
        self._monitors = []
        if config.scan_region == "mouse":
            self.set_scan_follow_mouse()
        elif config.scan_region == "region":
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

                # prevent multiple ocr runs during auto_scan_interval_seconds
                seconds_since_last_ocr = time.perf_counter() - self.last_ocr_put_time
                if config.auto_scan_mode and seconds_since_last_ocr < config.auto_scan_interval_seconds:
                    logger.debug(
                        f"...{seconds_since_last_ocr:.2f}s since last ocr, sleeping for another {config.auto_scan_interval_seconds - seconds_since_last_ocr:.2f}s")
                    self._sleep_and_handle_loop_exit(config.auto_scan_interval_seconds - seconds_since_last_ocr)
                    continue

                # prevent ocr runs without mouse movements for auto-on-mouse-move mode
                if config.auto_scan_mode and config.auto_scan_on_mouse_move and self.last_mouse_pos == self.input_loop.get_mouse_pos():
                    continue
                self.last_mouse_pos = self.input_loop.get_mouse_pos()

                logger.debug("screenmanager acquiring lock...")
                with self.shared_state.screen_lock:
                    logger.debug("...successfully acquired lock by screenmanager")
                    start_time = time.perf_counter()
                    if config.scan_region == "mouse":
                        monitor = self.monitor_under_mouse()
                        if monitor:
                            self.monitor = monitor
                    geometry = self.get_monitor_geometry(self.monitor)
                    screenshot = self.take_screenshot()
                logger.debug("...successfully released lock by screenmanager")
                processing_duration = time.perf_counter() - start_time
                logger.debug(f"Screenshot {screenshot.size} complete in {processing_duration:.2f}s")

                last_screenshot = self.last_screenshots.get(geometry)
                if last_screenshot and last_screenshot.raw == screenshot.raw:
                    logger.debug(f"Screen content didnt change... skipping ocr")
                    self._sleep_and_handle_loop_exit(0.1)
                    continue

                if config.scan_region != "mouse":
                    self.last_screenshots.clear()  # only one area is ever scanned in the other modes
                self.last_screenshots[geometry] = screenshot
                self.last_mouse_pos = self.input_loop.get_mouse_pos()
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                self.shared_state.ocr_queue.put((img, geometry))
                self.last_ocr_put_time = time.perf_counter()
            except:
                logger.exception("An unexpected error occurred in the screenshot loop. Continuing...")
                self._sleep_and_handle_loop_exit(1)
        logger.debug("Screenshot thread stopped.")

    def take_screenshot(self):
        with mss.mss() as sct:
            sct_img = sct.grab(self.monitor)
            return sct_img

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

    def set_scan_follow_mouse(self):
        logger.info("Set scan area to the screen under the mouse")
        self._refresh_monitors()
        self.monitor = self.monitor_under_mouse() or (self._monitors[0] if self._monitors else None)

    def _refresh_monitors(self):
        with mss.mss() as sct:
            self._monitors = list(sct.monitors[1:])  # [0] is the combined virtual screen

    def _find_monitor(self, x, y):
        for m in self._monitors:
            if m["left"] <= x < m["left"] + m["width"] and m["top"] <= y < m["top"] + m["height"]:
                return m
        return None

    def monitor_under_mouse(self):
        x, y = self.input_loop.get_mouse_pos()
        monitor = self._find_monitor(x, y)
        if monitor is None:  # monitor layout may have changed
            self._refresh_monitors()
            monitor = self._find_monitor(x, y)
        return monitor

    @staticmethod
    def get_monitor_geometry(monitor):
        if not monitor:
            return 0, 0, 0, 0
        return monitor["left"], monitor["top"], monitor["width"], monitor["height"]

    def get_scan_geometry(self):
        """Geometry of the area hit scans should use right now (the screen under the mouse in follow-mouse mode)."""
        if config.scan_region == "mouse":
            return self.get_monitor_geometry(self.monitor_under_mouse())
        return self.get_monitor_geometry(self.monitor)

    def force_screenshot_trigger(self):
        self.last_screenshots = {}
        self.last_mouse_pos = None

    def _sleep_and_handle_loop_exit(self, interval):
        if config.auto_scan_mode:
            time.sleep(interval)
            self.shared_state.screenshot_trigger_event.set()
        else:
            self.shared_state.hit_scan_queue.trigger()

    @staticmethod
    def get_screens():
        with mss.mss() as sct:
            return sct.monitors