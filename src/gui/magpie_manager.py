# src/gui/magpie_manager.py
import logging
import time

from src.config.config import IS_WINDOWS, config

logger = logging.getLogger(__name__)

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    try:
        user32 = ctypes.windll.user32
        HWND = wintypes.HWND
        LPCWSTR = wintypes.LPCWSTR
        HANDLE = wintypes.HANDLE
        LONG = wintypes.LONG

        FindWindowW = user32.FindWindowW
        FindWindowW.argtypes = [LPCWSTR, LPCWSTR]
        FindWindowW.restype = HWND

        IsWindowVisible = user32.IsWindowVisible
        IsWindowVisible.argtypes = [HWND]
        IsWindowVisible.restype = ctypes.c_int

        GetPropW = user32.GetPropW
        GetPropW.argtypes = [HWND, LPCWSTR]
        GetPropW.restype = HANDLE


        class RECT(ctypes.Structure):
            _fields_ = [("left", LONG), ("top", LONG), ("right", LONG), ("bottom", LONG)]

            @property
            def width(self): return self.right - self.left

            @property
            def height(self): return self.bottom - self.top


        class MagpieManager:
            _instance = None

            def __new__(cls):
                if cls._instance is None:
                    cls._instance = super(MagpieManager, cls).__new__(cls)
                return cls._instance

            def __init__(self):
                self.last_check_time = 0
                self.cache_duration = 0.5  # seconds
                self.cached_info = None
                self.class_name = "Window_Magpie_967EB565-6F73-4E94-AE53-00CC42592A22"

            def _get_prop_safe(self, hwnd, prop_name):
                prop = GetPropW(hwnd, prop_name)
                return prop if prop is not None else 0

            def _fetch_magpie_info(self):
                """Performs the actual WinAPI calls to find the Magpie window and its properties."""
                hwnd_scaling = FindWindowW(self.class_name, None)
                if not hwnd_scaling or not IsWindowVisible(hwnd_scaling):
                    return None

                info = {
                    "src_rect": RECT(
                        self._get_prop_safe(hwnd_scaling, "Magpie.SrcLeft"),
                        self._get_prop_safe(hwnd_scaling, "Magpie.SrcTop"),
                        self._get_prop_safe(hwnd_scaling, "Magpie.SrcRight"),
                        self._get_prop_safe(hwnd_scaling, "Magpie.SrcBottom"),
                    ),
                    "dest_rect": RECT(
                        self._get_prop_safe(hwnd_scaling, "Magpie.DestLeft"),
                        self._get_prop_safe(hwnd_scaling, "Magpie.DestTop"),
                        self._get_prop_safe(hwnd_scaling, "Magpie.DestRight"),
                        self._get_prop_safe(hwnd_scaling, "Magpie.DestBottom"),
                    ),
                }
                if info["src_rect"].width > 0 and info["dest_rect"].width > 0:
                    return info
                return None

            def get_info(self):
                """
                Returns cached Magpie info if available and not stale, otherwise fetches new info.
                This is the rate-limited entry point.
                """
                if not config.magpie_compatibility:
                    return None

                now = time.time()
                if (now - self.last_check_time) > self.cache_duration:
                    self.last_check_time = now
                    self.cached_info = self._fetch_magpie_info()
                return self.cached_info

            def transform_raw_to_visual(self, raw_mouse_pos: tuple[int, int], ratio) -> tuple[int, int]:
                """
                Transforms a raw physical mouse coordinate to its visual on-screen coordinate
                if Magpie is active. Otherwise, returns the coordinate unchanged.
                """
                magpie_info = self.get_info()
                if not magpie_info:
                    return raw_mouse_pos

                src = magpie_info["src_rect"]
                dest = magpie_info["dest_rect"]
                mx, my = raw_mouse_pos
                mx = int(mx * ratio)
                my = int(my * ratio)

                if src.width > 0 and src.height > 0 and (src.left <= mx < src.right and src.top <= my < src.bottom):
                    relative_x = (mx - src.left) / src.width
                    relative_y = (my - src.top) / src.height
                    screen_x = dest.left + (relative_x * dest.width)
                    screen_y = dest.top + (relative_y * dest.height)
                    return int(screen_x / ratio), int(screen_y / ratio)

                return raw_mouse_pos

    except (AttributeError, OSError) as e:
        logger.warning(f"Could not initialize Windows API for Magpie integration: {e}")


        class MagpieManager:  # Dummy class if ctypes fails
            _instance = None

            def __new__(cls):
                if cls._instance is None: cls._instance = super(MagpieManager, cls).__new__(cls)
                return cls._instance

            def transform_raw_to_visual(self, raw_mouse_pos: tuple[int, int], ratio) -> tuple[int, int]:
                return raw_mouse_pos

else:
    class MagpieManager:  # Dummy class for non-Windows platforms
        _instance = None

        def __new__(cls):
            if cls._instance is None: cls._instance = super(MagpieManager, cls).__new__(cls)
            return cls._instance

        def transform_raw_to_visual(self, raw_mouse_pos: tuple[int, int], ratio) -> tuple[int, int]:
            """On non-Windows systems, this is a no-op."""
            return raw_mouse_pos

magpie_manager = MagpieManager()
