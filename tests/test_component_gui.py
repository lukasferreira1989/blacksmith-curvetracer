#!/usr/bin/env python3
"""Testes da janela de cadastro e comparação de componentes (offscreen)."""

import base64
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PyQt6.QtWidgets import QApplication

from src.component_gui import ComponentManagerDialog

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class TestComponentManagerDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "components.db"
        self.live = None

        def get_live():
            return self.live

        self.dialog = ComponentManagerDialog(
            db_path=self.db_path,
            get_live_capture=get_live,
            capture_now=lambda: None,
        )

    def tearDown(self):
        self.dialog.close()
        self.dialog.deleteLater()
        self.tmp.cleanup()

    def _seed_component(self):
        self.dialog.reference_edit.setText("2N3904")
        self.dialog.manufacturer_edit.setText("onsemi")
        self.dialog.package_edit.setText("TO-92")
        self.dialog.tags_edit.setText("NPN, BJT")
        self.dialog.notes_edit.setPlainText("reference sample")
        component_id = self.dialog.save_profile()
        self.assertIsNotNone(component_id)
        return component_id

    def test_save_profile_and_reload(self):
        component_id = self._seed_component()
        component = self.dialog.db.get_component(component_id)
        self.assertEqual(component.reference, "2N3904")
        self.assertEqual(component.manufacturer, "onsemi")
        self.assertEqual(component.package, "TO-92")
        self.assertEqual(component.tags, "NPN, BJT")
        self.assertEqual(self.dialog.component_list.count(), 1)

        self.dialog.new_component()
        self.assertIsNone(self.dialog.current_id)
        self.assertEqual(self.dialog.component_list.count(), 1)

        self.dialog.load_component(component_id)
        self.assertEqual(self.dialog.current_id, component_id)
        self.assertEqual(self.dialog.reference_edit.text(), "2N3904")

    def test_add_pins_with_and_without_coordinates(self):
        component_id = self._seed_component()
        self.dialog.add_pin_without_position()
        self.dialog._on_pin_map_clicked(0.25, 0.75)

        pins = self.dialog.db.list_pins(component_id)
        self.assertEqual(len(pins), 2)
        self.assertEqual(pins[0].number, "1")
        self.assertIsNone(pins[0].x)
        self.assertEqual(pins[1].number, "2")
        self.assertAlmostEqual(pins[1].x, 0.25)
        self.assertAlmostEqual(pins[1].y, 0.75)
        self.assertEqual(self.dialog.pin_table.rowCount(), 2)

    def test_pin_label_edit_is_persisted(self):
        component_id = self._seed_component()
        self.dialog.add_pin_without_position()
        item = self.dialog.pin_table.item(0, 1)
        item.setText("BASE")
        pins = self.dialog.db.list_pins(component_id)
        self.assertEqual(pins[0].label, "BASE")

    def test_load_image_button_opens_file_dialog(self):
        """O clique real do botão deve abrir o seletor (sem bool como path)."""
        image_path = Path(self.tmp.name) / "part.png"
        image_path.write_bytes(PNG_1PX)

        with patch(
            "src.component_gui.QFileDialog.getOpenFileName",
            return_value=(str(image_path), ""),
        ) as picker:
            self.dialog.load_image_btn.click()
            picker.assert_called_once()

        self.assertTrue(self.dialog.pin_map.has_image())
        self.assertEqual(self.dialog._image_state, "loaded")

    def test_save_profile_button_creates_component(self):
        self.dialog.reference_edit.setText("BTN1")
        self.dialog.save_profile_btn.click()
        references = [c.reference for c in self.dialog.db.list_components()]
        self.assertEqual(references, ["BTN1"])
        self.assertIsNotNone(self.dialog.current_id)

    def test_import_csv_button_opens_file_dialog(self):
        component_id = self._seed_component()
        csv_path = Path(self.tmp.name) / "btn.csv"
        csv_path.write_text("Voltage_V,Current_A\n0.0,0.0\n0.1,0.001\n")

        with patch(
            "src.component_gui.QFileDialog.getOpenFileName",
            return_value=(str(csv_path), ""),
        ) as picker:
            self.dialog.import_capture_btn.click()
            picker.assert_called_once()

        self.assertEqual(len(self.dialog.db.list_captures(component_id)), 1)

    def test_search_filter_updates_list(self):
        self._seed_component()
        self.dialog.db.create_component("BC547", "onsemi")
        self.dialog.refresh_components()
        self.assertEqual(self.dialog.component_list.count(), 2)

        self.dialog.search_edit.setText("bc547")
        self.assertEqual(self.dialog.component_list.count(), 1)
        self.assertIn("BC547", self.dialog.component_list.item(0).text())

        self.dialog.search_edit.clear()
        self.assertEqual(self.dialog.component_list.count(), 2)

    def test_image_load_and_persist(self):
        component_id = self._seed_component()
        image_path = Path(self.tmp.name) / "part.png"
        image_path.write_bytes(PNG_1PX)

        self.dialog.load_image(str(image_path))
        self.assertTrue(self.dialog.pin_map.has_image())
        self.assertEqual(self.dialog._image_state, "loaded")
        self.assertIsNotNone(self.dialog.save_profile())

        name, mime, blob = self.dialog.db.get_component_image(component_id)
        self.assertEqual(name, "part.png")
        self.assertEqual(mime, "image/png")
        self.assertEqual(blob, PNG_1PX)

    def test_save_current_capture_and_compare(self):
        component_id = self._seed_component()
        self.dialog.add_pin_without_position()
        self.dialog.add_pin_without_position()

        x = np.linspace(0.0, 1.0, 200)
        y = 0.5 * x
        self.live = (x, y, "V", "A")
        self.dialog.capture_label_edit.setText("forward")
        self.dialog.capture_pin_a_combo.setCurrentIndex(1)
        self.dialog.capture_pin_b_combo.setCurrentIndex(2)
        self.dialog.save_current_capture()

        captures = self.dialog.db.list_captures(component_id)
        self.assertEqual(len(captures), 1)
        self.assertEqual(captures[0].label, "forward")
        self.assertEqual(captures[0].n_points, 200)
        self.assertEqual(self.dialog.capture_table.rowCount(), 1)
        self.assertEqual(self.dialog.reference_combo.count(), 1)

        self.dialog.reference_combo.setCurrentIndex(0)
        self.dialog.compare_now()
        self.assertIsNotNone(self.dialog._last_comparison)
        self.assertEqual(self.dialog._last_comparison.verdict, "MATCH")
        self.assertIn("MATCH", self.dialog.metrics_text.toPlainText())

        # Captura atual deslocada deve gerar anomalia
        self.live = (x, y + 0.3, "V", "A")
        self.dialog.compare_now()
        self.assertEqual(self.dialog._last_comparison.verdict, "DEVIATION")
        self.assertTrue(self.dialog._last_comparison.is_anomaly)

    def test_compare_refuses_mismatched_units(self):
        component_id = self._seed_component()
        self.live = (
            np.array([0.0, 1.0]), np.array([0.0, 0.001]), "V", "A"
        )
        self.dialog.save_current_capture()

        self.live = (np.array([0.0, 1.0]), np.array([0.0, 0.5]), "V", "V")
        with patch("src.component_gui.QMessageBox.warning") as warning:
            self.dialog.compare_now()
            warning.assert_called_once()
        self.assertIsNone(self.dialog._last_comparison)
        self.assertIsNotNone(self.dialog.db.get_component(component_id))

    def test_capture_and_save_button_acquires_and_stores(self):
        """O clique deve capturar um frame e salvar sem trocar de janela."""
        component_id = self._seed_component()
        x = np.linspace(0.0, 1.0, 120)
        y = 0.5 * x

        def capture_now(on_done=None):
            self.live = (x, y, "V", "A")
            if callable(on_done):
                on_done(True)
            return True

        self.dialog._capture_now = capture_now
        self.dialog.capture_label_edit.setText("inline capture")
        self.dialog.capture_save_btn.click()

        captures = self.dialog.db.list_captures(component_id)
        self.assertEqual(len(captures), 1)
        self.assertEqual(captures[0].label, "inline capture")
        self.assertEqual(captures[0].n_points, 120)
        self.assertEqual(self.dialog.capture_table.rowCount(), 1)
        self.assertEqual(self.dialog._live_capture[0][0], x[0])

    def test_capture_and_save_reports_failure_and_stores_nothing(self):
        component_id = self._seed_component()

        def capture_now_fails(on_done=None):
            return False

        self.dialog._capture_now = capture_now_fails
        with patch("src.component_gui.QMessageBox.warning") as warning:
            self.dialog.capture_save_btn.click()
            warning.assert_called_once()

        self.assertEqual(self.dialog.db.list_captures(component_id), [])
        self.assertEqual(self.dialog.capture_table.rowCount(), 0)
        self.assertIn("Capture failed", self.dialog.status_label.text())

    def test_capture_and_compare_reports_failure(self):
        self._seed_component()

        def capture_now_fails(on_done=None):
            return False

        self.dialog._capture_now = capture_now_fails
        with patch("src.component_gui.QMessageBox.warning") as warning:
            self.dialog.capture_compare_btn.click()
            warning.assert_called_once()

        self.assertIsNone(self.dialog._live_capture)
        self.assertIsNone(self.dialog._last_comparison)

    def test_import_csv(self):
        component_id = self._seed_component()
        csv_path = Path(self.tmp.name) / "curve.csv"
        csv_path.write_text(
            "Voltage_V,Current_A\n0.0,0.0\n0.1,0.001\n0.2,0.002\n"
        )
        self.dialog.import_capture_csv(str(csv_path))
        captures = self.dialog.db.list_captures(component_id)
        self.assertEqual(len(captures), 1)
        self.assertEqual(captures[0].n_points, 3)
        self.assertEqual(captures[0].label, "curve")

    def test_delete_capture_removes_only_capture(self):
        component_id = self._seed_component()
        self.live = (np.array([0.0, 1.0]), np.array([0.0, 1.0]), "V", "A")
        self.dialog.save_current_capture()
        self.assertEqual(len(self.dialog.db.list_captures(component_id)), 1)

        self.dialog.capture_table.selectRow(0)
        self.dialog.delete_selected_capture()
        self.assertEqual(self.dialog.db.list_captures(component_id), [])
        self.assertIsNotNone(self.dialog.db.get_component(component_id))


if __name__ == "__main__":
    unittest.main()
