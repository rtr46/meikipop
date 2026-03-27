# src/gui/overlay_selection.py
#
# Transparent, always-on-top QWidget that draws a coloured highlight
# rectangle around the currently selected word during gamepad navigation.
#
# Geometry: like OverlayFurigana, covers the scan region exactly.
#
# The highlight has two layers:
#   1. A semi-transparent fill (config.selection_opacity) to tint the word
#   2. A solid border in the same colour for crisp visibility

import logging

from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget, QApplication

from src.config.config import config
from src.ocr.interface import BoundingBox

logger = logging.getLogger(__name__)


class OverlaySelection(QWidget):
    """
    Draws a highlight box around the currently-selected word box.

    Call set_selection() to update the highlighted region; the widget
    automatically shows itself on the first call and repaints.
    Call hide_overlay() to hide it when leaving navigation mode.
    """

    def __init__(self, screen_manager):
        super().__init__()
        self._screen_manager = screen_manager
        # Stored in screen coordinates; converted to local on paint
        self._sel_sx: int = 0
        self._sel_sy: int = 0
        self._sel_sw: int = 0
        self._sel_sh: int = 0
        self._has_selection: bool = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hide()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_selection(self, box: BoundingBox,
                      off_x: int, off_y: int,
                      img_w: int, img_h: int):
        """
        Highlight the region described by *box* (normalised 0-1 coords).
        Positions and shows the overlay if not already visible.
        """
        if img_w == 0 or img_h == 0:
            return

        self._sel_sx = int(off_x + (box.center_x - box.width / 2) * img_w)
        self._sel_sy = int(off_y + (box.center_y - box.height / 2) * img_h)
        self._sel_sw = max(1, int(box.width * img_w))
        self._sel_sh = max(1, int(box.height * img_h))
        self._has_selection = True

        if not self.isVisible():
            self._reposition()
            self.show()
            self.raise_()

        self.update()  # thread-safe repaint request

    def hide_overlay(self):
        """Hide the widget and clear the selection."""
        self._has_selection = False
        self.hide()

    def set_selection_safe(self, box: BoundingBox,
                          off_x: int, off_y: int,
                          img_w: int, img_h: int):
        """
        Thread-safe version of set_selection() for calling from non-main threads.
        Use via QMetaObject.invokeMethod with Qt.QueuedConnection.
        """
        self.set_selection(box, off_x, off_y, img_w, img_h)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _reposition(self):
        off_x, off_y, img_w, img_h = self._screen_manager.get_scan_geometry()
        if img_w > 0 and img_h > 0:
            screen = QApplication.primaryScreen()
            ratio = screen.devicePixelRatio() if screen else 1
            self.setGeometry(
                int(off_x / ratio), int(off_y / ratio),
                int(img_w / ratio), int(img_h / ratio)
            )

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event):  # noqa: N802
        if not self._has_selection:
            return

        off_x, off_y, _, _ = self._screen_manager.get_scan_geometry()

        screen = QApplication.primaryScreen()
        ratio = screen.devicePixelRatio() if screen else 1

        # Convert to widget-local coordinates, accounting for display scaling
        local_x = (self._sel_sx - off_x) / ratio
        local_y = (self._sel_sy - off_y) / ratio
        local_w = self._sel_sw / ratio
        local_h = self._sel_sh / ratio
        rect = QRect(int(local_x), int(local_y), int(local_w), int(local_h))

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Semi-transparent fill
        fill_color = QColor(config.selection_color)
        fill_color.setAlpha(config.selection_opacity)
        painter.fillRect(rect, fill_color)

        # Solid border (slightly inset so it doesn't bleed outside the box)
        border_color = QColor(config.selection_color)
        border_color.setAlpha(230)
        pen = QPen(border_color, max(1, int(2 / ratio)))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        inset = QRect(int(local_x + 1), int(local_y + 1),
                      int(local_w - 2), int(local_h - 2))
        painter.drawRect(inset)

        painter.end()
