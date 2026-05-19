# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['techdeck\\__main__.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('plugins', 'plugins'),
        ('assets', 'assets'),
    ],
    hiddenimports=[
        'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets', 'PySide6.QtMultimedia',
        'openpyxl', 'pandas', 'fitz', 'pypdf', 'packaging', 'requests',
        'qrcode', 'qrcode.image', 'qrcode.image.base', 'qrcode.image.pure', 
        'qrcode.image.styledpil', 'qrcode.image.svg', 'qrcode.image.styles',
        'qrcode.image.styles.moduledrawers', 'qrcode.image.styles.colormasks',
        'PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL.ImageFont',
        'win32com', 'win32com.client', 'pythoncom', 'pywintypes'
    ],
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
    name='TechDeck',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets\\TechDeck.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TechDeck',
)
