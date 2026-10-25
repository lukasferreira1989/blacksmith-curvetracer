# CurveTracer OSS - Rigol DHO Edition

An oscilloscope-based open source curve tracer for analog circuit characterization using Rigol DHO800/DHO900 series oscilloscopes.

## Overview

This project provides a curve tracing solution for semiconductor device and analog circuit characterization, using a Rigol DHO800/DHO900 oscilloscope in X-Y mode to visualize V-I characteristics from an external analog curve tracer.

### Architecture

```
PC (Python) + PyVISA
    ↓
Rigol DHO800/DHO900 Oscilloscope (via LAN/USB)
    ↓
X-Y Mode (Channel 1 = V, Channel 2 = I via Shunt)
    ↓
External Analog Curve Tracer (generates V-I curves)
```

### Features

- **I-V Curve Visualization**: Real-time display of diode, transistor, MOSFET characteristics
- **Rigol DHO Integration**: Direct SCPI control via PyVISA or socket interface
- **X-Y Mode**: Proper oscilloscope configuration for curve tracing
- **Data Export**: CSV format with voltage/current values
- **Setup Management**: Save/load configurations in JSON
- **Multiple Update Modes**: Single capture or real-time streaming

## Supported Hardware

### Oscilloscopes
- Rigol DHO800 series (DHO820, DHO840, DHO860, DHO880)
- Rigol DHO900 series (DHO920, DHO940, DHO960, DHO980)
- Other Rigol oscilloscopes compatible with DHO SCPI commands

### Connection Methods
- **LAN (TCP/IP)**: Recommended for stable, high-speed communication
- **USB**: Alternative for direct PC connection

## Installation

```bash
# Clone or copy the project
cd curve-tracer-oss

# Install dependencies
pip install -r requirements.txt

# Launch the application
python -m curve_tracer
```

## Usage

### Initial Setup

1. **Connect the curve tracer**:
   - Connect the analog curve tracer output to Channel 1 (X-axis = Voltage)
   - Connect the shunt resistor output to Channel 2 (Y-axis = Current)
   - Ensure proper探头 attenuation settings (1x typically recommended)

2. **Connect the oscilloscope**:
   - Connect Rigol DHO to your PC via LAN or USB
   - Determine the VISA resource name (e.g., `TCPIP::192.168.1.150::INSTR`)

3. **Configure the application**:
   - Launch CurveTracer OSS
   - Enter the oscilloscope resource name or use Auto-Discover
   - Click CONNECT

### Acquisition Modes

#### Single Capture Mode
1. Configure channel settings (CH1=X, CH2=Y, probe ratios, etc.)
2. Click CAPTURE to acquire a single curve
3. Data auto-plots to the graph area
4. Use STOP to abort if needed

#### Real-time Mode
1. Select "Real-time" in Update Mode
2. Adjust update rate as needed
3. Click CAPTURE to start streaming
4. Click STOP or CAPTURE (now "STOP Real-time") to stop

### Channel Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| CH X | CHAN1 | Channel for voltage (X-axis) |
| CH Y | CHAN2 | Channel for current (Y-axis) |
| Probe X | 1.0 | Voltage probe attenuation |
| Probe Y | 1.0 | Current probe attenuation |
| Y is Direct Current | ✓ | Current mode (shunt resistor not needed) |
| Shunt R | 0 Ω | Shunt resistor value in ohms |
| Invert Y | ✗ | Invert current sign |

### Data Export

- **SAVE Data**: Exportes current graph data to CSV
- **LOAD Data**: Import CSV data for offline analysis
- **PRINT Screen**: Save screenshot as PNG/JPG

## SCPI Commands Reference

The application uses these Rigol DHO SCPI commands:

### Waveform Control
- `:WAV:SOUR <CHAN1|CHAN2>` - Set source channel
- `:WAV:MODE NORM` - Normal sampling mode
- `:WAV:FORM BYTE` - Byte format for data
- `:WAV:PRE?` - Get waveform preamble
- `:WAV:DATA?` - Get waveform data

### Channel Configuration
- `:CHAN{}:DISP <ON|OFF>` - Display channel
- `:CHAN{}:COUP <AC|DC|GND>` - Coupling
- `:CHAN{}:SCAL <val>` - Volts per division
- `:CHAN{}:OFFS <val>` - Vertical offset
- `:CHAN{}:PROB <ratio>` - Probe attenuation

### Acquisition Control
- `:RUN` - Continuous acquisition
- `:STOP` - Stop acquisition
- `:SING` - Single sweep mode

### System
- `*IDN?` - Identity query

## Troubleshooting

### Connection Issues
- **"Failed to connect"**: Check IP address, firewall, and oscilloscope network settings
- **Timeout errors**: Increase timeout in code or check network latency
- **No resource found**: Verify oscilloscope is connected and powered on

### Capture Issues
- **Empty data**: Ensure channels are displayed on oscilloscope
- **Noisy data**: Check probe connections and trigger settings
- **Wrong curve shape**: Verify channel mapping (CH1=X, CH2=Y) and probe settings

### Data Quality
- **Discontinuities**: Increase sweep points or adjust time scale
- **Clipping**: Adjust channel scale or use higher probe attenuation
- **Offset issues**: Check channel offset and shunt resistor value

## Development

### Code Structure
```
src/
├── scope_xy.py     # Rigol DHO interface (PyVISA + SCPI)
├── gui.py          # PyQt6 GUI
└── curve_tracer.py # Legacy - can be removed

docs/
├── DHO800900_ProgrammingGuide_EN.pdf  # SCPI reference
└── USAGE.md        # Usage guide
```

### Adding Features
1. All SCPI commands must follow DHO800/900 Programming Guide
2. Use try/except for all PyVISA/socket operations
3. Test with actual hardware before committing
4. Prefer socket interface for better performance on LAN

## License

MIT License - See LICENSE file for details

## Contributing

1. Fork the repository
2. Create a feature branch
3. Test with Rigol DHO hardware
4. Submit a pull request

## Acknowledgments

- PyVISA for instrument communication
- Rigol for DHO series oscilloscopes and documentation
- Original CurveTracer OSS project by Yokogawa
