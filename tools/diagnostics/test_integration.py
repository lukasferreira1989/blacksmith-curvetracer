#!/usr/bin/env python3
"""Testing PyVISA-py USB-TMC integration"""

import sys
sys.path.insert(0, '/home/lucas/Documentos/curve-tracer-oss')

from src.scope_xy import RigolScopeXY

print("Testing PyVISA-py USB-TMC connection...")

# Testar conexão com o device USB
scope = RigolScopeXY('USB0::6833::1100::DHO9S261401341::0::INSTR')

print(f"Connected: {scope.connected}")
print(f"IDN: {scope.get_idn()}")

# Testar waveform
scope._write(':WAV:MODE NORM')
scope._write(':WAV:FORMAT BYTE')
scope._write(':WAV:SOURCE CHAN1')

import time
time.sleep(0.5)

data = scope._query_binary(':WAV:DATA?')
print(f"Waveform data length: {len(data)}")
print(f"First 10 values: {data[:10]}")
print(f"Min/Max: {data.min()}/{data.max()}")

print("Test completed successfully!")
