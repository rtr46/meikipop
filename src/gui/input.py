# src/gui/input.py
import logging
import sys
import threading
import time

from pynput import mouse

from src.config.config import config, IS_LINUX, IS_MACOS

if IS_LINUX:
    from Xlib import display as xlib_display
    from Xlib.error import XError
    from Xlib import XK
elif IS_MACOS:
    import Quartz
    from AppKit import NSEvent
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
        self.modifier_groups = []
        modifier_map = {
            'shift': ['Shift_L', 'Shift_R'],
            'ctrl': ['Control_L', 'Control_R'],
            'alt': ['Alt_L', 'Alt_R']
        }
        hotkeys = self.hotkey_str.split('+')

        for key in hotkeys:
            target_keysyms = modifier_map.get(key)
            if not target_keysyms:
                logger.critical(f"Unsupported hotkey '{key}' for Linux/X11. Use 'shift', 'ctrl', or 'alt'.")
                sys.exit(1)
            group_keycodes = set()
            for keysym_str in target_keysyms:
                keysym = XK.string_to_keysym(keysym_str)
                if keysym:
                    keycode = self.display.keysym_to_keycode(keysym)
                    if keycode:
                        group_keycodes.add(keycode)

            if not group_keycodes:
                logger.critical(f"Could not find keycodes for hotkey '{key}'.")
                sys.exit(1)

            self.modifier_groups.append(group_keycodes)

    def is_hotkey_pressed(self) -> bool:
        try:
            key_map = self.display.query_keymap()
            for group in self.modifier_groups:
                group_is_pressed = False
                for keycode in group:
                    if (key_map[keycode // 8] >> (keycode % 8)) & 1:
                        group_is_pressed = True
                        break
                if not group_is_pressed:
                    return False
            return True
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


class MacOSKeyboardController:
    def __init__(self, hotkey_str):
        self.hotkey_str = hotkey_str.lower()
        self.modifiers = self.hotkey_str.split('+')

        # Map common hotkey strings to macOS key codes
        key_mapping = {
            'shift': [56, 60],  # Left and Right Shift
            'ctrl': [59, 62],   # Left and Right Control
            'alt': [58, 61],    # Left and Right Option/Alt
            'cmd': [55, 54],    # Left and Right Command
        }

        for mod in self.modifiers:
            self.keycodes_to_check = key_mapping.get(mod, [])
            if not self.keycodes_to_check:
                logger.critical(
                    f"Unsupported hotkey '{self.hotkey_str}' for macOS. Use 'shift', 'ctrl', 'alt', or 'cmd'.")
                sys.exit(1)

    def is_hotkey_pressed(self) -> bool:
        try:
            # Get current modifier flags
            flags = NSEvent.modifierFlags()

            # Iterate through all required modifiers in the combo
            for mod in self.modifiers:
                if mod == 'shift':
                    if not (flags & (1 << 17) or flags & (1 << 18)):
                        return False
                elif mod == 'ctrl':
                    if not (flags & (1 << 12)):
                        return False
                elif mod == 'alt':
                    if not (flags & (1 << 19)):
                        return False
                elif mod == 'cmd':
                    if not (flags & (1 << 20)):
                        return False
            return True
        except Exception as e:
            logger.warning(f"Error checking hotkey state: {e}")
            return False

class InputLoop(threading.Thread):
    def __init__(self, shared_state):
        super().__init__(daemon=True, name="InputLoop")
        self.shared_state = shared_state
        self.mouse_controller = mouse.Controller()

        self.hotkey_str = config.hotkey.lower()
        if IS_LINUX:
            self.keyboard_controller = LinuxX11KeyboardController(self.hotkey_str)
        elif IS_MACOS:
            self.keyboard_controller = MacOSKeyboardController(self.hotkey_str)
        else: # IS_WINDOWS
            self.keyboard_controller = WindowsKeyboardController(self.hotkey_str)

        self.started_auto_mode = False

    def run(self):
        logger.debug("Input thread started.")
        last_mouse_pos = (0, 0)
        hotkey_was_pressed = False

        while self.shared_state.running:
            if not config.is_enabled:
                time.sleep(0.1)
                continue
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

                # trigger screenshots + ocr in auto-on-mouse-move mode
                if config.auto_scan_mode and config.auto_scan_on_mouse_move and current_mouse_pos != last_mouse_pos:
                    self.shared_state.screenshot_trigger_event.set()

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

    def reapply_settings(self):
        logger.debug(f"InputLoop: Re-applying settings. New hotkey: '{config.hotkey}'.")
        self.hotkey_str = config.hotkey.lower()
        if IS_LINUX:
            self.keyboard_controller = LinuxX11KeyboardController(self.hotkey_str)
        elif IS_MACOS:
            self.keyboard_controller = MacOSKeyboardController(self.hotkey_str)
        else: # IS_WINDOWS
            self.keyboard_controller = WindowsKeyboardController(self.hotkey_str)

    @staticmethod
    def get_mouse_pos():
        with mouse.Controller() as mc:
            pos = mc.position
            # Convert floats to integers for QPoint compatibility
            return (int(pos[0]), int(pos[1]))
