import logging
import re
from typing import List, Optional

import numpy as np
from PIL import Image

# Import the MeikiOCR library
from meikiocr import MeikiOCR

# Import the "contract" classes from your application's interface
from src.ocr.interface import BoundingBox, OcrProvider, Paragraph, Word
from src.ocr.providers.postprocessing import group_lines_into_paragraphs

logger = logging.getLogger(__name__)

# --- pipeline configuration ---
# These thresholds are passed to the library's run_ocr method.
DET_CONFIDENCE_THRESHOLD = 0.5
REC_CONFIDENCE_THRESHOLD = 0.1

JAPANESE_REGEX = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]')


class MeikiOcrProvider(OcrProvider):
    """
    An OCR provider that uses the high-performance meikiocr library.
    This provider is specifically optimized for recognizing Japanese text from video games.
    """
    NAME = "meikiocr (local)"

    def __init__(self):
        """
        Initializes the provider by creating an instance of the MeikiOCR client.
        The library handles the model downloading and session management internally.
        """
        logger.info(f"initializing {self.NAME} provider...")
        self.ocr_client = None
        try:
            self.ocr_client = MeikiOCR()
            logger.info(f"{self.NAME} initialized successfully, running on: {self.ocr_client.active_provider}")

        except Exception as e:
            logger.error(f"failed to initialize {self.NAME}: {e}", exc_info=True)

    def scan(self, image: Image.Image) -> Optional[List[Paragraph]]:
        """
        Performs OCR on the given image by calling the meikiocr library.
        """
        if not self.ocr_client:
            logger.error(f"{self.NAME} was not initialized correctly. Cannot perform scan.")
            return None

        try:
            image_np_rgb = np.array(image.convert("RGB"))
            img_height, img_width = image_np_rgb.shape[:2]

            if img_width == 0 or img_height == 0:
                logger.error("invalid image dimensions received.")
                return None

            # --- 1. Run the entire OCR pipeline with a single library call ---
            ocr_results = self.ocr_client.run_ocr(
                image_np_rgb,
                det_threshold=DET_CONFIDENCE_THRESHOLD,
                rec_threshold=REC_CONFIDENCE_THRESHOLD,
                punct_conf_factor=0.2
            )

            # --- 2. Transform the library's output to MeikiPop's format ---
            return self._to_meikipop_paragraphs(ocr_results, img_width, img_height)

        except Exception as e:
            logger.error(f"an error occurred in {self.NAME}: {e}", exc_info=True)
            return None  # returning none indicates a failure.

    def _to_normalized_bbox(self, bbox_pixels: list, img_width: int, img_height: int) -> BoundingBox:
        """converts an [x1, y1, x2, y2] pixel bbox to a normalized meikipop BoundingBox."""
        x1, y1, x2, y2 = bbox_pixels
        box_w, box_h = x2 - x1, y2 - y1

        center_x = (x1 + box_w / 2) / img_width
        center_y = (y1 + box_h / 2) / img_height
        norm_w = box_w / img_width
        norm_h = box_h / img_height

        return BoundingBox(center_x, center_y, norm_w, norm_h)

    def _to_meikipop_paragraphs(self, ocr_results: list, img_width: int, img_height: int) -> List[Paragraph]:
        """converts the final meikiocr result list into meikipop's Paragraph format."""
        lines: List[Paragraph] = []
        for line_result in ocr_results:
            full_text = line_result.get("text", "").strip()
            chars = line_result.get("chars", [])
            if not full_text or not chars or not JAPANESE_REGEX.search(full_text):
                continue

            # create word objects for each character (best for precise lookups).
            words_in_line: List[Word] = []
            for char_info in chars:
                char_box = self._to_normalized_bbox(char_info['bbox'], img_width, img_height)
                words_in_line.append(Word(text=char_info['char'], separator="", box=char_box))

            # meikiocr doesn't provide a line-level box, so we must compute it
            # by finding the union of all character boxes in the line.
            min_x = min(c['bbox'][0] for c in chars)
            min_y = min(c['bbox'][1] for c in chars)
            max_x = max(c['bbox'][2] for c in chars)
            max_y = max(c['bbox'][3] for c in chars)
            line_box = self._to_normalized_bbox([min_x, min_y, max_x, max_y], img_width, img_height)

            line = Paragraph(
                full_text=full_text,
                words=words_in_line,
                box=line_box,
                is_vertical=line_box.width * 1.5 < line_box.height
            )
            lines.append(line)

        return group_lines_into_paragraphs(lines)
