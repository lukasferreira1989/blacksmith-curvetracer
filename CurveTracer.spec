# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the CurveTracer OSS Windows build.

Build with:
    pyinstaller --noconfirm --clean CurveTracer.spec

The result is a one-folder distribution (recommended for Qt/NumPy/SciPy):
    dist/CurveTracer/CurveTracer.exe
"""

from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_binary_assets

# PyVISA-py loads its backends dynamically, so their modules are not found by
# static import analysis. Collect all of them to keep the VISA fallback working
# in the frozen application (the primary connection uses socket port 5555).
hiddenimports = [
    module
    for module in collect_submodules("pyvisa_py")
    if ".testsuite" not in module
]
hiddenimports += [
    "pyvisa",
    "pyserial",
    "matplotlib.backends.backend_qt5agg",
    "matplotlib.backends.backend_qtagg",
    "matplotlib.pyplot",
    "matplotlib.backends.backend_qt5",
    "PyQt6",
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "PyQt6.QtPrintSupport",
]

# Collect matplotlib data files (colormaps, fonts, etc.)
datas = collect_data_files("matplotlib", include_py_files=False)

# Collect PyQt6 binaries (DLLs, etc.)
binaries = collect_binary_assets("matplotlib")
binaries += collect_binary_assets("PyQt6")
binaries += collect_binary_assets("PyQt6.QtCore")
binaries += collect_binary_assets("PyQt6.QtGui")
binaries += collect_binary_assets("PyQt6.QtWidgets")

a = Analysis(
    ["curvetracer.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "pytest",
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
    name="CurveTracer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="CurveTracer",
)
