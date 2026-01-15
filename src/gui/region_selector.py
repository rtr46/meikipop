# src/gui/region_selector.py
import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from PyQt6.QtCore import Qt, QPoint, QRect, QTimer, QEvent, QEventLoop
from PyQt6.QtGui import QColor, QPainter, QPen, QMouseEvent, QKeyEvent, QGuiApplication, QCursor, QScreen
from PyQt6.QtWidgets import QWidget, QApplication

from src.gui.input import InputLoop

logger = logging.getLogger(__name__)

DRAG_THRESHOLD_PX = 10


class SelectionMode(Enum):
    IDLE = auto()
    PENDING = auto()
    DRAGGING = auto()


class OverlayState(Enum):
    INACTIVE = auto()
    HOVERED = auto()
    SELECTING = auto()


@dataclass
class SelectionResult:
    region: Optional[QRect] = None
    screen_index: Optional[int] = None
    cancelled: bool = False

    @property
    def is_screen_selection(self) -> bool:
        return self.screen_index is not None and self.region is None

    @property
    def is_region_selection(self) -> bool:
        return self.region is not None and self.screen_index is None


class ScreenOverlay(QWidget):
    ALPHA_INACTIVE = 100
    ALPHA_HOVERED = 40
    ALPHA_SELECTING = 100

    def __init__(self, screen: QScreen, screen_index: int, parent=None):
        super().__init__(parent)
        self.screen = screen
        self.screen_index = screen_index
        self.state = OverlayState.INACTIVE
        self.selection_rect_local: Optional[QRect] = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.BypassWindowManagerHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(screen.geometry())

    def set_state(self, state: OverlayState):
        if self.state != state:
            self.state = state
            self.update()

    def set_selection_rect(self, rect: Optional[QRect]):
        if rect is not None:
            self.selection_rect_local = rect.translated(-self.geometry().topLeft())
        else:
            self.selection_rect_local = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)

        if self.state == OverlayState.HOVERED:
            alpha = self.ALPHA_HOVERED
        elif self.state == OverlayState.SELECTING:
            alpha = self.ALPHA_SELECTING
        else:
            alpha = self.ALPHA_INACTIVE

        painter.fillRect(self.rect(), QColor(0, 0, 0, alpha))

        if self.state == OverlayState.SELECTING and self.selection_rect_local is not None:
            rect = self.selection_rect_local.normalized()

            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            pen = QPen(QColor(30, 200, 255), 1, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            border_rect = rect.adjusted(0, 0, -1, -1)
            painter.drawRect(border_rect)


class RegionSelector:
    def __init__(self):
        self.overlays: list[ScreenOverlay] = []
        self.mode = SelectionMode.IDLE
        self.result: Optional[SelectionResult] = None
        self.event_loop: Optional[QEventLoop] = None

        self.press_pos_logical: Optional[QPoint] = None
        self.press_pos_physical: Optional[QPoint] = None
        self.current_pos_logical: Optional[QPoint] = None
        self.hovered_screen_index: Optional[int] = None

        self.update_timer = QTimer()
        self.update_timer.setInterval(16)
        self.update_timer.timeout.connect(self._on_timer_tick)

        self.event_filter = RegionSelectorEventFilter(self)

        screens = QGuiApplication.screens()
        for i, screen in enumerate(screens):
            mss_index = i + 1  # mss uses 1-based indexing (0 is combined virtual screen)
            overlay = ScreenOverlay(screen, mss_index)
            self.overlays.append(overlay)

    def _find_screen_at(self, pos: QPoint) -> Optional[int]:
        for i, overlay in enumerate(self.overlays):
            if overlay.geometry().contains(pos):
                return i
        return None

    def _get_mss_screen_index(self, overlay_index: int) -> int:
        return self.overlays[overlay_index].screen_index

    def _update_hovered_screen(self):
        cursor_pos = QCursor.pos()
        new_hovered = self._find_screen_at(cursor_pos)

        if new_hovered != self.hovered_screen_index:
            self.hovered_screen_index = new_hovered

            if self.mode != SelectionMode.DRAGGING:
                for i, overlay in enumerate(self.overlays):
                    if i == new_hovered:
                        overlay.set_state(OverlayState.HOVERED)
                    else:
                        overlay.set_state(OverlayState.INACTIVE)

    def _on_timer_tick(self):
        cursor_pos = QCursor.pos()
        self.current_pos_logical = cursor_pos

        if self.mode == SelectionMode.IDLE:
            self._update_hovered_screen()

        elif self.mode == SelectionMode.PENDING:
            if self.press_pos_logical:
                delta = cursor_pos - self.press_pos_logical
                distance = (delta.x() ** 2 + delta.y() ** 2) ** 0.5

                if distance > DRAG_THRESHOLD_PX:
                    self.mode = SelectionMode.DRAGGING
                    press_screen_idx = self._find_screen_at(self.press_pos_logical)
                    for i, overlay in enumerate(self.overlays):
                        if i == press_screen_idx:
                            overlay.set_state(OverlayState.SELECTING)
                        else:
                            overlay.set_state(OverlayState.INACTIVE)

            self._update_hovered_screen()

        elif self.mode == SelectionMode.DRAGGING:
            if self.press_pos_logical:
                selection_rect = QRect(self.press_pos_logical, cursor_pos).normalized()
                press_screen_idx = self._find_screen_at(self.press_pos_logical)

                if press_screen_idx is not None:
                    self.overlays[press_screen_idx].set_selection_rect(selection_rect)

    def _on_mouse_press(self, pos: QPoint):
        self.press_pos_logical = pos
        px, py = InputLoop.get_mouse_pos()
        self.press_pos_physical = QPoint(px, py)
        self.mode = SelectionMode.PENDING

    def _on_mouse_release(self, pos: QPoint):
        if self.mode == SelectionMode.PENDING:
            screen_idx = self._find_screen_at(pos)
            if screen_idx is not None:
                mss_idx = self._get_mss_screen_index(screen_idx)
                self.result = SelectionResult(screen_index=mss_idx)
                logger.info(f"Selected whole screen {mss_idx}")
            else:
                self.result = SelectionResult(cancelled=True)

        elif self.mode == SelectionMode.DRAGGING:
            px, py = InputLoop.get_mouse_pos()
            end_physical = QPoint(px, py)
            selection_rect = QRect(self.press_pos_physical, end_physical).normalized()
            self.result = SelectionResult(region=selection_rect)
            logger.info(f"Selected region {selection_rect}")

        self._cleanup()

    def _on_key_press(self, key: int):
        if key == Qt.Key.Key_Escape:
            self.result = SelectionResult(cancelled=True)
            logger.info("Region selection cancelled")
            self._cleanup()

    def _cleanup(self):
        self.update_timer.stop()
        QApplication.instance().removeEventFilter(self.event_filter)

        for overlay in self.overlays:
            overlay.close()

        if self.event_loop is not None:
            self.event_loop.quit()

    def run(self) -> SelectionResult:
        logger.info("Awaiting region selection... click a screen or drag to select a region")

        QApplication.instance().installEventFilter(self.event_filter)

        for overlay in self.overlays:
            overlay.show()

        self._update_hovered_screen()
        self.update_timer.start()

        self.event_loop = QEventLoop()
        self.event_loop.exec()

        return self.result

    @staticmethod
    def get_region() -> SelectionResult:
        selector = RegionSelector()
        return selector.run()


class RegionSelectorEventFilter(QWidget):
    def __init__(self, selector: RegionSelector):
        super().__init__()
        self.selector = selector

    def eventFilter(self, obj, event: QEvent) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress:
            mouse_event: QMouseEvent = event
            if mouse_event.button() == Qt.MouseButton.LeftButton:
                self.selector._on_mouse_press(QCursor.pos())
                return True

        elif event.type() == QEvent.Type.MouseButtonRelease:
            mouse_event: QMouseEvent = event
            if mouse_event.button() == Qt.MouseButton.LeftButton:
                self.selector._on_mouse_release(QCursor.pos())
                return True

        elif event.type() == QEvent.Type.KeyPress:
            key_event: QKeyEvent = event
            self.selector._on_key_press(key_event.key())
            return True

        return False
