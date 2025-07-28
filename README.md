# meikipop - universal japanese ocr popup dictionary

instantly look up japanese words anywhere on your screen. meikipop uses optical character recognition (ocr) to read text from websites, games, scanned manga, or even hard-coded video subtitles, giving you effortless dictionary lookups with the press of a key.


https://github.com/user-attachments/assets/6bc27de0-c01c-446c-a5c0-5e6cc6f26473


## features

*   **works everywhere:** if you can see it on your screen, you can look it up. no more limitations of browser extensions, hooks or application-specific tools.
*   **ocr-powered:** reads japanese text directly from images, making it perfect for games, comics, and videos.
*   **blazingly fast:** the dictionary is pre-processed into a highly optimized format for instant lookups. the ui is designed to be lightweight and responsive.
*   **simple & intuitive:** just point your mouse and press a hotkey. that's it.
*   **highly customizable:** change the hotkey, theme, colors, and layout to create your perfect reading experience.
*   **region or fullscreen:** scan your entire screen or select a specific region (like a game window or manga page) to improve performance.

## philosophy & limitations

meikipop is designed to do one thing and do it exceptionally well: provide fast, frictionless, on-screen dictionary lookups.

it is heavily inspired by the philosophy of [Nazeka](https://github.com/wareya/nazeka), a fantastic browser-based popup dictionary, and aims to bring that seamless experience to the entire desktop. it also draws inspiration from the ocr architecture of [owocr](https://github.com/AuroraWright/owocr/tree/master/owocr).

to maintain this focus, there are a few things meikipop is **not**:

*   **it is not an srs-mining tool.** meikipop does not include functionality to automatically create flashcards for programs like Anki.
*   **it is not a multi-dictionary tool.** while technically possible to adapt, the lookup logic is highly optimized for the structure and tags of the JMdict dictionary.

## installation

1.  **prerequisites:**
    *   Python 3.8+

2.  **download the latest release that includes a prebuilt dictionary:**
    * https://github.com/rtr46/meikipop/releases

3.  **install python dependencies and run:**
    ```bash
    pip install -r requirements.txt
    python main.py
    ```

## how to use

1.  run the application (`python main.py`). an icon will appear in your system tray.
2.  the first time you run the app in `region` mode, you will be prompted to select an area of your screen to scan (the scanned area will be send to google ocr).
3.  move your mouse over any japanese text on your screen.
4.  **press and hold the hotkey** (**shift** by default). a popup with dictionary entries will appear.
5.  keep holding the key and move your mouse to look up any additional words.
6.  release the hotkey to hide the popup.
7.  **right-click the system tray icon** to open the settings, reselect the scan region, change to full screen mode or quit the application.

## configuration

you can fully customize meikipop's behavior and appearance. right-click the tray icon and choose "settings" to open the configuration gui.

changes are saved to `config.ini` in the same folder as the application.

## building your own dictionary

if you want to build your own dictionary follow the instructions here to generate *.json files for your dictionary: [Nazeka](https://github.com/wareya/nazeka)
put those *.json files into the data folder and run
```bash
python build_dictionary.py
```

## license

meikipop is licensed under the GNU General Public License v3.0. see the `LICENSE` file for the full license text.
