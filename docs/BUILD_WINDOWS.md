# Building a Windows executable

CurveTracer OSS can be distributed as a standalone Windows application with
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

No NI-VISA installation is required: the application connects to the
oscilloscope through TCP socket port 5555 and falls back to the bundled
pure-Python `pyvisa-py` backend.

## Build locally (recommended)

1. Copy or clone the repository to the Windows machine, for example
   `E:\CurveTracer215e\curve-tracer-oss`.
2. Double-click `build_windows.bat`, or run it from `cmd.exe`:

   ```bat
   cd /d E:\CurveTracer215e\curve-tracer-oss
   build_windows.bat
   ```

3. The script creates `.venv-win`, installs the runtime and build
   dependencies, runs the test suite and builds the executable.

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
- `pyserial`, used by the PyVISA fallback.

The reference PDFs and the `examples/` folder are not bundled. They are only
development documentation.

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
- **Slow first start**: one-folder builds unpack less data than one-file
  builds; this is why one-folder is the default. Keep the folder on a local
  disk, not a slow network share.
- **Large folder**: a Qt + SciPy build is typically several hundred MB. This
  is expected.
