import os
import sys
from platformdirs import PlatformDirs


class MeikiPaths:
    """Centralized path resolution for meikipop."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            # Create the platformdirs instance as a composited object
            cls._instance = object.__new__(cls)
            cls._instance._platform_dirs = PlatformDirs("meikipop", appauthor=False, ensure_exists=True)
        return cls._instance

    @property
    def is_frozen(self):
        """Check if running as PyInstaller bundle"""
        return getattr(sys, 'frozen', False)

    @property
    def data_dir(self):
        """Location of dictionary.pkl"""
        return self._platform_dirs.user_data_dir
    
    @property
    def config_path(self):
        """Full path to config.ini"""
        return os.path.join(self._platform_dirs.user_config_dir, 'config.ini')
    
    @property
    def dictionary_path(self):
        """Location of dictionary.pkl"""
        return os.path.join(self.data_dir, 'dictionary.pkl')
    
    @property
    def cache_dir(self):
        """Location for cached downloads"""
        return self._platform_dirs.user_cache_dir
    
    @property
    def main_dir(self):
        """Location of bundled resources (icons, etc.)"""
        if self.is_frozen:
            return os.path.join(sys._MEIPASS, 'meikipop')
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    def get_resource_path(self, relative_path):
        """Get full path to a bundled resource"""
        return os.path.join(self.main_dir, 'resources', relative_path)


paths = MeikiPaths()