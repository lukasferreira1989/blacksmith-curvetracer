#!/usr/bin/env python3
"""
Módulo de reconstrução de curvas I-V
Preserva ordem original, não ordena por tensão/corrente
"""

import numpy as np
from typing import Tuple, List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class CurveReconstructor:
    """
    Reconstrutor de curvas I-V que preserva integridade física
    """
    
    def __init__(self):
        self.cycles = []
        self.branches = {}
    
    def reconstruct(self, vx: np.ndarray, vy: np.ndarray) -> Dict[str, Any]:
        """
        Reconstruir curva preservando ordem original
        """
        if len(vx) == 0 or len(vy) == 0:
            return {'vx': vx, 'vy': vy, 'cycles': [], 'branches': {}}
        
        # Garantir mesmo tamanho
        n = min(len(vx), len(vy))
        vx = vx[:n].copy()
        vy = vy[:n].copy()
        
        result = {
            'vx': vx,
            'vy': vy,
            'n_points': n,
            'preserved_order': True,
            'sorted': False,
            'cycles': [],
            'branches': {}
        }
        
        # Detectar ciclos
        result['cycles'] = self._detect_cycles(vx, vy)
        
        # Separar ramos
        result['branches'] = self._separate_branches(vx, vy)
        
        return result
    
    def _detect_cycles(self, vx: np.ndarray, vy: np.ndarray) -> List[Dict]:
        """Detectar ciclos de varredura"""
        cycles = []
        if len(vx) < 10:
            return cycles
        
        # Encontrar cruzamentos por zero ou mudanças de direção
        # Para sinais senoidais/triangulares
        crossings = []
        for i in range(1, len(vx)):
            if vx[i-1] * vx[i] < 0:  # Cruzamento por zero
                crossings.append(i)
            elif abs(vx[i] - vx[i-1]) < 1e-12 and i > 0:
                # Mudança extrema
                pass
        
        if len(crossings) >= 2:
            for i in range(len(crossings) - 1):
                start = crossings[i]
                end = crossings[i + 1]
                if end - start > 5:
                    cycles.append({
                        'start': int(start),
                        'end': int(end),
                        'vx': vx[start:end].tolist(),
                        'vy': vy[start:end].tolist()
                    })
        
        return cycles
    
    def _separate_branches(self, vx: np.ndarray, vy: np.ndarray) -> Dict[str, Any]:
        """Separar ramos de ida e volta"""
        if len(vx) < 2:
            return {'forward': None, 'reverse': None}
        
        # Detectar direção baseada em derivada
        dvx = np.diff(vx)
        forward_mask = np.zeros(len(vx), dtype=bool)
        reverse_mask = np.zeros(len(vx), dtype=bool)
        
        forward_mask[0] = True
        if len(dvx) > 0:
            # Primeiro ramo com direção predominante
            sign = np.sign(dvx[0]) if abs(dvx[0]) > 1e-12 else 1
            for i in range(1, len(vx)):
                if i-1 < len(dvx):
                    if np.sign(dvx[i-1]) == sign or abs(dvx[i-1]) < 1e-12:
                        forward_mask[i] = True
                    else:
                        reverse_mask[i] = True
                else:
                    reverse_mask[i] = True
        
        return {
            'forward': {'vx': vx[forward_mask], 'vy': vy[forward_mask]},
            'reverse': {'vx': vx[reverse_mask], 'vy': vy[reverse_mask]},
            'forward_count': int(np.sum(forward_mask)),
            'reverse_count': int(np.sum(reverse_mask))
        }
    
    def validate_capacitor_curve(self, vx: np.ndarray, vy: np.ndarray) -> Dict[str, Any]:
        """
        Validar curva de capacitor (deve ser circular/elíptica, não linha)
        """
        if len(vx) < 100:
            return {'valid': False, 'reason': 'Too few points'}
        
        try:
            coeffs = np.polyfit(vx, vy, 1)
            vy_fit = np.polyval(coeffs, vx)
            residual = np.mean((vy - vy_fit)**2)
            vy_range = np.max(vy) - np.min(vy)
            vx_range = np.max(vx) - np.min(vx)
            # Normalizar residual
            if vy_range > 0:
                norm_residual = residual / (vy_range ** 2)
            else:
                norm_residual = residual
            is_linear = norm_residual < 0.001
            
            correlation = np.corrcoef(vx, vy)[0, 1]
            
            return {
                'valid': not is_linear,
                'is_linear': bool(is_linear),
                'residual': float(residual),
                'norm_residual': float(norm_residual),
                'correlation': float(correlation),
                'reason': 'Linear curve detected (bad reconstruction)' if is_linear else 'Non-linear/Lissajous (OK)'
            }
        except Exception as e:
            return {'valid': False, 'reason': str(e)}
    
    def get_statistics(self, vx: np.ndarray, vy: np.ndarray) -> Dict[str, Any]:
        """Obter estatísticas da curva"""
        if len(vx) == 0:
            return {}
        
        return {
            'points': len(vx),
            'vx_min': float(np.min(vx)),
            'vx_max': float(np.max(vx)),
            'vy_min': float(np.min(vy)),
            'vy_max': float(np.max(vy)),
            'vx_range': float(np.max(vx) - np.min(vx)),
            'vy_range': float(np.max(vy) - np.min(vy)),
            'order_preserved': True
        }


def reconstruct_iv(vx: np.ndarray, vy: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Função simplificada para reconstrução I-V"""
    recon = CurveReconstructor()
    result = recon.reconstruct(vx, vy)
    return result['vx'], result['vy']
