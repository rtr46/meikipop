# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src/main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('src/ocr/providers/glens/provider.py', 'src/ocr/providers/glens'),
        ('src/ocr/providers/glens/lens_betterproto.py', 'src/ocr/providers/glens'),
        ('src/ocr/providers/glens/__init__.py', 'src/ocr/providers/glens'),
        ('src/ocr/providers/glensv2/provider.py', 'src/ocr/providers/glensv2'),
        ('src/ocr/providers/glensv2/lens_betterproto.py', 'src/ocr/providers/glensv2'),
        ('src/ocr/providers/glensv2/__init__.py', 'src/ocr/providers/glensv2'),
        ('src/ocr/providers/owocr/provider.py', 'src/ocr/providers/owocr'),
        ('src/ocr/providers/owocr/__init__.py', 'src/ocr/providers/owocr'),
        ('src/ocr/providers/__init__.py', 'src/ocr/providers'),
        ('src/resources/icon.ico', '.'),
        ('src/resources/icon.ico', 'src/resources'),
        ('src/resources/icon.inactive.ico', '.'),
        ('src/resources/icon.inactive.ico', 'src/resources'),
    ],
    hiddenimports=['src.ocr.providers.glens', 'src.ocr.providers.glensv2', 'src.ocr.providers.owocr'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='meikipop',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
