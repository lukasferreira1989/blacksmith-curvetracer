#!/usr/bin/env python3
"""
Demonstração do uso do módulo Parameter Measurement
Este script mostra como usar a nova funcionalidade
"""

# Nota: Este exemplo assume que as dependências estão instaladas:
#   pip install -r requirements.txt

import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Import do módulo de parameter measurement
# Em produção, usaria:
#   from src.parameter_measure import ParameterMeasurer, measure_component
# Mas aqui simulamos com o código abaixo:

print("=" * 60)
print("Exemplo de uso do Parameter Measurement")
print("=" * 60)

# Simulação de dados (substituir pelos dados reais do scope)
print("\n1. Exemplo 1: Resistência de 100Ω")
print("-" * 40)

# Dados sintéticos para resistor
import numpy as np
vx_resistor = np.linspace(0, 5, 100)
vy_resistor = vx_resistor / 100  # I = V/R, R = 100Ω

print(f"   Tensão: {vx_resistor[0]:.2f}V a {vx_resistor[-1]:.2f}V")
print(f"   Corrente: {vy_resistor[0]:.4f}A a {vy_resistor[-1]:.4f}A")
print(f"   Resistência calculada: 100.00 Ω")

# O ParameterMeasurer detectaria:
#   - Tipo: resistor
#   - Parâmetros: {'r_resistance': 100.0, ...}

print("\n2. Exemplo 2: Diodo LED")
print("-" * 40)

# Dados sintéticos para diodo
vx_diode = np.linspace(-5, 2, 500)
vy_diode = np.array([
    1e-12 * np.exp((v - 0.7) / 0.026) if v > 0.7 else 1e-12 
    for v in vx_diode
])

print(f"   Tensão: {vx_diode[0]:.1f}V a {vx_diode[-1]:.1f}V")
print(f"   Corrente: {vy_diode[np.argmax(vy_diode > 1e-6)]:.4f}A (em condução)")
print(f"   Vf estimado: ~0.7V")

# O ParameterMeasurer detectaria:
#   - Tipo: diode_standard
#   - Parâmetros: {'vf_forward_voltage': 0.7, 'vbr_breakdown_voltage': -5.0, ...}

print("\n3. Exemplo 3: MOSFET")
print("-" * 40)

# Dados sintéticos para MOSFET
vx_mosfet = np.linspace(0, 5, 500)
vy_mosfet = np.array([
    0.5 * (v - 2.0) if v > 2.0 else 1e-9
    for v in vx_mosfet
])

print(f"   Tensão (Vgs): {vx_mosfet[0]:.1f}V a {vx_mosfet[-1]:.1f}V")
print(f"   Corrente (Id): {vy_mosfet[-1]:.4f}A (em condução)")
print(f"   Threshold voltage: ~2.0V")

# O ParameterMeasurer detectaria:
#   - Tipo: mosfet
#   - Parâmetros: {'vgs_threshold_voltage': 2.0, 'rds_on_resistance': 2.0, ...}

print("\n4. Exemplo 4: Capacitor")
print("-" * 40)

# Dados sintéticos para capacitor (curva Lissajous)
t = np.linspace(0, 4*np.pi, 500)
vx_cap = np.sin(t)
vy_cap = np.cos(t) * 0.1

print(f"   Tensão: {vx_cap.min():.2f}V a {vx_cap.max():.2f}V")
print(f"   Corrente: {vy_cap.min():.4f}A a {vy_cap.max():.4f}A")
print(f"   Forma: Lissajous (circular/semi-circular)")

# O ParameterMeasurer detectaria:
#   - Tipo: capacitor
#   - Parâmetros: {'c_capacitance_estimate': X, ...}

print("\n5. Integração com GUI")
print("-" * 40)
print("   O Parameter Measurement pode ser integrado à interface gráfica:")
print("   - Painel 'Parameter Measurement' no painel esquerdo")
print("   - Botão 'MEASURE' para calcular parâmetros automaticamente")
print("   - Exibição dos parâmetros detectados no painel direito")
print("   - Salvar medições no banco de dados SQLite")

print("\n" + "=" * 60)
print("Para usar com o osciloscópio real:")
print("=" * 60)
print("""
1. Importe o módulo:
   from src.parameter_measure import ParameterMeasurer

2. Capture dados do scope:
   vx, vy = scope.capture_xy('CHAN1', 'CHAN2')

3. Meça os parâmetros:
   measurer = ParameterMeasurer()
   result = measurer.measure(vx, vy)

4. Use os resultados:
   print(f"Tipo: {result.component_type}")
   print(f"Parâmetros: {result.parameters}")
   print(f"Confiança: {result.confidence:.1%}")
""")

print("\n" + "=" * 60)
print("Próximos passos:")
print("=" * 60)
print("1. Integrar com src/gui.py (painel de Parameter Measurement)")
print("2. Adicionar botão 'MEASURE' na interface")
print("3. Exibir resultados em tempo real")
print("4. Testar com componentes reais conectados ao osciloscópio")
