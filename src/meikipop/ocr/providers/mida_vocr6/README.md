# mida + VOCR6 (local): a meikipop OCR provider

Text detection by **mida** (`mida_ocr_l.onnx`, MeikiOCR's author's line detector) and recognition by **VOCR6.2-L**
(fast ONNX), both on the CPU: the "mida + L" arm of [vita-vn-ocr](https://github.com/bee-san/vita-vn-ocr)
(`docs/desktop.md`, issue #169). Pick **"mida + VOCR6 (local)"** in the tray menu under *OCR provider*.

## Setup

1. Copy this folder to `src/meikipop/ocr/providers/mida_vocr6/`.
2. Put **`mida_ocr_l.onnx`** in the models folder (the log names the exact path if it is missing):
    - Windows `%LOCALAPPDATA%\meikipop\models\mida_vocr6\`
    - Linux `~/.local/share/meikipop/models/mida_vocr6/`
    - macOS `~/Library/Application Support/meikipop/models/mida_vocr6/`
    - or any directory named in the environment variable `MEIKIPOP_MIDA_VOCR_DIR`

   Only the file with sha256 `9f72bce5...8aed` is accepted: the decode was tuned on it.
3. Select the provider. The first start downloads `VOCR6.2_L_fast.onnx` (2.5 MB, sha256-checked) from vita-vn-ocr's
   pre-release `v0.5.1-onnx.2` into the same folder; after that it works offline.

No new dependencies (`numpy`, `opencv`, `onnxruntime`, `Pillow`, `platformdirs` come with meikipop / meikiocr).
Tested on onnxruntime 1.20.1 (what meikipop pins on Windows) and 1.29.

## How it works

1. mida finds the horizontal text lines (the screenshot is fit into 960x544 for the network only).
2. Each line is cut from the **full-resolution** screenshot, padded a little at its two ends (never across the line:
   boxes stay as tall as the text, so name plates and dialogue stay separate paragraphs), and read by VOCR6.
3. Every character becomes one `Word` with its own cell (VOCR6's own cell calibration was refit, see `CHARBOX_CAL` in
   `vocr_onnx.py`: the shipped one left cells about 11% of a character too far right), so the hover lookup lands on the
   right character; then
   meikipop's usual grouping into paragraphs and furigana separation. Lines without kana or kanji are dropped.

## Limits

- **No vertical text** (VOCR6's recognizer is horizontal): use the meikiocr provider for vertical games.
- No Japanese, no result: English-only UI text does not show.
- vita-vn-ocr measured this combination as more accurate than textspot8 on PC screenshots and faster than MeikiOCR's
  detector, but less accurate than MeikiOCR's detector + VOCR6 (1.38% vs 0.70% dialogue CER on their PC test set;
  their numbers). Old low-resolution games were the weakest.
- Packaged (PyInstaller) builds list providers in the `.spec` files: add this package's files there.
- Threads: `THREADS` at the top of `provider.py` (up to 4).

## Files and licences

| file                       | origin                                                                                                     |
|----------------------------|------------------------------------------------------------------------------------------------------------|
| `provider.py`, `models.py` | this provider                                                                                              |
| `mida_detector.py`         | decode ported from vita-vn-ocr's `eval/mida_det.py` (GPL-3.0-or-later)                                     |
| `vocr_onnx.py`             | vita-vn-ocr's `tools/vocr_onnx.py` (GPL-3.0-or-later), recognizer path only, with a refit cell calibration |
| `VOCR6.2_L_fast.onnx`      | downloaded at first use. **Non-commercial use only** (see the release's `VOCR6-ATTRIBUTION.md`)            |
| `mida_ocr_l.onnx`          | yours. Its licence is not stated by its author, so it is neither bundled nor downloaded                    |
