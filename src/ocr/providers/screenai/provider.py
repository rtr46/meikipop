import ctypes
import logging
import os
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import List, Optional

from PIL import Image
from .chrome_screen_ai_pb2 import VisualAnnotation

from src.ocr.interface import OcrProvider, Paragraph, Word, BoundingBox
from src.ocr.providers.postprocessing import group_lines_into_paragraphs

JAPANESE_REGEX = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]')

logger = logging.getLogger(__name__)


@contextmanager
def suppress_output():
    """Redirects C/C++ level stdout and stderr to devnull to suppress native library spam."""
    devnull = os.open(os.devnull, os.O_WRONLY)
    original_stdout = os.dup(1)
    original_stderr = os.dup(2)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    try:
        yield
    finally:
        os.dup2(original_stdout, 1)
        os.dup2(original_stderr, 2)
        os.close(original_stdout)
        os.close(original_stderr)
        os.close(devnull)


class ScreenAiOcr(OcrProvider):
    NAME = "Chrome Screen AI (local)"

    # Class-level variables to ensure the native DLL is only initialized ONCE per app lifetime
    _is_initialized = False
    _lib = None
    _SkBitmap = None
    _cb1 = None
    _cb2 = None

    def __init__(self):
        base_dir = Path.home() / ".config" / "screen_ai"
        self.model_dir = base_dir / "resources"

        dll_name = 'chrome_screen_ai.dll' if sys.platform == 'win32' else 'libchromescreenai.so'
        self.dll_path = self.model_dir / dll_name

        if not self.dll_path.exists():
            # Provide helpful instructions before failing
            logger.error(
                f"Please download the screenai component from this link and extract it to the {base_dir} folder:\n"
                f"https://chrome-infra-packages.appspot.com/p/chromium/third_party/screen-ai"
            )
            raise RuntimeError("Screen AI components missing.")

        self._initialize_library()

    def _initialize_library(self):
        # If already initialized by a previous instance, reuse the loaded lib and exit
        if ScreenAiOcr._is_initialized:
            self.lib = ScreenAiOcr._lib
            self.SkBitmap = ScreenAiOcr._SkBitmap
            return

        class SkColorInfo(ctypes.Structure):
            _fields_ = [('fColorSpace', ctypes.c_void_p), ('fColorType', ctypes.c_int32),
                        ('fAlphaType', ctypes.c_int32)]

        class SkISize(ctypes.Structure):
            _fields_ = [('fWidth', ctypes.c_int32), ('fHeight', ctypes.c_int32)]

        class SkImageInfo(ctypes.Structure):
            _fields_ = [('fColorInfo', SkColorInfo), ('fDimensions', SkISize)]

        class SkPixmap(ctypes.Structure):
            _fields_ = [('fPixels', ctypes.c_void_p), ('fRowBytes', ctypes.c_size_t), ('fInfo', SkImageInfo)]

        class SkBitmap(ctypes.Structure):
            _fields_ = [('fPixelRef', ctypes.c_void_p), ('fPixmap', SkPixmap), ('fFlags', ctypes.c_uint32)]

        self.SkBitmap = SkBitmap
        self.lib = ctypes.CDLL(str(self.dll_path))

        @ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_char_p)
        def get_file_content_size(p):
            path = self.model_dir / p.decode('utf-8')
            return os.path.getsize(path) if path.exists() else 0

        @ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_uint32, ctypes.c_void_p)
        def get_file_content(p, s, ptr):
            path = self.model_dir / p.decode('utf-8')
            if path.exists():
                with open(path, 'rb') as f:
                    ctypes.memmove(ptr, f.read(s), s)

        # Store callbacks at the class level so Python's Garbage Collector doesn't delete them
        ScreenAiOcr._cb1 = get_file_content_size
        ScreenAiOcr._cb2 = get_file_content

        self.lib.SetFileContentFunctions.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.lib.InitOCRUsingCallback.restype = ctypes.c_bool
        self.lib.SetOCRLightMode.argtypes = [ctypes.c_bool]
        self.lib.PerformOCR.argtypes = [ctypes.POINTER(SkBitmap), ctypes.POINTER(ctypes.c_uint32)]
        self.lib.PerformOCR.restype = ctypes.c_void_p
        self.lib.FreeLibraryAllocatedCharArray.argtypes = [ctypes.c_void_p]

        # Suppress the initialization logs
        with suppress_output():
            self.lib.SetFileContentFunctions(ScreenAiOcr._cb1, ScreenAiOcr._cb2)
            if not self.lib.InitOCRUsingCallback():
                raise RuntimeError("InitOCRUsingCallback failed.")
            self.lib.SetOCRLightMode(False)
            time.sleep(0.5)

        # Mark as globally initialized
        ScreenAiOcr._lib = self.lib
        ScreenAiOcr._SkBitmap = self.SkBitmap
        ScreenAiOcr._is_initialized = True

    def scan(self, image: Image.Image) -> Optional[List[Paragraph]]:
        try:
            if image.width * image.height > 4000000:
                image.thumbnail((2000, 2000), Image.Resampling.LANCZOS)

            img_rgba = image.convert('RGBA')
            width, height = img_rgba.size
            img_bytes = img_rgba.tobytes()

            bitmap = self.SkBitmap()
            bitmap.fPixmap.fPixels = ctypes.cast(ctypes.c_char_p(img_bytes), ctypes.c_void_p)
            bitmap.fPixmap.fRowBytes = width * 4
            bitmap.fPixmap.fInfo.fColorInfo.fColorType = 4  # kRGBA_8888
            bitmap.fPixmap.fInfo.fColorInfo.fAlphaType = 1  # kPremul
            bitmap.fPixmap.fInfo.fDimensions.fWidth = width
            bitmap.fPixmap.fInfo.fDimensions.fHeight = height

            output_length = ctypes.c_uint32(0)

            # Suppress the heavy console spam during the actual OCR process
            with suppress_output():
                result_ptr = self.lib.PerformOCR(ctypes.byref(bitmap), ctypes.byref(output_length))

            if not result_ptr:
                return []

            proto_bytes = ctypes.string_at(result_ptr, output_length.value)
            self.lib.FreeLibraryAllocatedCharArray(result_ptr)

            response = VisualAnnotation()
            response.ParseFromString(proto_bytes)

            return self._transform(response, width, height)

        except Exception as e:
            logger.error(f"{self.NAME} error: {e}", exc_info=True)
            return None

    def _transform(self, response: VisualAnnotation, img_w: int, img_h: int) -> List[Paragraph]:
        raw_lines = []
        for line_box in response.lines:
            line_has_japanese = any(JAPANESE_REGEX.search(w.utf8_string) for w in line_box.words)
            if not line_has_japanese:
                continue
            r = line_box.bounding_box
            line_bbox = BoundingBox(
                center_x=(r.x + r.width / 2) / img_w,
                center_y=(r.y + r.height / 2) / img_h,
                width=r.width / img_w,
                height=r.height / img_h
            )

            is_vertical = (line_box.direction == 3)  # DIRECTION_TOP_TO_BOTTOM

            meiki_words = []

            for word_box in line_box.words:
                for symbol in word_box.symbols:
                    wr = symbol.bounding_box
                    w_bbox = BoundingBox(
                        center_x=(wr.x + wr.width / 2) / img_w,
                        center_y=(wr.y + wr.height / 2) / img_h,
                        width=wr.width / img_w,
                        height=wr.height / img_h
                    )
                    meiki_words.append(Word(
                        text=symbol.utf8_string,
                        separator='',
                        box=w_bbox
                    ))

            raw_lines.append(Paragraph(
                full_text=line_box.utf8_string,
                words=meiki_words,
                box=line_bbox,
                is_vertical=is_vertical
            ))

        return group_lines_into_paragraphs(raw_lines)
