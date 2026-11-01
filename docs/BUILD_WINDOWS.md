# Building a Windows executable

Blacksmith CurveTracer can be distributed as a standalone Windows application with
[PyInstaller](https://pyinstaller.org/). The user does not need Python or the
project sources to run it.

> **Important:** PyInstaller is not a cross-compiler. A Windows `.exe` must be
> built on Windows (native Windows or a Windows CI runner). Building from
> WSL/Linux produces a Linux binary, not a Windows executable.

## Requirements

- Windows 10/11, 64-bit.
- 64-bit Python 3.11, 3.12 or 3.13 from
  [python.org](https://www.python.org/downloads/windows/), with
  *Add python.exe to PATH* enabled.
- Do **not** use the Microsoft Store alias (`python.exe` from
  `WindowsApps`); it does not create a usable virtual environment for builds.
- Network access during the first build to download pip packages.

NI-VISA is **not required** to build or to use TCP/IP. For USB-TMC there are
two options:

- **NI-VISA (recommended):** install
  [NI-VISA](https://www.ni.com/en/support/download/download.ni-visa.html) on the
  target machine. The application uses the system VISA library, which talks to
  the instrument's USB-TMC driver.
- **pyusb + WinUSB:** the build bundles `pyusb` and
  [`libusb-package`](https://pypi.org/project/libusb-package/) (which ships
  `libusb-1.0.dll`). In this case the oscilloscope must be bound to the WinUSB
  driver (for example with [Zadig](https://zadig.akeo.ie/)); the Rigol/NI-VISA
  driver cannot be used by libusb at the same time.

TCP/IP (socket port 5555) needs no extra driver.


## Build locally (recommended)

1. Copy or clone the repository to the Windows machine, for example
   `E:\CurveTracer215e\curve-tracer-oss`.
2. Double-click `build_windows.bat`, or run it from `cmd.exe`:

   ```bat
   cd /d E:\CurveTracer215e\curve-tracer-oss
   build_windows.bat
   ```

3. The script creates `.venv-win`, installs the runtime and build
   dependencies, runs the test suite, builds the executable and runs a
   self-check on the frozen application (imports, Qt, Matplotlib and libusb).

Result:

```text
dist\CurveTracer\CurveTracer.exe
```

Distribute the **whole `dist\CurveTracer` folder**, zipped. Do not copy only
the `.exe`: Qt, NumPy, SciPy, Matplotlib and the Python runtime live beside it.

### Manual build

```bat
py -3 -m venv .venv-win
.venv-win\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-build.txt
python -m unittest discover -s tests
python -m PyInstaller --noconfirm --clean CurveTracer.spec
dist\CurveTracer\CurveTracer.exe --self-check
```

## Build with GitHub Actions

The workflow `.github/workflows/build-windows.yml` builds the executable on a
`windows-latest` runner and uploads the `dist/CurveTracer` folder as the
`CurveTracer-windows` artifact.

- Manual run: **Actions → Build Windows executable → Run workflow**.
- Tag run: push a tag such as `v1.0.0`.

Download the artifact from the workflow run and unzip it on the target
machine.

## What is bundled

`CurveTracer.spec` includes:

- the PyQt6 GUI and the Matplotlib Qt backend;
- NumPy, SciPy and the component registry (SQLite is part of Python);
- all `pyvisa_py` backends (they are imported dynamically);
- `pyserial`, used by the PyVISA serial backend;
- `pyusb`, the `usb.backend.*` modules and, on Windows, the
  `libusb-1.0.dll` from `libusb-package` (in `_internal\libusb_package` and
  in the application root);
- `PyUSBTMC`/`cPyUSBTMC` only when they are installed at build time.


The reference PDFs and the `examples/` folder are not bundled. They are only
development documentation.

## Application icon

The Windows executable icon is generated from
[`docs/images/blacksmith.jpeg`](images/blacksmith.jpeg) (or
`docs/blacksmith.jpeg`) on every build by `tools/make_icon.py`:

- the script creates `build/blacksmith.ico` (16–256 px, square crop);
- `CurveTracer.spec` runs the script and passes the `.ico` to PyInstaller's
  `EXE(..., icon=...)`;
- `build_windows.bat` also runs the script before invoking PyInstaller, so the
  build fails early with a clear message if the image is missing.

To change the icon, replace `docs/images/blacksmith.jpeg` and rebuild. Pillow
is listed in `requirements-build.txt` (it is also a Matplotlib dependency). The
same image is bundled as `assets/blacksmith.jpeg` and used as the GUI
window/taskbar icon at runtime.

## Runtime data

The component registry uses the current Windows user profile:

```text
C:\Users\<user>\.curvetracer\components.db
```

It is created automatically on first use. To use a different database, set
the environment variable before launching:

```bat
set CURVETRACER_DB=D:\lab\components.db
CurveTracer.exe
```

## Troubleshooting

- **Windows SmartScreen / antivirus warning**: unsigned PyInstaller
  executables are sometimes flagged. Choose *More info → Run anyway* on your
  own machine. For distribution, sign the executable with a code-signing
  certificate.
- **`python` opens the Microsoft Store**: install Python from python.org and
  disable the Store aliases in *Settings → Apps → Advanced app settings →
  App execution aliases*.
- **Application closes immediately / no window**: the spec builds a windowed
  app without a console. Temporarily set `console=True` in `CurveTracer.spec`,
  rebuild and run from `cmd.exe` to see the traceback. Alternatively run
  `python src/gui.py` in the source tree.
- **Cannot connect to the oscilloscope**: check the IP address, that port
  5555 is reachable and that the Windows firewall allows the application. The
  status bar must show the instrument ID before capturing.
- **`--self-check` fails after the build**: the windowed executable does not
  show a console, so read `%LOCALAPPDATA%\CurveTracer\curvetracer.log`. It lists
  the module or DLL that could not be loaded. Running
  `dist\CurveTracer\CurveTracer.exe --self-check` from `cmd.exe` always exits
  with code 1 when something is missing.
- **USB device does not appear in the Resource list**: click *Refresh*. With
  NI-VISA the resource looks like
  `USB0::0x1AB1::0x044C::<serial>::INSTR`. Without NI-VISA, make sure the
  instrument is bound to WinUSB (Zadig); the build already bundles
  `libusb-1.0.dll`, so no manual DLL copy is needed. Otherwise only TCP/IP
  will work.
- **Log file**: the windowed executable writes diagnostics to
  `%LOCALAPPDATA%\CurveTracer\curvetracer.log`.

- **Slow first start**: one-folder builds unpack less data than one-file
  builds; this is why one-folder is the default. Keep the folder on a local
  disk, not a slow network share.
- **Large folder**: a Qt + SciPy build is typically several hundred MB. This
  is expected.
