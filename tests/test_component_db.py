#!/usr/bin/env python3
"""Testes de persistência de componentes, pinos e capturas."""

import base64
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.component_db import ComponentDB, detect_image_mime

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class TestComponentDB(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "components.db"
        self.db = ComponentDB(self.path)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_component_crud_and_listing(self):
        cid = self.db.create_component(
            "2N3904", "onsemi", "TO-92", "NPN, BJT", "sample"
        )
        component = self.db.get_component(cid)
        self.assertEqual(component.reference, "2N3904")
        self.assertEqual(component.manufacturer, "onsemi")
        self.assertEqual(component.package, "TO-92")
        self.assertEqual(component.tags, "NPN, BJT")
        self.assertFalse(component.has_image)

        self.db.update_component(cid, reference="2N3904G", notes="updated")
        component = self.db.get_component(cid)
        self.assertEqual(component.reference, "2N3904G")
        self.assertEqual(component.notes, "updated")

        listed = self.db.list_components()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].id, cid)

        self.assertTrue(self.db.delete_component(cid))
        self.assertIsNone(self.db.get_component(cid))
        self.assertEqual(self.db.list_components(), [])

    def test_reference_is_required(self):
        with self.assertRaises(ValueError):
            self.db.create_component("   ")
        cid = self.db.create_component("R1")
        with self.assertRaises(ValueError):
            self.db.update_component(cid, reference="")

    def test_image_roundtrip_and_detection(self):
        cid = self.db.create_component("IC1")
        self.assertEqual(detect_image_mime(PNG_1PX), "image/png")
        with self.assertRaises(ValueError):
            detect_image_mime(b"not an image")

        self.db.set_component_image(cid, PNG_1PX, "ic1.png")
        name, mime, blob = self.db.get_component_image(cid)
        self.assertEqual(name, "ic1.png")
        self.assertEqual(mime, "image/png")
        self.assertEqual(blob, PNG_1PX)
        self.assertTrue(self.db.get_component(cid).has_image)

        self.db.clear_component_image(cid)
        _, _, blob = self.db.get_component_image(cid)
        self.assertIsNone(blob)
        self.assertFalse(self.db.get_component(cid).has_image)

    def test_pins_crud_and_normalized_coordinates(self):
        cid = self.db.create_component("J1")
        p1 = self.db.add_pin(cid, "1", "VCC", 0.1, 0.2)
        p2 = self.db.add_pin(cid, "2", "GND")
        pins = self.db.list_pins(cid)
        self.assertEqual([p.number for p in pins], ["1", "2"])
        self.assertEqual(pins[0].label, "VCC")
        self.assertAlmostEqual(pins[0].x, 0.1)
        self.assertIsNone(pins[1].x)

        self.db.update_pin(p1, label="VCC_5V", x=0.3, y=0.4)
        pins = {p.id: p for p in self.db.list_pins(cid)}
        self.assertEqual(pins[p1].label, "VCC_5V")
        self.assertAlmostEqual(pins[p1].x, 0.3)

        with self.assertRaises(ValueError):
            self.db.add_pin(cid, "3", x=1.5, y=0.5)
        with self.assertRaises(ValueError):
            self.db.add_pin(cid, "4", x=0.5)  # x sem y

        self.assertTrue(self.db.delete_pin(p2))
        self.assertEqual(len(self.db.list_pins(cid)), 1)

    def test_duplicate_pin_number_rejected(self):
        cid = self.db.create_component("U1")
        self.db.add_pin(cid, "1")
        with self.assertRaises(Exception):
            self.db.add_pin(cid, "1")

    def test_capture_roundtrip_preserves_order_and_samples(self):
        cid = self.db.create_component("Q1")
        pa = self.db.add_pin(cid, "1", "B")
        pb = self.db.add_pin(cid, "2", "E")
        xs = [0.0, 0.1, 0.05, -0.2, 0.3]
        ys = [0.0, 0.01, 0.02, -0.03, 0.04]

        capture_id = self.db.add_capture(
            cid, xs, ys, label="B-E forward", pin_a=pa, pin_b=pb,
            x_unit="V", y_unit="A",
        )
        capture = self.db.get_capture(capture_id)
        self.assertEqual(capture.x, xs)  # ordem temporal intacta
        self.assertEqual(capture.y, ys)  # nenhuma amostra removida
        self.assertEqual(capture.n_points, len(xs))
        self.assertEqual(capture.pin_a_number, "1")
        self.assertEqual(capture.pin_b_number, "2")
        self.assertEqual(capture.x_unit, "V")
        self.assertEqual(capture.y_unit, "A")

        summaries = self.db.list_captures(cid)
        self.assertEqual(len(summaries), 1)
        self.assertIsNone(summaries[0].x)
        self.assertEqual(summaries[0].n_points, 5)

    def test_capture_validation(self):
        cid = self.db.create_component("D1")
        with self.assertRaises(ValueError):
            self.db.add_capture(cid, [0.0], [0.0, 1.0])
        with self.assertRaises(ValueError):
            self.db.add_capture(cid, [], [])
        with self.assertRaises(ValueError):
            self.db.add_capture(cid, [0.0, float("nan")], [0.0, 1.0])

    def test_cascade_delete_removes_pins_and_captures(self):
        cid = self.db.create_component("U2")
        pin = self.db.add_pin(cid, "1")
        cap = self.db.add_capture(cid, [0, 1], [0, 1], pin_a=pin)
        self.db.delete_component(cid)
        self.assertEqual(self.db.list_pins(cid), [])
        self.assertIsNone(self.db.get_capture(cap))

    def test_delete_pin_keeps_capture_but_clears_pin_reference(self):
        cid = self.db.create_component("U3")
        pin = self.db.add_pin(cid, "1")
        cap = self.db.add_capture(cid, [0, 1], [0, 1], pin_a=pin)
        self.db.delete_pin(pin)
        capture = self.db.get_capture(cap)
        self.assertIsNotNone(capture)
        self.assertIsNone(capture.pin_a)
        self.assertIsNone(capture.pin_a_number)

    def test_persistence_across_reopen(self):
        cid = self.db.create_component("IC2", "TI", "DIP-8")
        self.db.add_pin(cid, "1", "OUT", 0.25, 0.75)
        self.db.add_capture(cid, [0.0, 1.0], [0.0, 0.001], label="OUT")
        self.db.close()

        reopened = ComponentDB(self.path)
        try:
            component = reopened.get_component(cid)
            self.assertEqual(component.reference, "IC2")
            self.assertEqual(len(component.pins), 1)
            self.assertEqual(component.pins[0].label, "OUT")
            self.assertEqual(len(component.captures), 1)
            capture = reopened.get_capture(component.captures[0].id)
            self.assertEqual(capture.x, [0.0, 1.0])
        finally:
            reopened.close()


if __name__ == "__main__":
    unittest.main()
