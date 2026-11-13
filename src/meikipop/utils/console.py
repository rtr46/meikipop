# meikipop/utils/console.py
"""
Optional console window handling.

On Windows meikipop runs without a visible console window by default. The console can be opened (and hidden
again) from the tray icon's context menu. Everything that was logged before the console was opened is kept in a
small in-memory buffer and replayed once the console is shown, so no output is lost.

On other platforms (or when meikipop was started from an existing terminal) nothing is hidden and the console
toggle is not offered.
"""
import collections
import logging
import os
import sys
import threading

from meikipop.config.config import IS_WINDOWS

_MAX_BUFFERED_LINES = 2000

# win32 constants
_SW_HIDE = 0
_SW_SHOW = 5
_SC_CLOSE = 0xF060
_MF_BYCOMMAND = 0x0
_CP_UTF8 = 65001


def _win32():
    """Returns (kernel32, user32) with handle-returning functions typed correctly for 64-bit Windows."""
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32
    kernel32.GetConsoleWindow.restype = wintypes.HWND
    user32.GetSystemMenu.argtypes = [wintypes.HWND, wintypes.BOOL]
    user32.GetSystemMenu.restype = wintypes.HMENU
    user32.DeleteMenu.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    return kernel32, user32


class _BufferHandler(logging.Handler):
    def __init__(self, manager):
        super().__init__()
        self.manager = manager

    def emit(self, record):
        try:
            self.manager._append_to_buffer(self.format(record))
        except Exception:
            self.handleError(record)


class ConsoleManager:
    def __init__(self):
        self._buffer = collections.deque(maxlen=_MAX_BUFFERED_LINES)
        self._buffer_lock = threading.Lock()
        self._stream_handler = None
        self._formatter = None
        # True if meikipop controls its own console window (i.e. it was not started from an existing terminal)
        self.can_toggle = False

    # --- logging integration ---

    def install_logging(self, logger: logging.Logger, formatter: logging.Formatter):
        self._formatter = formatter
        buffer_handler = _BufferHandler(self)
        buffer_handler.setFormatter(formatter)
        logger.addHandler(buffer_handler)
        if sys.stdout is not None:
            self._stream_handler = logging.StreamHandler(sys.stdout)
            self._stream_handler.setFormatter(formatter)
            logger.addHandler(self._stream_handler)

    def print(self, message: str):
        """print() replacement that also keeps the message for when the console is opened later."""
        self._append_to_buffer(message)
        if sys.stdout is not None:
            try:
                print(message, flush=True)
            except Exception:
                pass

    def _append_to_buffer(self, line: str):
        with self._buffer_lock:
            self._buffer.append(line)

    # --- console window handling ---

    def hide_on_startup(self):
        """Hides the console window on startup, unless it belongs to a terminal the user started us from."""
        if not IS_WINDOWS:
            return
        try:
            import ctypes
            kernel32, user32 = _win32()
            hwnd = kernel32.GetConsoleWindow()
            if not hwnd:
                # windowed build without any console: we can create one on demand.
                # Some libraries write to stdout/stderr unconditionally, so give them somewhere harmless to write.
                if sys.stdout is None:
                    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
                if sys.stderr is None:
                    sys.stderr = open(os.devnull, 'w', encoding='utf-8')
                self.can_toggle = True
                return
            process_list = (ctypes.c_uint32 * 4)()
            attached_processes = kernel32.GetConsoleProcessList(process_list, 4)
            if attached_processes == 1:
                # this console was created just for us, so it is safe to hide it
                self.can_toggle = True
                self._disable_close_button(hwnd)
                user32.ShowWindow(hwnd, _SW_HIDE)
        except Exception:
            logging.getLogger(__name__).exception("Could not hide console window.")

    def is_visible(self) -> bool:
        if not IS_WINDOWS:
            return True
        try:
            kernel32, user32 = _win32()
            hwnd = kernel32.GetConsoleWindow()
            return bool(hwnd) and bool(user32.IsWindowVisible(hwnd))
        except Exception:
            return False

    def show(self):
        if not IS_WINDOWS or not self.can_toggle:
            return
        kernel32, user32 = _win32()
        hwnd = kernel32.GetConsoleWindow()
        if not hwnd:
            if not kernel32.AllocConsole():
                logging.getLogger(__name__).error("Could not open a console window.")
                return
            self._attach_streams_to_new_console()
            hwnd = kernel32.GetConsoleWindow()
            self._disable_close_button(hwnd)
        user32.ShowWindow(hwnd, _SW_SHOW)

    def hide(self):
        if not IS_WINDOWS or not self.can_toggle:
            return
        kernel32, user32 = _win32()
        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            user32.ShowWindow(hwnd, _SW_HIDE)

    def _attach_streams_to_new_console(self):
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(_CP_UTF8)
        stream = open('CONOUT$', 'w', encoding='utf-8', errors='replace', buffering=1)
        sys.stdout = stream
        sys.stderr = stream

        # replay everything that happened before the console was opened
        with self._buffer_lock:
            buffered = list(self._buffer)
        for line in buffered:
            stream.write(line + '\n')
        stream.flush()

        if self._stream_handler is None:
            self._stream_handler = logging.StreamHandler(stream)
            if self._formatter:
                self._stream_handler.setFormatter(self._formatter)
            logging.getLogger().addHandler(self._stream_handler)
        else:
            self._stream_handler.setStream(stream)

    @staticmethod
    def _disable_close_button(hwnd):
        """Closing a console window kills the whole process, so remove its close button. Use the tray menu instead."""
        try:
            _, user32 = _win32()
            hmenu = user32.GetSystemMenu(hwnd, False)
            if hmenu:
                user32.DeleteMenu(hmenu, _SC_CLOSE, _MF_BYCOMMAND)
        except Exception:
            pass


console_manager = ConsoleManager()
