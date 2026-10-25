# Usage Guide - Rigol DHO Edition

## Quick Start

1. Connect your Rigol DHO800/DHO900 oscilloscope to the analog curve tracer
2. Connect the oscilloscope to your PC via LAN or USB
3. Launch CurveTracer OSS
4. Enter the VISA resource name (e.g., `TCPIP::192.168.1.150::INSTR`)
5. Click CONNECT
6. Configure channels (CH1=X/Voltage, CH2=Y/Current)
7. Click CAPTURE

## Hardware Setup

### Wiring

1. **Analog Curve Tracer Output → Oscilloscope CH1 (X-axis)**
   - This input represents voltage (V) across the device under test

2. **Shunt Resistor Output → Oscilloscope CH2 (Y-axis)**
   - This input represents current (I) through the device
   - Current is calculated as V_shunt / R_shunt

3. **Probe Settings**
   - Use 1x probes for best accuracy
   - Adjust Probe X and Probe Y values if using 10x probes

### Oscilloscope Requirements

- DHO800 or DHO900 series oscilloscope
- Oscilloscope must be accessible via LAN (TCP/IP) or USB
- SCPI command set compatible with DHO800/DHO900 Programming Guide

## Measurement Operations

### Single Capture (Default Mode)

This mode captures one complete curve per click.

1. **Configure acquisition settings**:
   - Channel selections (CH1, CH2)
   - Probe attenuation factors
   - Shunt resistor value (if needed)

2. **Capture**:
   - Click CAPTURE button
   - Wait for acquisition to complete
   - Curve plots automatically

3. **Stop**:
   - Click STOP to abort
   - Single capture reads a fixed frame and then resumes the oscilloscope in
     X-Y mode; the GUI keeps the captured frame and the instrument continues
     running

### X-Y Display in the GUI

The graph mirrors the DHO X-Y screen:

- 8 divisions on each axis, with a square plotting area.
- Each axis spans `8 x Volts/div` of its channel (`:CHAN<n>:SCAL?`).
- The center of each axis is `-offset` (`:CHAN<n>:OFFS?`), matching the
  scope's graticule. Example: CH2 offset `8.78 mV` -> center `-8.78 mV`.
- Samples are plotted in acquisition order; no sorting, smoothing, or
  artificial closing is applied.
- Both Single Capture and Real-time leave the oscilloscope running in X-Y
  after the transfer; Single Capture stops only long enough to read a fixed
  frame.

### Display States

- **Program opened, not connected**: no graph is drawn; only a centered
  "No data / Connect to the oscilloscope and capture" hint is shown.
- **Connected, no capture yet**: the GUI shows only the 8 x 8 graticule,
  using the instrument's current `:CHAN<n>:SCAL?` and `:CHAN<n>:OFFS?` values.
  Changing the X/Y channel selectors or the shunt refreshes this empty grid.
- **After CAPTURE or LOAD Data**: the trace is drawn over the same graticule.
- Disconnecting returns to the no-data state and clears the loaded trace.

### Cursor

The **Cursor** selector controls the coordinate readout:

| Mode | Behavior |
|---|---|
| Off | No cursor overlay |
| Free | Dashed crosshair follows the mouse; the annotation shows X and Y in physical units |
| Single-Plot | Click to place a persistent crosshair; click again to move it |

Cursor values use the units of each axis (V/mV/µV and A/mA/µA), including the
`I = V/R` conversion when a shunt is configured.

### Real-time Mode

This mode continuously updates the display.

1. **Enable real-time**:
   - Change Update Mode dropdown to "Real-time"
   - Adjust Update Rate (0.1-10 seconds)

2. **Start streaming**:
   - Click CAPTURE
   - View real-time updates
   - Click STOP to exit

## Channel Configuration

### Channel X (Voltage Input)

| Setting | Options | Default | Description |
|---------|---------|---------|-------------|
| CH X | CHAN1, CHAN2 | CHAN1 | Input channel for voltage |
| Probe X | 0.001 - 10000 | 1.0 | Probe attenuation factor |

### Channel Y (Current Input)

| Setting | Options | Default | Description |
|---------|---------|---------|-------------|
| CH Y | CHAN1, CHAN2 | CHAN2 | Input channel for current |
| Probe Y | 0.001 - 10000 | 1.0 | Probe attenuation factor |
| Y is Direct Current | ✓/✗ | ✓ | Current mode (no shunt needed) |
| Shunt R (Ω) | 0 - 1000000 | 0 (None) | Shunt resistor value; 0 disables conversion |

### Y-Axis Calculation

The current (Y-axis) is calculated as follows:

```
If Shunt R > 0:
    I = V_shunt / Shunt_R

If Shunt R = 0 and Y is Direct Current:
    I = V_shunt  (assuming probe already converts to current)

If Shunt R = 0 and Y is NOT Direct Current:
    I = V_shunt (keep as voltage)
```

## Device Types

### Diode Characterization
1. Connect diode to curve tracer
2. Ensure channel X shows forward/reverse voltage
3. Click CAPTURE
4. Analyze forward voltage and reverse leakage

### Transistor Characterization
1. Connect transistor to curve tracer
2. Configure base/gate drive
3. Click CAPTURE
4. View transfer characteristics

### MOSFET Characterization
1. Connect MOSFET to curve tracer
2. Configure gate voltage sweep
3. Click CAPTURE
4. View Id-Vds curves

## Configuration Files

### Save Configuration
- Click SAVE Setup to save current settings
- Configuration stored as JSON
- Includes: resource, channels, probes, shunt, updates

### Load Configuration
- Click LOAD Setup to restore settings
- Supports all saved configuration fields

## Data Export

### Save Data (CSV)
1. Click SAVE Data button
2. Enter filename with .csv extension
3. CSV contains: Voltage_V, Current_A columns

### Load Data (CSV)
1. Click LOAD Data button
2. Select previously saved CSV file
3. Data replots to graph area

### Save Screenshot
1. Click PRINT Screen button
2. Select PNG or JPG format
3. High-resolution image saved (150 DPI)

## SCPI Commands Reference

The application uses these Rigol SCPI commands:

| Command | Purpose |
|---------|---------|
| `:RUN` | Start continuous acquisition |
| `:STOP` | Stop acquisition |
| `:SING` | Single sweep trigger |
| `:WAV:SOUR CHAN1` | Set source channel |
| `:WAV:MODE NORM` | Normal sampling |
| `:WAV:FORM BYTE` | Byte data format |
| `:WAV:PRE?` | Get preamble (scaling) |
| `:WAV:DATA?` | Get waveform data |
| `*IDN?` | Get device identity |
| `:CHAN1:SCAL?` | Get vertical scale |

## Troubleshooting

### Cannot Connect
- Verify oscilloscope IP and network connectivity
- Check firewall settings
- Ensure oscilloscope is in remote mode

### No Data Captured
- Verify channels are displayed on oscilloscope
- Check trigger settings on oscilloscope
- Ensure probe connections are secure

### Incorrect Curve Shape
- Verify channel mapping (CH1=X, CH2=Y)
- Check probe attenuation settings
- Verify shunt resistor value

### Data Quality Issues
- Use proper grounding
- Minimize cable length
- Check oscilloscope sampling rate

## Safety

1. **Always start with low voltages**
2. **Verify connections before powering**
3. **Use appropriate current limits**
4. **Ensure proper probe voltage ratings**
5. **Never exceed device under test ratings**

## Support

For issues:
1. Check oscilloscope SCPI compatibility
2. Verify PyVISA installation
3. Test oscilloscope with Rigol'sUltraSig software
4. Review DHO800900 Programming Guide
