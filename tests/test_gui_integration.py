#!/usr/bin/env python3
"""
Testes de integração da GUI com Parameter Measurement
(Sem dependências pesadas)
"""

import unittest
import ast
import re


class TestGUIMeasureIntegration(unittest.TestCase):
    """Testes de integração da GUI com Parameter Measurement"""

    def setUp(self):
        """Carrega o código da GUI"""
        with open('src/gui.py', 'r') as f:
            self.gui_code = f.read()

    def test_has_parameter_measure_import(self):
        """Verifica import do parameter_measure"""
        self.assertIn('from parameter_measure import', self.gui_code)
        self.assertIn('from src.parameter_measure import', self.gui_code)
        self.assertIn('HAS_PARAMETER_MEASURE', self.gui_code)

    def test_has_measure_button(self):
        """Verifica criação do botão MEASURE"""
        self.assertIn('self.measure_btn', self.gui_code)
        self.assertIn('MEASURE', self.gui_code)
        # Deve criar o botão condicionalmente
        self.assertIn('if HAS_PARAMETER_MEASURE:', self.gui_code)

    def test_has_measurement_panel(self):
        """Verifica panel de resultados"""
        self.assertIn('Component Measurement', self.gui_code)
        self.assertIn('self.measurement_type_label', self.gui_code)
        self.assertIn('self.measurement_confidence_label', self.gui_code)
        self.assertIn('self.measurement_params_text', self.gui_code)
        self.assertIn('self.measurement_notes_text', self.gui_code)

    def test_has_on_measure_method(self):
        """Verifica método on_measure"""
        self.assertIn('def on_measure(self):', self.gui_code)
        self.assertIn('ParameterMeasurer()', self.gui_code)
        self.assertIn('measurer.measure(vx, vy)', self.gui_code)

    def test_has_display_measurement_method(self):
        """Verifica método _display_measurement"""
        self.assertIn('def _display_measurement(self, result):', self.gui_code)
        self.assertIn('measurement_type_label', self.gui_code)
        self.assertIn('confidence', self.gui_code)

    def test_connects_measure_button_signal(self):
        """Verifica conexão do sinal do botão"""
        self.assertIn('self.measure_btn.clicked.connect', self.gui_code)
        self.assertIn('on_measure', self.gui_code)

    def test_has_last_measurement_attribute(self):
        """Verifica atributo para armazenar resultado"""
        self.assertIn('_last_measurement', self.gui_code)

    def test_error_handling_for_missing_module(self):
        """Verifica tratamento quando módulo não disponível"""
        # Deve mostrar aviso quando HAS_PARAMETER_MEASURE é False
        self.assertIn('Parameter Measurement module is not available', self.gui_code)

    def test_syntactically_valid(self):
        """Verifica que o código é sintaticamente válido"""
        try:
            ast.parse(self.gui_code)
        except SyntaxError as e:
            self.fail(f"Syntax error in gui.py: {e}")


if __name__ == '__main__':
    unittest.main()
