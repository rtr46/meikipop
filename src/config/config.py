# src/config/config.py
import configparser
import logging
import sys

logger = logging.getLogger(__name__)

APP_NAME = "meikipop"
APP_VERSION = "v.1.12.5"
MAX_DICT_ENTRIES = 10
IS_LINUX = sys.platform.startswith('linux')
IS_WINDOWS = sys.platform.startswith('win')
IS_MACOS = sys.platform.startswith('darwin')

class Config:
    _instance = None

    _SCHEMA = {
        'Settings': {
            'hotkey': 'shift',
            'scan_region': 'region',
            'max_lookup_length': 25,
            'glens_low_bandwidth': False,
            'ocr_provider': 'Google Lens (remote)',
            'auto_scan_mode': False,
            'auto_scan_mode_lookups_without_hotkey': True,
            'auto_scan_interval_seconds': 0.0,
            'auto_scan_on_mouse_move': False,
            'magpie_compatibility': False
        },
        'Theme': {
            'theme_name': 'Nazeka',
            'font_family': '',
            'font_size_definitions': 14,
            'font_size_header': 18,
            'compact_mode': True,
            'show_all_glosses': False,
            'show_deconjugation': False,
            'show_pos': False,
            'show_tags': False,
            'show_frequency': False,
            'show_kanji': True,
            'show_examples': False,
            'show_components': False,
            'color_background': '#2E2E2E',
            'color_foreground': '#F0F0F0',
            'color_highlight_word': '#88D8FF',
            'color_highlight_reading': '#90EE90',
            'background_opacity': 245,
            'popup_position_mode': 'flip_vertically'
        },
        'Gamepad': {
            # Master switch - all gamepad features disabled by default
            'gamepad_enabled': False,
            # Which physical joystick to use (0 = first detected)
            'gamepad_joystick_index': 0,
            # Button indices (Xbox layout: A=0 B=1 X=2 Y=3 LB=4 RB=5 Back=6 Start=7 L3=8 R3=9)
            'gamepad_toggle_button': 6,  # Back/Select: enter/exit navigation mode
            'gamepad_exit_button': 1,  # B: quick-exit navigation mode
            'gamepad_furigana_button': 3,  # Y: toggle furigana overlay
            'gamepad_word_prev_button': 4,  # LB: jump to previous token (word-level nav)
            'gamepad_word_next_button': 5,  # RB: jump to next token (word-level nav)
            # D-pad is always used for character navigation when in nav mode
        },
        'Furigana': {
            # Whether to show furigana overlay when the popup is visible
            'furigana_enabled': False,
            # Color for furigana text
            'furigana_color': '#FFE066',
            # Pixel size for furigana text (smaller than game text)
            'furigana_font_size': 11,
            # Color for the gamepad selection highlight box
            'selection_color': '#FF4444',
            # Alpha 0-255 for the selection fill
            'selection_opacity': 120,
        }
    }

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        parser = configparser.ConfigParser()
        parser.read('config.ini', encoding='utf-8')

        for section, settings in self._SCHEMA.items():
            for key, default in settings.items():
                if parser.has_option(section, key):
                    if isinstance(default, bool):
                        val = parser.getboolean(section, key)
                    elif isinstance(default, int):
                        val = parser.getint(section, key)
                    elif isinstance(default, float):
                        val = parser.getfloat(section, key)
                    else:
                        val = parser.get(section, key)
                else:
                    val = default
                setattr(self, key, val)

        self.is_enabled = True
        logger.info("Configuration loaded.")

    def save(self):
        parser = configparser.ConfigParser()
        for section, settings in self._SCHEMA.items():
            parser.add_section(section)
            for key in settings:
                val = getattr(self, key)
                parser.set(section, key, str(val).lower() if isinstance(val, bool) else str(val))

        with open('config.ini', 'w', encoding='utf-8') as f:
            parser.write(f)
        logger.info("Settings saved to config.ini.")


config = Config()
