# meikipop/ocr/providers/mida_vocr6/vocr_onnx.py
"""The VOCR6 line recognizer on ONNX Runtime: the recognizer path of vita-vn-ocr's `tools/vocr_onnx.py` (GPL-3.0-or-later),
trimmed to what this provider uses (no spotter, no character LM, no confidences). Unchanged except cells():

- preprocess(): runtime/vocr.c's line preprocessing: integer luma (77 R + 150 G + 29 B) >> 8, 255 - grey for dark text,
  OpenCV INTER_LINEAR's fixed-point resize to the model's height, right pad to a multiple of 8 by repeating the last column
- spans(): greedy CTC (blank 0)
- cells(): each character's cell along the line, after runtime/vocr_charbox.c but with its own calibration (see CHARBOX_CAL)
- line_dark(): runtime/vocr.c's check for dark text on a light background
"""
import json
from dataclasses import dataclass
from typing import List

import numpy as np
import onnxruntime as ort

F32 = np.float32
FORMAT = 1


def _meta(sess):
    raw = sess.get_modelmeta().custom_metadata_map
    out = {}
    for k, v in raw.items():
        try:
            out[k] = json.loads(v)
        except ValueError:
            out[k] = v
    if out.get("vocr.format") != FORMAT:
        raise ValueError(f"not a vocr ONNX file of format {FORMAT} (vocr.format {out.get('vocr.format')!r})")
    return out


def grey_of(img):
    """uint8 grey of an H x W grey or H x W x 3/4 RGB(A) image: (77 R + 150 G + 29 B) >> 8, as the C side."""
    a = np.asarray(img)
    if a.dtype != np.uint8:
        raise TypeError(f"images are uint8, not {a.dtype}")
    if a.ndim == 2:
        return a
    if a.ndim == 3 and a.shape[2] in (3, 4):
        r, g, b = (a[..., i].astype(np.uint16) for i in range(3))
        return ((77 * r + 150 * g + 29 * b) >> 8).astype(np.uint8)
    raise ValueError("an H x W grey or H x W x 3 / 4 RGB(A) image")


def resized_width(w, h, height=32, max_width=1024, min_width=8):
    """vocr_resized_width(): round(w * height / h), half to even, clamped to [min_width, max_width]."""
    num = w * height
    q = (2 * num + h) // (2 * h)
    if (2 * num + h) % (2 * h) == 0 and q & 1:
        q -= 1
    return max(min_width, min(max_width, q))


def _coef(n_out, n_in):
    """runtime/vocr.c row_table / col_coef for an n_in -> n_out resize: per output index (i0, i1, a0, a1), the two
    source indices and their 11-bit weights, from the same double / float arithmetic as OpenCV's INTER_LINEAR."""
    scale = 1.0 / (float(n_out) / float(n_in))
    t = (np.arange(n_out, dtype=np.float64) + 0.5) * scale
    f = (t - 0.5).astype(F32)
    s = f.astype(np.int64)  # (int) truncates; floor for negatives below
    s = np.where(s.astype(F32) > f, s - 1, s)
    f = (f - s.astype(F32)).astype(F32)
    return s, f


def _round_even(v):
    return np.rint(v).astype(np.int64)  # v >= 0, float32: cvRound's half to even


def preprocess(img, invert=False, height=32, stride=8, max_width=1024):
    """(the network's input, H x padded width uint8; the resized width nw) for a line crop, as vocr_run() sees it."""
    g = grey_of(img)
    h, w = g.shape
    if not h or not w or h > 65535 or w > 65535:
        raise ValueError("an empty or oversized crop")
    if invert:
        g = 255 - g
    nw = resized_width(w, h, height, max_width)
    padded = (nw + stride - 1) // stride * stride
    sy, fy = _coef(height, h)
    r0 = np.clip(sy, 0, h - 1)
    r1 = np.clip(sy + 1, 0, h - 1)
    b0 = _round_even(((F32(1) - fy) * F32(2048)).astype(F32))
    b1 = _round_even((fy * F32(2048)).astype(F32))
    sx, fx = _coef(nw, w)
    low = sx < 0
    fx = np.where(low, F32(0), fx).astype(F32)
    sx = np.where(low, 0, sx)
    high = sx >= w - 1
    fx = np.where(high, F32(0), fx).astype(F32)
    sx = np.where(high, w - 1, sx)
    a0 = _round_even(((F32(1) - fx) * F32(2048)).astype(F32))
    a1 = _round_even((fx * F32(2048)).astype(F32))
    s1 = np.where(sx + 1 < w, sx + 1, sx)
    cols = np.minimum(np.arange(padded), nw - 1)  # the pad repeats the last resized column
    sx, s1, a0, a1 = sx[cols], s1[cols], a0[cols], a1[cols]
    gi = g.astype(np.int64)
    p0, p1 = gi[r0], gi[r1]  # [height, w]
    h0 = p0[:, sx] * a0[None, :] + p0[:, s1] * a1[None, :]
    h1 = p1[:, sx] * a0[None, :] + p1[:, s1] * a1[None, :]
    out = (((b0[:, None] * (h0 >> 4)) >> 16) + ((b1[:, None] * (h1 >> 4)) >> 16) + 2) >> 2
    return out.astype(np.uint8), nw


def spans(best):
    """[(class, f0, f1)]: the greedy characters, each with its run of frames."""
    out, last = [], 0
    for t, c in enumerate(np.asarray(best, np.int64).tolist()):
        if c and c != last:
            out.append([c, t, t])
        elif c and c == last:
            out[-1][2] = t
        last = c
    return [tuple(s) for s in out]


# eval/charbox.py's calibration groups
_CLOSE = "、。，．」』）】〉》〕｝］〙〗”’"
_OPEN = "「『（【〈《〔｛［〘〖“‘"
_DOTS = "…‥・"
_SMALL = "ぁぃぅぇぉっゃゅょゎゕゖァィゥェォッャュョヮヵヶㇰㇱㇲㇳㇴㇵㇶㇷㇸㇹㇺㇻㇼㇽㇾㇿ"
_LONG = "ー―─～〜－"
_MARK = "！？♪☆★♥♡※"
Q = 16  # charbox fixed point: 1/16 px


def char_group(ch):
    """eval/charbox.py group(): 0 other, 1 close, 2 open, 3 dots, 4 small, 5 long, 6 mark, 7 half."""
    if len(ch) != 1:
        return 0
    for g, s in ((1, _CLOSE), (2, _OPEN), (3, _DOTS), (4, _SMALL), (5, _LONG), (6, _MARK)):
        if ch in s:
            return g
    o = ord(ch)
    return 7 if o < 0x80 or 0xFF61 <= o <= 0xFF9F else 0


def _div_round(a, b):
    return (a + b // 2) // b if a >= 0 else -((-a + b // 2) // b)


# Offsets in 1/16 resized px: [all characters, then one per char_group]. The model's own table (-36, 0, -12, 4, 38, -16,
# -10, 0, 8) was fit on VOCR5-L and left cells ~0.45 frames (11% of a character, up to half) too far right on VOCR6.2-L.
# Refit on 13.8k characters of synthetic text (5 fonts, 720p-4K): the bias is the same for every font, size and
# resolution. Groups with too little data (open brackets, dots, half-width) keep the model's value.
CHARBOX_CAL = [-107, 0, 183, 4, 38, 7, -4, 44, 8]


def cells(sp, w, h, nw, groups, stride=8):
    """Per greedy character (centre, x0, x1) in 1/16 crop px along the line: the centre is the middle of the character's
    frames plus CHARBOX_CAL, the cell runs halfway to its neighbours' centres (the ends by half the median pitch)."""
    n = len(sp)
    if not n:
        return []
    c = []
    for cls, f0, f1 in sp:
        r = Q * stride * (f0 + f1 + 1) // 2 + CHARBOX_CAL[0] + CHARBOX_CAL[1 + groups[cls]]
        c.append(min(max(_div_round(r * w, nw), 0), w * Q))
    d = sorted(c[i + 1] - c[i] for i in range(n - 1))
    pitch = d[(len(d) - 1) // 2] if d else h * Q
    if pitch <= 0:
        pitch = h * Q
    cuts = [_div_round(c[i] + c[i + 1], 2) for i in range(n - 1)]
    lo = [max(0, c[0] - pitch // 2)] + cuts
    hi = cuts + [min(w * Q, c[-1] + pitch // 2)]
    return [(c[i], lo[i], max(lo[i], hi[i])) for i in range(n)]


@dataclass
class Char:
    text: str
    x0: float  # its cell [x0, x1) along the line, in crop px
    x1: float


class Recognizer:
    def __init__(self, path, session_options):
        self.sess = ort.InferenceSession(str(path), session_options, providers=["CPUExecutionProvider"])
        meta = _meta(self.sess)
        if meta["vocr.kind"] != "recognizer":
            raise ValueError(f"{path}: not a recognizer")
        self.vocab = meta["vocr.vocab"]
        self.height, self.stride, self.max_width = meta["vocr.height"], meta["vocr.stride"], meta["vocr.max_width"]
        self.groups = [char_group(t) for t in self.vocab]
        self.has_sections = "head_sections" in [i.name for i in self.sess.get_inputs()]

    def read(self, img: np.ndarray, invert: bool = False) -> List[Char]:
        """The characters of one line crop (H x W grey uint8; invert for dark text), each with its cell, in crop px."""
        h, w = img.shape
        x, nw = preprocess(img, invert, self.height, self.stride, self.max_width)
        feeds = {"grey": np.ascontiguousarray(x)[None, None]}
        if self.has_sections:
            feeds["head_sections"] = np.array(True)
        sp = spans(self.sess.run(["best"], feeds)[0])
        return [Char(self.vocab[cls], x0 / Q, x1 / Q)
                for (cls, _, _), (_, x0, x1) in zip(sp, cells(sp, w, h, nw, self.groups, self.stride))]


def line_dark(g: np.ndarray) -> bool:
    """True if the text in a line crop (H x W grey uint8) is darker than its background."""
    a = g.astype(np.int32)
    h, w = a.shape
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    bg = int(np.sort(border)[len(border) // 2])
    cum = np.cumsum(np.bincount(a.ravel(), minlength=256)).astype(np.int64)
    n = w * h
    lo = int(np.searchsorted(cum, n * 2 // 100, side="left"))
    hi = int(np.searchsorted(cum, n * 98 // 100, side="left"))
    d = max(16, (hi - lo) // 4)
    return int((a < bg - d).sum()) > 8 * int((a > bg + d).sum())
