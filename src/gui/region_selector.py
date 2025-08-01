# src/gui/region_selector.py
import logging

from PyQt6.QtWidgets import QDialog
from PyQt6.QtCore import Qt, QPoint, QRect
from PyQt6.QtGui import QColor, QPainter, QPen, QMouseEvent, QKeyEvent, QGuiApplication

from src.gui.input import InputLoop

logger = logging.getLogger(__name__) # Get the logger

class RegionSelector(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        #Create a widget that spans the entire virtual desktop (all monitors)
        screens = QGuiApplication.screens()
        virtual_desktop_rect = QRect()
        for screen in screens:
            screen_geometry = screen.geometry()
            screen_geometry.setSize( screen.size() * screen.devicePixelRatio())
            virtual_desktop_rect = virtual_desktop_rect.united(screen_geometry)
        self.setGeometry(virtual_desktop_rect)

        # Window setup for a seamless overlay
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)

        # Points for drawing the overlay (in Qt's logical coordinates)
        self.begin_logical = QPoint()
        self.end_logical = QPoint()

        # Points for the final result (in physical coordinates)
        self.begin_physical = None
        self.selection_rect = None  # This will store the final QRect in physical coordinates

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))

        if not self.begin_logical.isNull() and not self.end_logical.isNull():
            # Use logical coordinates for drawing on the widget
            rect_logical = QRect(self.begin_logical, self.end_logical).normalized()

            # Clear the selected area
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect_logical, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            # Draw the border, adjusted to be fully visible at the edges
            pen = QPen(QColor(30, 200, 255), 1, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            border_rect = rect_logical.adjusted(0, 0, -1, -1)
            painter.drawRect(border_rect)

    def mousePressEvent(self, event: QMouseEvent):
        # Store Qt's logical position for drawing the overlay
        self.begin_logical = event.position().toPoint()
        if not self.begin_logical:
            self.begin_logical = QPoint(1,1)
        self.end_logical = self.begin_logical

        # Store the physical position for the final result
        px, py = InputLoop.get_mouse_pos()
        self.begin_physical = QPoint(px, py)

        self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        # Update the logical position for drawing continuously
        self.end_logical = event.position().toPoint()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        # Get the final physical position
        px, py = InputLoop.get_mouse_pos()
        end_physical = QPoint(px, py)

        # Create the final selection rectangle using the stored physical coordinates
        self.selection_rect = QRect(self.begin_physical, end_physical).normalized()
        self.accept()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.selection_rect = None
            self.reject()

    @staticmethod
    def get_region():
        logger.info("Awaiting region selection... you can change the scan region in the tray")
        selector = RegionSelector()
        if selector.exec() == QDialog.DialogCode.Accepted:
            return selector.selection_rect
        return None