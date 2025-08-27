# src/config/config.py
import configparser
import logging
import sys

logger = logging.getLogger(__name__)

APP_NAME = "meikipop"
APP_VERSION = "v.1.1.1"
MAX_DICT_ENTRIES = 10
IS_LINUX = sys.platform.startswith('linux')
IS_WINDOWS = sys.platform.startswith('win')
IS_MACOS = sys.platform.startswith('darwin')

class Config:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        self._load()

    def _load(self):
        config = configparser.ConfigParser()

        # Step 1: Set hardcoded defaults
        defaults = {
            'Settings': {
                'hotkey': 'shift',
                'scan_region': 'region',
                'max_lookup_length': '25',
                'quality_mode': 'balanced',
                'ocr_provider': 'Google Lens',
                'auto_scan_mode': 'false',
                'auto_scan_mode_lookups_without_hotkey': 'true'
            },
            'Theme': {
                'theme_name': 'Nazeka',
                'font_family': '',
                'font_size_definitions': '14',
                'font_size_header': '18',
                'compact_mode': 'true',
                'show_deconjugation': 'false',
                'show_pos': 'false',
                'show_tags': 'false',
                'color_background': '#2E2E2E',
                'color_foreground': '#F0F0F0',
                'color_highlight_word': '#88D8FF',
                'color_highlight_reading': '#90EE90',
                'background_opacity': '245',
                'popup_position_mode': 'flip_vertically'
            }
        }
        config.read_dict(defaults)

        # Step 2: Load from config.ini, creating it if it doesn't exist
        try:
            if not config.read('config.ini'):
                with open('config.ini', 'w', encoding='utf-8') as configfile:
                    config.write(configfile)
                logger.info("config.ini not found, created with default settings.")
            else:
                logger.info("Loaded settings from config.ini.")
        except configparser.Error as e:
            logger.warning(f"Warning: Could not parse config.ini. Using defaults. Error: {e}")

        # Apply settings from the config object first
        self.hotkey = config.get('Settings', 'hotkey')
        self.scan_region = config.get('Settings', 'scan_region')
        self.max_lookup_length = config.getint('Settings', 'max_lookup_length')
        self.quality_mode = config.get('Settings', 'quality_mode')
        self.ocr_provider = config.get('Settings', 'ocr_provider')
        self.auto_scan_mode = config.getboolean('Settings', 'auto_scan_mode')
        self.auto_scan_mode_lookups_without_hotkey = config.getboolean('Settings',
                                                                       'auto_scan_mode_lookups_without_hotkey')
        self.theme_name = config.get('Theme', 'theme_name')
        self.font_family = config.get('Theme', 'font_family')
        self.font_size_definitions = config.getint('Theme', 'font_size_definitions')
        self.font_size_header = config.getint('Theme', 'font_size_header')
        self.compact_mode = config.getboolean('Theme', 'compact_mode')
        self.show_deconjugation = config.getboolean('Theme', 'show_deconjugation')
        self.show_pos = config.getboolean('Theme', 'show_pos')
        self.show_tags = config.getboolean('Theme', 'show_tags')
        self.color_background = config.get('Theme', 'color_background')
        self.color_foreground = config.get('Theme', 'color_foreground')
        self.color_highlight_word = config.get('Theme', 'color_highlight_word')
        self.color_highlight_reading = config.get('Theme', 'color_highlight_reading')
        self.background_opacity = config.getint('Theme', 'background_opacity')
        self.popup_position_mode = config.get('Theme', 'popup_position_mode')

        self.is_enabled = True

        # todo command line args parsing

    def save(self):
        config = configparser.ConfigParser()
        config['Settings'] = {
            'hotkey': self.hotkey,
            'scan_region': self.scan_region,
            'max_lookup_length': str(self.max_lookup_length),
            'quality_mode': self.quality_mode,
            'ocr_provider': self.ocr_provider,
            'auto_scan_mode': str(self.auto_scan_mode).lower(),
            'auto_scan_mode_lookups_without_hotkey': str(self.auto_scan_mode_lookups_without_hotkey).lower()
        }
        config['Theme'] = {
            'theme_name': self.theme_name,
            'font_family': self.font_family,
            'font_size_definitions': str(self.font_size_definitions),
            'font_size_header': str(self.font_size_header),
            'compact_mode': str(self.compact_mode).lower(),
            'show_deconjugation': str(self.show_deconjugation).lower(),
            'show_pos': str(self.show_pos).lower(),
            'show_tags': str(self.show_tags).lower(),
            'color_background': self.color_background,
            'color_foreground': self.color_foreground,
            'color_highlight_word': self.color_highlight_word,
            'color_highlight_reading': self.color_highlight_reading,
            'background_opacity': str(self.background_opacity),
            'popup_position_mode': self.popup_position_mode
        }
        with open('config.ini', 'w', encoding='utf-8') as configfile:
            config.write(configfile)
        logger.info("Settings saved to config.ini.")

# The singleton instance
config = Config()