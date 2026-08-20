# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

a = Analysis(
    ['techdeck\\__main__.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('plugins', 'plugins'),
        ('assets', 'assets'),
        # 911 Inspection Dimensions reads the drawings with RapidOCR, whose ONNX models
        # and per-model config.yaml files are package DATA, not code - PyInstaller does
        # not follow them from the imports, so the frozen exe raises FileNotFoundError
        # on the first run without these. (collect_data_files pulls the .onnx + .yaml +
        # the character dictionary out of site-packages/rapidocr_onnxruntime.)
        *collect_data_files('rapidocr_onnxruntime'),
    ],
    hiddenimports=[
        # First-party modules only imported dynamically by plugins (which PyInstaller's
        # static analysis can't see), so they must be forced in or the frozen exe is
        # missing them -> "cannot import name 'plugin_sdk' from 'techdeck.core'" /
        # "No module named 'techdeck.core.plugin_window'" (bit customer_dxf_quoting).
        'techdeck.core.plugin_sdk',
        'techdeck.core.plugin_window',
        # Sentry Drone: plugin_sdk lazy-imports both (sentry_style -> sentry_mode;
        # pick_directory_gui/pick_file_gui -> chopper_picker for GUI plugins).
        # Both are inside function bodies, so force them in.
        'techdeck.core.sentry_mode',
        'techdeck.ui.widgets.chopper_picker',
        # Only imported by the game_asa_the_video_game plugin's run.py (loads at runtime).
        'techdeck.ui.widgets.steelbeams_game',
        'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets', 'PySide6.QtMultimedia',
        'PySide6.QtCharts',
        # openpyxl.drawing.image is only imported by 911_sspo_invoicing_prep's run.py
        # (embeds the ASA logo on the Invoice Supplement tab).
        'openpyxl', 'openpyxl.drawing.image', 'pandas', 'fitz', 'pypdf', 'packaging', 'requests',
        'qrcode', 'qrcode.image', 'qrcode.image.base', 'qrcode.image.pure', 
        'qrcode.image.styledpil', 'qrcode.image.svg', 'qrcode.image.styles',
        'qrcode.image.styles.moduledrawers', 'qrcode.image.styles.colormasks',
        'PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL.ImageFont',
        # Only imported by 911_inspection_dimensions' run.py: the on-device drawing
        # reader (RapidOCR on ONNX Runtime) plus the array/vision libs it pulls in.
        # No network and no external exe - the models ship in datas above.
        'rapidocr_onnxruntime', 'onnxruntime', 'onnxruntime.capi',
        'onnxruntime.capi._pybind_state', 'numpy', 'cv2', 'yaml', 'shapely', 'pyclipper',
        'win32com', 'win32com.client', 'pythoncom', 'pywintypes'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Dev/IDE and stdlib never imported by the app or any plugin.
        'tkinter', 'Pythonwin', 'pydoc_data',
        # DevKit dev tools (Pixel Studio + authoring scripts) live under tools/
        # and must NEVER ship. The shell lazy-imports them only behind the
        # source-only dev-mode gate (techdeck.ui.dev_mode.is_dev_build), but
        # PyInstaller's static analysis can't see that guard, so exclude the
        # whole package here to keep it out of every frozen build.
        'tools',
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
