# Usage Guide

## Quick Start

1. Connect your Yokogawa GS610/GS820 or compatible SMU via USB/GPIB/LAN
2. Launch CurveTracer OSS
3. Select your instrument from the device list
4. Choose measurement type and sweep parameters
5. Click Start Measurement

## Measurement Types

### Diode I-V
Characterizes diode forward/reverse characteristics. Measures current vs voltage.

### FET Output (Id-Vd)
For MOSFET/JFET output characteristics. Vary drain-source voltage for different gate voltages.

### FET Transfer (Id-Vg)
Transfer characteristics. Vary gate voltage at constant drain voltage.

### BJT Output (Ic-Vce)
BJT output characteristics. Vary collector-emitter voltage for different base currents.

## Configuration Files

Measurement configurations can be saved in JSON format for reproducibility.

## SCPI Commands

The software uses standard SCPI commands. For Yokogawa GS series:
- `*IDN?` - Identify instrument
- `:SOUR:VOLT <value>` - Set voltage
- `:MEAS:CURR?` - Measure current
- `:OUTP ON/OFF` - Enable/disable output

## Safety

- Always check compliance limits
- Start with low voltages/currents
- Use proper protection for sensitive devices
- Ensure correct wiring/polarity
