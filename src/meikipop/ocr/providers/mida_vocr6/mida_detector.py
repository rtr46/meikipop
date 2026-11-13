# meikipop/ocr/providers/mida_vocr6/mida_detector.py
"""The mida line detector (`mida_ocr_l.onnx`; the decode is tuned on the one file pinned in models.py) on ONNX Runtime's
CPU provider, horizontal lines only.

Adapted from `eval/mida_det.py` of https://github.com/bee-san/vita-vn-ocr (GPL-3.0-or-later). The network (read from the
file by that project's authors): input "images" float32 (1, 3, h, w), BGR, 0-1; output "maps" (1, 4, ceil(h/8), ceil(w/8)):
  K   line kernel logit (> 0 on a band along a line's middle)    O   orientation logit (> 0: vertical)
  A1  distance from a cell's centre to the line's top edge       A2  the same to its bottom edge   (stride units)
Decode: 4-connected components of K > 0 with at least 2 cells; the line's top / bottom are the mean of its cells'
(centre - 8 A1) / (centre + 8 A2); left / right are the component's cells, since the kernel stops short of a line's ends.

The crop is then padded for the recognizer, which reads slightly better with some context (measured on 600 synthetic
scenes): each end grows by END_GROW x the line's height plus a small fixed pad. There is NO padding across the line:
that would make the reported boxes ~1.5x taller than the text and merge name plates into dialogue paragraphs.
"""
from typing import List, Tuple

import cv2
import numpy as np
import onnxruntime as ort

STRIDE = 8
FIT_W, FIT_H = 960, 544  # the frame is fit inside this for the network only (up or down)
MIN_CELLS = 2
END_GROW = 0.4  # each line end grows by this x the line's height
END_PAD_BASE = 4  # plus max(2, round(4 * frame height / 544)) source px


class MidaDetector:
    def __init__(self, model_path, threads: int = 4):
        so = ort.SessionOptions()
        so.intra_op_num_threads = max(1, threads)
        so.inter_op_num_threads = 1
        so.log_severity_level = 3
        so.add_session_config_entry("session.intra_op.allow_spinning", "0")  # no idle spinning in a background app
        so.add_session_config_entry("session.inter_op.allow_spinning", "0")
        so.enable_mem_pattern = False  # the input size varies per scan
        self.sess = ort.InferenceSession(str(model_path), so, providers=["CPUExecutionProvider"])

    def detect(self, rgb: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Horizontal text lines of an H x W x 3 RGB uint8 image as integer crops (x, y, w, h), top to bottom."""
        H, W = rgb.shape[:2]
        s = min(FIT_W / W, FIT_H / H)
        ch = max(1, round(H * s))
        cw = max(1, round(W * ch / H))
        img = cv2.resize(rgb, (cw, ch), interpolation=cv2.INTER_LINEAR) if (cw, ch) != (W, H) else rgb
        x = np.ascontiguousarray(img[:, :, ::-1].transpose(2, 0, 1)[None], np.float32) / 255.0  # BGR, CHW
        maps = self.sess.run(["maps"], {"images": x})[0][0].astype(np.float64)
        return self._decode(maps, cw / W, ch / H, W, H)

    @staticmethod
    def _decode(maps: np.ndarray, fx: float, fy: float, W: int, H: int) -> List[Tuple[int, int, int, int]]:
        k, o, a1, a2 = maps
        end_pad = max(2, round(END_PAD_BASE * H / 544))
        n, labels = cv2.connectedComponents((k > 0).astype(np.uint8), connectivity=4)
        crops = []
        for c in range(1, n):
            rows, cols = np.nonzero(labels == c)
            if rows.size < MIN_CELLS or o[rows, cols].sum() > 0:  # too small, or vertical (not readable)
                continue
            centre = STRIDE * rows + (STRIDE - 1) / 2
            top = np.mean(centre - STRIDE * a1[rows, cols]) / fy
            bottom = np.mean(centre + STRIDE * a2[rows, cols]) / fy
            if bottom - top < 1:
                continue
            left, right = STRIDE * cols.min() / fx, STRIDE * (cols.max() + 1) / fx
            grow = END_GROW * (bottom - top) * fy / fx + end_pad  # END_GROW x the line's height, in source px
            x0, x1 = max(0, int(np.floor(left - grow))), min(W, int(np.ceil(right + grow)))
            y0, y1 = max(0, int(np.floor(top))), min(H, int(np.ceil(bottom)))
            if x1 > x0 and y1 > y0:
                crops.append((x0, y0, x1 - x0, y1 - y0))
        return sorted(crops, key=lambda c: (c[1], c[0]))
