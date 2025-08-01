# src/main.py
import sys
import threading
import signal

from PyQt6.QtCore import qInstallMessageHandler
from PyQt6.QtWidgets import QApplication

from src.config.config import config, APP_NAME, APP_VERSION
from src.gui.input import InputLoop
from src.screenshot.screenmanager import ScreenManager
from src.ocr.ocr import OcrProcessor
from src.ocr.hitdetector import HitDetector
from src.dictionary.lookup import Lookup
from src.gui.popup import Popup
from src.gui.tray import TrayIcon
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
    """A thread-safe object to hold and coordinate state between workers."""
    def __init__(self):
        self.lock = threading.Lock()
        self.running = True

        # Coordination events (Condition Variables)
        self.cv_screenshot = threading.Condition(self.lock)
        self.cv_ocr = threading.Condition(self.lock)
        self.cv_hit_detector = threading.Condition(self.lock)
        self.cv_lookup = threading.Condition(self.lock)

        # State flags
        self.trigger_screenshot = False
        self.trigger_ocr = False
        self.trigger_hit_detection = False
        self.trigger_lookup = False
        
        # Data passed between threads
        self.mouse_pos = (0, 0)
        self.screenshot_data = None
        self.ocr_results = None
        self.hit_result = None
        self.lookup_result = None
        self.hotkey_is_pressed = False
        
def main():
    setup_logging()
    shared_state = SharedState()

    global original_handler
    original_handler = qInstallMessageHandler(qt_message_handler)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    popup_window = Popup(shared_state)

    screen_manager = ScreenManager(shared_state)
    tray_icon = TrayIcon(screen_manager)
    threads = [
        InputLoop(shared_state),
        screen_manager,
        OcrProcessor(shared_state),
        HitDetector(shared_state),
        Lookup(shared_state, popup_window)
    ]

    for t in threads:
        t.start()
        
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    ready_message = f"""
    --------------------------------------------------
    {APP_NAME}.{APP_VERSION} is running in the background.

      - To use: Press and hold '{config.hotkey}' over Japanese text. 
      - To configure or change scan area: Right-click the icon in your system tray.
      - To exit: Press Ctrl+C in this terminal.

    --------------------------------------------------
    """
    print(ready_message)
    exit_code = app.exec()

    with shared_state.lock:
        shared_state.running = False
        shared_state.cv_screenshot.notify_all()
        shared_state.cv_ocr.notify_all()
        shared_state.cv_hit_detector.notify_all()
        shared_state.cv_lookup.notify_all()
    sys.exit(exit_code)

if __name__ == '__main__':
    main()