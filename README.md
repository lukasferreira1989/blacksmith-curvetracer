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
- `:WAV:MODE <RAW|MAX|NORM>` - Waveform reading mode (RAW preferred, with MAX/NORM fallback)
- `:WAV:FORM BYTE` - Byte format for data
- `:WAV:PRE?` - Get waveform preamble
- `:WAV:DATA?` - Get waveform data

### X-Y Mode
- `:TIM:XY:ENABle <ON|OFF>` - Enable/query X-Y mode
- `:TIM:XY:X?` - Query the channel used for the X axis
- `:TIM:XY:Y?` - Query the channel used for the Y axis
- `:TIM:XY:GRID?` - Query the X-Y grid type (FULL/HALF/NONE)

### Channel Configuration
- `:CHAN{}:DISP <ON|OFF>` - Display channel (queried before writing; re-sending `ON` clears the X-Y trace until the next acquisition)
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

## X-Y Display Scale (GUI)

The GUI reproduces the DHO X-Y graticule:

- **8 vertical divisions per axis**, with a square plot area, so one X
  division occupies the same screen space as one Y division.
- **Span of each axis = 8 x Volts/div** of the corresponding channel
  (`:CHAN<n>:SCAL?`). Example: CH1 200 mV/div -> 1.6 V total; CH2 1 V/div ->
  8 V total.
- **Center of each axis = `-offset`**, where `offset` is read from
  `:CHAN<n>:OFFS?`. This follows the DHO manual, which defines the screen
  limits as `±4 x VerticalScale - OFFSet`; it is also confirmed by the
  preamble formula `V = (raw - YREFerence - YORigin) * YINCrement` (at screen
  center `raw == YREFerence`, hence `V == -offset`). Example: offset `+8.78 mV`
  -> center `-8.78 mV` on the scope (and in the GUI).
- **No normalization between axes.** The original sample pairs and their
  physical units are preserved; a vertical line remains vertical and
  capacitor ellipses keep the same proportions relative to the graticule
  (same number of divisions per axis) as on the instrument.
- **Single capture freezes the scope** (`:STOP`) and keeps it in X-Y mode, so
  the GUI and the instrument display can be compared frame by frame. The
  scope is not resumed automatically; use RUN on the instrument or Real-time
  mode to continue.

### Verified DHO924S behavior

- IDN: `RIGOL TECHNOLOGIES,DHO924S,DHO9S261401341,00.01.04`.
- With CH1 `0.2 V/div` and CH2 `1 V/div`, the GUI axes are 1.6 V and 8 V
  wide, centered at `-offset`, with 8 divisions each.
- The X-Y trace remains on the instrument after capture when the driver:
  - queries `:CHAN<n>:DISP?` before ever writing `DISP ON`;
  - only writes `:TIM:XY:X/Y` when the source actually changes;
  - keeps `:TIM:XY:ENABle` on and leaves the acquisition stopped.
- Re-sending `DISP ON` or `TIM:XY:X/Y` with unchanged values clears the X-Y
  trace until the next acquisition (observed on hardware); the driver avoids
  those redundant writes.

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
├── scope_xy.py        # Rigol DHO interface (PyVISA + SCPI), X-Y capture
├── gui.py             # PyQt6 GUI and 8x8 X-Y rendering
├── driver.py          # Centralized driver with error queue/logging
├── discovery.py       # LAN/USB Rigol discovery
├── curve_reconstruct.py  # I-V curve reconstruction/validation
└── simulator.py       # Offline simulator for tests without hardware

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


## Atualizações (DHO924S)

- Suporte exclusivo Rigol DHO800/DHO900 via PyVISA/socket (porta 5555)
- Modo X-Y com preservação da ordem temporal original
- Driver centralizado em `src/driver.py`
- Reconstrução I-V em `src/curve_reconstruct.py`
- Testes automatizados para curvas I-V
- Descoberta de rede/USB
- Simulador para testes sem hardware
- Grade X-Y da GUI com 8 divisões por eixo, seguindo `:CHAN<n>:SCAL?`
- Centro de cada eixo em `-offset` (`:CHAN<n>:OFFS?`), conforme manual e
  confirmado no display do DHO924S
- Captura única congela o frame em X-Y e mantém o display do osciloscópio
  visível para comparação
- Escala do eixo Y corrigida quando há shunt (`I = V/R`)
- Corrigido o campo Shunt R: `0` = sem shunt (antes o mínimo `0.001 Ω`
  multiplicava CH2 por 1000 silenciosamente)
- Leitura de socket robusta: drena terminadores pendentes após blobs TMC e
  evita respostas atrasadas corromperem `SCAL?`/`OFFS?`
- Canais X/Y sincronizados com `:TIM:XY:X?`/`:TIM:XY:Y?`

### Testes executados (2026-10-25)

```
python -m unittest tests.test_iv_reconstruction tests.test_curvetracer -v
Ran 27 tests in ~5 s
OK
```

Validação em hardware real (DHO924S em `192.168.68.104:5555`):
- CH1 `0.2 V/div`, CH2 `1 V/div`
- GUI: X = `-0.82420 .. +0.77580 V`, Y = `-4.00878 .. +3.99122 V`
- Centro X = `-24.2 mV`, centro Y = `-8.781 mV` (iguais ao display)
- `:TIM:XY:ENABle?` permaneceu `1` após a captura
- O traço X-Y continuou visível no osciloscópio após a captura
