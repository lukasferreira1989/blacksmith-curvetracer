# Blacksmith CurveTracer

**English** | [Português (Brasil)](README.pt-BR.md)

<p align="center">
  <img src="docs/images/blacksmith.jpeg" alt="Blacksmith CurveTracer logo" width="240">
</p>

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Platforms](https://img.shields.io/badge/platforms-Linux%20%7C%20Windows-lightgrey)](#requirements)

**Blacksmith CurveTracer** acquires the **X-Y display** of a Rigol
DHO800/DHO900 or MSO5000 oscilloscope, pairs CH1/CH2 sample by sample, and
plots the V-I curve on a PC. It supports LAN and USB, 10k–1M-point captures,
CSV export, a SQLite component registry and reference-vs-live comparison.

> **⚠️ This is not a standalone curve tracer.** The software only reads the
> oscilloscope screen. You need an external analog **VI curve tester** — for
> example the **ASA VI Curve Tester** — connected to the scope's CH1/CH2.

![Blacksmith CurveTracer connected to an MSO5074](docs/images/gui-mso5074.png)

## Contents

- [Features](#features)
- [Hardware you need](#hardware-you-need)
- [Install and run](#install-and-run)
- [Quick start](#quick-start)
- [Using the GUI](#using-the-gui)
- [Capture pipeline and memory depth](#capture-pipeline-and-memory-depth)
- [Display scale and math](#display-scale-and-math)
- [Data formats](#data-formats)
- [Component registry](#component-registry)
- [SCPI compatibility](#scpi-compatibility)
- [Configuration and environment](#configuration-and-environment)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Performance and limitations](#performance-and-limitations)
- [Project structure](#project-structure)
- [Development](#development)
- [Safety, license and contributing](#safety-license-and-contributing)
- [Donations](#donations)

---

## Features

- **Rigol DHO800/900 and MSO5000** support with automatic family detection.
- **X-Y acquisition** from CH1/CH2, preserving the original sample order.
- **10,000–1,000,000-point RAW captures**, or 1,000 screen points in `NORM`.
- **LAN socket, PyVISA and USB-TMC** (PyUSBTMC or NI-VISA/pyvisa-py).
- **Single capture and real-time** modes with a configurable interval.
- **8 x 8 graticule** with the instrument's scale, offset and SI units.
- **Cursor** (`Off`, `Free`, `Single-Plot`) with physical-unit readout.
- **CSV import/export** and JSON setup save/load.
- **Component registry** (SQLite): images, pin maps, captures and comparison.
- **Windows `.exe`** build with PyInstaller and GitHub Actions.

**Tested:** DHO924S `00.01.04` (LAN) and MSO5074 `00.01.03.03.00` (USB).

---

## Hardware you need

The measurement chain has three parts:

| Part | Role | Examples |
|---|---|---|
| External VI curve tester | Generates the swept signal and X/Y voltages | **ASA VI Curve Tester** (handheld, 2 channels, 4 frequencies), classic Tektronix 576, any analog tracer with X/Y outputs |
| Rigol oscilloscope | Displays the X-Y curve and is read by this software | DHO800/900, MSO5000 |
| PC + this software | Acquires, plots, exports and compares | Blacksmith CurveTracer |

![Required hardware wiring](docs/images/required-hardware-wiring.png)

1. Connect the tester probes to the device under test (DUT).
2. Tester **X output** (or channel X) → scope **CH1** (voltage).
3. Tester **Y output** (or channel Y) → scope **CH2** (current/shunt).
4. Use a common ground between tester and scope.
5. Connect the scope to the PC via LAN or USB.

Depending on the tester, X/Y may be separate jacks or selected by a switch.
The outputs must be analog voltages compatible with the scope inputs; a tester
without X/Y outputs cannot be used with this software.

### Probes and shunt

- Use **1x probes** for best accuracy; set **Probe X/Y** for 10x probes.
- With **Shunt R > 0**, current is `I = V_CH2 / R` and the Y axis is in amperes.
- With **Shunt R = 0**, the Y axis remains in volts.
- The **Y is Direct Current** checkbox is stored in the setup; the numerical
  conversion is driven by **Shunt R**.
- Changing the shunt does not recalculate an existing curve; capture again.

### ASA VI Curve Tester

The **ASA VI Curve Tester** is a low-cost handheld unit with **2 channels and 4
adjustable test frequencies**. Search online for **"ASA VI Curve Tester"** or
**"testador de curva VI ASA"**, or ask a local electronics supplier.

> Marketplace photos are not embedded here because those images are
> copyrighted. If you own an ASA, add your photos to `docs/images/` and
> reference them in this section.

![Example of a curve tracer (Tektronix 576)](docs/images/curve-tracer-example.jpg)

*Example of a real curve tracer (Tektronix 576); the ASA is a compact handheld
alternative. Photo: Shelby Jueden, [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/),
via [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Tek576_CurveTracer_TransistorTest.jpg);
resized for this README. The photo is CC BY-SA 4.0; the rest of the project is MIT.*

---

## Install and run

### Requirements

- **Linux** (tested), **Windows 10/11 64-bit** (tested/build supported).
  macOS is expected to work but is not officially tested.
- **Python 3.11+**. For the Windows `.exe`, use 64-bit Python **3.11–3.13**
  from [python.org](https://www.python.org/downloads/windows/); do not use the
  Microsoft Store alias.
- Runtime packages: `PyVISA`, `PyVISA-py[usb]`, `numpy`, `matplotlib`, `PyQt6`,
  `scipy`, `pyserial`, `psutil`.
- Optional: `PyUSBTMC` for direct USB on Linux; `pyinstaller`/`Pillow`/`pytest`
  for the Windows build.

**USB drivers:** on Windows install **NI-VISA** (recommended) *or* bind the
scope to **WinUSB** with [Zadig](https://zadig.akeo.ie/). On Linux, add a udev
rule if libusb cannot open the device. LAN needs no VISA driver.

### Linux (source)

```bash
git clone <repository-url> curve-tracer-oss
cd curve-tracer-oss
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install PyUSBTMC        # optional: direct USB path
python curvetracer.py
```

If USB access is denied, create `/etc/udev/rules.d/99-rigol.rules`:

```udev
SUBSYSTEM=="usb", ATTR{idVendor}=="1ab1", MODE="0666", GROUP="plugdev"
```

Then `sudo udevadm control --reload-rules && sudo udevadm trigger`.

### Windows

The Windows section is the **single place** for both options: run from source
or build the executable.

#### Option A — run from source

```bat
py -3 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python curvetracer.py
```

#### Option B — build the `.exe` with `build_windows.bat`

> **TL;DR:** install 64-bit Python 3.11–3.13, double-click
> **`build_windows.bat`**, and use `dist\CurveTracer\CurveTracer.exe`.
> Distribute the **whole `dist\CurveTracer` folder**, not only the `.exe`.

```bat
cd /d E:\path\to\curve-tracer-oss
build_windows.bat
```

You can also double-click `build_windows.bat`. If the window closes
immediately, run it from `cmd.exe` to see the error.

The script:

1. finds a supported 64-bit Python;
2. creates/uses `.venv-win`;
3. installs `requirements.txt` and `requirements-build.txt`;
4. runs the automated tests with discovery disabled;
5. generates `docs\images\blacksmith.ico` from `docs\images\blacksmith.jpeg`;
6. builds with `python -m PyInstaller --noconfirm --clean CurveTracer.spec`;
7. runs `dist\CurveTracer\CurveTracer.exe --self-check`;
8. verifies that the executable exists.

Output:

```text
dist\CurveTracer\CurveTracer.exe
```

The folder contains the executable **and** the Python runtime, Qt, NumPy,
SciPy, Matplotlib and USB libraries. Zip and distribute the whole folder.

> **Important:** PyInstaller is not a cross-compiler. A Windows `.exe` must be
> built on Windows (or a Windows CI runner); building on Linux/WSL produces a
> Linux binary.

**Manual build (debugging only):**

```bat
py -3.12 -m venv .venv-win
.venv-win\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-build.txt
python -m unittest discover -s tests
python -m PyInstaller --noconfirm --clean CurveTracer.spec
dist\CurveTracer\CurveTracer.exe --self-check
```

**Run/test the built executable:**

```bat
dist\CurveTracer\CurveTracer.exe
tools\windows\test_exe.bat
tools\windows\test_run.bat
```

The icon comes from `docs/images/blacksmith.jpeg` via `tools/make_icon.py`;
the same image is used as the GUI window icon. Logs from the windowed build:
`%LOCALAPPDATA%\CurveTracer\curvetracer.log`.

**GitHub Actions:** the workflow
[`.github/workflows/build-windows.yml`](.github/workflows/build-windows.yml)
builds on `windows-latest` and uploads the `CurveTracer-windows` artifact.

### macOS (source, experimental)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python curvetracer.py
```

Use PyVISA/NI-VISA or pyvisa-py for the instrument connection.

---

## Quick start

1. Set up the external VI curve tester and wire it to CH1/CH2 (see
   [Hardware you need](#hardware-you-need)).
2. Connect the scope to the PC via LAN or USB.
3. Launch `python curvetracer.py`.
4. Press **Refresh**, select the scope, press **CONNECT**.
5. Configure CH X/Y, probes and shunt; press **CAPTURE**.
6. Use **SAVE Data** for CSV or **COMPONENTS** to store a reference.

---

## Using the GUI

The main window is shown at the top of this README.

### Top bar

| Control | Description |
|---|---|
| **SAVE Setup / LOAD Setup** | Save/load JSON configuration. |
| **Resource** | Editable combo with discovered devices; type a VISA/socket resource if needed. |
| **Refresh** | Re-run USB/LAN discovery. |
| **CONNECT** | Connect/disconnect. |
| **CAPTURE** | Single capture or start/stop real-time. |
| **COMPONENTS** | Open the component registry. |

### Oscilloscope configuration

| Setting | Default | Description |
|---|---|---|
| CH X (Voltage) | `CHAN1` | X-axis channel. |
| CH Y (Current) | `CHAN2` | Y-axis channel. |
| Probe X / Y | `1.0` | Probe attenuation (`0.001`–`10000`). |
| Y is Direct Current | checked | Stored in the setup; see the shunt note. |
| Shunt R (Ω) | `0` | `I = V/R` when > 0; `0` keeps Y in volts. |
| Invert Y | unchecked | Invert the Y sign. |

> On the MSO5000 the X/Y sources are fixed at CH1/CH2. On the DHO800/900 the
> selectors are applied with `:TIMebase:XY:X/Y`.

### Acquisition settings

| Setting | Default | Description |
|---|---|---|
| Update Mode | `Single Capture` | `Single Capture` or `Real-time`. |
| Update Rate | `5.0 s` | Delay between real-time frames (`0.1`–`10.0 s`). |
| Mem Depth | `Auto` | `Auto`, `1k`, `10k`, `100k`, `1M`, `5M`/`10M` (DHO) or `10M`–`200M` (MSO). Values ≤ 1M are read in RAW; Auto/larger use 1,000 screen points. |
| Update | `N/A` | Effective real-time rate. |

### Capture modes

- **Single Capture:** press **CAPTURE**; the acquisition runs in a worker
  thread, the scope stops only to read the frame and resumes in X-Y.
- **Real-time:** select `Real-time`, set the interval, press **CAPTURE**;
  the button becomes **STOP Real-time**.

### Graph and cursor

- **Grid** toggles the graticule.
- **Cursor**: `Off`, `Free` (follows the mouse) or `Single-Plot` (click to
  place/move). Values include shunt conversion.
- **SAVE Data / LOAD Data / PRINT Screen**: CSV and PNG/JPG output.

### Display states

| State | What is shown |
|---|---|
| Opened, not connected | Centered “No data” hint. |
| Connected, no capture | Empty 8 x 8 graticule at the scope's scale/offset. |
| After capture / LOAD Data | Graticule + curve at the instrument scale. |

---

## Capture pipeline and memory depth

For each capture:

1. Identify the instrument with `*IDN?` and select the DHO/MSO dialect.
2. Ensure X-Y mode: DHO `:TIMebase:XY:ENABle ON`; MSO `:TIMebase:MODE XY`.
3. Sync X/Y sources (DHO `:TIMebase:XY:X/Y`; MSO fixed CH1/CH2).
4. Stop the acquisition so both channels come from the same frame.
5. Check channel display with `:CHANnel<n>:DISPlay?`; avoid redundant
   `DISP ON` writes.
6. Configure `:WAVeform:SOURce/MODE/FORMat` and `:STARt`/`:STOP`; read the
   preamble.
7. Read `:WAVeform:DATA?`, parse the TMC block and convert with
   `V = (raw - YREFerence - YORigin) * YINCrement`.
8. Pair channels by index, apply probe/shunt/invert, then resume acquisition.

### Memory depth and points

The **Mem Depth** selector sets `:ACQuire:MDEPth` (default **Auto**):

| Selected depth | Mode | Points per channel |
|---|---|---|
| `Auto` with depth ≤ 1M | `RAW` | current memory depth |
| `Auto` with depth > 1M | `NORM` | 1,000 screen points |
| `1k`, `10k`, `100k`, `1M` | `RAW` | exactly the selected depth |
| `5M`…`200M` | `NORM` | 1,000 screen points |

`WAVEFORM_MAX_POINTS = 1_000_000` is a transfer/plotting safety cap, not an
instrument limit. The selected depth stays for the session; on disconnect the
driver restores `Auto`. The MSO may split large RAW blocks into ~200 KB USBTMC
transfers; the driver joins them.

---

## Display scale and math

Both families use a **square 8 x 8 X-Y graticule**:

```text
span   = 8 * Volts_per_division
center = -offset
min    = center - span/2
max    = center + span/2
```

This follows `V = (raw - YREFerence - YORigin) * YINCrement`; at the screen
center `V = -offset`. The GUI applies the same convention. Shunt conversion
also divides the Y scale/center by `R`; probes multiply the channel data.

| Instrument X-Y screen | GUI |
|---|---|
| ![MSO5074 X-Y screen](docs/images/mso5074-xy-screen.png) | ![GUI curve](docs/images/gui-curve-example.png) |

No axis normalization is applied: original sample pairs are preserved, a
vertical line stays vertical and capacitor ellipses keep their shape.

---

## Data formats

**CSV** (`SAVE Data`/`LOAD Data`):

```csv
Voltage_V,Current_A
-1.234,0.000123
```

Samples are written in acquisition order. `LOAD Data` accepts `Voltage_V`/
`Current_A`, `V`/`I` or `X`/`Y`, and two-column files without a header. With
`Shunt R = 0` the second column is the Y-axis voltage; the header remains
`Current_A`.

**Setup JSON** keys: `resource`, `ch_x`, `ch_y`, `probe_x`, `probe_y`,
`y_direct`, `shunt`, `invert`, `update_mode`, `update_rate`, `mem_depth`.
Loading adds the saved resource to the combo if needed.

---

## Component registry

Open with **COMPONENTS**. It is a separate, non-modal window with three tabs.

![Component registry](docs/images/component-registry.png)

- **Profile & Pins:** reference image, metadata, pin table and normalized
  pin positions on the image (`0..1`).
- **Captures:** **CAPTURE Now + SAVE**, **SAVE Current Capture**, **IMPORT
  CSV**. Every sample is stored in acquisition order with units and label.
- **Compare:** select a saved reference, press **USE Current Capture** (or
  **CAPTURE + COMPARE**) and **COMPARE**.

The comparison reports method, sample count, RMS/NRMSE, maximum/P95 deviation,
correlation and a verdict:

| Verdict | Criterion (default tolerance 5% of reference Y span) |
|---|---|
| **MATCH** | NRMSE ≤ tolerance, max deviation ≤ 2× tolerance, correlation ≥ 0.90 |
| **WARNING** | NRMSE ≤ 2× tolerance, max deviation ≤ 4× tolerance |
| **DEVIATION** | beyond warning limits |

Monotonic curves use interpolation; loops use a geometric nearest-neighbor
method. Stored samples are never sorted, smoothed or modified; units must match.

![Reference vs. live comparison](docs/images/component-compare.png)

Database: `~/.curvetracer/components.db`; override with `CURVETRACER_DB`.
Images are BLOBs, captures are JSON arrays. Deleting a component removes its
pins/captures; deleting a pin keeps its captures.

---

## SCPI compatibility

| Command | DHO800/900 | MSO5000 | Notes |
|---|---|---|---|
| `*IDN?` | ✅ | ✅ | Family detection |
| `:RUN` / `:STOP` / `:SING` | ✅ | ✅ | Acquisition |
| `:TIMebase:MODE XY` | ✅ | ✅ | X-Y on MSO; valid on DHO |
| `:TIMebase:MODE?` | ✅ | ✅ | DHO returns MAIN/ROLL; MSO returns XY |
| `:TIMebase:XY:ENABle` | ✅ | ❌ | DHO X-Y enable |
| `:TIMebase:XY:X/Y` | ✅ | ❌ | DHO X/Y sources |
| `:CHANnel<n>:SCALe?` / `:OFFSet?` | ✅ | ✅ | Scale/offset |
| `:CHANnel<n>:DISPlay?` | ✅ | ✅ | Display state |
| `:WAVeform:SOURce/MODE/FORMat` | ✅ | ✅ | Waveform setup |
| `:WAVeform:STARt/STOP` | ✅ | ✅ | RAW range |
| `:WAVeform:PREamble?` / `:DATA?` | ✅ | ✅ | Preamble/TMC data |
| `:ACQuire:MDEPth?` | ✅ | ✅ | Mem Depth selection |
| `:ACQuire:SRATe?` | ✅ | ✅ | Sample rate |
| `:SYSTem:ERRor?` | ✅ | ✅ | Error queue |

Reference PDFs: [`docs/`](docs/): DHO800900 guide and MSO5000 guide.

---

## Configuration and environment

| Variable | Effect |
|---|---|
| `CURVETRACER_DB` | Component SQLite database path. |
| `CURVETRACER_SKIP_DISCOVERY` | Skip USB/LAN discovery in the GUI. |
| `CURVETRACER_NO_DISCOVERY` | Alias for the above. |
| `QT_QPA_PLATFORM` | `offscreen` for headless tests; Linux defaults to `xcb`. |
| `LOCALAPPDATA` | Windows log directory for the frozen app. |

Headless tests:

```bash
QT_QPA_PLATFORM=offscreen \
CURVETRACER_SKIP_DISCOVERY=1 \
CURVETRACER_NO_DISCOVERY=1 \
python -m pytest tests -q
```

---

## Testing

```bash
python -m pytest tests -q
python -m unittest discover -s tests
```

**131 tests** pass on Linux. On Windows without `PyUSBTMC`, two hardware-only
tests are skipped (129 passed, 2 skipped). `pytest.ini` restricts collection to
`tests/`; manual hardware scripts are in `tools/diagnostics/` and are not run
by CI or by `build_windows.bat`.

Main files: `test_scope_commands.py`, `test_iv_reconstruction.py`,
`test_gui_states.py`, `test_mso_compat.py`, `test_component_db.py`,
`test_component_compare.py`, `test_component_gui.py`, `test_curvetracer.py`.

Validated on real hardware: DHO924S (LAN) and MSO5074 (USB), including 10k/
100k/1M RAW captures and Auto/NORM.

---

## Troubleshooting

- **Not discovered:** check LAN/subnet/firewall port 5555; on USB click
  **Refresh** and check `lsusb`/udev (Linux) or NI-VISA/WinUSB (Windows).
  Discovery scans up to 1022 hosts; typing the resource directly works.
- **USB timeout on MSO:** the driver uses a “lite” USBTMC init without
  `GET_CAPABILITIES`; if it still fails, power-cycle the scope with the cable
  connected, reconnect, or use LAN.
- **Only a small arc / wrong curve:** use **Mem Depth Auto** (NORM screen
  points) or an explicit depth ≤ 1M; check CH1=X/CH2=Y, probes, shunt and
  **Invert Y**.
- **No data:** confirm channels are displayed and the scope is in X-Y; check
  `:SYST:ERR?` in the log.
- **Setup save/load:** the Resource field is editable; loading adds the saved
  resource to the list.
- **Windows logs:** `%LOCALAPPDATA%\CurveTracer\curvetracer.log`.

---

## Performance and limitations

| Operation | DHO924S (LAN) | MSO5074 (USB) |
|---|---|---|
| Connect + IDN | ~1 s | ~0.6–1.3 s |
| Auto (NORM 1,000 pts on MSO) | ~2 s | ~2 s |
| 10k RAW | ~2 s | ~2 s |
| 1M RAW | — | ~2.5 s capture (~4 s with plot) |

- **MSO X-Y sources are fixed at CH1/CH2.**
- **Memory depth is user-selected** (default Auto); on disconnect Auto is
  restored. If the app is killed, check the scope's Mem Depth menu.
- **1M-point RAW cap** is a plotting/transfer limit; larger depths use NORM.
- **8 x 8 graticule** on both families.
- **Y is Direct Current** is stored but conversion uses **Shunt R**.
- **CSV header** is fixed; with no shunt the second column is volts.
- `src/driver.py` and `src/discovery.py` are auxiliary/legacy; the GUI uses
  `src/scope_xy.py`.
- macOS is not officially tested; Windows `.exe` must be built on Windows.
- Firmware validated on DHO924S `00.01.04` and MSO5074 `00.01.03.03.00`.

---

## Project structure

```text
curve-tracer-oss/
├── curvetracer.py              # entry point + --self-check
├── CurveTracer.spec            # PyInstaller build
├── build_windows.bat           # Windows .exe build
├── pytest.ini                  # collects only tests/
├── requirements*.txt
├── LICENSE / README*.md / CHANGELOG.md
├── docs/
│   ├── BUILD_WINDOWS.md, USAGE.md, RIGOL_XY.md, ROADMAP.md
│   ├── DHO800900_ProgrammingGuide_EN.pdf, MSO5_programming_guide.pdf
│   ├── images/                 # screenshots + attributions
│   └── internal/               # historical refactoring notes
├── examples/
│   ├── rigol_xy_capture.py
│   └── data/                   # sample CSV curves
├── src/
│   ├── scope_xy.py             # transport + SCPI + X-Y capture
│   ├── gui.py                  # PyQt6 main window
│   ├── component_db.py, component_compare.py, component_gui.py
│   ├── driver.py, discovery.py, curve_reconstruct.py, simulator.py
├── tools/
│   ├── make_icon.py, compatibility_matrix.py, install-ni-visa.sh
│   ├── diagnostics/            # manual hardware scripts (not CI)
│   └── windows/                # executable test helpers
└── tests/                      # 131 automated tests
```

---

## Development

- Run from source: `python curvetracer.py` or `python src/gui.py`.
- Add SCPI features in `src/scope_xy.py`; check both PDFs and gate
  family-specific commands with `_is_mso_family()`.
- Add tests under `tests/` (no hardware); use `tools/diagnostics/` only for
  manual hardware probes.
- Keep GUI/instrument I/O in worker threads; never sort, smooth or rewrite
  acquired samples.
- Validate on real hardware when changing SCPI behavior.

---

## Safety, license and contributing

**Safety:** start with low voltages/currents, use a current limit, respect
probe/scope/DUT ratings, use proper grounding/isolation, and never exceed the
DUT limits. The authors are not responsible for damage or injury.

**License:** MIT — see [LICENSE](LICENSE).

**Contributing:** fork, create a branch, add tests, run the suite, validate on
hardware when relevant, and submit a PR. Bug reports should include the
`*IDN?`, connection method, OS/Python version, error text and reproduction
steps.

**Acknowledgments:** Rigol for the programming guides and instruments; the
PyVISA, PyUSBTMC, PyQt6, Matplotlib, NumPy and SciPy communities; and the
original CurveTracer OSS contributors.

---

## Donations

If this project helped you:

**Bitcoin (BTC):**

```text
bc1q2p5mpsulcger8af3fp2e2rj4hehtmul5zt5fsr
```

No obligation — code contributions, bug reports and hardware feedback are just
as valuable.

---

See [CHANGELOG.md](CHANGELOG.md) for version history (current: **2.1.0**).
More detailed guides: [docs/USAGE.md](docs/USAGE.md),
[docs/BUILD_WINDOWS.md](docs/BUILD_WINDOWS.md),
[docs/RIGOL_XY.md](docs/RIGOL_XY.md).
