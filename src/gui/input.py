# src/gui/input.py
import logging
import sys
import threading
import time

from pynput import mouse

from src.config.config import config, IS_LINUX

if IS_LINUX:
    from Xlib import display as xlib_display
    from Xlib.error import XError
    from Xlib import XK
else:
    import keyboard


logger = logging.getLogger(__name__)

class LinuxX11KeyboardController:
    def __init__(self, hotkey_str):
        self.hotkey_str = hotkey_str.lower()
        try:
            self.display = xlib_display.Display()
            self._setup_keycodes()
        except (XError, Exception) as e:
            logger.critical("Could not connect to X server. Is DISPLAY environment variable set? Error: %s", e)
            logger.critical("Meikipop cannot run without a graphical session.")
            sys.exit(1)

    def _setup_keycodes(self):
        self.keycodes_to_check = set()
        modifier_map = {
            'shift': ['Shift_L', 'Shift_R'],
            'ctrl': ['Control_L', 'Control_R'],
            'alt': ['Alt_L', 'Alt_R']
        }
        target_keysyms = modifier_map.get(self.hotkey_str)
        if not target_keysyms:
            logger.critical(f"Unsupported hotkey '{self.hotkey_str}' for Linux/X11. Use 'shift', 'ctrl', or 'alt'.")
            sys.exit(1)
        for keysym_str in target_keysyms:
            keysym = XK.string_to_keysym(keysym_str)
            if keysym:
                keycode = self.display.keysym_to_keycode(keysym)
                if keycode:
                    self.keycodes_to_check.add(keycode)
        if not self.keycodes_to_check:
            logger.critical(f"Could not find keycodes for hotkey '{self.hotkey_str}'.")
            sys.exit(1)
    def is_hotkey_pressed(self) -> bool:
        try:
            key_map = self.display.query_keymap()
            for keycode in self.keycodes_to_check:
                if (key_map[keycode // 8] >> (keycode % 8)) & 1:
                    return True
            return False
        except XError:
            return False

class WindowsKeyboardController:
    def __init__(self, hotkey_str):
        self.hotkey_str = hotkey_str.lower()

    def is_hotkey_pressed(self) -> bool:
        try:
            return keyboard.is_pressed(self.hotkey_str)
        except ImportError:
            logger.critical("FATAL: The 'keyboard' library failed to import a backend. This often means it needs to be run with administrator/sudo privileges.")
            sys.exit(1)
        except Exception:
            return False

class InputLoop(threading.Thread):
    def __init__(self, shared_state):
        super().__init__(daemon=True, name="InputLoop")
        self.shared_state = shared_state
        self.mouse_controller = mouse.Controller()

        self.hotkey_str = config.hotkey.lower()
        self.keyboard_controller = LinuxX11KeyboardController(self.hotkey_str) if IS_LINUX else WindowsKeyboardController(self.hotkey_str)

        self.started_auto_mode = False

    def run(self):

        logger.debug("Input thread started.")
        last_mouse_pos = (0, 0)
        hotkey_was_pressed = False

        while self.shared_state.running:
            try:
                current_mouse_pos = self.mouse_controller.position
                try:
                    hotkey_is_pressed = self.keyboard_controller.is_hotkey_pressed()
                except Exception:
                    hotkey_is_pressed = False

                # trigger screenshots + ocr in manual mode
                if hotkey_is_pressed and not hotkey_was_pressed and not config.auto_scan_mode:
                    logger.info(f"Input: Hotkey '{config.hotkey}' pressed. Triggering screenshot.")
                    self.shared_state.screenshot_trigger_event.set()

                # trigger initial screenshots + ocr in auto mode
                if not self.started_auto_mode and config.auto_scan_mode:
                    self.shared_state.screenshot_trigger_event.set()
                self.started_auto_mode = config.auto_scan_mode

                # trigger hit_scans + lookups
                if current_mouse_pos != last_mouse_pos:
                    self.shared_state.hit_scan_queue.put((False, None))

                if hotkey_was_pressed and not hotkey_is_pressed:
                    logger.info(f"Input: Hotkey '{config.hotkey}' released.")

                last_mouse_pos = current_mouse_pos
                hotkey_was_pressed = hotkey_is_pressed
                self.hotkey_is_pressed = hotkey_is_pressed
            except:
                logger.exception("An unexpected error occurred in the input loop. Continuing...")
            finally:
                time.sleep(0.01)
        logger.debug("Input thread stopped.")

    def is_virtual_hotkey_down(self):
        return self.keyboard_controller.is_hotkey_pressed() or (
                    config.auto_scan_mode and config.auto_scan_mode_lookups_without_hotkey)

    @staticmethod
    def get_mouse_pos():
        with mouse.Controller() as mc:
            return mc.position