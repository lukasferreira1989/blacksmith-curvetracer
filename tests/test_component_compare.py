#!/usr/bin/env python3
"""Testes da comparação entre captura salva e captura atual."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.component_compare import compare_curves


class TestCompareCurves(unittest.TestCase):
    def test_identical_monotonic_curves_match(self):
        x = np.linspace(-1.0, 1.0, 500)
        y = 0.5 * x + 0.1
        result = compare_curves(x, y, x, y)
        self.assertEqual(result.method, "interpolation")
        self.assertEqual(result.verdict, "MATCH")
        self.assertFalse(result.is_anomaly)
        self.assertAlmostEqual(result.nrmse, 0.0, places=9)
        self.assertAlmostEqual(result.correlation, 1.0, places=6)
        self.assertEqual(result.n_reference, 500)
        self.assertEqual(result.n_live, 500)

    def test_shifted_curve_is_detected_as_deviation(self):
        x = np.linspace(0.0, 1.0, 300)
        y = x.copy()
        result = compare_curves(x, y, x, y + 0.2, tolerance=0.05)
        self.assertEqual(result.method, "interpolation")
        self.assertEqual(result.verdict, "DEVIATION")
        self.assertTrue(result.is_anomaly)
        self.assertGreater(result.nrmse, 0.05)
        self.assertAlmostEqual(result.max_error, 0.2, places=6)

    def test_warning_band(self):
        x = np.linspace(0.0, 1.0, 300)
        y = x.copy()
        result = compare_curves(x, y, x, y + 0.2, tolerance=0.15)
        self.assertEqual(result.verdict, "WARNING")
        self.assertTrue(result.is_anomaly)

    def test_interpolation_uses_overlap_only(self):
        x_ref = np.linspace(0.0, 2.0, 200)
        x_live = np.linspace(1.0, 3.0, 200)
        result = compare_curves(x_ref, x_ref, x_live, x_live)
        self.assertEqual(result.method, "interpolation")
        self.assertEqual(result.verdict, "MATCH")
        self.assertEqual(result.x_overlap, (1.0, 2.0))

    def test_non_monotonic_loop_identical(self):
        t = np.linspace(0, 2 * np.pi, 400)
        x = np.cos(t)
        y = np.sin(t)
        result = compare_curves(x, y, x, y)
        self.assertEqual(result.method, "geometric")
        self.assertEqual(result.verdict, "MATCH")
        self.assertAlmostEqual(result.nrmse, 0.0, places=9)
        self.assertGreater(result.correlation, 0.99)

    def test_reversed_loop_still_matches(self):
        t = np.linspace(0, 2 * np.pi, 400)
        x = np.cos(t)
        y = np.sin(t)
        result = compare_curves(x, y, x[::-1], y[::-1])
        self.assertEqual(result.verdict, "MATCH")
        self.assertGreater(result.correlation, 0.99)

    def test_distorted_loop_is_deviation(self):
        t = np.linspace(0, 2 * np.pi, 400)
        x = np.cos(t)
        y = np.sin(t)
        result = compare_curves(x, y, x, 1.5 * y, tolerance=0.05)
        self.assertEqual(result.method, "geometric")
        self.assertEqual(result.verdict, "DEVIATION")
        self.assertTrue(result.is_anomaly)
        self.assertGreater(result.nrmse, 0.05)

    def test_no_x_overlap_falls_back_to_geometric(self):
        x_ref = np.linspace(0.0, 1.0, 100)
        x_live = np.linspace(5.0, 6.0, 100)
        result = compare_curves(x_ref, x_ref, x_live, x_live)
        self.assertEqual(result.method, "geometric")
        self.assertIsNone(result.x_overlap)
        self.assertEqual(result.verdict, "DEVIATION")

    def test_local_spike_is_flagged_even_with_low_rms(self):
        x = np.linspace(0.0, 1.0, 800)
        y = x.copy()
        spike = 0.15 * np.exp(-((x - 0.5) / 0.01) ** 2)
        result = compare_curves(x, y, x, y + spike, tolerance=0.05)
        # O RMS fica baixo, mas o desvio máximo é 15% do span: não é MATCH.
        self.assertLess(result.nrmse, 0.05)
        self.assertAlmostEqual(result.max_error_normalized, 0.15, places=2)
        self.assertEqual(result.verdict, "WARNING")

        strict = compare_curves(x, y, x, y + spike, tolerance=0.02)
        self.assertEqual(strict.verdict, "DEVIATION")

    def test_requires_enough_points(self):
        with self.assertRaises(ValueError):
            compare_curves([0.0], [0.0], [0.0, 1.0], [0.0, 1.0])
        with self.assertRaises(ValueError):
            compare_curves([0.0, 1.0], [0.0], [0.0, 1.0], [0.0, 1.0])

    def test_non_finite_samples_are_ignored(self):
        x = np.array([0.0, 0.5, np.nan, 1.0])
        y = np.array([0.0, 0.5, 99.0, 1.0])
        result = compare_curves(x, y, [0.0, 0.5, 1.0], [0.0, 0.5, 1.0])
        self.assertEqual(result.n_reference, 3)
        self.assertEqual(result.verdict, "MATCH")


if __name__ == "__main__":
    unittest.main()
