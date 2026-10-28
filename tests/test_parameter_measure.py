#!/usr/bin/env python3
"""
Testes automatizados para Parameter Measurement
"""

import unittest
import numpy as np
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestParameterMeasurer(unittest.TestCase):
    """Testes para ParameterMeasurer"""
    
    def setUp(self):
        """Configuração inicial"""
        from src.parameter_measure import ParameterMeasurer
        self.measurer = ParameterMeasurer()
    
    def test_empty_data_returns_unknown(self):
        """Dados vazios devem retornar tipo 'unknown'"""
        vx = np.array([])
        vy = np.array([])
        result = self.measurer.measure(vx, vy)
        
        self.assertEqual(result.component_type, 'unknown')
        self.assertEqual(result.confidence, 0.0)
    
    def test_resistor_linear_curve(self):
        """Resistor ideal deve ter curva linear"""
        vx = np.linspace(0, 5, 100)
        vy = vx / 100  # R = 100Ω
        
        result = self.measurer.measure(vx, vy)
        
        self.assertEqual(result.component_type, 'resistor')
        self.assertIn('r_resistance', result.parameters)
        self.assertAlmostEqual(result.parameters['r_resistance'], 100, places=1)
    
    def test_diode_forward_characteristic(self):
        """Diodo deve mostrar condução unidirecional"""
        vx = np.linspace(-2, 1, 500)
        vy = np.zeros_like(vx)
        for i, v in enumerate(vx):
            if v < 0.7:
                vy[i] = 1e-12
            else:
                vy[i] = 1e-12 * np.exp((v - 0.7) / 0.026)
        
        result = self.measurer.measure(vx, vy)
        
        self.assertIn(result.component_type, ['diode', 'diode_standard'])
        self.assertIn('vf_forward_voltage', result.parameters)
        self.assertLess(result.parameters['vf_forward_voltage'], 0.9)
    
    def test_diode_schottky(self):
        """Diodo Schottky deve ter Vf menor"""
        vx = np.linspace(-2, 0.5, 500)
        vy = np.zeros_like(vx)
        for i, v in enumerate(vx):
            if v < 0.3:
                vy[i] = 1e-12
            else:
                vy[i] = 1e-12 * np.exp((v - 0.3) / 0.026)
        
        result = self.measurer.measure(vx, vy)
        
        self.assertIn(result.component_type, ['diode', 'diode_schottky', 'diode_standard'])
    
    def test_zener_reverse_breakdown(self):
        """Zener deve mostrar ruptura reversa"""
        vx = np.linspace(-10, 2, 500)
        vy = np.zeros_like(vx)
        for i, v in enumerate(vx):
            if v < -5:  # Zener de 5V
                vy[i] = -1e-3 * (v + 5)  # Região de ruptura
            elif v > 0.7:
                vy[i] = 1e-12 * np.exp(v / 0.026)
            else:
                vy[i] = 1e-12
        
        result = self.measurer.measure(vx, vy)
        
        self.assertEqual(result.component_type, 'zener')
        self.assertIn('vbr_breakdown_voltage', result.parameters)
        self.assertLess(result.parameters['vbr_breakdown_voltage'], -1.0)
    
    def test_capacitor_lissajous(self):
        """Capacitor deve mostrar curva circular/elíptica"""
        t = np.linspace(0, 4*np.pi, 500)
        vx = np.sin(t)
        vy = np.cos(t) * 0.5  # Elipse
        
        result = self.measurer.measure(vx, vy)
        
        self.assertEqual(result.component_type, 'capacitor')
        self.assertIn('c_capacitance_estimate', result.parameters)
    
    def test_transistor_curves(self):
        """Transistor deve mostrar forma característica"""
        # Simular famílias de curvas de BJT
        vx = np.zeros(0)
        vy = np.zeros(0)
        
        for ib in [10e-6, 20e-6, 30e-6, 40e-6, 50e-6]:
            vce = np.linspace(0, 10, 100)
            ic = ib * 100 * np.ones_like(vce)  # hFE = 100
            ic[vce > 2] = ib * 100  # Região ativa
            
            vx = np.concatenate([vx, vce])
            vy = np.concatenate([vy, ic])
        
        result = self.measurer.measure(vx, vy)
        
        self.assertIn(result.component_type, ['transistor'])
    
    def test_mosfet_curve(self):
        """MOSFET deve mostrar caracteísti com threshold"""
        vx = np.linspace(0, 5, 500)
        vy = np.zeros_like(vx)
        
        vth = 2.0  # Threshold voltage
        for i, v in enumerate(vx):
            if v < vth:
                vy[i] = 1e-9  # Cut-off
            else:
                vy[i] = 0.5 * (v - vth)  # Região ativa
        
        result = self.measurer.measure(vx, vy)
        
        self.assertIn(result.component_type, ['mosfet', 'transistor'])
        self.assertIn('vgs_threshold_voltage', result.parameters)
    
    def test_confidence_calculation(self):
        """Confiança deve estar entre 0 e 1"""
        vx = np.linspace(0, 5, 100)
        vy = vx / 100
        
        result = self.measurer.measure(vx, vy)
        
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)
    
    def test_parameters_json_serializable(self):
        """Parâmetros devem ser serializáveis em JSON"""
        vx = np.linspace(0, 5, 100)
        vy = vx / 100
        
        result = self.measurer.measure(vx, vy)
        
        # Deve ser serializável
        import json
        try:
            json.dumps(result.parameters)
        except TypeError:
            self.fail("Parameters not JSON serializable")
    
    def test_measure_component_function(self):
        """Função measure_component deve retornar dict"""
        from src.parameter_measure import measure_component
        
        vx = np.linspace(0, 5, 100)
        vy = vx / 100
        
        result = measure_component(vx, vy)
        
        self.assertIsInstance(result, dict)
        self.assertIn('component_type', result)
        self.assertIn('parameters', result)
        self.assertIn('confidence', result)


class TestComponentDetection(unittest.TestCase):
    """Testes específicos de detecção de componentes"""
    
    def setUp(self):
        from src.parameter_measure import ParameterMeasurer
        self.measurer = ParameterMeasurer()
    
    def test_detect_diode_type(self):
        """Detectar tipo de diodo (Schottky vs standard)"""
        # Schottky
        vx_schottky = np.linspace(-2, 0.5, 500)
        vy_schottky = np.array([1e-12 * np.exp((v - 0.3) / 0.026) if v > 0 else 1e-12 for v in vx_schottky])
        
        result_schottky = self.measurer.measure(vx_schottky, vy_schottky)
        
        # Standard diode
        vx_std = np.linspace(-2, 1.0, 500)
        vy_std = np.array([1e-12 * np.exp((v - 0.7) / 0.026) if v > 0 else 1e-12 for v in vx_std])
        
        result_std = self.measurer.measure(vx_std, vy_std)
        
        # Ambos devem ser detectados como diodos
        self.assertIn(result_schottky.component_type, ['diode', 'diode_schottky', 'diode_standard'])
        self.assertIn(result_std.component_type, ['diode', 'diode_schottky', 'diode_standard'])
    
    def test_detect_high_resistance(self):
        """Detectar resistor de alta resistência"""
        vx = np.linspace(0, 10, 100)
        vy = vx / 1e6  # 1MΩ
        result = self.measurer.measure(vx, vy)
        
        self.assertEqual(result.component_type, 'resistor')
        self.assertAlmostEqual(result.parameters['r_resistance'], 1e6, places=2)
    
    def test_detect_low_resistance(self):
        """Detectar resistor de baixa resistência"""
        vx = np.linspace(0, 1, 100)
        vy = vx / 0.1  # 0.1Ω
        
        result = self.measurer.measure(vx, vy)
        
        self.assertEqual(result.component_type, 'resistor')
        self.assertAlmostEqual(result.parameters['r_resistance'], 0.1, places=2)


class TestMeasurementUtilities(unittest.TestCase):
    """Testes de utilitários de medição"""
    
    def test_diode_regions_detection(self):
        """Detectar regiões da curva do diodo"""
        from src.parameter_measure import ParameterMeasurer
        
        measurer = ParameterMeasurer()
        
        vx = np.linspace(-5, 1, 500)
        vy = np.array([1e-12 * np.exp((v - 0.7) / 0.026) if v > 0 else 1e-12 for v in vx])
        
        result = measurer.measure(vx, vy)
        
        self.assertIn('detected_regions', result.__dict__)
        regions = result.detected_regions
        
        # Deve ter regiões forward e reverse
        self.assertIn('forward', regions)
        self.assertIn('reverse', regions)
    
    def test_resistor_linearity(self):
        """Verificar linearidade de resistor"""
        from src.parameter_measure import ParameterMeasurer
        
        measurer = ParameterMeasurer()
        
        vx = np.linspace(0, 5, 100)
        vy = 2.0 * vx + 0.1  # R = 0.5Ω com pequeno offset
        
        result = measurer.measure(vx, vy)
        
        self.assertEqual(result.component_type, 'resistor')
        self.assertLess(result.parameters['r_linearity_error'], 0.1)


class TestIntegrationWithGUI(unittest.TestCase):
    """Testes de integração com a interface"""
    
    def test_measurement_integration(self):
        """Testar que medições são integráveis na GUI"""
        from src.parameter_measure import measure_component
        from src.curve_reconstruct import CurveReconstructor
        
        # Simular dados do scope
        t = np.linspace(0, 2*np.pi, 1000)
        vx = np.sin(t)
        vy = (np.cos(t) - 0.5) * 0.1  # Corrente com offset
        
        # Reconstruir
        recon = CurveReconstructor()
        result = recon.reconstruct(vx, vy)
        
        # Medir
        measurement = measure_component(result['vx'], result['vy'])
        
        # Verificar estrutura
        self.assertIn('component_type', measurement)
        self.assertIn('parameters', measurement)
        self.assertIn('confidence', measurement)
        self.assertIn('notes', measurement)


if __name__ == '__main__':
    unittest.main()
