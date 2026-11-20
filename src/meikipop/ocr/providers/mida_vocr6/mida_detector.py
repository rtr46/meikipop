# meikipop/ocr/providers/mida_vocr6/mida_detector.py
"""The MIDA line detector, decoded like mida_distribution/infer_mida.py: RGB input, aspect-preserving
downscale-only preprocessing, confidence/orientation-aware decode, raw boxes for both orientations.

The network (read from the file by vita-vn-ocr's authors): input "images" float32 (1, 3, h, w), RGB, 0-1;
output "maps" (1, 4, ceil(h/8), ceil(w/8)):
  K   line kernel logit (> 0 on a band along a line's middle)    O   orientation logit (> 0: vertical)
  A1  distance from a cell's centre to the line's near edge      A2  the same to its far edge   (stride units)

Box expansion, padding and filtering for the recognizer live in line_crops.py, not here.
"""
import math
from dataclasses import dataclass
from typing import List, Tuple

import cv2
import numpy as np
import onnxruntime as ort

STRIDE = 8


@dataclass(frozen=True)
class Line:
    """A raw detected text line in source-image pixels."""
    box: Tuple[float, float, float, float]  # x0, y0, x1, y1
    vertical: bool
    conf: float


def target_size(h: int, w: int, max_pixels: int) -> Tuple[int, int]:
    nw, nh = w, h
    if max_pixels and nw * nh > max_pixels:
        f = math.sqrt(max_pixels / float(nw * nh))
        nw, nh = max(1, int(nw * f)), max(1, int(nh * f))
        while nw * nh > max_pixels and (nw > 1 or nh > 1):
            if nw >= nh and nw > 1:
                nw -= 1
            elif nh > 1:
                nh -= 1
    return nh, nw


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def decode(maps, stride=STRIDE, img_hw=None, k_thresh=0.5, min_cells=2, min_conf=0.5,
           min_across=2.0, max_boxes=256):
    kp = sigmoid(maps[0])
    ncomp, labels = cv2.connectedComponents((kp > k_thresh).astype(np.uint8), connectivity=4)
    ncomp -= 1
    if ncomp <= 0:
        return []
    r, c = np.nonzero(labels)
    lab = labels[r, c] - 1
    cnt = np.bincount(lab, minlength=ncomp).astype(np.float64)

    def mean(v):
        return np.bincount(lab, weights=v, minlength=ncomp) / np.maximum(cnt, 1)

    conf = mean(kp[r, c])
    vert = mean(sigmoid(maps[1][r, c])) > 0.5
    ai = np.where(vert[lab], c, r)
    al = np.where(vert[lab], r, c)
    cc = stride * ai + (stride - 1) / 2.0
    near = mean(cc - maps[2][r, c] * stride)
    far = mean(cc + maps[3][r, c] * stride)
    lo = np.full(ncomp, 1 << 30)
    hi = np.full(ncomp, -1)
    np.minimum.at(lo, lab, al)
    np.maximum.at(hi, lab, al)
    a_lo = stride * lo.astype(np.float64)
    a_hi = stride * (hi + 1).astype(np.float64)
    out = []
    for i in range(ncomp):
        if cnt[i] < min_cells or conf[i] < min_conf or far[i] - near[i] < min_across:
            continue
        x0, x1, y0, y1 = (near[i], far[i], a_lo[i], a_hi[i]) if vert[i] else (a_lo[i], a_hi[i], near[i], far[i])
        if img_hw is not None:
            x0, y0 = max(0.0, x0), max(0.0, y0)
            x1, y1 = min(float(img_hw[1]), x1), min(float(img_hw[0]), y1)
        if x1 <= x0 or y1 <= y0:
            continue
        out.append(Line((float(x0), float(y0), float(x1), float(y1)), bool(vert[i]), float(conf[i])))
    out.sort(key=lambda line: -line.conf)
    return out[:max_boxes]


class MidaDetector:
    def __init__(self, model_path, threads: int = 4, max_pixels: int = 600_000, k_thresh: float = 0.5,
                 min_cells: int = 2, min_conf: float = 0.5, min_across: float = 2.0, max_boxes: int = 256):
        so = ort.SessionOptions()
        so.intra_op_num_threads = max(1, threads)
        so.inter_op_num_threads = 1
        so.log_severity_level = 3
        so.add_session_config_entry("session.intra_op.allow_spinning", "0")
        so.add_session_config_entry("session.inter_op.allow_spinning", "0")
        so.enable_mem_pattern = False
        self.sess = ort.InferenceSession(str(model_path), so, providers=["CPUExecutionProvider"])
        self.max_pixels = max_pixels
        self.k_thresh = k_thresh
        self.min_cells = min_cells
        self.min_conf = min_conf
        self.min_across = min_across
        self.max_boxes = max_boxes

    def detect(self, rgb: np.ndarray) -> List[Line]:
        """Detect horizontal and vertical text lines in an H x W x 3 RGB uint8 image."""
        h, w = rgb.shape[:2]
        nh, nw = target_size(h, w, self.max_pixels)
        im = rgb if (nh, nw) == (h, w) else cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA)
        x = np.ascontiguousarray(im.transpose(2, 0, 1)[None], np.float32) / 255.0
        maps = self.sess.run(["maps"], {"images": x})[0][0].astype(np.float64)
        lines = decode(maps, STRIDE, img_hw=(nh, nw), k_thresh=self.k_thresh, min_cells=self.min_cells,
                       min_conf=self.min_conf, min_across=self.min_across, max_boxes=self.max_boxes)
        sx, sy = nw / w, nh / h
        return [Line((line.box[0] / sx, line.box[1] / sy, line.box[2] / sx, line.box[3] / sy),
                     line.vertical, line.conf) for line in lines]
