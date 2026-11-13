# meikipop/ocr/providers/mida_vocr6/provider.py
"""mida line detection + VOCR6.2-L recognition, fully local on the CPU (the "mida + L" arm of
https://github.com/bee-san/vita-vn-ocr, docs/desktop.md).

mida finds the horizontal text lines; each is cut from the full-resolution screenshot (dark text is inverted, as the
recognizer was trained) and read by VOCR6 (greedy CTC), which returns every character with its own cell along the line.
Vertical text is not supported: use the meikiocr provider for it.
"""
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple

import numpy as np
import onnxruntime as ort
from PIL import Image

from meikipop.ocr.interface import BoundingBox, OcrProvider, Paragraph, Word
from meikipop.ocr.providers.postprocessing import group_lines_into_paragraphs
from . import models
from . import vocr_onnx as V
from .mida_detector import MidaDetector

logger = logging.getLogger(__name__)

JAPANESE_REGEX = re.compile(r'[぀-ゟ゠-ヿ一-龯]')

THREADS = min(4,
              os.cpu_count() or 1)  # detector threads, and lines read in parallel (4 was the fastest in vita-vn-ocr's timings)


class MidaVocr6Provider(OcrProvider):
    NAME = "mida + VOCR6 (local)"

    def __init__(self):
        logger.info(f"initializing {self.NAME} provider...")
        mida_path = models.ensure_mida()  # downloads on first use
        vocr_path = models.ensure_vocr()  # downloads on first use
        self.detector = MidaDetector(mida_path, threads=THREADS)

        so = ort.SessionOptions()
        so.intra_op_num_threads = so.inter_op_num_threads = 1  # parallelism is across lines
        so.log_severity_level = 3
        so.add_session_config_entry("session.intra_op.allow_spinning", "0")
        self.recognizer = V.Recognizer(vocr_path, so)
        self._pool = ThreadPoolExecutor(max_workers=THREADS, thread_name_prefix="vocr6-line")
        logger.info(f"{self.NAME} initialized with {THREADS} threads")

    def scan(self, image: Image.Image) -> Optional[List[Paragraph]]:
        try:
            rgb = np.asarray(image.convert("RGB"))
            H, W = rgb.shape[:2]
            if W == 0 or H == 0:
                logger.error("invalid image dimensions received.")
                return None

            crops = self.detector.detect(rgb)
            lines = [p for p in self._pool.map(lambda c: self._read_line(rgb, c), crops) if p is not None]
            return group_lines_into_paragraphs(lines)

        except Exception as e:
            logger.error(f"an error occurred in {self.NAME}: {e}", exc_info=True)
            return None

    def _read_line(self, rgb: np.ndarray, crop: Tuple[int, int, int, int]) -> Optional[Paragraph]:
        """Reads one line crop (x, y, w, h) into a single-line Paragraph, or None if it fails or has no Japanese."""
        x, y, w, h = crop
        try:
            grey = V.grey_of(rgb[y:y + h, x:x + w])
            chars = self.recognizer.read(grey, invert=V.line_dark(grey))
        except Exception as e:
            logger.warning(f"could not read the line at {crop}: {e}")
            return None

        # one Word per character, so hover lookups land on the right character; the cell is at least 1 px wide
        H, W = rgb.shape[:2]
        words = [Word(text=c.text, separator="", box=_norm(x + c.x0, y, x + max(c.x1, c.x0 + 1), y + h, W, H)) for c in
                 chars]
        full_text = "".join(
            c.text for c in chars)  # hit scan maps a hover position to full_text through the words' text lengths
        if not JAPANESE_REGEX.search(full_text):
            return None
        return Paragraph(full_text=full_text, words=words, box=_norm(x, y, x + w, y + h, W, H), is_vertical=False)


def _norm(x0: float, y0: float, x1: float, y1: float, W: int, H: int) -> BoundingBox:
    """A pixel box as a normalized meikipop BoundingBox (center and size, 0.0 to 1.0)."""
    return BoundingBox(center_x=(x0 + x1) / 2 / W, center_y=(y0 + y1) / 2 / H, width=(x1 - x0) / W,
                       height=(y1 - y0) / H)
