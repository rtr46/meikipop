# src/gui/popup.py
import logging
import threading
from typing import List

from PyQt6.QtCore import QTimer, QPoint
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtGui import QCursor, QGuiApplication
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QLayout

from src.config.config import config, MAX_DICT_ENTRIES
from src.dictionary.lookup import DictionaryEntry

logger = logging.getLogger(__name__)

class Popup(QWidget):
    def __init__(self, shared_state, input_loop):
        super().__init__()
        self._latest_data = None
        self._last_latest_data = None
        self._last_mouse_pos = None
        self._data_lock = threading.Lock()
        self.shared_state = shared_state
        self.input_loop = input_loop

        self.is_visible = False
        # The timer now checks our custom buffer instead of a queue
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.process_latest_data_loop)
        self.timer.start(10)

        # layout and styling
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        main_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        self.frame = QFrame()
        self.frame_layout = QVBoxLayout(self.frame)
        self.frame_layout.setContentsMargins(0, 0, 0, 0)

        self.frame.setFixedWidth(config.popup_width)
        bg_color = QColor(config.color_background)
        r, g, b = bg_color.red(), bg_color.green(), bg_color.blue()
        a = config.background_opacity
        self.frame.setStyleSheet(f"""
            QFrame {{
                background-color: rgba({r}, {g}, {b}, {a});
                color: {config.color_foreground};
                border-radius: 8px;
                border: 1px solid #555;
            }}
            QLabel {{
                background-color: transparent;
                color: {config.color_foreground};
                border: none;
                font-family: "{config.font_family}";
            }}
        """)

        # --- Pre-populate with Entry Containers ---
        self.entry_containers = []
        self.separators = []
        self.no_results_label = None

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(2)

        self.no_results_label = QLabel("No results found.")
        self.no_results_label.setStyleSheet(f"font-size: {config.font_size_definitions}px;")
        self.no_results_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_results_label.setVisible(False) # Start hidden
        content_layout.addWidget(self.no_results_label)

        # Create and add the fixed number of entry containers
        for i in range(MAX_DICT_ENTRIES):
            container = self._create_empty_entry_container()
            container.setVisible(False) # Start hidden
            self.entry_containers.append(container)
            content_layout.addWidget(container)

            # Add Separator Line (between potential entries)
            if i < MAX_DICT_ENTRIES - 1:
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setFrameShadow(QFrame.Shadow.Sunken)
                line.setStyleSheet(f"border: 1px solid {config.color_separator_line};")
                line.setVisible(False) # Start hidden, controlled by update_content
                content_layout.addWidget(line)
                self.separators.append(line)

        # Add the content layout (holding labels, containers, separators) to the frame's layout
        self.frame_layout.addLayout(content_layout)
        self.content_layout = content_layout # Keep reference

        # Add the styled frame to the main popup layout
        main_layout.addWidget(self.frame)
        self.show_popup()

    def set_latest_data(self, data):
        with self._data_lock:
            self._latest_data = data

    def get_latest_data(self):
        with self._data_lock:
            return self._latest_data

    def process_latest_data_loop(self):
        latest_data = self.get_latest_data()
        if latest_data and latest_data != self._last_latest_data:
            self.update_popup_content(latest_data)
        self._last_latest_data = latest_data

        if self._latest_data and self.input_loop.is_virtual_hotkey_down():
            self.show_popup()
        else:
            self.hide_popup()

        # todo fix bug where popup gets initially drawn in the wrong position and then flip causing flicker, see below
        mouse_pos = QCursor.pos()
        # if self._last_mouse_pos != mouse_pos:
        self.move_to(mouse_pos.x(), mouse_pos.y())
        # self._last_mouse_pos = mouse_pos

    def update_popup_content(self, entries: List[DictionaryEntry]):
        if not entries:
            if self.no_results_label:
                self.no_results_label.setVisible(True)
            # Hide all entry containers and separators
            for container in self.entry_containers:
                container.setVisible(False)
            for separator in self.separators:
                separator.setVisible(False)
            return

        num_entries_to_show = min(len(entries), MAX_DICT_ENTRIES)
        if self.no_results_label:
            self.no_results_label.setVisible(False)

        for i in range(MAX_DICT_ENTRIES):
            container = self.entry_containers[i]
            if i > 0:
                separator = self.separators[i - 1]
            if i < num_entries_to_show:
                # --- Update and Show ---
                entry = entries[i]

                # 1a. Update Header
                header_html = f'<span style="color: {config.color_highlight_word}; font-size:{config.font_size_header}px;">{entry.written_form}</span>'
                if entry.reading:
                    header_html += f' <span style="color: {config.color_highlight_reading}; font-size:{config.font_size_header - 2}px;">{entry.reading}</span>'
                if entry.deconjugation_process and not config.hide_deconjugation:
                    deconj_str = " ← ".join(p for p in entry.deconjugation_process if p)
                    if deconj_str:
                        header_html += f' <span style="color:{config.color_foreground}; font-size:{config.font_size_definitions - 2}px; opacity:0.8;">({deconj_str})</span>'
                container.header_label.setText(header_html)
                container.header_label.setVisible(True)

                # 1b. Update Definitions
                sense_html_parts = []
                for idx, gloss_list in enumerate(entry.definitions):
                    sense_text = "; ".join(gloss_list)
                    sense_html_parts.append(f'({idx + 1}) {sense_text}')
                separator_mode = "; " if config.compact_mode else "<br>"
                definitions_html = separator_mode.join(sense_html_parts)
                definitions_html_final = f'<div style="font-size:{config.font_size_definitions}px;">{definitions_html}</div>'
                container.definitions_label.setText(definitions_html_final)
                container.definitions_label.setVisible(True)

                container.setVisible(True)
                if i > 0:
                    separator.setVisible(True)
            else:
                container.setVisible(False)
                if i > 0:
                    separator.setVisible(False)

        # todo fix bug where popup gets initially drawn in the wrong position and then flip causing flicker
        #  this seems to fix it but why and how to do it more cleanly?
        # self.frame.adjustSize()
        # self.adjustSize()
        logger.info("finished updating popup content")


    def _create_empty_entry_container(self) -> QWidget:
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # Create header label (empty initially)
        header_label = QLabel("")
        header_label.setTextFormat(Qt.TextFormat.RichText)
        container_layout.addWidget(header_label)

        # Create definitions label (empty initially)
        definitions_label = QLabel("")
        definitions_label.setWordWrap(True)
        definitions_label.setTextFormat(Qt.TextFormat.RichText)
        definitions_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        container_layout.addWidget(definitions_label)

        # Store references to the labels as attributes of the container for easy access
        container.header_label = header_label
        container.definitions_label = definitions_label

        return container

    def move_to(self, x, y):
        cursor_point = QPoint(x, y)
        screen = QGuiApplication.screenAt(cursor_point)

        # Fallback to the primary screen if the cursor is somehow not on any screen
        if not screen:
            screen = QGuiApplication.primaryScreen()

        screen_geometry = screen.geometry()

        popup_width = self.width()
        popup_height = self.height()
        offset = 15

        final_x = x + offset
        final_y = y + offset

        if final_x + popup_width > screen_geometry.right():
            final_x = x - popup_width - offset
        if final_y + popup_height > screen_geometry.bottom():
            final_y = y - popup_height - offset

        if final_x < screen_geometry.left():
            final_x = screen_geometry.left()
        if final_y < screen_geometry.top():
            final_y = screen_geometry.top()

        self.move(final_x, final_y)

    def hide_popup(self):
        # logger.debug(f"hide_popup triggered while visibility:{self.is_visible}")
        if not self.is_visible:
            return
        self.hide()
        logger.debug("hide_popup releasing lock...")
        self.shared_state.screen_lock.release()
        logger.debug("...successfully released lock by hide_popup")
        self.is_visible = False

    def show_popup(self):
        # logger.debug(f"show_popup triggered while visibility:{self.is_visible}")
        if self.is_visible:
            return
        logger.debug("show_popup acquiring lock...")
        self.shared_state.screen_lock.acquire()
        logger.debug("...successfully acquired lock by show_popup")
        self.show()
        self.is_visible = True
