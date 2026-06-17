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
        # First-party modules only imported dynamically by plugins (which PyInstaller's
        # static analysis can't see), so they must be forced in or the frozen exe is
        # missing them -> "cannot import name 'plugin_sdk' from 'techdeck.core'" /
        # "No module named 'techdeck.core.plugin_window'" (bit customer_dxf_quoting).
        'techdeck.core.plugin_sdk',
        'techdeck.core.plugin_window',
        # Only imported by the steeltube_game plugin's run.py (loads at runtime).
        'techdeck.ui.widgets.steelbeams_game',
        'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets', 'PySide6.QtMultimedia',
        'PySide6.QtCharts',
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
    excludes=[
        # Dev/IDE and stdlib never imported by the app or any plugin.
        'tkinter', 'Pythonwin', 'pydoc_data',
        # Qt modules NOT imported anywhere in techdeck/ or plugins/ (verified by
        # grep: only QtCharts/QtCore/QtGui/QtMultimedia/QtSvg/QtWidgets are used).
        # Excluding the bindings stops PyInstaller pulling these large, unused
        # stacks (WebEngine/Quick/Qml/3D, etc.).
        # HARD RULE 8 CAVEAT: if a future plugin imports one of these, REMOVE it
        # from this list or the frozen build will ImportError.
        'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineQuick', 'PySide6.QtWebChannel', 'PySide6.QtWebSockets',
        'PySide6.QtQuick', 'PySide6.QtQuick3D', 'PySide6.QtQuickWidgets',
        'PySide6.QtQml', 'PySide6.QtQmlModels',
        'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DExtras',
        'PySide6.Qt3DInput', 'PySide6.Qt3DAnimation', 'PySide6.Qt3DLogic',
        'PySide6.QtDataVisualization', 'PySide6.QtDesigner', 'PySide6.QtUiTools',
        'PySide6.QtTest', 'PySide6.QtSql', 'PySide6.QtBluetooth',
        'PySide6.QtNfc', 'PySide6.QtPositioning', 'PySide6.QtSensors',
        'PySide6.QtSerialPort', 'PySide6.QtSerialBus', 'PySide6.QtScxml',
        'PySide6.QtRemoteObjects', 'PySide6.QtTextToSpeech',
        'PySide6.QtPdf', 'PySide6.QtPdfWidgets',
    ],
    noarchive=False,
    optimize=0,
)

# ── Size trimming ────────────────────────────────────────────────────────────
# English-only app: drop Qt's bundled translation catalogs (~6 MB of .qm files).
a.datas = [d for d in a.datas
           if 'translations' not in d[0].replace('\\', '/').lower()
           or 'pyside6' not in d[0].replace('\\', '/').lower()]

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
