from platformdirs import PlatformDirs

class MeikiPaths:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = PlatformDirs("meikipop", appauthor=False, ensure_exists=True)
        return cls._instance

paths = MeikiPaths()