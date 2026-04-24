# meikipop/main.py
import argparse
import signal
import sys
import threading

from PyQt6.QtCore import qInstallMessageHandler
from PyQt6.QtWidgets import QApplication

from meikipop.utils.logger import setup_logging
from meikipop.config.config import config, APP_NAME, APP_VERSION
from meikipop.dictionary.lookup import Lookup
from meikipop.gui.input import InputLoop
from meikipop.gui.popup import Popup
from meikipop.gui.tray import TrayIcon
from meikipop.ocr.hit_scan import HitScanner
from meikipop.ocr.ocr import OcrProcessor
from meikipop.screenshot.screenmanager import ScreenManager
from meikipop.utils.lastest_queue import LatestValueQueue


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


def run_gui():
    setup_logging()
    shared_state = SharedState()

    global original_handler
    original_handler = qInstallMessageHandler(qt_message_handler)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    input_loop = InputLoop(shared_state)
    popup_window = Popup(shared_state, input_loop)

    screen_manager = ScreenManager(shared_state, input_loop)  # trigger region selection
    lookup = Lookup(shared_state, popup_window)  # load dictionary

    ocr_processor = OcrProcessor(shared_state, screen_manager)
    hit_scanner = HitScanner(shared_state, input_loop, screen_manager)
    tray_icon = TrayIcon(screen_manager, ocr_processor, popup_window, input_loop, lookup)

    for t in [lookup, hit_scanner, ocr_processor, screen_manager, input_loop]:
        t.start()

    ready_message = f"""
    --------------------------------------------------
    {APP_NAME}.{APP_VERSION} is running in the background.

      - To configure or change scan area: Right-click the icon in your system tray.
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
    shared_state.hit_scan_queue.trigger()
    shared_state.lookup_queue.put(None)
    sys.exit(exit_code)


def main():
    parser = argparse.ArgumentParser(
        prog="meikipop",
        description="Universal Japanese OCR popup dictionary"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("build-dict", help="Build the dictionary from source files")

    import_html_parser = subparsers.add_parser("import-yomitan-dict-html", help="Import Yomitan dictionary (HTML format)")
    import_html_parser.add_argument("dictionary_files", nargs='+', help="Path(s) to the dictionary zip file(s)")

    import_text_parser = subparsers.add_parser("import-yomitan-dict-text", help="Import Yomitan dictionary (text format)")
    import_text_parser.add_argument("dictionary_files", nargs='+', help="Path(s) to the dictionary zip file(s)")

    args = parser.parse_args()

    if args.command == "build-dict":
        from meikipop.scripts.build_dictionary import main as build_main
        build_main()
    elif args.command == "import-yomitan-dict-html":
        from meikipop.scripts.import_yomitan_dict_html import main as import_html_main
        import_html_main([*args.dictionary_files])
    elif args.command == "import-yomitan-dict-text":
        from meikipop.scripts.import_yomitan_dict_text import main as import_text_main
        import_text_main([*args.dictionary_files])
    else:
        run_gui()


if __name__ == "__main__":
    main()