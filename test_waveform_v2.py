#!/usr/bin/env python3
"""
Teste de waveform com PyVISA-py USB-TMC - Correção
"""

import pyvisa
import time
import numpy as np

print("=" * 60)
print("TESTE WAVEFORM - RIGOL DHO924S via USB-TMC")
print("=" * 60)

rm = pyvisa.ResourceManager('@py')
resource = 'USB0::6833::1100::DHO9S261401341::0::INSTR'

try:
    inst = rm.open_resource(resource)
    inst.timeout = 20000
    inst.read_termination = '\r\n'
    inst.write_termination = '\r\n'
    
    # Limpar buffer de erro (clear)
    try:
        inst.write('*CLS')  # Clear status
        time.sleep(0.05)
    except:
        pass
    
    print(f"\n[1] IDN: {inst.query('*IDN?').strip()}")
    
    # Configurar waveform - com delays adequados
    print("\n[2] Configurando waveform...")
    inst.write(':WAV:PRE?')
    time.sleep(1.0)  # esperar resposta completa
    
    # Limpar buffer antes de ler
    try:
        inst.read()
    except:
        pass
    
    preamble_str = inst.query(':WAV:PRE?')
    print(f"  Preâmbulo: {preamble_str[:100]}...")
    
    parts = preamble_str.split(',')
    if len(parts) >= 10:
        fmt = parts[0].strip()
        inc = float(parts[3])
        pt_o = int(parts[4])
        vdiv = float(parts[6])
        voff = float(parts[7])
        points = int(parts[2])
        print(f"  Format: {fmt}, Inc: {inc}s, Points: {points}")
        print(f"  VDiv: {vdiv}V, VOff: {voff}V")
    
    # Configurar modo waveform
    print("\n[3] Configurando modo...")
    inst.write(':WAV:MODE NORM')
    time.sleep(0.1)
    inst.write(':WAV:FORMAT BYTE')
    time.sleep(0.1)
    inst.write(':WAV:SOURCE CHAN1')
    time.sleep(0.1)
    
    # Teste: usar read_raw() para pegar tudo raw
    print("\n[4] Teste read_raw() após ':WAV:DATA?'")
    try:
        inst.write(':WAV:DATA?')
        time.sleep(0.5)  # espera
        
        start = time.time()
        raw_data = inst.read_raw()
        elapsed = time.time() - start
        print(f"  Tempo: {elapsed*1000:.1f}ms")
        print(f"  Tamanho: {len(raw_data)} bytes")
        print(f"  First 50 bytes: {raw_data[:50]}")
        
        # Parsing do formato
        # '#9000001000' = # + 9 (número de dígitos) + 000001000 (1000 bytes)
        if raw_data.startswith(b'#'):
            # Encontrar o fim do tamanho
            try:
                # Formato: #N + N dígitos + dados
                if len(raw_data) > 2 and chr(raw_data[1]).isdigit():
                    num_digits = int(chr(raw_data[1]))
                    data_start = 2 + num_digits  # '#N' + N digits
                    data = raw_data[data_start:]
                    
                    print(f"  Header: {raw_data[:data_start]}")
                    print(f"  Data start: {data_start}")
                    print(f"  Dados: {len(data)} bytes")
                    print(f"  Primeiros 10 bytes: {list(data[:10])}")
                    print(f"  Min/max: {min(data)} / {max(data)}")
                    
            except Exception as e:
                print(f"  Parse error: {e}")
                print(f"  Raw first 30 chars: {raw_data[:30]}")
                
    except Exception as e:
        print(f"  ERRO: {e}")
        import traceback
        traceback.print_exc()
    
    # Teste: ler preâmbulo corretamente
    print("\n[5] Teste correto de preâmbulo...")
    try:
        # Enviar comando e ler com read_raw para evitar parsing automático
        inst.write(':WAV:PRE?')
        time.sleep(0.5)
        
        raw_preamble = inst.read_raw()
        print(f"  Raw preamble: {raw_preamble[:100]}")
        
        # Decode Manualmente (sem read_termination que pode interferir)
        preamble_text = raw_preamble.decode('ascii').rstrip('\r\n')
        parts = preamble_text.split(',')
        print(f"  Parsed parts: {len(parts)}")
        if len(parts) >= 10:
            print(f"  Format: {parts[0]}, Points: {parts[2]}, XInc: {parts[3]}")
            
    except Exception as e:
        print(f"  ERRO: {e}")
        import traceback
        traceback.print_exc()
    
    inst.close()
    
except Exception as e:
    print(f"\nErro: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
