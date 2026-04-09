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

there are a few different ways to install and run meikipop. note that when meikipop is started for the first time, a dictionary and ocr models may be downloaded.

### easiest: prepackaged binaries

just download, unpack and start the executable binary. no python installation required:
* https://github.com/rtr46/meikipop/releases/latest

### recommended: install via pypi

if you already have python 3.10+ installed, this is the most flexible option that lets you run directly from source, enables you to edit the program and lets you add your own custom ocr providers. 

<details>
<summary>click here for mac os specific setup steps</summary>

* go to **System Preferences** > **Security & Privacy** > **Privacy**
* add/enable your terminal app in **Input Monitoring**, **Screen Recording** and **Accessibility**

note that there may be problems when using python 3.14. use one of [these workarounds](https://github.com/rtr46/meikipop/issues/43) if necessary.
</details>
<details>
<summary>click here for linux specific setup steps</summary>

install the following packages for your distro:
* **Fedora** - `sudo dnf install libxcb xcb-util xcb-util-cursor libxkbcommon-x11 libxkbcommon xcb-util-wm xcb-util-keysyms pipewire-gstreamer`
* **Ubuntu** - `sudo apt install cmake libcairo2-dev libgirepository-2.0-dev libgstreamer1.0-dev gstreamer1.0-pipewire libxcb-xkb-dev libxcb-cursor-dev libxcb-xinerama0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1-dev libxcb-shape0`
</details>



```bash
#... activate your environment if any
pip install --upgrade meikipop
meikipop  # run the application
```

## how to use

1.  run the application (`meikipop`).
2.  the first time you run the app in `region` mode, you will be prompted to select an area of your screen to scan.
3.  move your mouse over any japanese text on your screen.
4.  a popup with dictionary entries will appear.
5.  **right-click the system tray icon** to open the settings, reselect the scan region, change the ocr provider or quit the application.

## configuration

you can fully customize meikipop's behavior and appearance. right-click the tray icon and choose "settings" to open the configuration gui.

changes are saved to a platform-specific user data directory:
- Windows: `%LOCALAPPDATA%\meikipop\config.ini`
- Linux: `~/.config/meikipop/config.ini`
- macOS: `~/Library/Application Support/meikipop/config.ini`

## using alternative ocr backends...

meikipop's architecture allows you to choose whatever ocr suits your use case best:
- meikiocr (default/local): possibly the fastest local ocr worth using on cpu and can run even faster on nvidia gpus. primarily designed for video games with horizontal text. poor accuracy for vertical text.
- google lens (remote): high accuracy, but requires an internet connection and has higher latency then the local options.
- chrome screen ai (local): alternative local ocr worth checking out if meikiocr does not fit your use case. requires additional setup ([instructions](https://github.com/rtr46/meikipop/releases/tag/v1.10.0))
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
meikipop build-dict
```

if you want to import a yomitan dictionary that is possible as well. you can import multiple yomitan dictionaries at once, but be aware that this will overwrite your default dictionary:

```bash
# try to keep as much of the dictionary's original formatting
meikipop import-yomitan-dict-html my_yomitan_dict.zip
# or create a compact, text only dictionary
meikipop import-yomitan-dict-text my_yomitan_dict.zip
```

## license

meikipop is licensed under the GNU General Public License v3.0. see the `LICENSE` file for the full license text.


