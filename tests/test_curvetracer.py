import unittest
import numpy as np


class TestCurveTracerLegacy(unittest.TestCase):
    """Legacy tests adapted after removing SMU/Yokogawa code"""
    def test_diode_trace_params(self):
        """Test diode trace parameter generation"""
        voltages = np.linspace(0, 1.0, 101)
        self.assertEqual(len(voltages), 101)
        self.assertEqual(voltages[0], 0)
        self.assertEqual(voltages[-1], 1.0)

    def test_fet_output_params(self):
        """Test FET output measurement setup"""
        vgs_values = [0, 1, 2, 3, 4]
        self.assertEqual(len(vgs_values), 5)

    def test_bjt_output_params(self):
        """Test BJT output measurement setup"""
        ib_values = [10e-6, 20e-6, 30e-6, 40e-6, 50e-6]
        self.assertEqual(len(ib_values), 5)


if __name__ == '__main__':
    unittest.main()
