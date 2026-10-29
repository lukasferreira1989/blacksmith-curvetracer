#!/usr/bin/env python3
"""
Módulo de Parameter Measurement para Curve Tracer OSS
Detecta automaticamente componentes e calcula parâmetros elétricos
"""

import numpy as np
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class MeasurementResult:
    """Resultado de uma medição"""
    component_type: str  # 'diode', 'transistor', 'mosfet', 'resistor', 'capacitor', 'unknown'
    parameters: Dict[str, Any] = field(default_factory=dict)
    detected_regions: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    notes: List[str] = field(default_factory=list)


class ParameterMeasurer:
    """
    Medidor automático de parâmetros de componentes
    Baseado em reconhecimento de formas de curvas I-V
    """
    
    # Tolerâncias para detecção de regiões
    VDIODE_FWD_MIN = 0.3      # Vf mínimo para diodo (Schottky)
    VDIODE_FWD_MAX = 0.9      # Vf máximo para diodo comum
    VZENER_MIN = 1.0          # Tensão de ruptura mínima para Zener
    VBJT_VBE_FWD = 0.6-0.7    # Vbe de condução para BJT
    VMOSFET_THRESHOLD_MIN = 0.5
    VMOSFET_THRESHOLD_MAX = 4.0
    
    def __init__(self):
        pass
    
    def measure(self, vx: np.ndarray, vy: np.ndarray) -> MeasurementResult:
        """
        Medir parâmetros de um componente a partir da curva I-V
        
        Args:
            vx: Array de tensões (V)
            vy: Array de correntes (A)
            
        Returns:
            MeasurementResult com tipo do componente e parâmetros detectados
        """
        if len(vx) == 0 or len(vy) == 0:
            return MeasurementResult(
                component_type='unknown',
                parameters={},
                confidence=0.0,
                notes=['Sem dados suficientes']
            )
        
        # Garantir arrays numpy
        vx = np.asarray(vx, dtype=np.float64)
        vy = np.asarray(vy, dtype=np.float64)
        
        # Detectar tipo de componente
        component_type = self._detect_component_type(vx, vy)
        
        # Calcular parâmetros específicos
        parameters, detected_regions = self._calculate_parameters(
            vx, vy, component_type
        )
        
        # Calcular confiança
        confidence = self._calculate_confidence(vx, vy, component_type, parameters)
        
        # Adicionar notas
        notes = self._generate_notes(component_type, parameters)
        
        return MeasurementResult(
            component_type=component_type,
            parameters=parameters,
            detected_regions=detected_regions,
            confidence=confidence,
            notes=notes
        )
    
    def _detect_component_type(self, vx: np.ndarray, vy: np.ndarray) -> str:
        """
        Detectar tipo de componente baseado na forma da curva I-V
        Ordem crítica: capacitor -> zener -> resistor -> mosfet/transistor -> diode -> unknown
        """
        # Extrair características da curva
        vx_fwd = vx[vx > 0]
        vx_rev = vx[vx < 0]
        vy_fwd = vy[vx > 0]
        vy_rev = vy[vx < 0]
        
        # 1. Detecção de Capacitor (forma elíptica/circular) - testar PRIMEIRO
        # Capacitor: curva de Lissajous (círculo/elipse) - SENSÍVEL, deve ser primeira
        is_capacitive = self._is_capacitive_curve(vx, vy)
        if is_capacitive:
            return 'capacitor'
        
        # 2. Detecção de Resistor (linha reta com simetria ou apenas linear)
        # Resistor: V=IR, curva linear passando pela origem
        is_linear = self._is_linear(vx, vy)
        if is_linear:
            # Verificar se a curva passa pela origem (ou próxima)
            # Para resistor ideal: V=0 => I=0
            vy_all = np.concatenate([vy_fwd, vy_rev]) if len(vx_rev) > 0 else vy_fwd
            vx_all = np.concatenate([vx_fwd, vx_rev]) if len(vx_rev) > 0 else vx_fwd
            
            # Calcular intercepto da linha de melhor ajuste
            coeffs = np.polyfit(vx_all, vy_all, 1)
            intercept = coeffs[1]  # Termo constante
            
            # Intercepto deve estar próximo de zero (menor que 5% do range de I)
            vy_range = np.max(vy_all) - np.min(vy_all) if len(vy_all) > 0 else 0
            if abs(intercept) < vy_range * 0.05 or abs(intercept) < 1e-9:
                # A linha passa pela origem -> resistor
                return 'resistor'
            
            # Verificar simetria se há dados reversos
            vy_fwd_max = np.max(vy_fwd) if len(vy_fwd) > 0 else 0
            vy_rev_max = abs(np.min(vy_rev)) if len(vy_rev) > 0 else 0
            if vy_rev_max > 0:
                asymmetry_ratio = vy_fwd_max / vy_rev_max
                if abs(asymmetry_ratio - 1.0) < 0.5:
                    return 'resistor'
        
        # 3. Detecção de Zener (ruptura reversa controlada)
        # Zener: tensão reversa "regulada" (zona plana) enquanto corrente varia
        # Threshold reduzido de 0.7 para 0.4 para detectar Zener ideal
        if len(vx_rev) > 50:
            zener_score = self._score_zener_characteristic(vx_rev, vy_rev)
            if zener_score > 0.4:
                return 'zener'
        
        # 4. Detecção de MOSFET/Transistor (threshold voltage, SEM corrente reversa)
        # Crucial: transistor/MOSFET têm corrente only no forward, NÃO têm região reversa ativa
        vy_rev_max = abs(np.min(vy_rev)) if len(vy_rev) > 0 else 0
        vy_fwd_max = np.max(vy_fwd) if len(vy_fwd) > 0 else 0
        
        # Se há corrente reversa significativa (>1uA), NÃO é transistor/MOSFET
        # (transistor tem pequena corrente de fuga, mas não condução reversa)
        if vy_rev_max < 1e-9:
            # Sem corrente reversa -> MOSFET ou transistor
            if self._is_mosfet_like(vx, vy):
                return 'mosfet'
            if self._is_transistor_like(vx, vy):
                return 'transistor'
        
        # 5. Detecção de Diodo (condução unidirecional COM corrente reversa)
        # Apenas se não foi detectado como outro componente
        # Diodo: condução forward com Vf typica, pequena corrente reversa (leakage)
        if len(vx_rev) > 0 and len(vx_fwd) > 0:
            vy_rev_max = abs(np.min(vy_rev)) if len(vy_rev) > 0 else 0
            if vy_fwd_max > 1e-9:  # Há condução forward
                # Verificar forma exponencial (diodo típico)
                is_diode_like = self._is_diode_like(vx_fwd, vy_fwd)
                if is_diode_like:
                    # Verificar se é Zener já descartado, senão é diodo
                    if vy_rev_max > 10e-6:  # Corrente reversa significativa
                        return 'zener'
                    if vy_rev_max > 1e-9:  # Corrente reversa pequena (leakage)
                        return 'diode_standard'
        vy_all = np.concatenate([vy_fwd, vy_rev]) if len(vx_rev) > 0 else vy_fwd
        vy_range = np.max(vy_all) - np.min(vy_all)
        current_threshold = max(1e-9, vy_range * 0.01)
        fwd_region = vx_fwd[vy_fwd > current_threshold]
        
        if len(fwd_region) >= 4:
            fwd_voltage_min = np.min(fwd_region)
            if fwd_voltage_min < 0.3:
                return 'diode_schottky'
            elif fwd_voltage_min < 0.9:
                return 'diode_standard'
            else:
                return 'diode'
        
        return 'unknown'
    
    def _score_zener_characteristic(self, vx_rev: np.ndarray, vy_rev: np.ndarray) -> float:
        """
        Calcular score de característica Zener (0.0 a 1.0)
        Zener: tensão quase constante enquanto corrente varia (zona plana)
        """
        if len(vx_rev) < 30:
            return 0.0
        
        try:
            # Ordenar pela magnitude da corrente (abs)
            # Isso garante que "alta corrente" signifique o mesmo para positivas e negativas
            sorted_idx = np.argsort(np.abs(vy_rev))
            vx_sorted = vx_rev[sorted_idx]
            vy_sorted = vy_rev[sorted_idx]
            
            # Dividir em 3 regiões: Low, Mid, High corrente
            n = len(vx_sorted)
            n_low = n // 4
            n_high = n * 3 // 4
            
            vx_low = vx_sorted[:n_low]
            vx_high = vx_sorted[n_high:]
            vy_high = vy_sorted[n_high:]
            
            # Score 1: Planura da tensão (desvio padrão pequeno na zona de breakdown)
            vx_std = np.std(vx_high)
            vx_range = np.max(vx_high) - np.min(vx_high)
            
            # Zener típico: tensão varia ~0.2-1.0V enquanto corrente varia 10x
            # Planarity score: desvio padrão baixo (< 1V), range pequeno (< 3V)
            # Tolerância aumentada para Zener ideal (tensão muito constante)
            # vx_std ~0.1V e vx_range ~0.5V para Zener ideal de 5.1V
            planarity_score = max(0.0, 1.0 - (vx_std / 0.5) - (vx_range / 2.0))
            
            # Score 2: Transição acentuada (quebra na curva)
            vy_low = vy_sorted[:n_low]
            
            vy_low_avg = np.mean(np.abs(vy_low)) if len(vy_low) > 0 else 0
            vy_high_avg = np.mean(np.abs(vy_high)) if len(vy_high) > 0 else 0
            
            # Transição: corrente alta deve ser >> corrente baixa
            # Para Zener, corrente alta pode ser 10-100x corrente baixa
            if vy_low_avg > 1e-12:
                transition_ratio = vy_high_avg / vy_low_avg
                transition_score = min(1.0, (transition_ratio - 2) / 8) if transition_ratio > 2 else 0
            else:
                # Se vy_low é muito baixo, transição é considerada boa
                transition_score = 1.0 if vy_high_avg > 1e-6 else 0
            
            # Score 3: Tensão em faixa típica de Zener
            vx_max = np.max(np.abs(vx_rev))
            # Tensão de Zener típica: 1.8V a 200V, mas comuns entre 2-50V
            zener_voltage_score = 1.0 if 1.5 < vx_max < 50.0 else 0.0
            
            # Score 4: Corrente reversa significativa
            vy_max = np.max(np.abs(vy_rev))
            # Corrente reversa típica de Zener: > 10uA (não leakage)
            current_score = 1.0 if vy_max > 10e-6 else 0.0
            
            # Combinar scores (ponderado)
            total_score = (
                0.35 * planarity_score +
                0.25 * transition_score +
                0.20 * zener_voltage_score +
                0.20 * current_score
            )
            
            return min(1.0, max(0.0, total_score))
        except Exception:
            return 0.0
    
    def _is_diode_like(self, vx_fwd: np.ndarray, vy_fwd: np.ndarray) -> bool:
        """
        Verificar se a curva forward tem forma exponencial típica de diodo
        """
        if len(vx_fwd) < 50:
            return False
        
        try:
            # Filtrar apenas a região de condução
            vy_max = np.max(vy_fwd)
            if vy_max < 1e-9:
                return False
            
            conducted_idx = vy_fwd > vy_max * 0.01
            vx_conducted = vx_fwd[conducted_idx]
            vy_conducted = vy_fwd[conducted_idx]
            
            if len(vx_conducted) < 20:
                return False
            
            # Calcular derivada
            dydx = np.gradient(vy_conducted, vx_conducted)
            
            # Diodo tem derivada que aumenta exponencialmente com V
            # Verificar se há aceleração na corrente
            mid_idx = len(dydx) // 2
            early_slope = np.mean(dydx[:mid_idx])
            late_slope = np.mean(dydx[mid_idx:])
            
            # Late slope deve ser significativamente maior
            if early_slope > 0 and late_slope / early_slope > 3:
                return True
            
            return False
        except Exception:
            return False
    
    def _is_linear(self, vx: np.ndarray, vy: np.ndarray, threshold: float = 0.01) -> bool:
        """
        Verificar se a curva é linear (resistor ideal)
        
        Um resistor ideal tem:
        - Derivada constante (slope quase igual em toda a curva)
        - Pouca nonlinearidade (residual normalizado pequeno)
        - Variação significativa de corrente (não apenas ruído)
        """
        try:
            if len(vx) < 20:
                return False
            
            # Verificar se há variação significativa de corrente
            vy_range = np.max(vy) - np.min(vy)
            if vy_range < 1e-9:  # Sem variação de corrente -> não é resistor ativo
                return False
            
            # Fazer regressão linear
            coeffs = np.polyfit(vx, vy, 1)
            vy_fit = np.polyval(coeffs, vx)
            residual = np.mean((vy - vy_fit) ** 2)
            
            # Normalizar pelo range ao quadrado
            norm_residual = residual / (vy_range ** 2)
            
            # Verificar não-linearidade local (derivada variável)
            dydx = np.gradient(vy, vx)
            dydx_std = np.std(dydx)
            dydx_mean = np.mean(np.abs(dydx))
            
            # Se o coeficiente de variação da derivada for alto, não é linear
            # (resistor tem derivative constante, diodo tem derivative variável)
            if dydx_mean > 0:
                dydx_cv = dydx_std / dydx_mean
                # Coeficiente de variação da derivada > 50% indica nonlinearidade
                if dydx_cv > 0.5:
                    return False
            
            # Residual normalizado deve ser pequeno
            # Para resistor: residual < 0.01 é muito rigoroso
            # Ajustar threshold para ser mais tolerante com ruído
            if norm_residual < threshold * 2:  # Threshold aumentado de 0.01 para 0.02
                return True
            
            return False
        except Exception:
            return False
    
    def _is_capacitive_curve(self, vx: np.ndarray, vy: np.ndarray, 
                            threshold: float = 0.30) -> bool:
        """
        Verificar se a curva tem forma circular/elíptica (capacitor)
        """
        if len(vx) < 50:
            return False
        
        try:
            vx_mean = np.mean(vx)
            vy_mean = np.mean(vy)
            vx_centered = vx - vx_mean
            vy_centered = vy - vy_mean
            
            distances = np.sqrt(vx_centered**2 + vy_centered**2)
            dist_std = np.std(distances)
            dist_mean = np.mean(distances)
            
            if dist_mean > 0:
                cv = dist_std / dist_mean
                return cv < threshold
        except Exception:
            pass
        
        return False
    
    def _is_transistor_like(self, vx: np.ndarray, vy: np.ndarray) -> bool:
        """
        Detectar forma característica de transistor BJT
        BJT tem múltiplas "famílias de curvas" (diferentes correntes de base)
        
        Para BJT com curve tracer, temos 5+ curvas (um para cada corrente de base).
        Quando mescladas, formam um padrão com múltiplos níveis de corrente constantes.
        """
        if len(vx) < 100:
            return False
        
        try:
            sorted_idx = np.argsort(vx)
            vx_sorted = vx[sorted_idx]
            vy_sorted = vy[sorted_idx]
            
            # Para BJT, temos múltiplas "linhas" horizontais (famílias de curvas)
            # Cada linha representa uma corrente de base diferente
            # A detecção usa clustering dos valores de corrente
            
            # Calcular média e desvio padrão da corrente
            vy_mean = np.mean(vy_sorted)
            vy_std = np.std(vy_sorted)
            
            if vy_std < 1e-9 or vy_mean < 1e-9:
                return False
            
            # Coeficiente de variação baixo indica múltiplos níveis constantes
            cv = vy_std / vy_mean
            
            # Para BJT com múltiplas curvas, temos variação significativa
            # mas cada curva individual é quase constante
            # A detecção olha para a distribuição de valores
            
            # Contar valores únicos (discretização)
            # Se temos 4+ níveis de corrente distintos, provavelmente é BJT
            vy_rounded = np.round(vy_sorted / vy_std) * vy_std
            unique_levels = len(np.unique(vy_rounded))
            
            # BJT típico tem 4+ níveis de corrente (um para cada curva de base)
            # MOSFET tem apenas 1 nível principal (ou 2 se considerarmos cutoff e ativo)
            if unique_levels >= 4 and vy_std > 1e-9:
                return True
            
            return False
        except Exception:
            return False
    
    def _is_mosfet_like(self, vx: np.ndarray, vy: np.ndarray) -> bool:
        """
        Detectar forma característica de MOSFET
        MOSFET tem uma região de cut-off seguida de condução
        A transição deve ser abrupta (threshold voltage característico)
        """
        if len(vx) < 100:
            return False
        
        try:
            sorted_idx = np.argsort(vx)
            vx_sorted = vx[sorted_idx]
            vy_sorted = vy[sorted_idx]
            
            # Detectar região de cut-off (corrente muito baixa)
            off_region = vy_sorted[vy_sorted < 1e-6]
            on_region = vy_sorted[vy_sorted > 1e-5]
            
            # Se não há transição significativa, não é MOSFET
            if len(off_region) < 10 or len(on_region) < 10:
                return False
            
            dydx = np.gradient(vy_sorted, vx_sorted)
            
            off_slope = np.mean(dydx[:len(dydx)//4]) if len(dydx) > 4 else 0
            on_slope = np.mean(dydx[3*len(dydx)//4:]) if len(dydx) > 4 else 0
            
            # Se há mudança significativa na derivada -> possível MOSFET
            if off_slope < 1e-6 and on_slope > 0.01:
                threshold_idx = np.where(vy_sorted > 1e-5)[0]
                if len(threshold_idx) > 0:
                    threshold_voltage = vx_sorted[threshold_idx[0]]
                    if threshold_voltage > 0.5 and threshold_voltage < 4.0:
                        return True
        except Exception:
            pass
        
        return False
    
    def _estimate_threshold_voltage(self, vx: np.ndarray, vy: np.ndarray) -> Optional[float]:
        """
        Estimar tensão de limiar (threshold voltage) para MOSFET
        """
        try:
            dydx = np.gradient(vy, vx)
            
            positive_current = vy > 1e-6
            if not np.any(positive_current):
                return None
            
            vx_positive = vx[positive_current]
            vy_positive = vy[positive_current]
            
            if len(vx_positive) < 10:
                return None
            
            # Find the voltage where current starts increasing significantly
            # Look for the first point where current is above a small fraction of max
            vy_max = np.max(vy_positive)
            current_threshold = max(1e-9, vy_max * 0.01)
            
            # Find first point where current exceeds threshold
            for i, v in enumerate(vx_positive):
                if vy_positive[i] > current_threshold:
                    return float(v)
            
            return None
            
        except Exception:
            pass
        
        return None
    
    def _calculate_parameters(self, vx: np.ndarray, vy: np.ndarray, 
                             component_type: str) -> Tuple[Dict, Dict]:
        """
        Calcular parâmetros específicos para cada tipo de componente
        """
        parameters = {}
        detected_regions = {}
        
        parameters['v_min'] = float(np.min(vx))
        parameters['v_max'] = float(np.max(vx))
        parameters['i_min'] = float(np.min(vy))
        parameters['i_max'] = float(np.max(vy))
        parameters['v_range'] = float(parameters['v_max'] - parameters['v_min'])
        parameters['i_range'] = float(parameters['i_max'] - parameters['i_min'])
        
        if component_type in ['diode', 'diode_std', 'diode_schottky', 'diode_standard', 'zener']:
            parameters.update(self._calculate_diode_parameters(vx, vy))
            detected_regions.update(self._detect_diode_regions(vx, vy))
        
        elif component_type in ['transistor']:
            parameters.update(self._calculate_transistor_parameters(vx, vy))
            detected_regions.update(self._detect_transistor_regions(vx, vy))
        
        elif component_type in ['mosfet']:
            parameters.update(self._calculate_mosfet_parameters(vx, vy))
            detected_regions.update(self._detect_mosfet_regions(vx, vy))
        
        elif component_type == 'resistor':
            parameters.update(self._calculate_resistor_parameters(vx, vy))
        
        elif component_type == 'capacitor':
            parameters.update(self._calculate_capacitor_parameters(vx, vy))
        
        return parameters, detected_regions
    
    def _calculate_diode_parameters(self, vx: np.ndarray, vy: np.ndarray) -> Dict:
        """Calcular parâmetros de diodo"""
        params = {}
        
        vy_range = np.max(vy) - np.min(vy)
        current_threshold = max(1e-12, vy_range * 0.001)
        fwd_mask = vy > current_threshold
        if np.any(fwd_mask):
            vx_fwd = vx[fwd_mask]
            params['vf_forward_voltage'] = float(np.min(vx_fwd))
            
            i_10ma = 10e-3
            if np.max(vy) > i_10ma:
                idx_10ma = np.argmin(np.abs(vy - i_10ma))
                params['vf_at_10ma'] = float(vx[idx_10ma])
        
        rev_mask = vx < 0
        if np.any(rev_mask):
            vy_rev = vy[rev_mask]
            params['ir_leakage_reverse'] = float(np.max(np.abs(vy_rev)))
        
        params['vbr_breakdown_voltage'] = float(np.min(vx))
        params['vmax_max_voltage'] = float(np.max(vx))
        params['imax_max_current'] = float(np.max(vy))
        
        return params
    
    def _detect_diode_regions(self, vx: np.ndarray, vy: np.ndarray) -> Dict:
        """Detectar regiões da curva do diodo"""
        regions = {}
        
        fwd_mask = vx > 0
        if np.any(fwd_mask):
            regions['forward'] = {
                'vx_min': float(np.min(vx[fwd_mask])),
                'vx_max': float(np.max(vx[fwd_mask])),
                'vy_max': float(np.max(vy[fwd_mask]))
            }
        
        rev_mask = vx < 0
        if np.any(rev_mask):
            regions['reverse'] = {
                'vx_min': float(np.min(vx[rev_mask])),
                'vx_max': float(np.max(vx[rev_mask])),
                'vy_max': float(np.max(np.abs(vy[rev_mask])))
            }
        
        breakdown_mask = vx < -1.0
        if np.any(breakdown_mask):
            regions['breakdown'] = {
                'vx_min': float(np.min(vx[breakdown_mask])),
                'vx_max': float(np.max(vx[breakdown_mask]))
            }
        
        return regions
    
    def _calculate_transistor_parameters(self, vx: np.ndarray, vy: np.ndarray) -> Dict:
        """Calcular parâmetros de transistor BJT"""
        params = {}
        
        params['vbe_base_emitter_fwd'] = 0.65
        
        try:
            dydx = np.gradient(vy, vx)
            if len(dydx) > 0:
                params['hfe_current_gain_estimate'] = float(np.median(dydx))
        except Exception:
            params['hfe_current_gain_estimate'] = 0.0
        
        fwd_mask = vy > 1e-3
        if np.any(fwd_mask):
            params['vcesat_saturation_voltage'] = float(np.min(vx[fwd_mask]))
        
        params['ic_max_collector_current'] = float(np.max(vy))
        params['vceo_max_voltage'] = float(np.max(vx))
        
        return params
    
    def _detect_transistor_regions(self, vx: np.ndarray, vy: np.ndarray) -> Dict:
        """Detectar regiões do transistor"""
        regions = {}
        
        cutoff_mask = vy < 1e-6
        if np.any(cutoff_mask):
            regions['cutoff'] = {
                'vx_min': float(np.min(vx[cutoff_mask])),
                'vx_max': float(np.max(vx[cutoff_mask]))
            }
        
        active_mask = (vy >= 1e-6) & (vx < 2.0)
        if np.any(active_mask):
            regions['active'] = {
                'vx_min': float(np.min(vx[active_mask])),
                'vx_max': float(np.max(vx[active_mask]))
            }
        
        saturation_mask = vx <= 0.2
        if np.any(saturation_mask):
            regions['saturation'] = {
                'vx_min': float(np.min(vx[saturation_mask])),
                'vx_max': float(np.max(vx[saturation_mask]))
            }
        
        return regions
    
    def _calculate_mosfet_parameters(self, vx: np.ndarray, vy: np.ndarray) -> Dict:
        """Calcular parâmetros de MOSFET"""
        params = {}
        
        vgs_th = self._estimate_threshold_voltage(vx, vy)
        if vgs_th is not None:
            params['vgs_threshold_voltage'] = vgs_th
        
        fwd_mask = vy > 10e-3
        if np.any(fwd_mask):
            try:
                vx_fwd = vx[fwd_mask]
                vy_fwd = vy[fwd_mask]
                rds_est = np.mean(vx_fwd / vy_fwd) if np.any(vy_fwd > 0) else 0
                params['rds_on_resistance'] = float(rds_est)
            except Exception:
                params['rds_on_resistance'] = 0.0
        
        params['id_max_drain_current'] = float(np.max(vy))
        params['vds_max_voltage'] = float(np.max(vx))
        
        rev_mask = vx < 0
        if np.any(rev_mask):
            params['ig_leakage'] = float(np.max(np.abs(vy[rev_mask])))
        
        return params
    
    def _detect_mosfet_regions(self, vx: np.ndarray, vy: np.ndarray) -> Dict:
        """Detectar regiões do MOSFET"""
        regions = {}
        
        cutoff_mask = vy < 1e-6
        if np.any(cutoff_mask):
            regions['cutoff'] = {
                'vx_min': float(np.min(vx[cutoff_mask])),
                'vx_max': float(np.max(vx[cutoff_mask]))
            }
        
        on_mask = vy > 10e-3
        if np.any(on_mask):
            regions['on'] = {
                'vx_min': float(np.min(vx[on_mask])),
                'vx_max': float(np.max(vx[on_mask]))
            }
        
        return regions
    
    def _calculate_resistor_parameters(self, vx: np.ndarray, vy: np.ndarray) -> Dict:
        """Calcular parâmetros de resistor"""
        params = {}
        
        try:
            nonzero = np.abs(vy) > 1e-12
            if np.any(nonzero):
                r_values = vx[nonzero] / vy[nonzero]
                params['r_resistance'] = float(np.median(r_values))
                params['r_std'] = float(np.std(r_values))
        except Exception:
            params['r_resistance'] = 0.0
            params['r_std'] = 0.0
        
        p_max = np.max(vx * vy)
        params['p_max_dissipated_power'] = float(p_max)
        
        params['r_linearity_error'] = float(1.0 - self._is_linear(vx, vy))
        
        return params
    
    def _calculate_capacitor_parameters(self, vx: np.ndarray, vy: np.ndarray) -> Dict:
        """Calcular parâmetros de capacitor"""
        params = {}
        
        params['vc_max_voltage'] = float(np.max(np.abs(vx)))
        
        try:
            nonzero = np.abs(vy) > 1e-9
            if np.any(nonzero):
                z_est = np.mean(np.abs(vx[nonzero] / vy[nonzero]))
                params['c_capacitance_estimate'] = float(1.0 / z_est) if z_est > 0 else 0.0
        except Exception:
            params['c_capacitance_estimate'] = 0.0
        
        p_avg = np.mean(np.abs(vx * vy))
        params['p_dissipation'] = float(p_avg)
        
        return params
    
    def _calculate_confidence(self, vx: np.ndarray, vy: np.ndarray, 
                             component_type: str, 
                             parameters: Dict) -> float:
        """
        Calcular confiança da detecção (0.0 a 1.0)
        """
        confidence = 0.5
        
        try:
            vx_range = np.max(vx) - np.min(vx)
            vy_range = np.max(vy) - np.min(vy)
            
            if vx_range > 0.1 and vy_range > 1e-6:
                confidence += 0.2
            
            if component_type == 'diode' and 'vf_forward_voltage' in parameters:
                vf = parameters['vf_forward_voltage']
                if 0.3 <= vf <= 1.0:
                    confidence += 0.2
            
            if component_type == 'resistor' and 'r_resistance' in parameters:
                r = parameters['r_resistance']
                if 1.0 <= r <= 1e6:
                    confidence += 0.2
            
            if component_type == 'capacitor' and 'c_capacitance_estimate' in parameters:
                c = parameters['c_capacitance_estimate']
                if 1e-12 <= c <= 1e-3:
                    confidence += 0.2
            
            if component_type == 'unknown':
                confidence -= 0.3
            
            confidence = max(0.0, min(1.0, confidence))
            
        except Exception:
            confidence = 0.5
        
        return confidence
    
    def _generate_notes(self, component_type: str, parameters: Dict) -> List[str]:
        """Gerar notas sobre a medição"""
        notes = []
        
        if component_type == 'diode' or component_type == 'diode_schottky':
            notes.append("Componente com condução unidirecional")
            if 'vf_forward_voltage' in parameters:
                notes.append(f"Vf = {parameters['vf_forward_voltage']:.3f} V")
        
        elif component_type == 'zener':
            notes.append("Componente com ruptura reversa (Zener)")
            if 'vbr_breakdown_voltage' in parameters:
                notes.append(f"Tensão de ruptura = {abs(parameters['vbr_breakdown_voltage']):.2f} V")
        
        elif component_type == 'resistor':
            notes.append("Componente linear (resistor)")
            if 'r_resistance' in parameters:
                notes.append(f"R = {parameters['r_resistance']:.2f} Ω")
        
        elif component_type == 'capacitor':
            notes.append("Componente com característica capacitiva")
            if 'c_capacitance_estimate' in parameters:
                notes.append(f"C (estimado) = {parameters['c_capacitance_estimate']*1e6:.2f} µF")
        
        elif component_type in ['transistor', 'mosfet']:
            notes.append("Dispositivo semicondutor de potência")
            if 'rds_on_resistance' in parameters:
                notes.append(f"Rds(ON) = {parameters['rds_on_resistance']*1e3:.1f} mΩ")
            if 'vgs_threshold_voltage' in parameters:
                notes.append(f"Vgs(th) = {parameters['vgs_threshold_voltage']:.2f} V")
        
        else:
            notes.append("Tipo de componente não identificado")
            notes.append("Tente verificar a conexão do componente")
        
        notes.append(f"Confiança da detecção: {self._calculate_confidence(None, None, component_type, parameters)*100:.0f}%")
        
        return notes


def measure_component(vx: np.ndarray, vy: np.ndarray) -> Dict[str, Any]:
    """
    Função conveniente para medição de componente
    Retorna dicíonario JSON-serializable
    """
    measurer = ParameterMeasurer()
    result = measurer.measure(vx, vy)
    
    return {
        'component_type': result.component_type,
        'parameters': result.parameters,
        'detected_regions': result.detected_regions,
        'confidence': result.confidence,
        'notes': result.notes
    }
