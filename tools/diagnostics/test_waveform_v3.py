#!/usr/bin/env python3
"""
Teste USB-TMC usando read_raw/write_raw para evitar problemas de encoding
"""

import pyvisa
import time
import numpy as np

print("=" * 60)
print("TESTE USB-TMC V3 - Sem decode automático")
print("=" * 60)

rm = pyvisa.ResourceManager('@py')
resource = 'USB0::6833::1100::DHO9S261401341::0::INSTR'

try:
    inst = rm.open_resource(resource)
    inst.timeout = 20000
    # Não usar read_termination para comandos que misturam texto e binário
    inst.read_termination = None
    inst.write_termination = None
    
    print(f"\n[1] IDN via query()...")
    try:
        idn = inst.query('*IDN?')
        print(f"  IDN: {idn.strip()}")
    except UnicodeDecodeError as e:
        print(f"  UnicodeDecodeError: {e}")
        # Fallback para read_raw
        inst.write('*IDN?')
        time.sleep(0.5)
        raw = inst.read_raw()
        idn_str = raw.decode('latin-1').strip()
        print(f"  IDN (latin-1): {idn_str}")
    
    # Teste waveform com read_raw/write_raw
    print("\n[2] Configurando waveform...")
    inst.write(':WAV:MODE NORM')
    time.sleep(0.1)
    inst.write(':WAV:FORMAT BYTE')
    time.sleep(0.1)
    inst.write(':WAV:SOURCE CHAN1')
    time.sleep(0.1)
    
    # Teste: ler preâmbulo
    print("\n[3] Ler preâmbulo com read_raw...")
    inst.write(':WAV:PRE?')
    time.sleep(1.0)
    raw_preamble = inst.read_raw()
    print(f"  Raw preamble: {raw_preamble[:100]}")
    
    preamble_text = raw_preamble.decode('latin-1').strip()
    print(f"  Decoded: {preamble_text}")
    
    parts = preamble_text.split(',')
    if len(parts) >= 10:
        print(f"  Format: {parts[0]}, Points: {parts[2]}, Inc: {parts[3]}")
    
    # Teste: ler waveform
    print("\n[4] Ler waveform com read_raw...")
    inst.write(':WAV:DATA?')
    time.sleep(1.0)  # mais tempo para garantir que os dados estão prontos
    
    start = time.time()
    raw_data = inst.read_raw()
    elapsed = time.time() - start
    print(f"  Tempo: {elapsed*1000:.1f}ms")
    print(f"  Tamanho: {len(raw_data)} bytes")
    print(f"  Primeiros 100 bytes: {raw_data[:100]}")
    
    # Parsing
    if raw_data.startswith(b'#'):
        try:
            if len(raw_data) > 1 and chr(raw_data[1]).isdigit():
                num_digits = int(chr(raw_data[1]))
                data_start = 2 + num_digits
                data = raw_data[data_start:]
                
                print(f"  Data start: {data_start}")
                print(f"  Dados: {len(data)} bytes")
                print(f"  Min/Max: {min(data)}/{max(data)}")
                print(f"  Primeiros 20: {list(data[:20])}")
                
        except Exception as e:
            print(f"  Parse error: {e}")
    
    inst.close()
    
except Exception as e:
    print(f"\nErro: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
