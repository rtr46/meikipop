# src/config/config.py
import configparser
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

APP_NAME = "meikipop"
APP_VERSION = "v.1.13.0"
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
        }
    }

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        self._config_path = self._resolve_config_path()
        parser = configparser.ConfigParser()
        parser.read(self._config_path, encoding='utf-8')

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
        logger.info(f"Configuration loaded from '{self._config_path}'.")

    def _resolve_config_path(self) -> str:
        """
        Resolve where config.ini should be read/written.

        - Source/dev runs: keep using local config.ini in CWD.
        - Frozen macOS app: use ~/Library/Application Support/meikipop/config.ini.
        - Frozen Windows/Linux: keep config beside executable for portability.
        """
        if not getattr(sys, 'frozen', False):
            return 'config.ini'

        if IS_MACOS:
            app_support_dir = Path.home() / 'Library' / 'Application Support' / APP_NAME
            app_support_dir.mkdir(parents=True, exist_ok=True)
            return str(app_support_dir / 'config.ini')

        return str(Path(sys.executable).resolve().parent / 'config.ini')

    def save(self):
        parser = configparser.ConfigParser()
        for section, settings in self._SCHEMA.items():
            parser.add_section(section)
            for key in settings:
                val = getattr(self, key)
                parser.set(section, key, str(val).lower() if isinstance(val, bool) else str(val))

        config_path = getattr(self, '_config_path', self._resolve_config_path())
        with open(config_path, 'w', encoding='utf-8') as f:
            parser.write(f)
        logger.info(f"Settings saved to '{config_path}'.")


config = Config()