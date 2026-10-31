#!/usr/bin/env python3
"""
Testes de estado da GUI: placeholder inicial, grade sem captura e cursor.
"""

import os
import sys
import time
import unittest
from unittest.mock import patch

# Testes rodam sem display (CI/WSL)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from matplotlib.backend_bases import MouseEvent
from PyQt6.QtWidgets import QApplication

from src.gui import CurveTracerMainWindow


class FakeScope:
    """Scope mínimo para testar escala/centro sem hardware."""

    last_waveform_mode = "RAW"
    scales = {"CHAN1": 0.2, "CHAN2": 1.0}
    offsets = {"CHAN1": 0.02419652, "CHAN2": 0.008780608}

    def get_channel_scale(self, channel):
        return self.scales[channel]

    def get_channel_offset(self, channel):
        return self.offsets[channel]

    def close(self):
        """A GUI chama close() ao fechar a janela; o fake também precisa ter."""
        return None


class FakeCaptureScope(FakeScope):
    """Scope que devolve um frame sintético e registra os parâmetros."""

    def __init__(self):
        self.last_kwargs = None

    def capture_xy(self, **kwargs):
        self.last_kwargs = kwargs
        return np.array([-0.1, 0.0, 0.1]), np.array([-2.0, 0.0, 2.0])

    def is_xy_enabled(self):
        return True


class SlowCaptureScope(FakeCaptureScope):
    """Scope cuja captura demora, para provar que a GUI não bloqueia."""

    def __init__(self, delay=0.5):
        super().__init__()
        self.delay = delay

    def capture_xy(self, **kwargs):
        time.sleep(self.delay)
        return super().capture_xy(**kwargs)


class TestGuiDisplayStates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        # Não varrer a rede durante os testes
        with patch("src.gui.discover_rigol", return_value=([], [])), \
             patch("src.gui.discover_rigol_network", return_value=[]):
            self.win = CurveTracerMainWindow()

    def tearDown(self):
        self.win.close()
        self.win.deleteLater()

    def _connect_fake(self):
        self.win.scope_xy = FakeScope()
        self.win.connected = True
        self.win.show_scope_grid()

    def test_initial_state_has_no_graph(self):
        """Ao abrir sem equipamento não deve existir gráfico nenhum."""
        self.assertEqual(self.win._view_state, "empty")
        self.assertFalse(self.win.ax.get_visible())
        self.assertTrue(self.win._placeholder_text.get_visible())
        self.assertEqual(len(self.win.ax.lines), 0)

    def test_connected_without_capture_shows_grid_only(self):
        """Conectado sem captura: apenas a grade 8x8 do instrumento."""
        self._connect_fake()
        self.assertEqual(self.win._view_state, "grid")
        self.assertTrue(self.win.ax.get_visible())
        self.assertFalse(self.win._placeholder_text.get_visible())
        self.assertEqual(len(self.win.ax.lines), 0)

        x_min, x_max = self.win.ax.get_xlim()
        y_min, y_max = self.win.ax.get_ylim()
        self.assertAlmostEqual((x_min + x_max) / 2, -0.02419652, places=9)
        self.assertAlmostEqual(x_max - x_min, 8 * 0.2, places=9)
        self.assertAlmostEqual((y_min + y_max) / 2, -0.008780608, places=9)
        self.assertAlmostEqual(y_max - y_min, 8 * 1.0, places=9)

        self.assertIn("aguardando captura", self.win.info_text.toPlainText().lower())
        self.assertIn("200 mV/div", self.win.ax.get_xlabel())
        self.assertIn("1 V/div", self.win.ax.get_ylabel())

    def test_capture_draws_trace_and_keeps_scope_scale(self):
        self._connect_fake()
        vx = np.array([-0.1, 0.0, 0.1])
        vy = np.array([-2.0, 0.0, 2.0])
        self.win.plot_curve(vx, vy)

        self.assertEqual(self.win._view_state, "data")
        self.assertGreaterEqual(len(self.win.ax.lines), 1)
        line = self.win.ax.lines[0]
        np.testing.assert_allclose(line.get_xdata(), vx)
        np.testing.assert_allclose(line.get_ydata(), vy)
        # A escala continua sendo a do instrumento, não a dos dados
        self.assertAlmostEqual(self.win.ax.get_xlim()[1] - self.win.ax.get_xlim()[0], 1.6, places=9)

    def test_placeholder_clears_previous_data(self):
        self._connect_fake()
        vx = np.array([0.0, 1.0])
        vy = np.array([0.0, 1.0])
        self.win.plot_curve(vx, vy)
        self.win.last_data = (vx, vy)
        self.assertIsNotNone(self.win.last_data)
        self.win.show_placeholder(clear_data=True)
        self.assertEqual(self.win._view_state, "empty")
        self.assertIsNone(self.win.last_data)
        self.assertFalse(self.win.ax.get_visible())
        self.assertEqual(len(self.win.ax.lines), 0)

    def test_shunt_converts_y_grid_to_amps(self):
        self.win.shunt_spin.setValue(100.0)
        self._connect_fake()
        y_min, y_max = self.win.ax.get_ylim()
        self.assertAlmostEqual(y_max - y_min, 8 * 1.0 / 100.0, places=9)
        self.assertIn("mA/div", self.win.ax.get_ylabel())
        self.assertIn("A]", self.win.ax.get_ylabel())

    def test_shunt_change_with_data_asks_for_new_capture(self):
        """Com curva na tela, o novo shunt só vale na próxima captura."""
        self._connect_fake()
        vx = np.array([0.0, 1.0])
        vy = np.array([0.0, 0.01])
        self.win.plot_curve(vx, vy)
        self.win.last_data = (vx, vy)

        self.win.shunt_spin.setValue(100.0)
        self.assertIn("press CAPTURE", self.win.status_label.text())

    def test_free_cursor_marks_position(self):
        self._connect_fake()
        self.win.cursor_combo.setCurrentText("Free")
        self.win._show_cursor(0.05, 1.5)

        self.assertTrue(self.win._cursor_vline.get_visible())
        self.assertTrue(self.win._cursor_hline.get_visible())
        self.assertTrue(self.win._cursor_marker.get_visible())
        self.assertTrue(self.win._cursor_annot.get_visible())
        text = self.win._cursor_annot.get_text()
        self.assertIn("X:", text)
        self.assertIn("Y:", text)
        self.assertIn("mV", text)  # X em mV (span de 1.6 V)

        self.win._hide_cursor()
        self.assertFalse(self.win._cursor_annot.get_visible())

    def test_free_cursor_follows_mouse_event(self):
        self._connect_fake()
        self.win.canvas.draw()
        self.win.cursor_combo.setCurrentText("Free")

        x_disp, y_disp = self.win.ax.transData.transform((0.1, 1.0))
        event = MouseEvent("motion_notify_event", self.win.canvas, x_disp, y_disp)
        self.win.on_mouse_move(event)

        self.assertTrue(self.win._cursor_annot.get_visible())
        self.assertIn("X:", self.win._cursor_annot.get_text())

    def test_grid_refreshes_when_channel_changes(self):
        self._connect_fake()
        self.assertAlmostEqual(self.win.ax.get_xlim()[1] - self.win.ax.get_xlim()[0], 1.6, places=9)
        # CHAN2 tem 1 V/div: a grade vazia deve acompanhar
        self.win.ch_x_combo.setCurrentText("CHAN2")
        self.assertAlmostEqual(self.win.ax.get_xlim()[1] - self.win.ax.get_xlim()[0], 8.0, places=9)

    def test_single_plot_cursor_on_click(self):
        self._connect_fake()
        self.win.canvas.draw()
        self.win.cursor_combo.setCurrentText("Single-Plot")

        x_disp, y_disp = self.win.ax.transData.transform((-0.1, -2.0))
        event = MouseEvent("button_press_event", self.win.canvas,
                           x_disp, y_disp, button=1)
        self.win.on_mouse_click(event)

        self.assertTrue(self.win._cursor_annot.get_visible())
        self.assertIn("Y:", self.win._cursor_annot.get_text())

        # Trocar para Off esconde o cursor persistente
        self.win.cursor_combo.setCurrentText("Off")
        self.assertFalse(self.win._cursor_annot.get_visible())

    def test_toolbar_has_no_coordinate_readout(self):
        """O toolbar não deve exibir o rótulo '(x, y) = (, )'."""
        self.assertFalse(self.win.toolbar.coordinates)
        self.assertFalse(hasattr(self.win.toolbar, "locLabel"))

    def test_cursor_ignored_when_empty(self):
        self.win.cursor_combo.setCurrentText("Free")
        self.win.on_mouse_move(MouseEvent("motion_notify_event", self.win.canvas, 10, 10))
        self.assertIsNone(self.win._cursor_annot)

    def test_live_capture_exposes_axis_units(self):
        self._connect_fake()
        self.win.shunt_spin.setValue(100.0)
        vx = np.array([0.0, 1.0])
        vy = np.array([0.0, 0.01])
        self.win.plot_curve(vx, vy)
        self.win.last_data = (vx, vy)

        live = self.win.get_live_capture()
        self.assertIsNotNone(live)
        np.testing.assert_allclose(live[0], vx)
        np.testing.assert_allclose(live[1], vy)
        self.assertEqual(live[2], "V")
        self.assertEqual(live[3], "A")
        self.assertTrue(hasattr(self.win, "components_btn"))

    def test_capture_single_plots_and_reports_success(self):
        scope = FakeCaptureScope()
        self.win.scope_xy = scope
        self.win.connected = True

        self.assertTrue(self.win.capture_single())
        self.assertTrue(self._wait_until(lambda: self.win._capture_worker is None))
        self.assertEqual(self.win._view_state, "data")
        self.assertIsNotNone(self.win.last_data)
        self.assertIn("Captured 3 points", self.win.status_label.text())
        # Mesmo em Real-time, o botão da janela de componentes usa uma
        # captura única (não inicia a thread de tempo real).
        self.win.update_mode_combo.setCurrentText("Real-time")
        self.assertTrue(self.win.capture_single())
        self.assertTrue(self._wait_until(lambda: self.win._capture_worker is None))
        self.assertIsNone(self.win._rt_worker)

    def test_single_capture_does_not_block_gui(self):
        """A captura única roda em thread separada (não congela a interface)."""
        scope = SlowCaptureScope(delay=0.5)
        self.win.scope_xy = scope
        self.win.connected = True

        started = time.time()
        self.assertTrue(self.win.capture_single())
        elapsed = time.time() - started

        self.assertLess(elapsed, 0.2)  # retornou antes da captura terminar
        self.assertIsNotNone(self.win._capture_worker)
        self.assertTrue(self._wait_until(lambda: self.win._capture_worker is None))
        self.assertIsNotNone(self.win.last_data)
        self.assertTrue(scope.last_kwargs["keep_xy"])
        self.assertTrue(scope.last_kwargs["resume_after"])

    def test_single_capture_invokes_completion_callback(self):
        scope = FakeCaptureScope()
        self.win.scope_xy = scope
        self.win.connected = True

        results = []
        self.assertTrue(self.win.capture_single(on_done=results.append))
        self.assertTrue(self._wait_until(lambda: bool(results)))
        self.assertEqual(results, [True])

    def test_capture_single_silent_does_not_open_dialog(self):
        """A janela de componentes chama _capture_single(show_errors=False)."""
        self.win.scope_xy = None
        self.win.connected = False
        with patch("src.gui.QMessageBox.warning") as warning:
            self.assertFalse(self.win._capture_single(show_errors=False))
            warning.assert_not_called()
        self.assertIn("Not connected", self.win.status_label.text())

    def _wait_until(self, condition, timeout=5.0):
        """Processa eventos da GUI até ``condition`` virar True."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.app.processEvents()
            if condition():
                return True
            time.sleep(0.01)
        self.app.processEvents()
        return condition()

    def _stop_realtime_and_wait(self):
        self.win.stop_realtime()
        self.assertTrue(self._wait_until(lambda: self.win._rt_worker is None))
        self.assertEqual(self.win.capture_btn.text(), "CAPTURE")
        self.assertTrue(self.win.capture_btn.isEnabled())

    def test_realtime_update_plots_and_resumes_xy(self):
        scope = FakeCaptureScope()
        self.win.scope_xy = scope
        self.win.connected = True
        self.win.show_scope_grid()
        self.assertEqual(self.win._view_state, "grid")

        self.win.start_realtime()
        self.assertTrue(self._wait_until(lambda: self.win.last_data is not None))

        self.assertEqual(self.win._view_state, "data")
        np.testing.assert_allclose(self.win.last_data[0], [-0.1, 0.0, 0.1])
        self.assertTrue(scope.last_kwargs["keep_xy"])
        self.assertTrue(scope.last_kwargs["resume_after"])

        self._stop_realtime_and_wait()

    def test_realtime_shunt_passes_resistance(self):
        scope = FakeCaptureScope()
        self.win.scope_xy = scope
        self.win.connected = True
        self.win.shunt_spin.setValue(100.0)
        self.win.start_realtime()
        self.assertTrue(self._wait_until(lambda: scope.last_kwargs is not None))
        self.assertEqual(scope.last_kwargs["shunt_r"], 100.0)
        self._stop_realtime_and_wait()

    def test_update_mode_locked_while_realtime_running(self):
        """Trocar o Update Mode no meio do tempo real não pode travar a GUI."""
        scope = FakeCaptureScope()
        self.win.scope_xy = scope
        self.win.connected = True
        self.win.start_realtime()
        self.assertTrue(self._wait_until(lambda: self.win.last_data is not None))

        # O combo fica desabilitado enquanto a thread de captura roda
        self.assertFalse(self.win.update_mode_combo.isEnabled())

        # Mesmo forçado para outro modo, o CAPTURE apenas encerra o tempo real
        self.win.update_mode_combo.setCurrentText("Single Capture")
        self.win.on_capture()
        self.assertTrue(self._wait_until(lambda: self.win._rt_worker is None))
        self.assertEqual(self.win.capture_btn.text(), "CAPTURE")
        self.assertTrue(self.win.capture_btn.isEnabled())

    def test_single_capture_refused_while_realtime_running(self):
        """Captura única na thread da GUI não pode concorrer com o worker."""
        scope = FakeCaptureScope()
        self.win.scope_xy = scope
        self.win.connected = True
        self.win.start_realtime()
        self.assertTrue(self._wait_until(lambda: self.win.last_data is not None))

        self.assertFalse(self.win.capture_single())
        self.assertIn("Real-time running", self.win.status_label.text())
        self._stop_realtime_and_wait()


if __name__ == "__main__":
    unittest.main()
