# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the CurveTracer OSS Windows build.

Build with:
    pyinstaller --noconfirm --clean CurveTracer.spec

The result is a one-folder distribution (recommended for Qt/NumPy/SciPy):
    dist/CurveTracer/CurveTracer.exe
"""

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

# PyVISA loads the backend with importlib ("pyvisa_" + backend), so neither
# pyvisa-py nor its modules appear in the static import analysis.
hiddenimports = [
    module
    for module in collect_submodules("pyvisa")
    if ".testsuite" not in module
]
hiddenimports += [
    module
    for module in collect_submodules("pyvisa_py")
    if ".testsuite" not in module
]
hiddenimports += [
    "pyvisa_py",
    "pyserial",
    # Matplotlib's Qt backend is selected at runtime.
    "matplotlib.backends.backend_qt5agg",
    "matplotlib.backends.backend_qtagg",
    "matplotlib.backends.backend_qt5",
    "matplotlib.pyplot",
    "PyQt6",
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "PyQt6.QtPrintSupport",
]

# USB support: pyvisa-py/pyusb load the backend at runtime, so the modules must
# be listed explicitly.
hiddenimports += [
    "usb",
    "usb.core",
    "usb.util",
    "usb.backend.libusb1",
    "usb.backend.libusb0",
    "usb.backend.openusb",
]

# Matplotlib data files (fonts, colormaps, style sheets); PyInstaller's own
# hook also collects these, duplicates are de-duplicated.
datas = collect_data_files("matplotlib", include_py_files=False)
binaries = []

# libusb-package (Windows) provides libusb-1.0.dll for pyusb/pyvisa-py when
# NI-VISA is not installed. collect_all keeps the DLL inside the package so
# libusb_package.get_library_path() works in the frozen app; the package's own
# PyInstaller hook also places a copy at the application root for ctypes.
try:
    import libusb_package
except Exception:
    libusb_package = None

if libusb_package is not None:
    libusb_datas, libusb_binaries, libusb_hidden = collect_all("libusb_package")
    datas += libusb_datas
    binaries += libusb_binaries
    hiddenimports += libusb_hidden
    hiddenimports.append("libusb_package")

    # Extra copy at the root: pyusb's ctypes fallback also finds it there.
    try:
        _libusb_path = libusb_package.get_library_path()
    except Exception:
        _libusb_path = None
    if _libusb_path is not None:
        binaries.append((str(_libusb_path), "."))

# PyUSBTMC is optional (alternative USB path, mostly used on Linux). Only
# bundle it when it is installed at build time.
try:
    import PyUSBTMC
except Exception:
    PyUSBTMC = None

if PyUSBTMC is not None:
    usbtmc_datas, usbtmc_binaries, usbtmc_hidden = collect_all("PyUSBTMC")
    datas += usbtmc_datas
    binaries += usbtmc_binaries
    hiddenimports += usbtmc_hidden
    hiddenimports.append("PyUSBTMC")
    try:
        import cPyUSBTMC  # noqa: F401

        hiddenimports.append("cPyUSBTMC")
    except Exception:
        pass

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
        # Not used by CurveTracer. pandas is only an optional matplotlib
        # integration and zeroconf only serves HiSLIP discovery (we use the
        # raw Rigol socket on port 5555), so keep the build small.
        "pandas",
        "zeroconf",
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
