# -*- mode: python ; coding: utf-8 -*-

# Sadece PyInstaller'in otomatik yakalayamayabilecegi moduller
hiddenimports = [
    'keyboard',
    'pynput',

    'pynput.keyboard',
    'pynput.keyboard._win32',
    'win32timezone',
    'win32clipboard',
    'win32con',
    'pywintypes',
    'PyQt6.QtNetwork',
    'src.utils.locales',
    'src.utils.crashlog',
]

# Kullanilmayan agir Qt / Python modullerini disla
excludes = [
    'PyQt5', 'PySide2', 'PySide6',
    'PyQt6.QtWebEngine', 'PyQt6.QtWebEngineCore', 'PyQt6.QtWebEngineWidgets',
    'PyQt6.QtWebEngineQuick', 'PyQt6.QtWebChannel',
    'PyQt6.Qt3DAnimation', 'PyQt6.Qt3DCore', 'PyQt6.Qt3DExtras',
    'PyQt6.Qt3DInput', 'PyQt6.Qt3DLogic', 'PyQt6.Qt3DRender',
    'PyQt6.QtMultimedia', 'PyQt6.QtMultimediaWidgets',
    'PyQt6.QtQuick', 'PyQt6.QtQuick3D', 'PyQt6.QtQuickWidgets', 'PyQt6.QtQml',
    'PyQt6.QtBluetooth', 'PyQt6.QtCharts', 'PyQt6.QtDataVisualization',
    'PyQt6.QtLocation', 'PyQt6.QtPositioning', 'PyQt6.QtSensors',
    'PyQt6.QtSerialPort', 'PyQt6.QtSql', 'PyQt6.QtTest', 'PyQt6.QtXml',
    'PyQt6.QtDesigner', 'PyQt6.QtHelp', 'PyQt6.QtOpenGL', 'PyQt6.QtOpenGLWidgets',
    'PyQt6.QtSvg', 'PyQt6.QtSvgWidgets', 'PyQt6.QtNfc', 'PyQt6.QtRemoteObjects',
    'PyQt6.QtTextToSpeech', 'PyQt6.QtSpatialAudio', 'PyQt6.QtPdf', 'PyQt6.QtPdfWidgets',
    'PyQt6.QtDBus',
    'tkinter', 'matplotlib', 'numpy', 'pandas', 'scipy', 'PIL', 'cv2', 'torch',
    'pyautogui',
]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    # Yalnizca tepsi/pencere ikonu paketlenir (EXE ikonu asagidaki icon= ile gomulur)
    datas=[('assets/icons/keyboard.png', 'assets/icons')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='FlexiKey',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX kapali: bu makinede kurulu degil (sessizce atlanir) ve UPX'li paketlenmis EXE'ler
    # antivirus yanlis-pozitiflerini arttirir.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\icons\\FlexiKey.ico'],
    # Windows 'Ayrintilar' sekmesi: surum bilgisi (src/utils/updater.py UpdateChecker.CURRENT_VERSION ile ayni olmali)
    version='file_version_info.txt',
)
