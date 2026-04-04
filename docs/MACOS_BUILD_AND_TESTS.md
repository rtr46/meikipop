# macOS build and compatibility test plan

## what was added in this repository

- A dedicated PyInstaller spec for macOS app bundles: `meikipop.macos.spec`
- A reusable GitHub Actions workflow that builds `.dmg` on Intel and Apple Silicon runners: `.github/workflows/build-macos.yml`
- Integration of the macOS build into PR and tagged release pipelines.
- Runtime dictionary path resolution improvements for frozen builds to ensure `dictionary.pkl` is found when running from a `.app` bundle.

## local build step-by-step (macOS)

1. Activate virtual environment and install dependencies:

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install lxml pyinstaller
```

2. Build the dictionary:

```bash
python -m scripts.build_dictionary
```

3. Build the `.app` bundle with PyInstaller:

```bash
pyinstaller meikipop.macos.spec
```

4. Copy dictionary into the app bundle:

```bash
cp dictionary.pkl dist/meikipop.app/Contents/MacOS/dictionary.pkl
```

5. Build a `.dmg` package:

```bash
rm -rf dist/dmg-root
mkdir -p dist/dmg-root
cp -R dist/meikipop.app dist/dmg-root/
ln -s /Applications dist/dmg-root/Applications
hdiutil create \
  -volname "meikipop" \
  -srcfolder dist/dmg-root \
  -ov \
  -format UDZO \
  dist/meikipop.macos.local.dmg
```

## CI build behavior

The workflow `.github/workflows/build-macos.yml` builds two artifacts:

- `meikipop.macos.x64.dmg` on `macos-13`
- `meikipop.macos.arm64.dmg` on `macos-14`

Both are uploaded as workflow artifacts and included in tagged releases.

## compatibility test matrix recommendation

Run tests on real machines or VMs for at least:

- macOS 12 Monterey (Intel or Apple Silicon)
- macOS 13 Ventura (Intel)
- macOS 14 Sonoma (Apple Silicon)
- macOS 15 Sequoia (Apple Silicon)

## battery of tests (smoke + functional + resilience)

Use this checklist for each target macOS version:

1. Installation and launch
- Open `.dmg`
- Drag app to `/Applications`
- Launch once from Finder
- Confirm app starts without immediate crash

2. macOS permissions
- Verify prompts and granting for:
  - Accessibility
  - Screen Recording
  - Input Monitoring
- Relaunch app and confirm permissions persist

3. Core OCR path
- Region selection works
- OCR provider initialization succeeds (default and one local provider if available)
- Lookup popup appears on hotkey hold

4. Dictionary and UI behavior
- `dictionary.pkl` loads successfully
- Popup updates when moving mouse over text
- Tray icon and menu actions work (settings, region reselect, quit)

5. Stability
- Keep app running for 30 to 60 minutes in auto-scan mode
- Watch for memory growth and UI freeze
- Repeat start/quit cycle 10 times

6. Packaging integrity
- Verify `.app` contains `dictionary.pkl` in `Contents/MacOS`
- Verify the app can start after moving to `/Applications`

## optional automated sanity checks

In CI, after building `.app`, run:

```bash
codesign --verify --deep --strict dist/meikipop.app || true
spctl --assess --verbose=4 dist/meikipop.app || true
```

These checks are optional until signing/notarization is configured.

## note about signing/notarization

Unsigned apps can trigger Gatekeeper warnings on end-user machines.
For public distribution, plan to add:

- Developer ID signing
- Apple notarization
- Stapling notarization ticket to the app/dmg
