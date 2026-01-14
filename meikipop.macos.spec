# -*- mode: python ; coding: utf-8 -*-

import os

block_cipher = None

project_root = os.path.abspath(".")

a = Analysis(
    ["src/main.py"],
    pathex=[project_root],
    binaries=[],
    datas=[
        ("src/ocr/providers/glensv2/provider.py", "src/ocr/providers/glensv2"),
        ("src/ocr/providers/glensv2/lens_betterproto.py", "src/ocr/providers/glensv2"),
        ("src/ocr/providers/glensv2/__init__.py", "src/ocr/providers/glensv2"),
        ("src/ocr/providers/owocr/provider.py", "src/ocr/providers/owocr"),
        ("src/ocr/providers/owocr/__init__.py", "src/ocr/providers/owocr"),
        ("src/ocr/providers/meikiocr/provider.py", "src/ocr/providers/meikiocr"),
        ("src/ocr/providers/meikiocr/__init__.py", "src/ocr/providers/meikiocr"),
        ("src/ocr/providers/__init__.py", "src/ocr/providers"),
        ("src/resources/icon.ico", "src/resources"),
        ("src/resources/icon.inactive.ico", "src/resources"),
        ("jmdict_enhanced.pkl", "."),
    ],
    hiddenimports=["src.ocr.providers.glensv2", "src.ocr.providers.owocr", "src.ocr.providers.meikiocr"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="meikipop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="meikipop",
)

app = BUNDLE(
    coll,
    name="meikipop.app",
    bundle_identifier="com.meikipop.app",
    info_plist={
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
    },
)
