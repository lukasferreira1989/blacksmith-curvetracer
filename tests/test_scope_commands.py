#!/usr/bin/env python3
"""Testes dos comandos SCPI do driver X-Y (sem hardware)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.scope_xy import RigolScopeXY


class TestTriggerCommands(unittest.TestCase):
    def setUp(self):
        self.scope = RigolScopeXY()
        self.writes = []
        self.scope._write = self.writes.append

    def test_set_trigger_level_uses_documented_commands(self):
        self.scope.set_trigger_level("CHAN1", 0.5)
        self.assertEqual(
            self.writes,
            [":TRIG:EDGE:SOURce CHAN1", ":TRIG:EDGE:LEVel 0.5"],
        )

    def test_numeric_trigger_channel_is_normalized(self):
        self.scope.set_trigger_level("2", -1.25)
        self.assertEqual(
            self.writes,
            [":TRIG:EDGE:SOURce CHAN2", ":TRIG:EDGE:LEVel -1.25"],
        )

    def test_empty_trigger_channel_is_rejected(self):
        with self.assertRaises(ValueError):
            self.scope.set_trigger_level("  ", 0.5)
        self.assertEqual(self.writes, [])


if __name__ == "__main__":
    unittest.main()
