# meikipop - universal japanese ocr popup dictionary

instantly look up japanese words anywhere on your screen. meikipop uses optical character recognition (ocr) to read text from websites, games, scanned manga, or even hard-coded video subtitles.

## features

*   **works everywhere:** look up text from any window, game, or video.
*   **ocr-powered:** reads japanese text directly from images.
*   **anki integration:** create beautiful flashcards with screenshots, audio, and context sentences (`Alt+A`).
*   **smart cropping:** automatically crops screenshots to the relevant text area.
*   **clipboard support:** quickly copy recognized text (`Alt+C`).
*   **blazingly fast:** optimized dictionary lookups.
*   **highly customizable:** themes, fonts, and scan regions.

## installation

### windows: prepackaged binaries
download the latest release, unpack, and run `meikipop.run.bat`.
* https://github.com/rtr46/meikipop/releases/latest

### run from source
1.  install python 3.10+
2.  clone the repo: `git clone https://github.com/rtr46/meikipop.git`
3.  install dependencies: `pip install -r requirements.txt`
4.  build dictionary: `scripts/build_dictionary.bat` (windows) or `python -m scripts.build_dictionary`
5.  run: `meikipop.run.bat` (windows) or `python -m src.main`

## how to use

1.  run the application.
2.  select a scan region (first run).
3.  hold **shift** and hover over japanese text to see the popup.
4.  **shortcuts:**
    *   `Alt+A`: add card to **Anki** (requires [AnkiConnect](https://ankiweb.net/shared/info/2055492159)).
    *   `Alt+C`: copy text to clipboard.
5.  right-click the tray icon for settings.

## anki setup

1.  install the **AnkiConnect** add-on in Anki.
2.  ensure Anki is running.
3.  meikipop will automatically create a "Meikipop Card" model on first use.
4.  customize deck/model in `config.ini` if needed.

## configuration

settings are saved to `config.ini`. right-click the tray icon to open the settings gui.

## license

meikipop is licensed under the GNU General Public License v3.0. see the `LICENSE` file for the full license text.


