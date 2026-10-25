# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the CurveTracer OSS Windows build.

Build with:
    pyinstaller --noconfirm --clean CurveTracer.spec

The result is a one-folder distribution (recommended for Qt/NumPy/SciPy):
    dist/CurveTracer/CurveTracer.exe
"""

from PyInstaller.utils.hooks import collect_submodules

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
]

a = Analysis(
    ["curvetracer.py"],
    pathex=["src"],
    binaries=[],
    datas=[],
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
