# meikipop - universal japanese ocr popup dictionary

Instantly look up Japanese words anywhere on your screen. Meikipop uses OCR to read text from websites, games, manga scans, or even hard-coded video subtitles.

## Demo

https://github.com/user-attachments/assets/51e80ccb-d484-4314-ad5f-27b65e761ec9

## About this fork

This is a friendly fork of the original project at https://github.com/rtr46/meikipop. Our fork focuses on Anki-first quality-of-life tweaks.

## What I changed

- Built-in Anki card creation with region crop and context sentence `Alt+A`.
- DeepL jump for quick translation checks `Alt+D`.
- One-tap copy of the recognized text `Alt+C`.
- Duplicate guard: we skip adding a card if the word already exists in the chosen deck/model and show a short popup message.
- Cropping (images for anki) has been made possible.

## Features from original repository by rtr46

- works everywhere: if you can see it on your screen, you can look it up. no more limitations of browser extensions, hooks or application-specific tools.
- ocr-powered: reads japanese text directly from images, making it perfect for games, comics, and videos.
- blazingly fast: the dictionary is pre-processed into a highly optimized format for instant lookups. the ui is designed to be lightweight and responsive.
- simple & intuitive: just point your mouse and press a hotkey. that's it.
- highly customizable: change the hotkey, theme, colors, and layout to create your perfect reading experience.
- region or fullscreen: scan your entire screen or select a specific region (like a game window or manga page) to improve performance.
- pluggable ocr backend: comes with a great default ocr, but allows users to integrate owocr or their own ocr engines.

## Installation

Run from source:

1. Install Python 3.10+.
2. Clone this fork: `git clone https://github.com/pnotisdev/meikipop.git`.
3. Install dependencies: `pip install -r requirements.txt`.
4. Build dictionary: `scripts/build_dictionary.bat` (Windows) or `python -m scripts.build_dictionary`.
5. Run: `meikipop.run.bat` (Windows) or `python -m src.main`.

## How to use

1. Run the app.
2. Select a scan region (first run).
3. Hold **Shift** and hover over Japanese text to see the popup.
4. Shortcuts:
   - `Alt+A`: region-select screenshot, then add to Anki (needs [AnkiConnect](https://ankiweb.net/shared/info/2055492159).
   - `Alt+C`: copy recognized text.
   - `Alt+D`: open the current context in DeepL.
5. Right-click the tray icon for settings.

## Anki setup

1. Install the **AnkiConnect** add-on in Anki.
2. Keep Anki running.
3. Meikipop will auto-create the "Meikipop Card" model on first use.
4. Customize deck/model in `config.ini` if you like.

## Configuration

Settings live in `config.ini`. Right-click the tray icon to open the settings GUI.

## License

Meikipop is licensed under the GNU General Public License v3.0. See `LICENSE` for the full text.

Original credit: https://github.com/rtr46/meikipop
