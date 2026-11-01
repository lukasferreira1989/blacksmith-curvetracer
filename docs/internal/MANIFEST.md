# Legacy Code Removal - Blacksmith CurveTracer

## Summary

This document describes the legacy code removal performed during the refactoring of Blacksmith CurveTracer from a multi-instrument SMU-based solution to a Rigol DHO-only oscilloscope solution.

## Removed Files

### `src/curve_tracer.py` (REMOVED)
**Purpose**: Legacy base class for Yokogawa GS610/GS820 SMU instruments  
**Commands**: `:SOUR:VOLT`, `:SOUR:CURR`, `:MEAS:VOLT`, `:MEAS:CURR`, `:OUTP`, `:SENS:CURR:PROT`  
**Status**: **REMOVED** - Not needed for Rigol DHO oscilloscope-only operation

**Reason for removal**:
- This file implemented SMU (Source Measure Unit) control for Yokogawa instruments
- The new scope is explicitly for Rigol DHO oscilloscope X-Y mode
- No source measurement unit functionality is needed when using an external analog curve tracer

### `src/gui_faithful.py` (DEPRECATED - SHOULD BE REMOVED)
**Purpose**: Faithful Yokogawa GS610/GS820 GUI reproduction  
**Commands**: SMU sweep controls, channel 2 support, voltage/current source settings  
**Status**: **DEPRECATED** - Should be removed in future release

**Reason for removal**:
- Contains SMU-specific controls not applicable to oscilloscope mode
- Duplicate functionality with `gui.py`
- Maintainability burden for single-purpose application

### `src/__pycache__/` (CLEANED)
**Purpose**: Python bytecode cache directory  
**Status**: **CLEANED** - Removed during refactoring

## Modified Files

### `src/gui.py` (REFACTORED)
**Before**: Multi-mode GUI (SMU + Oscilloscope)  
**After**: Oscilloscope-only X-Y mode GUI

**Changes**:
- Removed SMU connection controls (CONNECT for Yokogawa)
- Removed sweep settings (start/stop voltage, points, etc.)
- Removed channel configuration for SMU (Function, Plot, Sweep Form)
- Kept only oscilloscope-specific settings:
  - CH X / CH Y selection
  - Probe X / Probe Y attenuation
  - Y is Direct Current toggle
  - Shunt R (Ω) value

### `README.md` (UPDATED)
**Before**: Multi-instrument support (Yokogawa + Rigol)  
**After**: Rigol DHO-only oscilloscope support

**Changes**:
- Removed SMU hardware section
- Added Rigol DHO hardware support list
- Updated architecture diagram

### `docs/USAGE.md` (UPDATED)
**Before**: SMU usage guide with Yokogawa commands  
**After**: Oscilloscope X-Y mode usage guide

**Changes**:
- Removed SMU measurement types (diode, FET, BJT setup for SMU)
- Added oscilloscope setup instructions
- Added channel configuration details

## SCPI Command Changes

### Removed Commands (SMU/Yokogawa)
```
*SOUR:VOLT <val>
*SOUR:CURR <val>
*MEAS:VOLT?
*MEAS:CURR?
*SENS:CURR:PROT <val>
*OUTP ON|OFF
*SENS:VOLT:RANG <val>
*SENS:CURR:RANG <val>
```

### Kept Commands (Rigol DHO oscilloscope)
```
:RUN
:STOP
:SING
:WAV:SOUR <CHAN1|CHAN2>
:WAV:MODE NORM
:WAV:FORM BYTE|WORD|ASC
:WAV:PRE?
:WAV:DATA?
:CHAN{n}:DISP ON|OFF
:CHAN{n}:COUP AC|DC|GND
:CHAN{n}:SCAL <val>
:CHAN{n}:OFFS <val>
:CHAN{n}:PROB <ratio>
:TIM:MAIN:SCAL <val>
*IDN?
*RST
```

## Migration Path for Users

### If you had Yokogawa GS610/GS820 automation:
1. Consider keeping a fork with legacy SMU code
2. Rigol DHO mode is for oscilloscope-based curve tracing only
3. SMU-specific features are not available in this version

### If you used the oscilloscope X-Y mode:
1. No changes needed - this mode is preserved and improved
2. Updated with correct SCPI commands per DHO800/DHO900 guide
3. Better error handling and connection robustness

## Verification Checklist

After refactoring, verify:

- [ ] Oscilloscope connection via VISA works
- [ ] Oscilloscope connection via socket (port 5555) works
- [ ] Channel configuration (CH1/CH2) works
- [ ] Probe attenuation settings work
- [ ] Capture single frame works
- [ ] Real-time mode works
- [ ] Data export to CSV works
- [ ] Setup save/load works
- [ ] Graph plotting works correctly
- [ ] No Yokogawa SMU code remains in codebase

## Future Considerations

If you need SMU functionality:
1. Keep original version in separate branch
2. Create modular design with abstract base classes
3. Implement interface switching for different hardware
4. Consider separate applications per hardware type

## Notes

- All SCPI commands verified against Rigol DHO800/DHO900 Programming Guide
- Socket connection (port 5555) maintained for compatibility with existing setups
- Error handling improved with try/except around all communication
- Code organization: `scope_xy.py` for interface, `gui.py` for display
