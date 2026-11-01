# Usando com traçador analógico + Rigol (modo X-Y)

## Setup
1. Conecte o traçador analógico em modo X-Y
2. Saída X -> Canal 1 do osciloscópio
3. Saída Y/I -> Canal 2 do osciloscópio
4. Mantenha sondas em 1x (padrão)
5. Conecte o Rigol por LAN ou USB

## Descobrir IP/endereço
```bash
cd /mnt/e/CurveTracer215e/curve-tracer-oss
source .venv/bin/activate
PYTHONPATH=$(pwd) python examples/rigol_xy_capture.py
```

## Teste direto
```bash
PYTHONPATH=$(pwd) python examples/rigol_xy_capture.py TCPIP::192.168.1.150::INSTR
```

O arquivo `examples/data/curve_xy.csv` será gerado com `V_X(V), I_Y(A_or_V)`

## Na GUI
1. Ative "Analog Curve Tracer (X-Y via Oscilloscope)"
2. Preencha o resource ou deixe auto-detect
3. Configure CH1/CH2 conforme seu cabo
4. "Y is direct current" geralmente fica marcado (caso contrário use Shunt R)
5. Clique em "Capture Curve / Start Measurement"
