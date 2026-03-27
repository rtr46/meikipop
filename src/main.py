# src/main.py
import signal
import sys
import threading

from PyQt6.QtCore import qInstallMessageHandler
from PyQt6.QtWidgets import QApplication

from src.config.config import config, APP_NAME, APP_VERSION
from src.dictionary.lookup import Lookup
from src.gui.input import InputLoop
from src.gui.overlay_furigana import OverlayFurigana
from src.gui.overlay_selection import OverlaySelection
from src.gui.popup import Popup
from src.gui.tray import TrayIcon
from src.ocr.hit_scan import HitScanner
from src.ocr.ocr import OcrProcessor
from src.screenshot.screenmanager import ScreenManager
from src.utils.lastest_queue import LatestValueQueue
from src.utils.logger import setup_logging


def qt_message_handler(mode, context, message):
    # Check if the message is the specific warning we want to suppress.
    if "QWindowsWindow::setGeometry" in message and "Unable to set geometry" in message:
        return  # Silently ignore this specific warning.
    if original_handler:
        original_handler(mode, context, message)

# This global variable will hold the original message handler.
original_handler = None


class SharedState:
    def __init__(self):
        self.running = True

        # events and queues
        self.screenshot_trigger_event = threading.Event()
        self.ocr_queue = LatestValueQueue()
        self.hit_scan_queue = LatestValueQueue()
        self.lookup_queue = LatestValueQueue()

        # screen lock - used by screen manager and popup
        self.screen_lock = threading.RLock()


def main():
    setup_logging()
    shared_state = SharedState()

    global original_handler
    original_handler = qInstallMessageHandler(qt_message_handler)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    input_loop = InputLoop(shared_state)
    screen_manager = ScreenManager(shared_state, input_loop)

    hit_scanner = HitScanner(shared_state, input_loop, screen_manager)

    overlay_furigana = OverlayFurigana(screen_manager)
    overlay_selection = OverlaySelection(screen_manager)
    popup_window = Popup(
        shared_state, input_loop,
        overlay_furigana=overlay_furigana,
        hit_scanner=hit_scanner,
    )

    lookup = Lookup(shared_state, popup_window)
    ocr_processor = OcrProcessor(shared_state, screen_manager)

    # ---- Gamepad subsystem (optional — silently skipped if disabled) ---------
    gamepad_controller = None
    if config.gamepad_enabled:
        try:
            from src.gamepad.navigation import NavigationState
            from src.gamepad.controller import GamepadController

            navigation = NavigationState(
                shared_state=shared_state,
                input_loop=input_loop,
                overlay_selection=overlay_selection,
                overlay_furigana=overlay_furigana,
                screen_manager=screen_manager,
            )

            # Set popup reference for thread-safe hiding
            navigation.set_popup(popup_window)

            # Wire up the HitScanner so NavigationState is notified on new OCR
            hit_scanner.set_ocr_update_callback(navigation.on_new_ocr_result)

            gamepad_controller = GamepadController(shared_state, input_loop, navigation)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(
                "Failed to initialise gamepad subsystem: %s  "
                "(Gamepad features will be unavailable this session.)", exc
            )

    # ---- Tray icon ----------------------------------------------------------
    tray_icon = TrayIcon(screen_manager, ocr_processor, popup_window, input_loop, lookup,
                         gamepad_controller=gamepad_controller)

    # ---- Start threads -------------------------------------------------------
    threads = [lookup, hit_scanner, ocr_processor, screen_manager, input_loop]
    if gamepad_controller is not None:
        threads.append(gamepad_controller)
    for t in threads:
        t.start()

    ready_message = f"""
    --------------------------------------------------
    {APP_NAME}.{APP_VERSION} is running in the background.

      - To use: Press and hold '{config.hotkey}' over Japanese text.
      - Gamepad: {'enabled — press Back/Select to enter navigation mode' if config.gamepad_enabled else 'disabled (enable in Settings → Gamepad)'}
      - To configure: Right-click the icon in your system tray.
      - To exit: Press Ctrl+C in this terminal.

    --------------------------------------------------
    """
    print(ready_message)

    def signal_handler(sig, frame):
        QApplication.quit()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    exit_code = app.exec()

    shared_state.running = False
    shared_state.screenshot_trigger_event.set()
    shared_state.ocr_queue.put(None)
    shared_state.hit_scan_queue.put((False, None))
    shared_state.lookup_queue.put(None)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
