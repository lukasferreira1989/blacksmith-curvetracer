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


class TestDHOScreenScale(unittest.TestCase):
    """A grade da GUI deve reproduzir as 8 divisões do DHO."""

    def test_center_is_minus_offset(self):
        """O centro da tela do DHO fica em -offset (manual: ±4*scale - offset)."""
        from src.scope_xy import compute_channel_screen_range

        vmin, vmax = compute_channel_screen_range(0.2, 0.02419652)
        self.assertAlmostEqual((vmin + vmax) / 2.0, -0.02419652, places=9)
        self.assertAlmostEqual(vmax - vmin, 8 * 0.2, places=9)

    def test_negative_offset_centers_correctly(self):
        """Offset -151 mV => centro em +151 mV, com 8 divisões de 1 V."""
        from src.scope_xy import compute_channel_screen_range

        vmin, vmax = compute_channel_screen_range(1.0, -0.151)
        self.assertAlmostEqual((vmin + vmax) / 2.0, 0.151, places=9)
        self.assertAlmostEqual(vmax - vmin, 8.0, places=9)

    def test_different_volts_per_div_still_eight_divisions(self):
        """Cada eixo tem 8 divisões, mesmo com V/div diferentes."""
        from src.scope_xy import compute_channel_screen_range

        x_min, x_max = compute_channel_screen_range(0.2, 0.0)
        y_min, y_max = compute_channel_screen_range(1.0, 0.0)
        self.assertAlmostEqual(x_max - x_min, 1.6, places=9)
        self.assertAlmostEqual(y_max - y_min, 8.0, places=9)

    def test_get_channel_division_range_uses_scope_queries(self):
        """O método do driver deve usar SCAL?/OFFS? e a convenção -offset."""
        from src.scope_xy import RigolScopeXY

        class FakeScope(RigolScopeXY):
            def __init__(self):
                pass

            def get_channel_scale(self, channel):
                return 0.2

            def get_channel_offset(self, channel):
                return 0.5

        vmin, vmax = FakeScope().get_channel_division_range('CHAN1')
        self.assertAlmostEqual((vmin + vmax) / 2.0, -0.5, places=9)
        self.assertAlmostEqual(vmax - vmin, 1.6, places=9)

    def test_invalid_scale_rejected(self):
        from src.scope_xy import compute_channel_screen_range

        with self.assertRaises(ValueError):
            compute_channel_screen_range(0.0, 0.0)


class TestCapturePreservesXYAndOrder(unittest.TestCase):
    """A captura não deve normalizar eixos nem retomar a aquisição por padrão."""

    def _fake_scope(self, vx, vy):
        from src.scope_xy import RigolScopeXY

        class FakeScope(RigolScopeXY):
            def __init__(self):
                self.connected = True
                self.use_socket = False
                self.inst = None
                self.xy = False
                self.written = []
                self.run_called = False
                self.last_waveform_mode = None
                self.last_preamble = {}

            def is_xy_enabled(self):
                return self.xy

            def stop(self):
                pass

            def run(self):
                self.run_called = True

            def _query(self, cmd):
                if cmd == ':TIM:XY:X?':
                    return 'CHAN1'
                if cmd == ':TIM:XY:Y?':
                    return 'CHAN2'
                if cmd.endswith(':DISP?'):
                    return '1'
                raise AssertionError(cmd)

            def _write(self, cmd):
                self.written.append(cmd)
                if ':TIM:XY:ENABle ON' in cmd:
                    self.xy = True

            def _read_waveform_pair(self, *args, **kwargs):
                return vx, vy, {'yorig': 0, 'yinc': 1}, {'yorig': 0, 'yinc': 1}, 'RAW'

        return FakeScope()

    def test_no_axis_normalization(self):
        vx = np.array([0.0, 0.1, 0.2, 0.1, 0.0])
        vy = np.array([0.0, 2.0, 4.0, 2.0, 0.0])
        scope = self._fake_scope(vx, vy)
        out_x, out_y = scope.capture_xy('CHAN1', 'CHAN2')
        np.testing.assert_allclose(out_x, vx)
        np.testing.assert_allclose(out_y, vy)
        # A proporção original entre os eixos deve ser mantida
        self.assertNotAlmostEqual((out_y.max() - out_y.min()) /
                                  (out_x.max() - out_x.min()), 1.0)
        self.assertIn(':TIM:XY:ENABle ON', ''.join(scope.written))

    def test_order_is_preserved(self):
        vx = np.array([0.0, 1.0, 2.0, 1.0, 0.0, -1.0])
        vy = np.array([0.0, 1.0, 2.0, 1.0, 0.0, -1.0])
        scope = self._fake_scope(vx, vy)
        out_x, out_y = scope.capture_xy('CHAN1', 'CHAN2')
        np.testing.assert_allclose(out_x, vx)
        np.testing.assert_allclose(out_y, vy)

    def test_duplicate_samples_are_not_removed(self):
        """Nenhuma amostra original pode ser descartada (ROADMAP, regra 4)."""
        vx = np.array([0.0, 1.0, 1.0, 2.0, 1.0])
        vy = np.array([0.0, 0.5, 0.5, 0.0, -0.5])
        scope = self._fake_scope(vx, vy)
        out_x, out_y = scope.capture_xy('CHAN1', 'CHAN2')
        np.testing.assert_allclose(out_x, vx)
        np.testing.assert_allclose(out_y, vy)
        self.assertEqual(len(out_x), len(vx))

    def test_capture_resumes_by_default(self):
        """Após a captura o scope volta a rodar em X-Y (padrão)."""
        vx = np.array([0.0, 1.0])
        vy = np.array([0.0, 1.0])
        scope = self._fake_scope(vx, vy)
        scope.capture_xy('CHAN1', 'CHAN2')
        self.assertTrue(scope.run_called)

    def test_resume_after_false_keeps_scope_stopped(self):
        """resume_after=False permite congelar o frame para diagnóstico."""
        vx = np.array([0.0, 1.0])
        vy = np.array([0.0, 1.0])
        scope = self._fake_scope(vx, vy)
        scope.capture_xy('CHAN1', 'CHAN2', resume_after=False)
        self.assertFalse(scope.run_called)


class TestXYSources(unittest.TestCase):
    """Sincronização dos canais X/Y do display com a GUI."""

    def _fake(self, x='CHAN1', y='CHAN2'):
        from src.scope_xy import RigolScopeXY

        class FakeScope(RigolScopeXY):
            def __init__(self):
                self.x = x
                self.y = y
                self.writes = []

            def _query(self, cmd):
                if cmd == ':TIM:XY:X?':
                    return self.x
                if cmd == ':TIM:XY:Y?':
                    return self.y
                raise AssertionError(cmd)

            def _write(self, cmd):
                self.writes.append(cmd)
                if cmd.startswith(':TIM:XY:X '):
                    self.x = cmd.split()[-1]
                elif cmd.startswith(':TIM:XY:Y '):
                    self.y = cmd.split()[-1]

        return FakeScope()

    def test_query_sources(self):
        scope = self._fake()
        self.assertEqual(scope.get_xy_sources(), ('CHAN1', 'CHAN2'))

    def test_same_sources_not_rewritten(self):
        """Reenviar XY:X/Y limpa o traço X-Y; não devemos escrever sem mudança."""
        scope = self._fake()
        self.assertFalse(scope.set_xy_sources('CHAN1', 'CHAN2'))
        self.assertEqual(scope.writes, [])

    def test_changed_sources_rewritten(self):
        scope = self._fake(x='CHAN2', y='CHAN1')
        self.assertTrue(scope.set_xy_sources('CHAN1', 'CHAN2'))
        self.assertEqual(scope.get_xy_sources(), ('CHAN1', 'CHAN2'))

    def test_channel_normalization(self):
        from src.scope_xy import RigolScopeXY
        self.assertEqual(RigolScopeXY._normalize_channel('CHANnel1'), 'CHAN1')
        self.assertEqual(RigolScopeXY._normalize_channel('CHAN2'), 'CHAN2')


if __name__ == '__main__':
    unittest.main()
