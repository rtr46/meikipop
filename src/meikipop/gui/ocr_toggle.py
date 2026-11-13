# meikipop/gui/ocr_toggle.py
"""Global hotkey that flips between two OCR providers, with a small on-screen notice."""
import logging

from PyQt6.QtCore import QObject, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QFont
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from meikipop.config.config import config, IS_WINDOWS

if IS_WINDOWS:
    import keyboard

logger = logging.getLogger(__name__)

TOAST_DURATION_MS = 1500


def qt_sequence_to_hotkey(text: str) -> str:
    """Converts a QKeySequence string ('Ctrl+Alt+O') into the 'keyboard' library format ('ctrl+alt+o')."""
    key_map = {'meta': 'windows', 'pgup': 'page up', 'pgdown': 'page down', 'del': 'delete', 'ins': 'insert'}
    parts = [p.strip().lower() for p in text.split('+') if p.strip()]
    return '+'.join(key_map.get(p, p) for p in parts)


def short_provider_name(name: str) -> str:
    """'Google Lens (remote)' -> 'Google Lens'"""
    return name.split(' (')[0]


class Toast(QWidget):
    """Small click-through notice shown near the bottom-center of the screen the mouse is on."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput |
            Qt.WindowType.WindowDoesNotAcceptFocus |
            Qt.WindowType.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

    def show_message(self, text: str):
        font = QFont(config.font_family)
        font.setPixelSize(max(config.font_size_header, 12))
        self.label.setFont(font)
        self.label.setText(text)
        self.label.setStyleSheet(
            f"background-color: rgba(30, 30, 30, 235); color: {config.color_foreground if config.color_foreground else '#F0F0F0'};"
            f"border: 1px solid #555; border-radius: 8px; padding: 8px 16px;"
        )
        self.adjustSize()

        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = geo.left() + (geo.width() - self.width()) // 2
        y = geo.top() + int(geo.height() * 0.85) - self.height()
        self.move(x, y)

        self.show()
        self.raise_()
        self.hide_timer.start(TOAST_DURATION_MS)


class OcrToggle(QObject):
    # emitted from the keyboard hook thread; Qt queues it onto the GUI thread
    _hotkey_triggered = pyqtSignal()

    def __init__(self, ocr_processor, on_switched=None):
        super().__init__()
        self.ocr_processor = ocr_processor
        self.on_switched = on_switched
        self.toast = Toast()
        self._registered_hotkey = None
        self._registered_hotkey_str = None
        self._hotkey_triggered.connect(self.toggle, Qt.ConnectionType.QueuedConnection)
        self.reapply_settings()

    def reapply_settings(self):
        hotkey = (config.ocr_toggle_hotkey or '').strip().lower()
        if self._registered_hotkey is not None and hotkey == self._registered_hotkey_str:
            return
        self._unregister()
        self._registered_hotkey_str = hotkey
        if not hotkey:
            return
        if not IS_WINDOWS:
            logger.warning("OCR switch hotkey is currently only supported on Windows.")
            return
        try:
            self._registered_hotkey = keyboard.add_hotkey(hotkey, self._hotkey_triggered.emit, suppress=False)
            logger.info(f"OCR switch hotkey '{hotkey}' registered.")
        except Exception as e:
            logger.error(f"Could not register OCR switch hotkey '{hotkey}': {e}")

    def _unregister(self):
        if self._registered_hotkey is not None:
            try:
                keyboard.remove_hotkey(self._registered_hotkey)
            except Exception:
                pass
            self._registered_hotkey = None

    def toggle(self):
        providers = self.ocr_processor.available_providers
        a, b = config.ocr_toggle_provider_a, config.ocr_toggle_provider_b
        target = b if config.ocr_provider == a else a

        if target not in providers:
            self.toast.show_message(f"OCR provider not available: {short_provider_name(target)}")
            return
        if target == config.ocr_provider:
            self.toast.show_message(f"OCR: {short_provider_name(target)}")
            return

        self.ocr_processor.switch_provider(target)
        if config.ocr_provider == target:
            self.toast.show_message(f"OCR: {short_provider_name(target)}")
        else:
            self.toast.show_message(f"Failed to switch to {short_provider_name(target)}")
        if self.on_switched:
            self.on_switched()
