#!/usr/bin/env python3
"""
Teste de waveform com PyVISA-py USB-TMC
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
    inst.timeout = 20000  # 20 segundos
    
    # Configurar read_termination (chave para funcionar!)
    inst.read_termination = '\r\n'
    inst.write_termination = '\r\n'
    
    print(f"\n[1] Conectado: {inst.query('*IDN?').strip()}")
    
    # Configurar waveform
    print("\n[2] Configurando waveform...")
    inst.write(':WAV:PRE?')
    time.sleep(0.1)
    
    preamble_str = inst.read()
    print(f"  Preâmbulo: {preamble_str[:100]}...")
    
    # Parâmetros do preâmbulo (formato padrão)
    # Formato: fmt, off, cnt, inc, pto, hor, ver, voff, mdepth, wform
    # Exemplo: "BYTE,0,1400,2.000000E-07,10,1.000000E-02,1.000000E+00,5.000000E-01,0,CHAN1"
    parts = preamble_str.split(',')
    if len(parts) >= 10:
        fmt = parts[0].strip()
        inc = float(parts[3])  # X increment
        pt_o = int(parts[4])   # Point offset
        vdiv = float(parts[6]) # Y div
        voff = float(parts[7]) # Y offset
        print(f"  Format: {fmt},Inc: {inc}s,PTO: {pt_o},VDiv: {vdiv}V,VOff: {voff}V")
    
    # Configurar modo waveform
    print("\n[3] Configurando modo BYTE...")
    inst.write(':WAV:MODE NORM')
    inst.write(':WAV:FORMAT BYTE')
    inst.write(':WAV:SOURCE CHAN1')
    time.sleep(0.2)
    
    # Teste básico com query()
    print("\n[4] Teste query(':WAV:DATA?')...")
    try:
        start = time.time()
        data_str = inst.query(':WAV:DATA?')
        elapsed = time.time() - start
        print(f"  Tempo: {elapsed*1000:.1f}ms")
        print(f"  Tamanho resposta: {len(data_str)} caracteres")
        
        # Extrair dados após ':WAV:DATA ' (10 caracteres)
        if data_str.startswith(':WAV:DATA '):
            data_part = data_str[10:]
            print(f"  Tamanho dados: {len(data_part)} caracteres")
        else:
            print(f"  Resposta completa: {data_str[:50]}...")
            
    except Exception as e:
        print(f"  ERRO: {e}")
        import traceback
        traceback.print_exc()
    
    # Teste com query_binary_values()
    print("\n[5] Teste query_binary_values(':WAV:DATA?')")
    try:
        start = time.time()
        
        # O DHO responde com: ':WAV:DATA #' + tamanho + dados binários
        # Para corrigir o parsing, precisamos usar raw_read
        inst.write(':WAV:DATA?')
        
        # Ler o header (':WAV:DATA #')
        header = inst.read_raw()
        print(f"  Header raw: {header[:20]}")
        
        # O formato é: #N + N dígitos + dados
        # Ex: #21400 -> 1400 bytes de dados
        
        elapsed = time.time() - start
        print(f"  Tempo total: {elapsed*1000:.1f}ms")
        
    except Exception as e:
        print(f"  ERRO: {e}")
        import traceback
        traceback.print_exc()
    
    # Teste: usar read_raw() para pegar tudo raw
    print("\n[6] Teste read_raw() após ':WAV:DATA?'")
    try:
        inst.write(':WAV:DATA?')
        time.sleep(0.5)  # espera
        
        start = time.time()
        raw_data = inst.read_raw()
        elapsed = time.time() - start
        print(f"  Tempo: {elapsed*1000:.1f}ms")
        print(f"  Tamanho: {len(raw_data)} bytes")
        print(f"  First 50 bytes: {raw_data[:50]}")
        
        # Tentar parsear o formato
        if raw_data.startswith(b':WAV:DATA #'):
            # Formato: #N + N dígitos + dados
            header_end = 10  # ':WAV:DATA #'
            # Encontrar o fim do header (número após #)
            for i in range(header_end, len(raw_data)):
                if not chr(raw_data[i]).isdigit():
                    header_end = i
                    break
            
            num_digits = int(raw_data[header_end-1:header_end].decode()) if raw_data[header_end-1:header_end].isdigit() else 1
            data_start = header_end + num_digits
            data = raw_data[data_start:]
            
            print(f"  Header end: {header_end}, num_digits: {num_digits}, data_start: {data_start}")
            print(f"  Dados: {len(data)} bytes")
            print(f"  Primeiros 20 bytes: {list(data[:20])}")
            
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
