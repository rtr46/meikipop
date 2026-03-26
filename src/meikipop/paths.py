import os
import sys
from platformdirs import PlatformDirs


class MeikiPaths:
    """Centralized path resolution for meikipop.
    
    Handles three modes:
    - frozen: Running as PyInstaller bundle (prebuilt)
    - editable: Running from source with pip install -e
    - regular: Running as pip install (non-editable)
    """
    
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
    def user_config_dir(self):
        return self._platform_dirs.user_config_dir
    
    @property
    def user_data_dir(self):
        return self._platform_dirs.user_data_dir
    
    @property
    def user_cache_dir(self):
        return self._platform_dirs.user_cache_dir
    
    @property
    def config_dir(self):
        """Location of config.ini"""
        if self.is_frozen:
            return os.path.dirname(sys.executable)
        return self.user_config_dir
    
    @property
    def config_path(self):
        """Full path to config.ini"""
        return os.path.join(self.config_dir, 'config.ini')
    
    @property
    def dictionary_path(self):
        """Location of dictionary.pkl"""
        if self.is_frozen:
            return os.path.join(os.path.dirname(sys.executable), 'dictionary.pkl')
        return os.path.join(self.user_data_dir, 'dictionary.pkl')
    
    @property
    def cache_dir(self):
        """Location for cached downloads"""
        return self.user_cache_dir
    
    @property
    def data_dir(self):
        """User data directory (for pip install)"""
        return self.user_data_dir
    
    @property
    def resource_dir(self):
        """Location of bundled resources (icons, etc.)"""
        if self.is_frozen:
            return os.path.join(sys._MEIPASS, 'meikipop')
        # For pip install/editable, use package directory (src/meikipop/)
        return os.path.dirname(os.path.abspath(__file__))
    
    def get_resource_path(self, relative_path):
        """Get full path to a bundled resource"""
        return os.path.join(self.resource_dir, relative_path)


paths = MeikiPaths()