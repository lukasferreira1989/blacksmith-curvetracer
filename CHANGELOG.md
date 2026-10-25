# Changelog - CurveTracer OSS

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
