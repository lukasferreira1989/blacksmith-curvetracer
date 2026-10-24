# CurveTracer OSS

An open source implementation of Yokogawa CurveTracer functionality for GS610/GS820 Source Measure Units and compatible instruments.

## Overview

This project provides a cross-platform curve tracing solution for semiconductor device characterization, implementing common curve tracer functionality including:

- **I-V Curve Measurements**: Diode, transistor, MOSFET, resistor characterization
- **FET Characterization**: Id-Vd, Id-Vg, Vth measurements  
- **BJT Characterization**: Ic-Vce, Ib-Vbe, hFE measurements
- **Multiple sweep types**: Linear, log, pulsed measurements
- **Graphical plotting**: Real-time curve display
- **Data export**: CSV, JSON, ASCII formats

## Supported Instruments

- Yokogawa GS610
- Yokogawa GS820
- Other SCPI-compatible Source Measure Units

## Features

- Device parameter extraction (Vth, β, Ron, etc.)
- Multiple measurement ranges and auto-ranging
- Pulsed measurement for self-heating reduction
- Compliance limiting and safety features
- Save/load measurement configurations
- Batch measurement automation

## Installation

```bash
pip install -r requirements.txt
python -m curve_tracer
```

## Dependencies

- PyVISA for instrument communication
- NumPy for data processing
- Matplotlib for plotting
- PyQt5/PySide6 for GUI
- Pandas for data export

## License

MIT License
