#!/usr/bin/env python3
"""
Teste de comunicação USB-TMC com Rigol DHO924S - Versão simplificada
"""

import pyvisa
import time

print("=" * 60)
print("TESTE USB-TMC - RIGOL DHO924S")
print("=" * 60)

rm = pyvisa.ResourceManager('@py')
resources = rm.list_resources()
usbtmc = [r for r in resources if 'USB' in r and 'INSTR' in r]

if not usbtmc:
    print("Nenhum dispositivo USB encontrado!")
    exit(1)

resource = usbtmc[0]
print(f"\nRecursos USB-TMC: {resources}")
print(f"Testando: {resource}")

try:
    inst = rm.open_resource(resource)
    inst.timeout = 20000  # 20 segundos
    print(f"Timeout: {inst.timeout}ms")
    
    # Teste simples
    print("\n[1] Teste: *IDN? com write/read_separate")
    inst.write('*IDN?')
    time.sleep(0.5)  # esperar resposta
    
    try:
        response = inst.read()
        print(f"  Sucesso! Resposta: {response}")
    except Exception as e:
        print(f"  ERRO read(): {e}")
    
    # Teste com read_termination customizado
    print("\n[2] Teste: *IDN? com read_termination='\\n'")
    inst.read_termination = '\n'
    try:
        response = inst.query('*IDN?')
        print(f"  Sucesso! Resposta: '{response.strip()}'")
    except Exception as e:
        print(f"  ERRO query(): {e}")
    
    # Teste com read_termination='\r\n'
    print("\n[3] Teste: *IDN? com read_termination='\\r\\n'")
    inst.read_termination = '\r\n'
    try:
        response = inst.query('*IDN?')
        print(f"  Sucesso! Resposta: '{response.strip()}'")
    except Exception as e:
        print(f"  ERRO query(): {e}")
    
    # Teste: checar valor padrão de read_termination
    print(f"\n[4] read_termination atual: {repr(inst.read_termination)}")
    print(f"  write_termination atual: {repr(inst.write_termination)}")
    
    inst.close()
    
except Exception as e:
    print(f"\nErro geral: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
