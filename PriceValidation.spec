# -*- mode: python ; coding: utf-8 -*-
# PriceValidation.spec — PyInstaller onedir build

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['src/price_validation/main.py'],
    pathex=[str(Path('src').resolve())],
    binaries=[],
    datas=[],
    hiddenimports=[
        'price_validation',
        'price_validation.config',
        'price_validation.config.paths',
        'price_validation.config.settings',
        'price_validation.ingestion',
        'price_validation.ingestion.fetch',
        'price_validation.ingestion.loader',
        'price_validation.validation',
        'price_validation.validation.compare',
        'price_validation.report',
        'price_validation.report.writer',
        'price_validation.ui',
        'price_validation.ui.app',
        'openpyxl',
        'pandas',
        'tkinter',
    ],
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
    name='PriceValidation',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
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
    upx=True,
    upx_exclude=[],
    name='PriceValidation',
)
