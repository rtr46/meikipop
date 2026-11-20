# meikipop/ocr/providers/mida_vocr6/line_crops.py
"""The MIDA -> VOCR6 mid-processing: turn raw detector lines into recognizer crops.

Kept separate from the detector so the expansion/filter parameters can be swept independently, and so
horizontal and vertical text can use different settings. Vertical crops are rotated anticlockwise for the
vertical recognizer; cell coordinates are mapped back to the original image here as well.
"""
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

from .mida_detector import Line

PixelBox = Tuple[float, float, float, float]


@dataclass(frozen=True)
class CropConfig:
    end_grow: float = 0.0
    end_pad: float = 0.0
    across_grow: float = 0.0
    across_pad: float = 0.0
    min_conf: float = 0.0
    min_len: float = 0.0
    min_thickness: float = 0.0
    end_before_pad: float = 0.0
    end_after_pad: float = 0.0
    across_before_pad: float = 0.0
    across_after_pad: float = 0.0
    shift: float = 0.0
    pad_to_thickness: float = 0.0

    @property
    def name(self) -> str:
        return (f"end={self.end_grow:g}/{self.end_pad:g}+({self.end_before_pad:g},{self.end_after_pad:g}) "
                f"across={self.across_grow:g}/{self.across_pad:g}+({self.across_before_pad:g},"
                f"{self.across_after_pad:g}) shift={self.shift:g} pad={self.pad_to_thickness:g} "
                f"conf>={self.min_conf:g} len>={self.min_len:g} thick>={self.min_thickness:g}")


DEFAULT_H = CropConfig(end_grow=0.4, end_pad=4.0, min_conf=0.5, min_len=12.0, min_thickness=4.0)
DEFAULT_V = CropConfig(end_grow=0.15, end_pad=4.0, across_grow=0.2, shift=2.0, min_conf=0.5, min_len=12.0,
                       min_thickness=4.0)


@dataclass(frozen=True)
class LineCrop:
    box: Tuple[int, int, int, int]
    vertical: bool
    conf: float
    line_box: PixelBox

    @property
    def width(self) -> int:
        return self.box[2] - self.box[0]

    @property
    def height(self) -> int:
        return self.box[3] - self.box[1]


def make_crop(line: Line, cfg: CropConfig, img_w: int, img_h: int) -> LineCrop | None:
    x0, y0, x1, y1 = line.box
    length, thickness = ((x1 - x0, y1 - y0) if not line.vertical else (y1 - y0, x1 - x0))
    if line.conf < cfg.min_conf or length < cfg.min_len or thickness < cfg.min_thickness:
        return None
    end = cfg.end_grow * thickness + cfg.end_pad
    across = cfg.across_grow * thickness + cfg.across_pad
    if cfg.pad_to_thickness > thickness:
        across += (cfg.pad_to_thickness - thickness) / 2
    if line.vertical:
        x0, x1 = x0 - across - cfg.across_before_pad + cfg.shift, x1 + across + cfg.across_after_pad + cfg.shift
        y0, y1 = y0 - end - cfg.end_before_pad, y1 + end + cfg.end_after_pad
    else:
        x0, x1 = x0 - end - cfg.end_before_pad, x1 + end + cfg.end_after_pad
        y0, y1 = y0 - across - cfg.across_before_pad + cfg.shift, y1 + across + cfg.across_after_pad + cfg.shift
    x0, y0 = max(0, int(np.floor(x0))), max(0, int(np.floor(y0)))
    x1, y1 = min(img_w, int(np.ceil(x1))), min(img_h, int(np.ceil(y1)))
    if x1 <= x0 or y1 <= y0:
        return None
    return LineCrop((x0, y0, x1, y1), line.vertical, line.conf, line.box)


def make_crops(lines: List[Line], cfg_h: CropConfig, cfg_v: CropConfig,
               img_w: int, img_h: int) -> List[LineCrop]:
    crops = [make_crop(line, cfg_v if line.vertical else cfg_h, img_w, img_h) for line in lines]
    return [crop for crop in crops if crop is not None]


def crop_image(rgb: np.ndarray, crop: LineCrop) -> np.ndarray:
    x0, y0, x1, y1 = crop.box
    part = rgb[y0:y1, x0:x1]
    return np.ascontiguousarray(np.rot90(part, 1)) if crop.vertical else part


def cell_boxes(crop: LineCrop, cells: List[Tuple[float, float]]) -> List[PixelBox]:
    """Character cells along the recognizer's crop -> pixel boxes in the original image."""
    x0, y0, x1, y1 = crop.box
    if crop.vertical:
        return [(float(x0), y0 + a, float(x1), y0 + b) for a, b in cells]
    return [(x0 + a, float(y0), x0 + b, float(y1)) for a, b in cells]
