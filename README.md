# meikipop - universal japanese ocr popup dictionary

instantly look up japanese words anywhere on your screen. meikipop uses optical character recognition (ocr) to read text from websites, games, scanned manga, or even hard-coded video subtitles, giving you effortless dictionary lookups with the press of a key (or even without)!

https://github.com/user-attachments/assets/a1834197-3059-438c-a2dc-716e8ec9078f

https://github.com/user-attachments/assets/ad0fa0ce-0f5f-4d1d-a99b-22e67e5fb80b



## features

*   **works everywhere:** if you can see it on your screen, you can look it up. no more limitations of browser extensions, hooks or application-specific tools.
*   **ocr-powered:** reads japanese text directly from images, making it perfect for games, comics, and videos.
*   **blazingly fast:** the dictionary is pre-processed into a highly optimized format for instant lookups. the ui is designed to be lightweight and responsive.
*   **simple & intuitive:** just point your mouse and press a hotkey. that's it.
*   **highly customizable:** change the hotkey, theme, colors, and layout to create your perfect reading experience.
*   **region or fullscreen:** scan your entire screen or select a specific region (like a game window or manga page) to improve performance.
* **pluggable ocr backend:** comes with a great default OCR, but allows advanced users to integrate their own OCR
  engines.

## philosophy & limitations

meikipop is designed to do one thing and do it exceptionally well: provide fast, frictionless, on-screen dictionary lookups.

it is heavily inspired by the philosophy of [Nazeka](https://github.com/wareya/nazeka), a fantastic browser-based popup dictionary, and aims to bring that seamless experience to the entire desktop. it also draws inspiration from the ocr architecture of [owocr](https://github.com/AuroraWright/owocr/tree/master/owocr).

to maintain this focus, there are a few things meikipop is **not**:

*   **it is not an srs-mining tool.** meikipop does not include functionality to automatically create flashcards for programs like Anki.
*   **it is not a multi-dictionary tool.** while technically possible to adapt, the lookup logic is highly optimized for the structure and tags of the JMdict dictionary.

## installation

### windows: meikipop.exe

this is the easiest way to run meikipop on windows and recommended for most windows user: https://github.com/rtr46/meikipop/releases

### windows + linux: bundled source + dict

1.  **prerequisites:**
    * python 3.10+

2.  **download the latest release that includes a prebuilt dictionary:**
    * https://github.com/rtr46/meikipop/releases

3.  **install python dependencies and run:**
    ```bash
    pip install -r requirements.txt
    python -m src.main # alternatively run the meiki.bat or meiki.sh
    ```

### macos (beta): bundled source + dict

note that meikipop is in beta for macos. it is lacking the tray and therefore the settings menu and a few options. you should be able to configure meikipop through the config.ini though. if you notice meikipop breaking with a new release, feel free to let us know via an issue and we will try to fix it. 

1.  **prerequisites:**
    * python 3.10+
  
2. **set required permissions**
    * go to **System Preferences** > **Security & Privacy** > **Privacy**
    * add/enable your terminal app in **Input Monitoring**, **Screen Recording** and **Accessibility**

3.  **download the latest release that includes a prebuilt dictionary:**
    * https://github.com/rtr46/meikipop/releases

4.  **install python dependencies and run:**
    ```bash
    pip install -r requirements.txt
    python -m src.main # alternatively run the meikipop.sh
    ```

## how to use

1.  run the application (`python -m src.main`). an icon will appear in your system tray.
2.  the first time you run the app in `region` mode, you will be prompted to select an area of your screen to scan (the scanned area will be send to google ocr).
3.  move your mouse over any japanese text on your screen.
4.  **press and hold the hotkey** (**shift** by default). a popup with dictionary entries will appear. depending on your internet connection this may take a while the first time...
5.  keep holding the key and move your mouse to look up any additional words.
6.  release the hotkey to hide the popup.
7.  **right-click the system tray icon** to open the settings, reselect the scan region, change to full screen mode or quit the application.
8.  make sure you try the **auto scan mode**. it continuously scans your screen to provide you with dictionary entries as fast as possible and without the need to press a hotkey.

## configuration

you can fully customize meikipop's behavior and appearance. right-click the tray icon and choose "settings" to open the configuration gui.

changes are saved to `config.ini` in the same folder as the application.

## extending with a custom ocr provider

meikipop's architecture allows you to replace the default ocr engine with one of your own. this is an advanced feature
for users who may want to use a local, offline ocr model or a different online service.

the application will automatically detect any valid ocr provider placed in the `src/ocr/providers` directory. to get
started, you can copy the `dummy` provider and use it as a template.

for a complete guide, see: [how to create a custom ocr provider](docs/CUSTOM_OCR_PROVIDER.md)

**note that this feature is not available in the bundled windows executable for now**

## building your own dictionary (optional)

you can find a bundled archive that contains meikipop src + a prebuilt dictionary in the releases. if you really want to build your own dictionary however, you can do that:

```bash
python -m scripts.build_dictionary
```

for more details, you can look here: [Nazeka](https://github.com/wareya/nazeka)

## license

meikipop is licensed under the GNU General Public License v3.0. see the `LICENSE` file for the full license text.


