# meikipop/gui/cursor_overlay.py
import sys
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QCursor, QPainter, QPen, QBrush
from PyQt6.QtWidgets import QWidget


class CursorOverlay(QWidget):
    SIZE = 4
    DOT_RADIUS = 4
    COLOR = QColor(255, 60, 60, 220)
    OUTLINE = QColor(0, 0, 0, 160)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.BypassWindowManagerHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        self._click_through_applied = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._track)
        self._timer.start(8)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._click_through_applied:
            self._apply_click_through()
            self._click_through_applied = True

    def _apply_click_through(self):
        """WA_TransparentForMouseEvents doesn't work for top-level windows.
        Each platform needs its own approach."""
        if sys.platform == 'win32':
            import ctypes
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            hwnd = int(self.winId())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT
            )
        elif sys.platform == 'darwin':
            # Tell the underlying NSWindow to ignore mouse events
            try:
                from AppKit import NSApplication
                ns_view = self.winId().__int__()
                # objc bridge: get NSWindow from winId
                import objc
                ns_window = objc.objc_object(c_void_p=ns_view).window()
                ns_window.setIgnoresMouseEvents_(True)
            except Exception:
                pass  # Quartz/AppKit not available; overlay will still show
        # Linux/X11: BypassWindowManagerHint + no input shape = clicks fall through
        # on most compositors already. If not, you'd need python-xlib to set
        # the XShape input mask — but that's rarely needed.

    def start(self):
        self.show()
        self._timer.start(8)

    def stop(self):
        self._timer.stop()
        self.hide()

    def _track(self):
        pos = QCursor.pos()
        half = self.SIZE // 2
        self.move(pos.x() - half, pos.y() - half)

    def paintEvent(self, _event):
        painter = QPainter(self)
        cx = cy = self.SIZE // 2

        painter.setPen(QPen(self.OUTLINE, 1))
        painter.setBrush(QBrush(self.COLOR))
        r = self.DOT_RADIUS
        painter.drawEllipse(cx - r, cy - r, r * 2, r * 2)
