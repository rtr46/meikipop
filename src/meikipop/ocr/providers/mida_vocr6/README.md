# mida + VOCR6 (local): a meikipop OCR provider

Text detection by **mida** (`mida_ocr_l.onnx`, MeikiOCR's author's line detector) and recognition by **VOCR6.2-L**
(fast ONNX), both on the CPU: the "mida + L" arm of [vita-vn-ocr](https://github.com/bee-san/vita-vn-ocr)
(`docs/desktop.md`, issue #169). Pick **"mida + VOCR6 (local)"** in the tray menu under *OCR provider*.

## Setup

1. Copy this folder to `src/meikipop/ocr/providers/mida_vocr6/`.
2. Select the provider. The first start downloads both models into the models folder (about 4 MB, sha256-checked); after
   that it works offline:
   - `mida_ocr_l.onnx` (1.75 MB) from the author's Hugging Face repo, [rtr46/mida](https://huggingface.co/rtr46/mida)
     (`mida_l_alpha_v0.0.1.onnx`; the decode is tuned on exactly this file)
   - `VOCR6.2_L_fast.onnx` (2.5 MB) from vita-vn-ocr's pre-release `v0.5.1-onnx.2`

   The models folder is `%LOCALAPPDATA%\meikipop\models\mida_vocr6\` on Windows,
   `~/.local/share/meikipop/models/mida_vocr6/`
   on Linux, `~/Library/Application Support/meikipop/models/mida_vocr6/` on macOS, or the directory named in the
   environment
   variable `MEIKIPOP_MIDA_VOCR_DIR`. To set up offline, put the two files there yourself: a file with the right sha256
   is
   never downloaded again.

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
| `mida_ocr_l.onnx`          | downloaded at first use from the author's Hugging Face repo (rtr46/mida)                                   |
