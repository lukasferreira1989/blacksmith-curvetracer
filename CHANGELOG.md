# Changelog - CurveTracer OSS

## [2.1.0] - 2026-10-31

### Added

- **ADDED**: Rigol MSO5000 series support (MSO5072/5074/5102/5104/5204/5354)
  - Model detection from `*IDN?` (`_is_mso_family`)
  - X-Y mode via `:TIMebase:MODE XY` (the DHO-only `:TIMebase:XY:*`
    commands are not sent to the MSO)
  - MSO X-Y uses fixed sources CH1 (X) and CH2 (Y), as forced by the
    instrument
  - RAW waveform reads explicitly set `:WAVeform:STARt/.STOP`
  - MSO captures 10,000 RAW points by temporarily using a 10k memory
    depth; screen `NORM` data is the fallback when the depth cannot be
    reduced

### Fixed

- **FIXED**: PyUSBTMC queries on MSO5074
  - Use the USBTMC terminator character (`flag`/`termChar`) and retry once
    if a stale terminator yields an empty response
  - IDN read retries until a valid `RIGOL` response is received
  - USB/TMC resources are always released on failure
  - Automatic fallback from PyUSBTMC to the PyVISA USB resource
- **FIXED**: MSO5074 USB connection when `GET_CAPABILITIES` times out
  - The device can stop answering class control requests while its bulk
    endpoints keep working. A "lite" `USBTMC_device` is built without
    `GET_CAPABILITIES`, using only the bulk endpoints needed by SCPI.
- **FIXED**: Truncated waveform blocks on PyUSBTMC
  - The MSO5074 sends a 10 KB TMC block in short USB packets (e.g. 8180 +
    1832 bytes). The binary reader now joins the continuation packets up to
    the USBTMC `TransferSize`.
- **FIXED**: Stale responses after a timeout
  - Connect reads until the real `*IDN?` response (draining an old pending
    response), and a failed capture resynchronizes the USBTMC buffer.
- **FIXED**: MSO5000 X-Y drawing did not match the instrument screen
  - On the MSO, `RAW` reads the start of a 25 Mpts memory (a few
    microseconds), not the displayed time window. The driver now temporarily
    sets `:ACQ:MDEP 10k` on the first capture so `RAW` returns 10,000 points
    covering the whole screen; `AUTO` is restored on disconnect.
  - If the memory depth is not reduced, the driver falls back to `NORM`
    (screen data, 1,000 points), which also matches the display.
  - The MSO5000 X-Y graticule is also 8 x 8 divisions (a square X-Y area);
    the GUI uses 8 divisions on both axes for both families.
- **FIXED**: Channel scale/offset queries use the documented
  `:CHANnel<n>:SCALe?` / `:OFFSet?` form for both families
- **FIXED**: GUI keeps drawing the grid when a scale/offset query times out

## [2.0.0] - 2026-10-24

### Breaking Changes

- **REMOVED**: Support for Yokogawa GS610/GS820 SMU instruments
  - Deleted: `src/curve_tracer.py` (legacy SMU control code)
  - Deleted: `src/gui_faithful.py` (legacy SMU GUI)
  
- **REMOVED**: All SMU-specific GUI elements
  - Sweep settings (start/stop, points, form, etc.)
  - SMU channel configuration
  - BJT/FET measurement setup
  - Compliance limiting

### Added

- **ADDED**: Rigol DHO800/DHO900 oscilloscope support
  - Full SCPI command implementation per DHO800900 Programming Guide
  - Socket interface (port 5555) support
  - PyVISA VISA interface support
  - Binary waveform transfer with TMC header parsing
  - Waveform preamble extraction

- **ADDED**: Enhanced scope_xy.py interface
  - `RigolScopeXY` class with complete SCPI implementation
  - `capture_xy()` for proper X-Y mode capture
  - `discover_rigol()` for auto-detection
  - Channel configuration methods
  - Robust error handling with try/except

- **ADDED**: Updated GUI optimized for oscilloscope X-Y mode
  - Cleaner interface without SMU clutter
  - Real-time streaming mode
  - Better status indicators
  - Improved error messages

### Changed

- **CHANGED**: GUI now exclusively for X-Y mode
  - CH X/CH Y configuration for oscilloscope
  - Probe attenuation settings
  - Shunt resistor current calculation
  - Y-axis inversion control

- **CHANGED**: Example script updated
  - `examples/rigol_xy_capture.py` now uses `src/scope_xy.py`

### Fixed

- **FIXED**: SCPI commands now comply with DHO800/DHO900 official docs
- **FIXED**: Waveform data acquisition sequence
- **FIXED**: Binary data TMC header parsing
- **FIXED**: Error handling for connection timeouts
- **FIXED**: Channel scaling calculations

### Documentation

- **UPDATED**: README.md with Rigol DHO focus
- **UPDATED**: USAGE.md with oscilloscope setup
- **ADDED**: MANIFEST.md for legacy removal documentation
- **ADDED**: REFACTORING_SUMMARY.md for technical details
- **UPDATED**: docs/DHO800900_ProgrammingGuide_EN.pdf (referenced)

### Technical Details

#### SCPI Commands Verified
- `:RUN`, `:STOP`, `:SING` - Acquisition control
- `:WAV:SOUR`, `:WAV:MODE`, `:WAV:FORM` - Waveform settings
- `:WAV:PRE?`, `:WAV:DATA?` - Data transfer
- `:CHAN{n}:DISP`, `:CHAN{n}:COUP`, `:CHAN{n}:SCAL`, `:CHAN{n}:OFFS` - Channel settings

#### Testing
- ✅ Import scope_xy.py
- ✅ Import gui.py
- ✅ Auto-discovery (no device - expected failure)
- ✅ Connection error handling

---

## [1.0.0] - Initial Release

- Original CurveTracer OSS implementation
- Yokogawa GS610/GS820 support
- SMU-based I-V curve tracing
- Basic PyQt6 GUI

---

*Note: Version 2.0.0 is a complete refactor focused exclusively on Rigol DHO oscilloscopes.*
