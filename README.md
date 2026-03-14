# meikipop - universal japanese ocr popup dictionary

instantly look up japanese words anywhere on your screen. meikipop uses optical character recognition (ocr) to read text from websites, games, scanned manga, or even hard-coded video subtitles, giving you effortless dictionary lookups with the press of a key (or even without)!

https://github.com/user-attachments/assets/a1834197-3059-438c-a2dc-716e8ec9078f



## features

*   **works everywhere:** if you can see it on your screen, you can look it up. no more limitations of browser extensions, hooks or application-specific tools.
*   **ocr-powered:** reads japanese text directly from images, making it perfect for games, comics, and videos.
*   **blazingly fast:** the dictionary is pre-processed into a highly optimized format for instant lookups. the ui is designed to be lightweight and responsive.
*   **simple & intuitive:** just point your mouse and press a hotkey. that's it.
*   **highly customizable:** change the hotkey, theme, colors, and layout to create your perfect reading experience.
*   **region or fullscreen:** scan your entire screen or select a specific region (like a game window or manga page) to improve performance.
*   **pluggable ocr backend:** lets you choose whatever ocr suits you best. whether you want the highest accuracy remote ocr, that runs great even on low-end hardware or you want blazingly fast and private local ocr.

## philosophy & limitations

meikipop is designed to do one thing and do it exceptionally well: provide fast, frictionless, on-screen dictionary lookups.

it is heavily inspired by the philosophy of [Nazeka](https://github.com/wareya/nazeka), a fantastic browser-based popup dictionary, and aims to bring that seamless experience to the entire desktop. it also draws inspiration from the ocr architecture of [owocr](https://github.com/AuroraWright/owocr/tree/master/owocr).

to maintain this focus, there are a few things meikipop is **not**:

*   **it is not an srs-mining tool.** meikipop does not include functionality to automatically create flashcards for programs like anki.
*   **it is not a multi-dictionary tool.** while meikipops lets you import yomitan dictionaries, it is designed to run best with a single, semi-custom jmdict+kanjidic dictionary. 

## installation

### windows + linux (x11): prepackaged binaries + dictionary

this is the easiest way to run meikipop on windows and linux and is recommended for most users. no python installation required. just download, unpack and start the executable binary:
* https://github.com/rtr46/meikipop/releases/latest

### windows + linux (x11) + macos (beta): run from source

if you want to develop or use custom ocr provider, modify meikipop's behaviour, want to debug an error or prefer to run from source for any other reason, this is the way to go. for windows + linux ignore the macos specific parts.

(note that meikipop is in beta for macos. the tray and therefore the settings menu may or may not show up - you should still be able to configure meikipop through the config.ini. if you notice meikipop breaking with a new release, feel free to let us know via an issue and we will try to fix it.)

1.  **prerequisites:**
    * python 3.10+
  
2. **set required permissions (macos only)**
    * go to **System Preferences** > **Security & Privacy** > **Privacy**
    * add/enable your terminal app in **Input Monitoring**, **Screen Recording** and **Accessibility**

3.  **download the latest release that includes a prebuilt dictionary:**
    * git clone https://github.com/rtr46/meikipop.git
    * or simply download and unpack the source archive: https://github.com/rtr46/meikipop/archive/refs/heads/main.zip

4.  **install python dependencies, build a dictionary and run:**
    ```bash
    pip install -r requirements.txt
    pip install lxml # needed for the build_dictionary script
    python -m scripts.build_dictionary # you can alternatively use the dictionary from one of the binary distributions 
    python -m src.main # run meikipop
    ```

## how to use

1.  run the application (`python -m src.main`). an icon will appear in your system tray.
2.  the first time you run the app in `region` mode, you will be prompted to select an area of your screen to scan (the scanned area will be send to google ocr).
3.  move your mouse over any japanese text on your screen.
4.  **press and hold the hotkey** (**shift** by default). a popup with dictionary entries will appear. depending on your internet connection this may take a while the first time...
5.  keep holding the key and move your mouse to look up any additional words.
6.  release the hotkey to hide the popup.
7.  **right-click the system tray icon** to open the settings, reselect the scan region, change the ocr provider or quit the application.
8.  make sure you try the **auto scan mode**. it continuously scans your screen to provide you with dictionary entries as fast as possible and without the need to press a hotkey.

## configuration

you can fully customize meikipop's behavior and appearance. right-click the tray icon and choose "settings" to open the configuration gui.

changes are saved to `config.ini` in the same folder as the application.

## using alternative ocr backends...

meikipop's architecture allows you to choose whatever ocr suits your use case best:
- google lens (default/remote): fast and platform independent, but every scan shares your screen with google.
- meikiocr (local): possibly the fastest local ocr worth using on cpu and can run even faster on nvidia gpus. primarily designed for video games with horizontal text. poor accuracy for vertical text.
- chrome screen ai (local): alternative local ocr worth checking out if meikiocr does not fit your use case. requires additional setup ((instructions)[https://github.com/rtr46/meikipop/releases/tag/v1.10.0])
- owocr: owocr lets you choose from even more ocr backends (see below)
- custom ocr provider: if you are running from source it is very simple to integrate any ocr provider on your own (see below) 

### ...via owocr provider

owocr lets you run any relevant ocr engine and lets meikipop use it. just run a local [owocr](https://github.com/AuroraWright/owocr/tree/master/owocr) instance and select the owocr ocr provider from meikipop's system tray menu.

make sure you:

* use owocr 1.15.0 or newer
* enable reading from and writing to websockets
* choose the json output format
* and use an ocr backend that supports coordinates (most do)
    ```bash
    pip install -U "owocr>=1.15"
    owocr -r websocket -w websocket -of json -e glens # replace glens with your favorite owocr backend
    ```

### ...via custom ocr provider

you can develop your own ocr provider. to get started, you can copy the `dummy` provider and use it as a template.

for a complete guide, see: [how to create a custom ocr provider](docs/CUSTOM_OCR_PROVIDER.md)

## building your own dictionary (optional)

in case you want to update your dictionary you can simply run:

```bash
python -m scripts.build_dictionary
```

if you want to import a yomitan dictionary that is possible as well. you can import multiple yomitan dictionaries at once, but be aware that this will overwrite your default dictionary:

```bash
python -m scripts.import_yomitan_dict my_yomitan_dict.zip
```

## license

meikipop is licensed under the GNU General Public License v3.0. see the `LICENSE` file for the full license text.


