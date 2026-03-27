# src/gui/popup.py
import logging
import threading
from typing import List, Optional

from PyQt6.QtCore import QTimer, QPoint, QSize
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QCursor, QFont, QFontMetrics, QFontInfo
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QApplication

from src.config.config import config, IS_MACOS
from src.dictionary.lookup import DictionaryEntry, KanjiEntry
from src.gui.magpie_manager import magpie_manager

# macOS-specific imports for focus management
if IS_MACOS:
    try:
        import Quartz
    except ImportError:
        Quartz = None

logger = logging.getLogger(__name__)


class Popup(QWidget):
    def __init__(self, shared_state, input_loop,
                 overlay_furigana=None, hit_scanner=None):
        """
        overlay_furigana  – OverlayFurigana instance (optional)
        hit_scanner       – HitScanner instance used to fetch the latest
                            OCR result when showing the furigana overlay (optional)
        """
        super().__init__()
        self._latest_data = None
        self._last_latest_data = None
        self._data_lock = threading.Lock()
        self._previous_active_window_on_mac = None

        self.shared_state = shared_state
        self.input_loop = input_loop
        self.overlay_furigana = overlay_furigana
        self.hit_scanner = hit_scanner

        self.is_visible = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.process_latest_data_loop)
        self.timer.start(10)

        self.probe_label = QLabel()
        self.probe_label.setWordWrap(True)
        self.probe_label.setTextFormat(Qt.TextFormat.RichText)

        self.is_calibrated = False
        self.header_chars_per_line = 50
        self.def_chars_per_line = 50

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.frame = QFrame()
        self._apply_frame_stylesheet()
        main_layout.addWidget(self.frame)

        self.content_layout = QVBoxLayout(self.frame)
        self.content_layout.setContentsMargins(10, 10, 10, 10)

        self.display_label = QLabel()
        self.display_label.setWordWrap(True)
        self.display_label.setTextFormat(Qt.TextFormat.RichText)
        self.content_layout.addWidget(self.display_label)

        self.hide()

    def _apply_frame_stylesheet(self):
        bg_color = QColor(config.color_background)
        r, g, b = bg_color.red(), bg_color.green(), bg_color.blue()
        a = config.background_opacity
        self.probe_label.setFont(QFont(config.font_family))
        self.frame.setStyleSheet(f"""
            QFrame {{
                background-color: rgba({r}, {g}, {b}, {a});
                color: {config.color_foreground};
                border-radius: 8px;
                border: 1px solid #555;
            }}
            QLabel {{
                background-color: transparent;
                border: none;
                font-family: "{config.font_family}";
            }}
            hr {{
                border: none;
                height: 1px;
            }}
        """)

    def _calibrate_empirically(self):
        logger.debug("--- Calibrating Font Metrics Empirically (One-Time) ---")

        # Log font info
        actual_font = self.display_label.font()
        font_info = QFontInfo(actual_font)
        logger.debug(f"[FONT DEBUG] Requested font family: '{config.font_family}' (or default)")
        logger.debug(f"[FONT DEBUG]   -> Actual resolved font family: '{font_info.family()}'")
        logger.debug(f"[FONT DEBUG]   -> Actual style name: '{font_info.styleName()}'")
        logger.debug(f"[FONT DEBUG]   -> Actual point size: {font_info.pointSize()}")
        logger.debug(f"[FONT DEBUG]   -> Actual pixel size: {font_info.pixelSize()}")
        logger.debug(f"[FONT DEBUG]   -> Is it bold? {font_info.bold()}")

        margins = self.content_layout.contentsMargins()
        border_width = 1
        horizontal_padding = margins.left() + margins.right() + (border_width * 2)

        screen = QApplication.primaryScreen()
        self.max_content_width = (int(screen.geometry().width() * 0.4)) - horizontal_padding

        header_font = QFont(config.font_family)
        header_font.setPixelSize(config.font_size_header)
        header_metrics = QFontMetrics(header_font)
        self.header_chars_per_line = self._find_chars_for_width(header_metrics, "Header")

        def_font = QFont(config.font_family)
        def_font.setPixelSize(config.font_size_definitions)
        def_metrics = QFontMetrics(def_font)
        self.def_chars_per_line = self._find_chars_for_width(def_metrics, "Definition")

        logger.debug(f"[CALIBRATE] Max content width: {self.max_content_width}px")
        logger.debug(f"[CALIBRATE] Empirically found {self.header_chars_per_line} header chars/line")
        logger.debug(f"[CALIBRATE] Empirically found {self.def_chars_per_line} definition chars/line")
        self.is_calibrated = True

    def _find_chars_for_width(self, metrics: QFontMetrics, name: str) -> int:
        low = 1
        high = 500
        best_fit = 1

        while low <= high:
            mid = (low + high) // 2
            if mid == 0: break

            test_string = 'x' * mid
            current_width = metrics.horizontalAdvance(test_string)

            if current_width <= self.max_content_width:
                best_fit = mid
                low = mid + 1
            else:
                high = mid - 1

        return best_fit if best_fit > 0 else 50

    def set_latest_data(self, data):
        with self._data_lock:
            self._latest_data = data

    def get_latest_data(self):
        with self._data_lock:
            return self._latest_data

    def process_latest_data_loop(self):
        if not self.is_calibrated:
            self._calibrate_empirically()

        latest_data = self.get_latest_data()
        if latest_data and latest_data != self._last_latest_data:
            # update popup content
            full_html, new_size = self._calculate_content_and_size_char_count(latest_data)
            self.display_label.setText(full_html)
            self.setFixedSize(new_size)
        self._last_latest_data = latest_data

        # Check if we should show or hide the popup
        should_show = self.input_loop.is_virtual_hotkey_down() and self._latest_data
        
        # Prevent immediate re-show after hide (ghost popup fix)
        # If we just hid and are now being asked to show, check cooldown
        if should_show and hasattr(self, '_hide_cooldown_end'):
            import time as time_module
            if time_module.time() < self._hide_cooldown_end:
                should_show = False
        
        if should_show:
            self.show_popup()
        else:
            self.hide_popup()

        # Position the popup near the effective cursor.
        # In gamepad navigation mode use the virtual cursor (the selected
        # character's bounding box centre) instead of the real mouse.
        if self.input_loop.gamepad_navigation_active and self.input_loop.virtual_mouse_pos:
            vx, vy = self.input_loop.virtual_mouse_pos
            # Convert from physical pixels to Qt logical pixels
            screen = QApplication.primaryScreen()
            ratio = screen.devicePixelRatio() if screen else 1
            vx = int(vx / ratio)
            vy = int(vy / ratio)
            cursor_pos = QPoint(vx, vy)
            self.move_to(cursor_pos.x(), cursor_pos.y(), apply_magpie_transform=False)
        else:
            cursor_pos = QCursor.pos()
            self.move_to(cursor_pos.x(), cursor_pos.y())

    def _render_kanji_entry(self, entry: KanjiEntry):
        # Colors and sizes from config
        c_word = config.color_highlight_word
        c_read = config.color_highlight_reading
        c_text = config.color_foreground
        fs_head = config.font_size_header
        fs_def = config.font_size_definitions
        show_details = config.show_examples or config.show_components

        readings_str = ", ".join(entry.readings)
        readings_str = f"[{readings_str}]"

        header_html = f"""
                    <span style="font-size:{fs_head}px; color:{c_word}; padding-right: 8px;">{entry.character}</span>
                    <span style="font-size:{fs_head - 2}px; color:{c_read};"> {readings_str}</span>
        """

        meanings_str = ", ".join(entry.meanings)
        meanings_html = f'<span style="font-size:{fs_def}px; color:{c_text};"> {meanings_str}</span>'
        if not config.compact_mode:
            meanings_html = f'<span style="font-size:{fs_def}px; color:{c_text};"> [字]</span><div>{meanings_html}</div>'

        examples_html = ""
        if config.show_examples:
            ex_parts = []
            for ex in entry.examples:
                part = (f"<span style='font-size:{fs_head - 2}px; color:{c_word}'>{ex['w']}</span> "
                        f"<span style='font-size:{fs_def}px; color:{c_read}'>[{ex['r']}]</span> "
                        f"<span style='font-size:{fs_def}px; color:{c_text}'>{ex['m']}</span>")
                ex_parts.append(part)
            if ex_parts:
                examples_html = f'<div>' \
                                f'{"; ".join(ex_parts)}</div>'

        components_html = ""
        if config.show_components:
            comp_parts = []
            for c in entry.components:
                part = (f"<span style='font-size:{fs_def}px; color:{c_word}'>{c.get('c', '')}</span> "
                        f"<span style='font-size:{fs_def}px; color:{c_text}'>{c.get('m', '')}</span>")
                comp_parts.append(part)
            if comp_parts:
                components_html = f'<div>{", ".join(comp_parts)}</div>'

        return f"""
        <div style="border: 1px solid {config.color_highlight_word};">
            {header_html}
            {meanings_html}
            {examples_html}
            {components_html}
        </div>
        """

    def _calculate_content_and_size_char_count(self, entries: Optional[List[DictionaryEntry]]) -> tuple[
        Optional[str], Optional[QSize]]:
        if not self.is_calibrated: return None, None
        if not entries: return None, None

        all_html_parts = []
        max_ratio = 0.0

        for i, entry in enumerate(entries):
            if i > 0:
                all_html_parts.append('<hr style="margin-top: 0px; margin-bottom: 0px;">')

            if isinstance(entry, KanjiEntry):
                header_definition = ', '.join(
                    entry.meanings) if config.show_examples or config.show_components else '[字]'
                header_text_calc = f"{entry.character} {', '.join(entry.readings)} {header_definition}"
                max_ratio = max(max_ratio, len(header_text_calc) / self.header_chars_per_line)

                max_ratio = max(max_ratio, 0.7)

                all_html_parts.append(self._render_kanji_entry(entry))
                continue

            header_text_calc = entry.written_form
            if entry.reading: header_text_calc += f" [{entry.reading}]"
            header_ratio = len(header_text_calc) / self.header_chars_per_line
            max_ratio = max(max_ratio, header_ratio)

            # --- HTML construction ---
            header_html = f'<span style="color: {config.color_highlight_word}; font-size:{config.font_size_header}px;">{entry.written_form}</span>'
            if entry.reading: header_html += f' <span style="color: {config.color_highlight_reading}; font-size:{config.font_size_header - 2}px;">[{entry.reading}]</span>'
            if entry.deconjugation_process and config.show_deconjugation:
                deconj_str = " ← ".join(p for p in entry.deconjugation_process if p)
                if deconj_str:
                    header_html += f' <span style="color:{config.color_foreground}; font-size:{config.font_size_definitions - 2}px; opacity:0.8;">({deconj_str})</span>'
            if config.show_frequency and entry.freq < 999_999:
                header_html += f' <span style="color:{config.color_foreground}; font-size:{config.font_size_definitions - 2}px; opacity:0.6;">#{entry.freq}</span>'
            def_text_parts_calc = []
            def_text_parts_html = []
            for idx, sense in enumerate(entry.senses):
                glosses = sense.get('glosses', [])
                glosses_str = ""
                if glosses:
                    glosses_str = ", ".join(glosses) if config.show_all_glosses else sense.get('glosses')[0]
                pos_list  = sense.get('pos', [])
                tags_list = sense.get('tags', [])
                sense_calc = f"({idx + 1})" if config.show_all_glosses else ""
                sense_html = f"<b>({idx + 1})</b> " if config.show_all_glosses else ""
                if config.show_pos and pos_list:
                    pos_str = f' ({", ".join(pos_list)})'
                    sense_calc += pos_str
                    sense_html += f'<span style="color:{config.color_foreground}; opacity:0.7;"><i>{pos_str}</i></span> '
                if config.show_tags and tags_list:
                    tags_str = f' [{", ".join(tags_list)}]'
                    sense_calc += tags_str
                    sense_html += f'<span style="color:{config.color_foreground}; font-size:{config.font_size_definitions - 2}px; opacity:0.7;">{tags_str}</span> '
                sense_calc += glosses_str
                sense_html += glosses_str
                def_text_parts_calc.append(sense_calc)
                def_text_parts_html.append(sense_html)

            if config.compact_mode:
                separator = "; "
                full_def_text_html = separator.join(def_text_parts_html)
                def_ratio = len(separator.join(def_text_parts_calc)) / self.def_chars_per_line
                max_ratio = max(max_ratio, def_ratio)
            else:
                separator = "<br>"
                full_def_text_html = separator.join(def_text_parts_html)
                for def_text_calc in def_text_parts_calc:
                    def_ratio = len(def_text_calc) / self.def_chars_per_line
                    max_ratio = max(max_ratio, def_ratio)

            definitions_html_final = f'{" " if config.compact_mode else "<br>"}<span style="font-size:{config.font_size_definitions}px;">{full_def_text_html}</span>'
            all_html_parts.append(f"{header_html}{definitions_html_final}")

        optimal_content_width = self.max_content_width * min(1.0, max_ratio)
        optimal_content_width = max(optimal_content_width, 200)

        full_html = "".join(all_html_parts)
        self.probe_label.setText(full_html)

        final_height = self.probe_label.heightForWidth(int(optimal_content_width))

        margins = self.content_layout.contentsMargins()
        border_width = 1
        horizontal_padding = margins.left() + margins.right() + (border_width * 2)
        vertical_padding = margins.top() + margins.bottom() + (border_width * 2)

        final_size = QSize(int(optimal_content_width) + horizontal_padding, final_height + vertical_padding)
        return full_html, final_size

    def move_to(self, x, y, apply_magpie_transform=True):
        cursor_point = QPoint(x, y)
        screen = QApplication.screenAt(cursor_point) or QApplication.primaryScreen()
        screen_geo = screen.geometry()
        popup_size = self.size()
        offset = 15

        if apply_magpie_transform:
            ratio = screen.devicePixelRatio()
            x, y = magpie_manager.transform_raw_to_visual((int(x), int(y)), ratio)

        # --- Positioning logic based on mode ---
        mode = config.popup_position_mode

        if mode == 'visual_novel_mode':
            # --- Vertical Position (VN Mode) ---
            screen_height = screen_geo.height()
            cursor_y_in_screen = y - screen_geo.top()
            is_below = True
            if cursor_y_in_screen > (2 * screen_height / 3):  # Lower third
                is_below = False  # Place above
            elif cursor_y_in_screen < (screen_height / 3):  # Upper third
                is_below = True  # Place below
            else:  # Middle third
                is_below = cursor_y_in_screen < (screen_height / 2)
            final_y = (y + offset) if is_below else (y - popup_size.height() - offset)

            # Vertical Push
            if final_y < screen_geo.top(): final_y = screen_geo.top()
            if final_y + popup_size.height() > screen_geo.bottom():
                final_y = screen_geo.bottom() - popup_size.height()

            # --- Horizontal Position (VN Mode) ---
            screen_width = screen_geo.width()
            cursor_x_in_screen = x - screen_geo.left()
            # Define anchor points for interpolation
            pos_right = x + offset
            pos_center = x - popup_size.width() / 2.0
            pos_left = x - popup_size.width() - offset

            # Interpolate smoothly between right, center, and left alignment
            if cursor_x_in_screen < screen_width / 2.0:
                ratio = cursor_x_in_screen / (screen_width / 2.0)
                final_x = pos_right * (1 - ratio) + pos_center * ratio
            else:
                ratio = (cursor_x_in_screen - (screen_width / 2.0)) / (screen_width / 2.0)
                final_x = pos_center * (1 - ratio) + pos_left * ratio

        elif mode == 'flip_horizontally':
            # X: Flip, Y: Push
            preferred_x = x + offset
            final_x = preferred_x if preferred_x + popup_size.width() <= screen_geo.right() else x - popup_size.width() - offset

            final_y = y + offset
            if final_y + popup_size.height() > screen_geo.bottom(): final_y = screen_geo.bottom() - popup_size.height()
            if final_y < screen_geo.top(): final_y = screen_geo.top()

        elif mode == 'flip_vertically':
            # X: Push, Y: Flip
            final_x = x + offset
            if final_x + popup_size.width() > screen_geo.right(): final_x = screen_geo.right() - popup_size.width()
            if final_x < screen_geo.left(): final_x = screen_geo.left()

            preferred_y = y + offset
            final_y = preferred_y if preferred_y + popup_size.height() <= screen_geo.bottom() else y - popup_size.height() - offset

        else:  # 'flip_both'
            # X: Flip
            preferred_x = x + offset
            final_x = preferred_x if preferred_x + popup_size.width() <= screen_geo.right() else x - popup_size.width() - offset

            # Y: Flip
            preferred_y = y + offset
            final_y = preferred_y if preferred_y + popup_size.height() <= screen_geo.bottom() else y - popup_size.height() - offset

        # Final clamp to ensure the popup is always fully visible.
        final_x = max(screen_geo.left(), min(final_x, screen_geo.right() - popup_size.width()))
        final_y = max(screen_geo.top(), min(final_y, screen_geo.bottom() - popup_size.height()))

        self.move(int(final_x), int(final_y))

    def hide_popup(self):
        if not self.is_visible:
            return
        was_visible = self.is_visible
        self.hide()
        self.is_visible = False
        if was_visible != self.is_visible:
            logger.debug(f"Popup visibility changed: {was_visible} -> {self.is_visible}")
        # Set cooldown to prevent ghost popup (immediate re-show)
        import time as time_module
        self._hide_cooldown_end = time_module.time() + 0.2  # 200ms cooldown
        QTimer.singleShot(50, lambda: self._release_lock_safely())
        self._restore_focus_on_mac()

        # Hide furigana overlay whenever the popup disappears
        if self.overlay_furigana:
            self.overlay_furigana.hide_overlay()

    def _release_lock_safely(self):
        logger.debug("hide_popup releasing lock...")
        self.shared_state.screen_lock.release()
        logger.debug("...successfully released lock by hide_popup")

    def show_popup(self):
        if self.is_visible:
            return
        was_visible = self.is_visible
        logger.debug("show_popup acquiring lock...")
        self.shared_state.screen_lock.acquire()
        logger.debug("...successfully acquired lock by show_popup")
        if was_visible != self.is_visible:
            logger.debug(f"Popup visibility changed: {was_visible} -> {self.is_visible}")

        self._store_active_window_on_mac()
        self.show()
        if IS_MACOS:
            self.raise_()

        self.is_visible = True

        # Show furigana overlay when the popup appears, if enabled.
        # Because show_popup() runs while screen_lock is held, the OCR
        # processor cannot take a new screenshot and accidentally capture
        # the overlay – the timing exclusion comes for free.
        if (self.overlay_furigana and config.furigana_enabled
                and self.hit_scanner and self.hit_scanner.last_ocr_result):
            self.overlay_furigana.show_overlay()

    def reapply_settings(self):
        logger.debug("Popup: Re-applying settings and triggering font recalibration.")
        self._apply_frame_stylesheet()
        self.is_calibrated = False

    def _store_active_window_on_mac(self):
        """Store the currently active window for focus restoration (macOS only)."""
        if not IS_MACOS or not Quartz:
            return
        try:
            active_app = Quartz.NSWorkspace.sharedWorkspace().frontmostApplication()
            if active_app:
                self._previous_active_window_on_mac = active_app
        except Exception as e:
            logger.warning(f"Failed to store active window: {e}")
            self._previous_active_window_on_mac = None

    def _restore_focus_on_mac(self):
        """Restore focus to the previously active application (macOS only)."""
        if not IS_MACOS or not Quartz or not self._previous_active_window_on_mac:
            return
        try:
            self._previous_active_window_on_mac.activateWithOptions_(Quartz.NSApplicationActivateAllWindows)
        except Exception as e:
            logger.warning(f"Failed to restore focus: {e}")
        finally:
            self._previous_active_window_on_mac = None
