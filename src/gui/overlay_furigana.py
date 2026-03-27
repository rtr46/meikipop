# src/gui/overlay_furigana.py
#
# Transparent, always-on-top QWidget that paints hiragana readings
# directly above (or beside, for vertical text) the OCR-recognised
# words on screen.
#
# Geometry: the widget covers exactly the scan region so all
# coordinate arithmetic uses simple local offsets.
#
# Lifecycle:
#   show_overlay()          – position + show
#   set_furigana(items)     – update data + schedule repaint
#   hide_overlay()          – hide + clear data
#
# The widget is mouse-transparent (WA_TransparentForMouseEvents) so it
# never interferes with clicks that should reach the game.

import logging
from typing import List, Tuple

from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import QWidget, QApplication

from src.config.config import config

logger = logging.getLogger(__name__)

# (screen_x, screen_y, screen_w, screen_h, reading_text, is_vertical)
FuriganaItem = Tuple[int, int, int, int, str, bool]


class OverlayFurigana(QWidget):
    """
    Paints hiragana furigana readings above OCR word bounding boxes.

    Reading text is drawn in config.furigana_color with a semi-transparent
    background rectangle for legibility against any game image.
    """

    def __init__(self, screen_manager):
        super().__init__()
        self._screen_manager = screen_manager
        self._items: List[FuriganaItem] = []

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # Keep it out of the taskbar / alt-tab
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hide()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_overlay(self):
        """Position the widget over the scan region and make it visible."""
        off_x, off_y, img_w, img_h = self._screen_manager.get_scan_geometry()
        if img_w == 0 or img_h == 0:
            return
        screen = QApplication.primaryScreen()
        ratio = screen.devicePixelRatio() if screen else 1
        self.setGeometry(
            int(off_x / ratio), int(off_y / ratio),
            int(img_w / ratio), int(img_h / ratio)
        )
        self.show()
        self.raise_()

    def hide_overlay(self):
        """Hide the widget and discard current data."""
        self._items = []
        self.hide()

    def set_furigana(self, items: List[FuriganaItem]):
        """
        Provide new furigana data and schedule a repaint.
        Safe to call from any thread via Qt's queued repaint.
        """
        self._items = items
        self.update()  # thread-safe repaint request

    def update_furigana_safe(self, items: List[FuriganaItem]):
        """
        Thread-safe version of set_furigana + show_overlay for calling from non-main threads.
        Use via QMetaObject.invokeMethod with Qt.QueuedConnection.
        """
        self.set_furigana(items)
        self.show_overlay()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event):  # noqa: N802
        if not self._items:
            return

        off_x, off_y, img_w, img_h = self._screen_manager.get_scan_geometry()
        if img_w == 0 or img_h == 0:
            return

        screen = QApplication.primaryScreen()
        ratio = screen.devicePixelRatio() if screen else 1

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        font_family = config.font_family if config.font_family else ""
        font = QFont(font_family)
        font.setPixelSize(max(8, int(config.furigana_font_size / ratio)))
        painter.setFont(font)
        fm = QFontMetrics(font)

        fg_color = QColor(config.furigana_color)
        bg_color = QColor(config.color_background)
        bg_color.setAlpha(180)

        for sx, sy, sw, sh, reading, is_vertical in self._items:
            # Convert from screen coords to widget-local coords, accounting for display scaling
            local_x = (sx - off_x) / ratio
            local_y = (sy - off_y) / ratio
            local_sw = sw / ratio
            local_sh = sh / ratio

            text_w = fm.horizontalAdvance(reading)
            text_h = fm.height()
            ascent = fm.ascent()

            if is_vertical:
                # Place reading to the right of the word box
                rx = local_x + local_sw + 2
                ry = local_y
                bg_rect = QRect(int(rx), int(ry), int(text_w + 4), int(max(local_sh, text_h + 4)))
                draw_x = rx + 2
                draw_y = ry + ascent + 2
            else:
                # Place reading above the word box
                rx = local_x
                ry = local_y - text_h - 2
                bg_rect = QRect(int(rx), int(ry), int(max(local_sw, text_w + 4)), int(text_h + 2))
                draw_x = rx + 2
                draw_y = ry + ascent

            # Clamp to widget bounds (use scaled dimensions)
            if bg_rect.right() > img_w / ratio:
                shift = bg_rect.right() - (img_w / ratio)
                bg_rect.moveLeft(bg_rect.left() - shift)
                draw_x -= shift
            if bg_rect.top() < 0:
                shift = -bg_rect.top()
                bg_rect.moveTop(0)
                draw_y += shift

            painter.fillRect(bg_rect, bg_color)
            painter.setPen(fg_color)
            painter.drawText(int(draw_x), int(draw_y), reading)

        painter.end()
