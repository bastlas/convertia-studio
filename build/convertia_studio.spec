# -*- mode: python ; coding: utf-8 -*-
"""Recette PyInstaller de Convertia Studio (Windows et Linux).

Usage :
    pyinstaller --noconfirm --clean convertia_studio.spec

Produit ``dist/ConvertiaStudio/`` (ConvertiaStudio.exe sous Windows), avec ffmpeg
embarqué dans ``bin/`` s'il a été déposé à côté de ce fichier de recette.
"""

import os
import sys

ROOT = os.path.abspath(os.getcwd())

# ffmpeg n'est pas embarqué dans l'archive PyInstaller : build/*.sh le copie
# dans dist/ConvertiaStudio/bin/ (l'application le cherche là, puis dans le PATH).
binaries = []

# DLL Qt tirées par QtWidgets mais inutiles ici (interface 100 % widgets)
DROP_DLLS = {
    "Qt6Quick.dll", "Qt6Qml.dll", "Qt6QmlModels.dll", "Qt6QmlMeta.dll",
    "Qt6QmlWorkerScript.dll", "Qt6QuickWidgets.dll", "Qt6Pdf.dll",
}

# modules Qt réellement utilisés : on exclut le reste pour limiter le poids
excludes = [
    "tkinter", "unittest", "pydoc_data", "test", "setuptools", "pip",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtQuick",
    "PySide6.QtQuickWidgets", "PySide6.QtQml", "PySide6.QtQuick3D",
    "PySide6.QtBluetooth", "PySide6.QtNetworkAuth", "PySide6.QtPositioning",
    "PySide6.QtSerialPort", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner",
    "PySide6.QtHelp", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSpatialAudio",
    "PySide6.QtSvgWidgets", "PySide6.QtTextToSpeech", "PySide6.QtUiTools",
    "PySide6.QtWebSockets", "PySide6.QtXml",
]

hiddenimports = [
    "convertia_studio.gui.pages.audio_page",
    "convertia_studio.gui.pages.coming_soon",
    "convertia_studio.gui.pages.image_page",
    "convertia_studio.gui.crop_dialog",
    "convertia_studio.image.engine",
    "convertia_studio.image.formats",
    "convertia_studio.gui.pages.video_page",
    "convertia_studio.video.engine",
    "convertia_studio.video.formats",
]

icon = os.path.join(ROOT, "build", "convertia_studio.ico")
if not os.path.isfile(icon):
    icon = os.path.join(ROOT, "convertia_studio.ico")
if not os.path.isfile(icon):
    icon = None

a = Analysis(
    [os.path.join(ROOT, "convertia_studio.pyw")],
    pathex=[ROOT],
    binaries=binaries,
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
a.binaries = [entry for entry in a.binaries
              if os.path.basename(entry[0]) not in DROP_DLLS]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ConvertiaStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ConvertiaStudio",
)
