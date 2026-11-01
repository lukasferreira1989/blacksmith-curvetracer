#!/usr/bin/env python3
"""
Teste de comunicação USB-TMC com Rigol DHO924S via PyVISA-py
Comparação entre: PyVISA-py vs /dev/usbtmc direto
"""

import pyvisa
import time
import os

print("=" * 60)
print("TESTE DE COMUNICAÇÃO USB-TMC - RIGOL DHO924S")
print("=" * 60)

# Passo 1: Listar recursos disponíveis
print("\n[1] Listando recursos USB TMC...")
rm = pyvisa.ResourceManager('@py')
resources = rm.list_resources()
print(f"Recursos encontrados: {resources}")

# Filtrar apenas recursos USB-TMC
usbtmc_resources = [r for r in resources if 'USB' in r and 'INSTR' in r]
print(f"USB-TMC resources: {usbtmc_resources}")

if not usbtmc_resources:
    print("Nenhum dispositivo USB-TMC encontrado!")
    exit(1)

resource = usbtmc_resources[0]
print(f"\nTestando com: {resource}")

# Passo 2: Teste com /dev/usbtmc direto (base de comparação)
print("\n[2] Teste direto /dev/usbtmc...")
usbtmc_path = "/dev/usbtmc2"  # assumindo o mesmo device
if os.path.exists(usbtmc_path):
    try:
        start = time.time()
        with open(usbtmc_path, 'w+b', buffering=0) as f:
            # Escrita
            f.write(b'*IDN?\n')
            f.flush()
            
            # Leitura
            f.read(512)  # leitura inicial para limpar buffer
            
            # Tempo de resposta
            write_time = time.time() - start
            print(f"  Escrita bem sucedida em {write_time*1000:.1f}ms")
            
            start = time.time()
            response = f.read(512)
            read_time = time.time() - start
            print(f"  Leitura bem sucedida em {read_time*1000:.1f}ms")
            print(f"  IDN: {response.decode().strip()}")
    except Exception as e:
        print(f"  ERRO /dev/usbtmc: {e}")
else:
    print(f"  {usbtmc_path} não encontrado")

# Passo 3: Teste com PyVISA-py (o que está falhando)
print(f"\n[3] Teste com PyVISA-py (resource: {resource})...")
try:
    inst = rm.open_resource(resource)
    
    # Configuração básica
    inst.timeout = 10000  # 10 segundos
    print(f"  Timeout configurado: {inst.timeout}ms")
    
    # Teste 3a: *IDN? via query()
    print("\n  [3a] Teste: query('*IDN?')")
    try:
        start = time.time()
        idn = inst.query('*IDN?')
        elapsed = time.time() - start
        print(f"    Sucesso! Tempo: {elapsed*1000:.1f}ms")
        print(f"    IDN: {idn.strip()}")
    except Exception as e:
        print(f"    ERRO query('*IDN?'): {e}")
    
    # Teste 3b: waveform via query_binary_values()
    print("\n  [3b] Teste: query_binary_values(':WAV:DATA?')")
    
    # Primeiro configurar o modo waveform
    try:
        inst.write(':WAV:PRE?')
        time.sleep(0.1)
        inst.write(':WAV:MODE NORM')
        inst.write(':WAV:FORMAT BYTE')
        inst.write(':WAV:SOURCE CHAN1')
        print("    Configuração de waveform enviada")
    except Exception as e:
        print(f"    ERRO config waveform: {e}")
        raise
    
    # Agora tentar ler os dados
    try:
        start = time.time()
        # Testar com diferentes chunk_size
        data = inst.query_binary_values(
            ':WAV:DATA?', 
            datatype='b',  # signed char (byte)
            container=bytes,
            chunk_size=1024*1024,  # 1MB
            header=False  # O DHO não envia header IEEE 488.2
        )
        elapsed = time.time() - start
        print(f"    Sucesso! Tempo: {elapsed*1000:.1f}ms, tamanho: {len(data)} bytes")
        print(f"    Primeiros 20 bytes: {data[:20]}")
    except Exception as e:
        print(f"    ERRO query_binary_values(): {e}")
        import traceback
        traceback.print_exc()
    
    inst.close()
    
except Exception as e:
    print(f"  ERRO PyVISA-py: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("TESTE CONCLUÍDO")
print("=" * 60)
