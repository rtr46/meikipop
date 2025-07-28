# popup.py
import logging
from typing import List

from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QFrame
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QMouseEvent, QColor

from lookup import DictionaryEntry
from settings import settings

logger = logging.getLogger(__name__)

class Popup(QWidget):
    """
    A frameless popup window, styled to look like Nazeka's UI.
    """
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(2)
        
        self.frame = QFrame()
        self.frame.setLayout(self.layout)

        self.frame.setFixedWidth(settings.popup_width)
        
        bg_color = QColor(settings.color_background)
        r, g, b = bg_color.red(), bg_color.green(), bg_color.blue()
        a = settings.background_opacity
        
        self.frame.setStyleSheet(f"""
            QFrame {{
                background-color: rgba({r}, {g}, {b}, {a});
                color: {settings.color_foreground};
                border-radius: 8px;
                border: 1px solid #555;
            }}
            QLabel {{
                background-color: transparent;
                color: {settings.color_foreground};
                border: none;
                font-family: "{settings.font_family}";
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0,0,0,0)
        main_layout.addWidget(self.frame)
        self.last_mouse_pos = None

    def update_content(self, entries: List[DictionaryEntry]):
        """Clears and rebuilds the popup's internal widgets and resizes correctly."""
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        
        if not entries:
            label = QLabel("No results found.")
            label.setStyleSheet(f"font-size: {settings.font_size_definitions}px;")
            self.layout.addWidget(label)
        else:
            for i, entry in enumerate(entries):
                if i > 0:
                    line = QFrame()
                    line.setFrameShape(QFrame.Shape.HLine)
                    line.setFrameShadow(QFrame.Shadow.Sunken)
                    line.setStyleSheet(f"border: 1px solid {settings.color_separator_line};")
                    self.layout.addWidget(line)

                header_html = f'<span style="color: {settings.color_highlight_word}; font-size:{settings.font_size_header}px;">{entry.written_form}</span>'
                if entry.reading:
                    header_html += f' <span style="color: {settings.color_highlight_reading}; font-size:{settings.font_size_header-2}px;">{entry.reading}</span>'
                
                if entry.deconjugation_process and not settings.hide_deconjugation:
                    deconj_str = " → ".join(p for p in entry.deconjugation_process if p)
                    if deconj_str:
                         header_html += f' <span style="color:{settings.color_foreground}; font-size:{settings.font_size_definitions-2}px; opacity:0.8;">({deconj_str})</span>'

                header_label = QLabel(header_html)
                header_label.setTextFormat(Qt.TextFormat.RichText)
                self.layout.addWidget(header_label)

                sense_html_parts = []
                for idx, gloss_list in enumerate(entry.definitions):
                    sense_text = "; ".join(gloss_list)
                    sense_html_parts.append(f'({idx+1}) {sense_text}')

                separator = "; " if settings.compact_mode else "<br>"
                definitions_html = separator.join(sense_html_parts)
                
                definitions_label = QLabel(f'<div style="font-size:{settings.font_size_definitions}px;">{definitions_html}</div>')
                
                definitions_label.setWordWrap(True)
                definitions_label.setTextFormat(Qt.TextFormat.RichText)
                definitions_label.setAlignment(Qt.AlignmentFlag.AlignTop)
                self.layout.addWidget(definitions_label)
        
        self.layout.activate()
        self.adjustSize()

    def move_to(self, x: int, y: int):
        """Calculates the correct screen position and moves the widget, but does NOT show it."""
        self.last_mouse_pos = (x, y)
        
        screen_geometry = QApplication.primaryScreen().geometry()
        popup_width = self.width()
        popup_height = self.height()
        
        final_x, final_y = x + 15, y + 15
        
        if final_y + popup_height > screen_geometry.height():
            final_y = y - popup_height - 15
        if final_x + popup_width > screen_geometry.width():
            final_x = x - popup_width - 15
            
        self.move(max(0, final_x), max(0, final_y))

    def show_at(self, x: int, y: int):
        """Moves the widget and then shows it. Used for simple cases."""
        self.move_to(x, y)
        if not self.isVisible():
            self.show()

    def follow_mouse(self, x: int, y: int):
        """Wrapper for show_at, primarily used for the already-visible front buffer."""
        if self.isVisible() and self.last_mouse_pos != (x, y):
             self.show_at(x, y)