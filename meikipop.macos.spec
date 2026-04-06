# -*- mode: python ; coding: utf-8 -*-

import re
from pathlib import Path

from PyInstaller.config import CONF


def _get_build_version() -> str:
    config_path = Path(CONF['specpath']) / 'src' / 'config' / 'config.py'
    match = re.search(r'^APP_VERSION\s*=\s*["\']([^"\']+)["\']', config_path.read_text(encoding='utf-8'), re.M)
    if not match:
        return '0.0.0'

    version = match.group(1)
    if version.startswith('v.'):
        return version[2:]
    if version.startswith('v'):
        return version[1:]
    return version


BUILD_VERSION = _get_build_version()

a = Analysis(
    ['src/main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('dictionary.pkl', '.'),
        ('src/ocr/providers/glensv2/provider.py', 'src/ocr/providers/glensv2'),
        ('src/ocr/providers/glensv2/lens_betterproto.py', 'src/ocr/providers/glensv2'),
        ('src/ocr/providers/glensv2/__init__.py', 'src/ocr/providers/glensv2'),
        ('src/ocr/providers/owocr/provider.py', 'src/ocr/providers/owocr'),
        ('src/ocr/providers/owocr/__init__.py', 'src/ocr/providers/owocr'),
        ('src/ocr/providers/meikiocr/provider.py', 'src/ocr/providers/meikiocr'),
        ('src/ocr/providers/meikiocr/__init__.py', 'src/ocr/providers/meikiocr'),
        ('src/ocr/providers/screenai/provider.py', 'src/ocr/providers/screenai'),
        ('src/ocr/providers/screenai/chrome_screen_ai_pb2.py', 'src/ocr/providers/screenai'),
        ('src/ocr/providers/screenai/view_hierarchy_pb2.py', 'src/ocr/providers/screenai'),
        ('src/ocr/providers/screenai/__init__.py', 'src/ocr/providers/screenai'),
        ('src/ocr/providers/__init__.py', 'src/ocr/providers'),
        ('src/resources/icon.ico', 'src/resources'),
        ('src/resources/icon.inactive.ico', 'src/resources'),
    ],
    hiddenimports=['src.ocr.providers.glensv2', 'src.ocr.providers.owocr', 'src.ocr.providers.meikiocr', 'src.ocr.providers.screenai'],
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
    [],
    exclude_binaries=True,
    name='meikipop',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
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
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='meikipop',
)

app = BUNDLE(
    coll,
    name='meikipop.app',
    icon='src/resources/icon.ico',
    bundle_identifier='io.github.rtr46.meikipop',
    version=BUILD_VERSION,
    info_plist={
        'CFBundleVersion': BUILD_VERSION,
    },
)