# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('icons', 'icons'),
        ('assets', 'assets'),
        ('custom_prompts.csv', '.'),
    ],
    hiddenimports=[
        'PySide6.QtSvg',
        'PySide6.QtSvgWidgets',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineCore',
        'keyring.backends',
        'keyring.backends.macOS',
        'google.genai',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'pandas',
        'pytest',
        'unittest',
        'IPython',
        'PySide6.QtQuick3D',
        'PySide6.QtQuick3DRuntimeRender',
        'PySide6.QtQuick3DParticles',
        'PySide6.Qt3DCore',
        'PySide6.Qt3DRender',
        'PySide6.Qt3DInput',
        'PySide6.Qt3DLogic',
        'PySide6.Qt3DAnimation',
        'PySide6.Qt3DExtras',
        'PySide6.QtCharts',
        'PySide6.QtGraphs',
        'PySide6.QtLocation',
        'PySide6.QtSensors',
        'PySide6.QtBluetooth',
        'PySide6.QtNfc',
        'PySide6.QtSpatialAudio',
        'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets',
        'PySide6.QtRemoteObjects',
        'PySide6.QtScxml',
        'PySide6.QtSerialPort',
        'PySide6.QtSerialBus',
        'PySide6.QtTest',
        'PySide6.QtSql',
        'PySide6.QtDesigner',
        'PySide6.QtHelp',
        'PySide6.QtUiTools',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AI PDF Viewer',
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
    icon=['icons/icon.icns'],
)
# Filter out unused Qt frameworks and heavy unused plugins (keep QtPositioning for WebEngine)
excluded_qt_keywords = [
    'Qt3D', 'QtQuick3D', 'QtCharts', 'QtGraphs', 'QtLocation',
    'QtSpatialAudio', 'QtMultimedia', 'QtVirtualKeyboard',
    'QtSensors', 'QtDataVisualization', 'QtWebView', 'QtTextToSpeech',
    'QtScxml', 'QtRemoteObjects',
]

filtered_binaries = [b for b in a.binaries if not any(k in b[0] for k in excluded_qt_keywords)]
filtered_datas = [d for d in a.datas if not any(k in d[0] for k in excluded_qt_keywords)]

coll = COLLECT(
    exe,
    filtered_binaries,
    filtered_datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AI PDF Viewer',
)
app = BUNDLE(
    coll,
    name='AI PDF Viewer.app',
    icon='icons/icon.icns',
    bundle_identifier=None,
    info_plist={
        'CFBundleDocumentTypes': [
            {
                'CFBundleTypeName': 'PDF Document',
                'CFBundleTypeRole': 'Viewer',
                'LSHandlerRank': 'Alternate',
                'LSItemContentTypes': ['com.adobe.pdf']
            }
        ]
    }
)
