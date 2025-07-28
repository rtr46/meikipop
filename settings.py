# settings.py
import configparser
import argparse
import multiprocessing

# The developer-defined app name now lives here.
APP_NAME = "meikipop"

class Settings:
    def __init__(self):
        self._load()

    def user_log(self, message: str):
        """Prints a user-facing log message to the console."""
        print(f"[{APP_NAME}] {message}")

    def _load(self):
        """Loads settings from defaults, config file, and CLI arguments."""
        config = configparser.ConfigParser()
        
        # Step 1: Set hardcoded defaults
        defaults = {
            'Settings': {
                'hotkey': 'shift',
                'scan_region': 'region',
                'max_lookup_length': '25',
                'quality_mode': 'fast'
            },
            'Theme': {
                'theme_name': 'Nazeka',
                'font_family': '',
                'font_size_definitions': '14',
                'font_size_header': '18',
                'compact_mode': 'true',
                'hide_deconjugation': 'true',
                'popup_width': '900',
                'color_background': '#2E2E2E',
                'color_foreground': '#F0F0F0',
                'color_highlight_word': '#88D8FF',
                'color_highlight_reading': '#90EE90',
                'color_separator_line': '#444444',
                'background_opacity': '245'
            }
        }
        config.read_dict(defaults)

        # Step 2: Load from config.ini, creating it if it doesn't exist
        try:
            if not config.read('config.ini'):
                with open('config.ini', 'w', encoding='utf-8') as configfile:
                    config.write(configfile)
                self.user_log("config.ini not found, created with default settings.")
            else:
                if multiprocessing.current_process().name == 'MainProcess':
                    self.user_log("Loaded settings from config.ini.")
        except configparser.Error as e:
            self.user_log(f"Warning: Could not parse config.ini. Using defaults. Error: {e}")

        # Step 3: Parse command-line arguments for temporary overrides
        parser = argparse.ArgumentParser(description=f"{APP_NAME} OCR Lookup Tool")
        parser.add_argument('--scan-region', type=str, choices=['screen', 'region'])
        parser.add_argument('--hotkey', type=str, choices=['shift', 'ctrl', 'alt'])
        args = parser.parse_args()

        # Apply settings from the config object first
        self.hotkey = config.get('Settings', 'hotkey')
        self.scan_region = config.get('Settings', 'scan_region')
        self.max_lookup_length = config.getint('Settings', 'max_lookup_length')
        self.quality_mode = config.get('Settings', 'quality_mode')
        self.theme_name = config.get('Theme', 'theme_name')
        self.font_family = config.get('Theme', 'font_family')
        self.font_size_definitions = config.getint('Theme', 'font_size_definitions')
        self.font_size_header = config.getint('Theme', 'font_size_header')
        self.compact_mode = config.getboolean('Theme', 'compact_mode')
        self.hide_deconjugation = config.getboolean('Theme', 'hide_deconjugation')
        self.popup_width = config.getint('Theme', 'popup_width')
        self.color_background = config.get('Theme', 'color_background')
        self.color_foreground = config.get('Theme', 'color_foreground')
        self.color_highlight_word = config.get('Theme', 'color_highlight_word')
        self.color_highlight_reading = config.get('Theme', 'color_highlight_reading')
        self.color_separator_line = config.get('Theme', 'color_separator_line')
        self.background_opacity = config.getint('Theme', 'background_opacity')
        
        # Apply command-line overrides
        if args.scan_region:
            self.scan_region = args.scan_region
            self.user_log(f"Using command-line override: scan_region = '{self.scan_region}'")
        if args.hotkey:
            self.hotkey = args.hotkey
            self.user_log(f"Using command-line override: hotkey = '{self.hotkey}'")

    def save(self):
        """Saves the current settings back to config.ini."""
        config = configparser.ConfigParser()
        config['Settings'] = {
            'hotkey': self.hotkey,
            'scan_region': self.scan_region,
            'max_lookup_length': str(self.max_lookup_length),
            'quality_mode': self.quality_mode
        }
        config['Theme'] = {
            'theme_name': self.theme_name,
            'font_family': self.font_family,
            'font_size_definitions': str(self.font_size_definitions),
            'font_size_header': str(self.font_size_header),
            'compact_mode': str(self.compact_mode).lower(),
            'hide_deconjugation': str(self.hide_deconjugation).lower(),
            'popup_width': str(self.popup_width),
            'color_background': self.color_background,
            'color_foreground': self.color_foreground,
            'color_highlight_word': self.color_highlight_word,
            'color_highlight_reading': self.color_highlight_reading,
            'color_separator_line': self.color_separator_line,
            'background_opacity': str(self.background_opacity)
        }
        with open('config.ini', 'w', encoding='utf-8') as configfile:
            config.write(configfile)
        self.user_log("Settings saved to config.ini.")

# --- CREATE THE GLOBAL INSTANCE ---
settings = Settings()