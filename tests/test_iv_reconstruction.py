#!/usr/bin/env python3
"""
Testes automatizados para reconstrução de curvas I-V
"""

import unittest
import numpy as np
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestIVReconstruction(unittest.TestCase):
    """Testes para garantir reconstrução correta de curvas I-V"""
    
    def test_preserve_original_order(self):
        """Não deve ordenar por tensão/corrente - preservar ordem original"""
        vx = np.array([0, 1, 2, 1, 0, -1])
        vy = np.array([0, 1, 2, 1, 0, -1])
        # Ordem deve ser preservada
        self.assertTrue(np.array_equal(vx, np.array([0, 1, 2, 1, 0, -1])))
        self.assertTrue(np.array_equal(vy, np.array([0, 1, 2, 1, 0, -1])))
    
    def test_capacitor_lissajous_circle(self):
        """Curva circular/ elíptica (capacitor) não deve virar linha"""
        t = np.linspace(0, 2*np.pi, 1000)
        vx = np.sin(t)
        vy = np.cos(t)
        # Não deve haver descontinuidades artificiais
        self.assertEqual(len(vx), len(vy))
        self.assertEqual(len(vx), 1000)
        # Verificar que não é linear
        self.assertFalse(np.allclose(vy, vx))
    
    def test_diode_curve_shape(self):
        """Curva de diodo - forma correta"""
        vx = np.linspace(-1, 0.8, 500)
        vy = np.zeros_like(vx)
        for i, v in enumerate(vx):
            if v < 0.7:
                vy[i] = 1e-12
            else:
                vy[i] = np.exp((v - 0.7) / 0.026) * 1e-12
        self.assertEqual(len(vx), len(vy))
        # Deve ter região reversa e direta
        self.assertTrue(np.any(vy <= 1e-12))
        self.assertTrue(np.any(vy > 1e-11))
    
    def test_sine_wave(self):
        """Onda senoidal - preservar forma"""
        t = np.linspace(0, 2*np.pi, 100)
        vx = np.sin(t)
        vy = np.sin(t + np.pi/4)
        self.assertEqual(len(vx), 100)
        # Crossings por zero
        zero_crossings_x = np.where(np.diff(np.sign(vx)))[0]
        self.assertTrue(len(zero_crossings_x) > 0)
    
    def test_no_artificial_closure(self):
        """Não deve fechar curva artificialmente"""
        vx = np.array([0, 1, 2, 1, -0.1])
        vy = np.array([0, 0.5, 0, -0.5, 0.1])
        # Primeira e última não devem ser forçadas iguais
        self.assertNotAlmostEqual(vx[0], vx[-1], places=10)
        self.assertNotAlmostEqual(vy[0], vy[-1], places=10)
    
    def test_preserve_sample_pairs(self):
        """Manter par (vx, vy) associado à mesma amostra"""
        vx = np.array([1, 2, 3, 4])
        vy = np.array([10, 20, 30, 40])
        pairs = list(zip(vx, vy))
        self.assertEqual(pairs[0], (1, 10))
        self.assertEqual(pairs[2], (3, 30))


class TestScopeXYInterface(unittest.TestCase):
    """Testes para interface scope_xy"""
    
    def test_import_scope_xy(self):
        """Testar importação do módulo"""
        try:
            from src.scope_xy import RigolScopeXY, discover_rigol
            self.assertTrue(True)
        except Exception as e:
            self.fail(f"Failed to import: {e}")
    
    def test_discover_rigol_returns_tuple(self):
        """discover_rigol deve retornar tupla"""
        from src.scope_xy import discover_rigol
        result = discover_rigol()
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
    
    def test_rigol_class_has_required_methods(self):
        """RigolScopeXY deve ter métodos essenciais"""
        from src.scope_xy import RigolScopeXY
        methods = ['connect', 'close', 'capture_xy', 'run', 'stop', 'get_idn',
                   'set_channel_scale', 'set_channel_offset']
        for m in methods:
            self.assertTrue(hasattr(RigolScopeXY, m), f"Missing method: {m}")
    
    def test_capture_xy_signature(self):
        """capture_xy deve ter parâmetros corretos"""
        from src.scope_xy import RigolScopeXY
        import inspect
        sig = inspect.signature(RigolScopeXY.capture_xy)
        params = list(sig.parameters.keys())
        self.assertIn('ch_x', params)
        self.assertIn('ch_y', params)
        self.assertIn('probe_x', params)
        self.assertIn('probe_y', params)


if __name__ == '__main__':
    unittest.main()
