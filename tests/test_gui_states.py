#!/usr/bin/env python3
"""
Testes de estado da GUI: placeholder inicial, grade sem captura e cursor.
"""

import os
import sys
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


class FakeCaptureScope(FakeScope):
    """Scope que devolve um frame sintético e registra os parâmetros."""

    def __init__(self):
        self.last_kwargs = None

    def capture_xy(self, **kwargs):
        self.last_kwargs = kwargs
        return np.array([-0.1, 0.0, 0.1]), np.array([-2.0, 0.0, 2.0])

    def is_xy_enabled(self):
        return True


class TestGuiDisplayStates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        # Não varrer a rede durante os testes
        with patch("src.gui.discover_rigol", return_value=([], [])):
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
        self.assertEqual(self.win._view_state, "data")
        self.assertIsNotNone(self.win.last_data)
        self.assertIn("Captured 3 points", self.win.status_label.text())
        # Mesmo em Real-time, o botão da janela de componentes usa uma
        # captura única (não inicia o timer).
        self.win.update_mode_combo.setCurrentText("Real-time")
        self.assertTrue(self.win.capture_single())
        self.assertIsNone(self.win.capture_timer)

    def test_realtime_update_plots_and_resumes_xy(self):
        scope = FakeCaptureScope()
        self.win.scope_xy = scope
        self.win.connected = True
        self.win.show_scope_grid()
        self.assertEqual(self.win._view_state, "grid")

        self.win.update_realtime()

        self.assertEqual(self.win._view_state, "data")
        self.assertIsNotNone(self.win.last_data)
        np.testing.assert_allclose(self.win.last_data[0], [-0.1, 0.0, 0.1])
        self.assertTrue(scope.last_kwargs["keep_xy"])
        self.assertTrue(scope.last_kwargs["resume_after"])

    def test_realtime_shunt_passes_resistance(self):
        scope = FakeCaptureScope()
        self.win.scope_xy = scope
        self.win.connected = True
        self.win.shunt_spin.setValue(100.0)
        self.win.update_realtime()
        self.assertEqual(scope.last_kwargs["shunt_r"], 100.0)


if __name__ == "__main__":
    unittest.main()
