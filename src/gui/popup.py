# src/gui/popup.py
import logging
import threading
import time
from typing import List, Optional

from PyQt6.QtCore import QTimer, QPoint, QSize
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QCursor, QFont, QFontMetrics, QFontInfo
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QApplication

from src.config.config import config, MAX_DICT_ENTRIES, IS_MACOS
from src.dictionary.lookup import DictionaryEntry
from src.gui.magpie_manager import magpie_manager

# macOS-specific imports for focus management
if IS_MACOS:
    try:
        import Quartz
    except ImportError:
        Quartz = None

logger = logging.getLogger(__name__)


class Popup(QWidget):
    def __init__(self, shared_state, input_loop):
        super().__init__()
        self._latest_data = None
        self._latest_context = None
        self._last_latest_data = None
        self._last_latest_context = None
        self._data_lock = threading.Lock()
        self._previous_active_window_on_mac = None
        
        self.anki_shortcut_was_pressed = False
        self.copy_shortcut_was_pressed = False

        self.shared_state = shared_state
        self.input_loop = input_loop

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
        self.display_label.linkActivated.connect(self.handle_link_click)
        self.content_layout.addWidget(self.display_label)

        self.hide()

    def handle_link_click(self, url):
        if url == "anki":
            self.add_to_anki()
        elif url == "copy":
            self.copy_to_clipboard()

    def add_to_anki(self):
        logger.info("Add to Anki clicked")
        if not self._latest_context:
            logger.warning("No context available for Anki")
            return
        
        # We need to run this in a separate thread to not block GUI
        threading.Thread(target=self._add_to_anki_thread).start()

    def _add_to_anki_thread(self):
        from src.utils.anki import AnkiConnect
        import base64
        from io import BytesIO
        
        anki = AnkiConnect()
        if not anki.is_connected():
            logger.error("Anki is not connected")
            return

        context = self._latest_context
        entries = self._latest_data
        if not entries:
            return
        
        entry = entries[0] # Use the first entry
        
        # Prepare data
        word = entry.written_form
        reading = entry.reading
        meanings = []
        for sense in entry.senses:
            meanings.append("; ".join(sense.get('glosses', [])))
        meaning_str = "<br>".join(meanings)
        
        sentence = context.get("context_text", "")
        screenshot = context.get("screenshot")
        context_box = context.get("context_box")
        
        logger.debug(f"Anki Context Box: {context_box}")

        screenshot_filename = f"meikipop_{int(time.time())}.png"
        screenshot_field = ""
        
        if screenshot:
            from PIL import Image
            # Convert mss screenshot to PIL Image
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            
            # Crop to context if available
            if context_box:
                width, height = img.size
                logger.debug(f"Original Image Size: {width}x{height}")
                
                # Calculate coordinates from normalized box
                c_x = context_box.center_x * width
                c_y = context_box.center_y * height
                b_w = context_box.width * width
                b_h = context_box.height * height
                
                left = c_x - (b_w / 2)
                top = c_y - (b_h / 2)
                right = c_x + (b_w / 2)
                bottom = c_y + (b_h / 2)
                
                logger.debug(f"Calculated Crop: {left}, {top}, {right}, {bottom}")
                
                # Add padding (e.g., 50px or 10% of dimension)
                padding_x = 50
                padding_y = 50
                
                left = max(0, int(left - padding_x))
                top = max(0, int(top - padding_y))
                right = min(width, int(right + padding_x))
                bottom = min(height, int(bottom + padding_y))
                
                logger.debug(f"Padded Crop: {left}, {top}, {right}, {bottom}")

                # Ensure we have a valid crop
                if right > left and bottom > top:
                    img = img.crop((left, top, right, bottom))
                    logger.debug("Image cropped successfully")
                else:
                    logger.warning("Invalid crop dimensions")
            else:
                logger.warning("No context box found for cropping")
            
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()
            anki.store_media_file(screenshot_filename, img_str)
            screenshot_field = f'<img src="{screenshot_filename}">'

        # Configure deck and model (hardcoded for now or from config)
        deck_name = config.anki_deck_name
        model_name = config.anki_model_name
        
        # Check if we need to create the Meikipop model
        if model_name == "Meikipop Card":
            available_models = anki.get_model_names()
            if available_models and model_name not in available_models:
                logger.info(f"Creating new Anki model: {model_name}")
                
                # Define model structure
                in_order_fields = ["Kana", "Sentence", "Picture", "Meaning", "Meaning Japanese", "Pitch", "Reading"]
                
                css = """
/* Base card styling */
.card {
  font-family: "Hiragino Sans", "Yu Gothic", "Meiryo", "MS PGothic", arial, sans-serif;
  color: #ffffff;
  text-align: center;
  padding: 0;
  margin: 0;
  height: 100vh;
  width: 100vw;
  display: flex;
  flex-direction: column;
  justify-content: center;
  overflow: hidden;
  position: fixed;
  top: 0;
  left: 0;
}

* {
  background: #1a1a1a;
}

html {
  background: #1a1a1a;
  min-height: 100vh;
}

body {
  background: #1a1a1a;
  margin: 0;
  padding: 0;
  overflow: hidden;
}

/* Front card specific */
.card-front {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  height: 100vh;
  padding: 20px;
}

/* Back card specific */
.card-back {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  height: 100vh;
  padding: 20px;
}

/* Japanese text (main word/phrase) */
.japanese-text {
  font-size: 52px;
  font-weight: 300;
  letter-spacing: 4px;
  margin-bottom: 12px;
  line-height: 1.3;
  color: #ffffff;
}

/* Context/sentence text below main word */
.context-text {
  font-size: 17px;
  color: #a0a0a0;
  margin-bottom: 8px;
  max-width: 700px;
}

/* Sentence on back */
.sentence-text {
  font-size: 19px;
  color: #b8b8b8;
  margin: 8px 0 15px 0;
  line-height: 1.4;
}

/* Image container */
.image-container {
  max-width: 90%;
  max-height: 35vh;
  margin: 15px auto;
  border-radius: 6px;
  overflow: hidden;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
}

.image-container img,
img {
  width: 100%;
  height: auto;
  max-height: 35vh;
  display: block;
  object-fit: contain;
}

/* Divider line */
.divider {
  width: 60%;
  height: 1px;
  background: linear-gradient(90deg, transparent, #444, transparent);
  margin: 12px auto;
}

/* Meaning text */
.meaning-text {
  font-size: 18px;
  color: #d0d0d0;
  margin: 10px 0;
  line-height: 1.5;
}

.meaning.japanese {
  font-size: 20px;
  color: #b0b0b0;
  margin: 8px 0;
  font-weight: 300;
}

/* Pitch accent */
.accent-graph {
  font-size: 90%;
  transform: scaleX(1);
  margin: 8px 0;
  opacity: 0.85;
}

.reading {
  font-size: 18px;
  color: #b0b0b0;
  margin: 6px 0;
}

/* Furigana styling - hidden by default, shown on hover */
ruby rt {
  font-size: 0.5em;
  color: #999;
  opacity: 0;
  transition: opacity 0.3s ease;
}

ruby:hover rt {
  opacity: 1;
}

/* Alternative: hide furigana on mobile tap/touch */
@media (hover: none) {
  ruby rt {
    opacity: 0;
  }
  
  ruby:active rt {
    opacity: 1;
  }
}
"""
                
                front_template = """
<div class="card-front">
  <div class="japanese-text">{{furigana:Kana}}</div>
  <!--{{#Sentence}}
  <div class="context-text">{{Sentence}}</div>
  {{/Sentence}}-->
</div>
"""
                
                back_template = """
<div class="card-back">
  <div class="japanese-text">{{furigana:Kana}}</div>
  {{#Sentence}}
  <div class="sentence-text">{{Sentence}}</div>
  {{/Sentence}}
  
  {{#Picture}}
  <div class="image-container">
    {{Picture}}
  </div>
  {{/Picture}}
  
  <div class="divider"></div>
  
  <div class="meaning-text">{{Meaning}}</div>
  
  {{#Meaning Japanese}}
  <div class="meaning japanese">{{Meaning Japanese}}</div>
  {{/Meaning Japanese}}
  
  {{#Pitch}}
  <div class="accent-graph">{{Pitch}}</div>
  <div class="reading">{{Reading}}</div>
  {{/Pitch}}
</div>
"""
                
                card_templates = [{
                    "Name": "Card 1",
                    "Front": front_template,
                    "Back": back_template
                }]
                
                result = anki.create_model(model_name, in_order_fields, css, card_templates)
                if result and result.get('error'):
                    logger.error(f"Failed to create model: {result.get('error')}")
                    return
                logger.info(f"Created model: {result}")

        # Get model fields
        model_fields = anki.get_model_field_names(model_name)
        if not model_fields:
             logger.error(f"Could not get fields for model: {model_name}")
             return

        fields = {}
        
        # 1. Identify target fields based on available model fields
        target_word = next((f for f in model_fields if f.lower() in ["front", "word", "expression", "vocab", "kanji"]), None)
        target_reading = next((f for f in model_fields if f.lower() in ["reading", "kana", "furigana"]), None)
        target_meaning = next((f for f in model_fields if f.lower() in ["meaning", "glossary", "definition", "english"]), None)
        target_sentence = next((f for f in model_fields if f.lower() in ["sentence", "context", "example"]), None)
        target_picture = next((f for f in model_fields if f.lower() in ["picture", "image", "screenshot"]), None)
        target_back = next((f for f in model_fields if f.lower() == "back"), None)

        # 2. Populate fields
        if target_word:
            fields[target_word] = word
        
        if target_reading:
            # Special handling for "Kana" field in Meikipop Card which expects Word[Reading] for furigana
            if model_name == "Meikipop Card" and reading:
                 fields[target_reading] = f"{word}[{reading}]"
            else:
                 fields[target_reading] = reading
            
        if target_meaning:
            fields[target_meaning] = meaning_str
            
        if target_sentence:
            fields[target_sentence] = sentence
            
        if target_picture:
            fields[target_picture] = screenshot_field

        # 3. Handle "Back" field (catch-all for Basic cards)
        if target_back:
            # If we have specific fields for meaning/sentence/picture, we might not want to duplicate them in Back,
            # UNLESS it's a Basic card where Back is the only place for them.
            # If we found target_meaning, target_sentence, OR target_picture, we assume it's a specialized card.
            # If we ONLY found target_word and target_back (like Basic Card), we dump everything in Back.
            
            is_basic_style = not (target_meaning or target_sentence or target_picture)
            
            if is_basic_style:
                content = []
                if reading: content.append(reading)
                if meaning_str: content.append(meaning_str)
                if sentence: content.append(f"<br>{sentence}")
                if screenshot_field: content.append(f"<br>{screenshot_field}")
                fields[target_back] = "<br>".join(content)

        result = anki.add_note(deck_name, model_name, fields, tags=["meikipop"])
        if result:
            logger.info(f"Added note: {result}")
        else:
            logger.error("Failed to add note")

    def copy_to_clipboard(self):
        logger.info("Copy to clipboard clicked")
        if not self._latest_context:
            return
        
        text = self._latest_context.get("context_text", "")
        QApplication.clipboard().setText(text)

    def _apply_frame_stylesheet(self):
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

    def set_latest_data(self, data, context=None):
        with self._data_lock:
            self._latest_data = data
            self._latest_context = context

    def get_latest_data(self):
        with self._data_lock:
            return self._latest_data, self._latest_context

    def process_latest_data_loop(self):
        if not self.is_calibrated:
            self._calibrate_empirically()

        latest_data, latest_context = self.get_latest_data()
        if latest_data and (latest_data != self._last_latest_data or latest_context != self._last_latest_context):
            # update popup content
            full_html, new_size = self._calculate_content_and_size_char_count(latest_data)
            self.display_label.setText(full_html)
            self.setFixedSize(new_size)
        self._last_latest_data = latest_data
        self._last_latest_context = latest_context

        if self._latest_data and self.input_loop.is_virtual_hotkey_down():
            self.show_popup()
            
            # Check for shortcuts
            anki_pressed = self.input_loop.is_key_pressed('alt+a')
            if anki_pressed and not self.anki_shortcut_was_pressed:
                self.add_to_anki()
            self.anki_shortcut_was_pressed = anki_pressed

            copy_pressed = self.input_loop.is_key_pressed('alt+c')
            if copy_pressed and not self.copy_shortcut_was_pressed:
                self.copy_to_clipboard()
            self.copy_shortcut_was_pressed = copy_pressed
        else:
            self.hide_popup()

        mouse_pos = QCursor.pos()
        self.move_to(mouse_pos.x(), mouse_pos.y())

    def _calculate_content_and_size_char_count(self, entries: Optional[List[DictionaryEntry]]) -> tuple[
        Optional[str], Optional[QSize]]:
        if not self.is_calibrated: return None, None

        if not entries:
            return None, None

        all_html_parts = []
        max_ratio = 0.0

        for i, entry in enumerate(entries[:min(len(entries), MAX_DICT_ENTRIES)]):
            if i > 0:
                all_html_parts.append('<hr style="margin-top: 0px; margin-bottom: 0px;">')

            header_text_calc = entry.written_form
            if entry.reading: header_text_calc += f" [{entry.reading}]"
            if config.show_tags and entry.tags:
                header_text_calc += f' [{", ".join(sorted(list(entry.tags)))}]'
            header_ratio = len(header_text_calc) / self.header_chars_per_line
            max_ratio = max(max_ratio, header_ratio)

            # --- HTML construction ---
            header_html = f'<span style="color: {config.color_highlight_word}; font-size:{config.font_size_header}px;">{entry.written_form}</span>'
            if entry.reading: header_html += f' <span style="color: {config.color_highlight_reading}; font-size:{config.font_size_header - 2}px;">[{entry.reading}]</span>'
            if config.show_tags and entry.tags:
                tags_str = ", ".join(sorted(list(entry.tags)))
                header_html += f' <span style="color:{config.color_foreground}; font-size:{config.font_size_definitions - 2}px; opacity:0.7;">[{tags_str}]</span>'
            if entry.deconjugation_process and config.show_deconjugation:
                deconj_str = " ← ".join(p for p in entry.deconjugation_process if p)
                if deconj_str:
                    header_html += f' <span style="color:{config.color_foreground}; font-size:{config.font_size_definitions - 2}px; opacity:0.8;">({deconj_str})</span>'
            def_text_parts_calc = []
            def_text_parts_html = []
            for idx, sense in enumerate(entry.senses):
                glosses_str = '; '.join(sense.get('glosses', []))
                pos_list = sense.get('pos', [])
                sense_calc = f"({idx + 1})"
                sense_html = f"<b>({idx + 1})</b> "
                if config.show_pos and pos_list:
                    pos_str = f' ({", ".join(pos_list)})'
                    sense_calc += pos_str
                    sense_html += f'<span style="color:{config.color_foreground}; opacity:0.7;"><i>{pos_str}</i></span> '
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

            definitions_html_final = f'<div style="font-size:{config.font_size_definitions}px;">{full_def_text_html}</div>'
            all_html_parts.append(f"{header_html}{definitions_html_final}")

        optimal_content_width = self.max_content_width * min(1.0, max_ratio)
        optimal_content_width = max(optimal_content_width, 200)

        full_html = "".join(all_html_parts)
        
        # Add buttons
        buttons_html = '<br><br><a href="anki" style="color: cyan; text-decoration: none;">[Add to Anki - Alt+A]</a> &nbsp; <a href="copy" style="color: cyan; text-decoration: none;">[Copy Text - Alt+C]</a>'
        full_html += buttons_html

        self.probe_label.setText(full_html)

        final_height = self.probe_label.heightForWidth(int(optimal_content_width))

        margins = self.content_layout.contentsMargins()
        border_width = 1
        horizontal_padding = margins.left() + margins.right() + (border_width * 2)
        vertical_padding = margins.top() + margins.bottom() + (border_width * 2)

        final_size = QSize(int(optimal_content_width) + horizontal_padding, final_height + vertical_padding)
        return full_html, final_size

    def move_to(self, x, y):
        cursor_point = QPoint(x, y)
        screen = QApplication.screenAt(cursor_point) or QApplication.primaryScreen()
        screen_geo = screen.geometry()
        popup_size = self.size()
        offset = 15

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
        # This acts as a safeguard against any edge cases.
        final_x = max(screen_geo.left(), min(final_x, screen_geo.right() - popup_size.width()))
        final_y = max(screen_geo.top(), min(final_y, screen_geo.bottom() - popup_size.height()))

        self.move(int(final_x), int(final_y))

    def hide_popup(self):
        # logger.debug(f"hide_popup triggered while visibility:{self.is_visible}")
        if not self.is_visible:
            return
        self.hide()
        self.is_visible = False
        QTimer.singleShot(50, lambda: self._release_lock_safely())  # prevent popup from being screenshotted
        self._restore_focus_on_mac()

    def _release_lock_safely(self):
        logger.debug("hide_popup releasing lock...")
        self.shared_state.screen_lock.release()
        logger.debug("...successfully released lock by hide_popup")

    def show_popup(self):
        # logger.debug(f"show_popup triggered while visibility:{self.is_visible}")
        if self.is_visible:
            return
        logger.debug("show_popup acquiring lock...")
        self.shared_state.screen_lock.acquire()
        logger.debug("...successfully acquired lock by show_popup")

        self._store_active_window_on_mac()
        self.show()
        if IS_MACOS:
            self.raise_()

        self.is_visible = True

    def reapply_settings(self):
        logger.debug("Popup: Re-applying settings and triggering font recalibration.")
        self._apply_frame_stylesheet()
        # By setting is_calibrated to False, the main loop will automatically
        # run _calibrate_empirically() again with the new font settings.
        self.is_calibrated = False

    def _store_active_window_on_mac(self):
        """Store the currently active window for focus restoration (macOS only)."""
        if not IS_MACOS or not Quartz:
            return

        try:
            # Get the currently active application
            active_app = Quartz.NSWorkspace.sharedWorkspace().frontmostApplication()
            if active_app:
                # Store the application reference instead of trying to get the window
                # We'll use the application to restore focus later
                self._previous_active_window_on_mac = active_app
        except Exception as e:
            logger.warning(f"Failed to store active window: {e}")
            self._previous_active_window_on_mac = None

    def _restore_focus_on_mac(self):
        """Restore focus to the previously active application (macOS only)."""
        if not IS_MACOS or not Quartz or not self._previous_active_window_on_mac:
            return

        try:
            # Activate the previously active application
            self._previous_active_window_on_mac.activateWithOptions_(Quartz.NSApplicationActivateAllWindows)
        except Exception as e:
            logger.warning(f"Failed to restore focus: {e}")
        finally:
            # Clear the stored application reference
            self._previous_active_window_on_mac = None
