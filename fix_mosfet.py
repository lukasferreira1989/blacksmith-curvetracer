#!/usr/bin/env python3
import re

# Read the file
with open('/home/lucas/Documentos/curve-tracer-oss/src/parameter_measure.py', 'r', encoding='utf-8') as f:
    content = f.read()

# New MOSFET detection function
new_mosfet = '''    def _is_mosfet_like(self, vx: np.ndarray, vy: np.ndarray) -> bool:
        """
        Detectar forma característica de MOSFET
        MOSFET tem uma região de cut-off (desligado) seguida de condução
        A transição deve ser abrupta (threshold voltage característico)
        """
        if len(vx) < 100:
            return False
        
        try:
            # Ordenar por tensão
            sorted_idx = np.argsort(vx)
            vx_sorted = vx[sorted_idx]
            vy_sorted = vy[sorted_idx]
            
            # Detectar região de cut-off (corrente muito baixa)
            off_region = vy_sorted[vy_sorted < 1e-6]
            on_region = vy_sorted[vy_sorted > 1e-5]
            
            # Se não há transição significativa, não é MOSFET
            if len(off_region) < 10 or len(on_region) < 10:
                return False
            
            # Encontrar o ponto de transição
            dydx = np.gradient(vy_sorted, vx_sorted)
            
            # Detectar onde a derivada aumenta significativamente
            off_slope = np.mean(dydx[:len(dydx)//4]) if len(dydx) > 4 else 0
            on_slope = np.mean(dydx[3*len(dydx)//4:]) if len(dydx) > 4 else 0
            
            # Se há uma mudança significativa na derivada -> possível MOSFET
            if off_slope < 1e-6 and on_slope > 0.01:
                # Verificar se a transição ocorre em uma tensão específica (threshold)
                threshold_idx = np.where(vy_sorted > 1e-5)[0]
                if len(threshold_idx) > 0:
                    threshold_voltage = vx_sorted[threshold_idx[0]]
                    if threshold_voltage > 0.5 and threshold_voltage < 4.0:
                        return True
        except Exception:
            pass
        
        return False
'''

# Replace the old function
pattern = r'    def _is_mosfet_like\(self, vx: np\.ndarray, vy: np\.ndarray\) -> bool:.*?(?=\n    def |\n    @|\Z)'
content = re.sub(pattern, new_mosfet, content, flags=re.DOTALL)

# Write the file
with open('/home/lucas/Documentos/curve-tracer-oss/src/parameter_measure.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("File updated successfully")
