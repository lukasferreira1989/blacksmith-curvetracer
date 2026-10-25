#!/usr/bin/env python3
"""
Matriz de compatibilidade DHO924S
"""
from dataclasses import dataclass
from typing import List

@dataclass
class Feature:
    name: str
    scpi_cmd: str
    implemented: bool
    tested: bool
    notes: str

MATRIX = [
    Feature("IDN Query", "*IDN?", True, True, "Funcional"),
    Feature("Run/Stop/Single", ":RUN/:STOP/:SING", True, True, "Funcional"),
    Feature("Channel Config", ":CHAN<n>:SCAL/OFFS/COUP/PROB", True, True, "Funcional"),
    Feature("Timebase", ":TIM:MAIN:SCAL", True, False, "Implementado"),
    Feature("Waveform Source", ":WAV:SOUR", True, True, "Funcional"),
    Feature("Waveform Mode RAW", ":WAV:MODE RAW", True, True, "Recomendado para DHO"),
    Feature("Waveform Mode NORM", ":WAV:MODE NORM", True, True, "Testado"),
    Feature("Waveform Format BYTE", ":WAV:FORM BYTE", True, True, "Funcional"),
    Feature("Waveform Preamble", ":WAV:PRE?", True, True, "10 params parsed"),
    Feature("Waveform Data Binary", ":WAV:DATA?", True, True, "TMC header parsed"),
    Feature("X-Y Capture", ":WAV:SOUR switch + capture", True, True, "Preserves order"),
    Feature("Error Query", ":SYST:ERR?", True, True, "In driver"),
    Feature("Acquisition Rate", ":ACQ:SRATe?", True, False, "In driver"),
    Feature("Trigger Config", ":TRIG:*", Partial(True), False, "Parcial"),
    Feature("FFT", ":FFT:*", False, False, "Não testado"),
    Feature("Math", ":MATH:*", False, False, "Não implementado"),
    Feature("AFG", ":SOURce:*", False, False, "Não exposto (verificar)"),
    Feature("USB Connection", "USB::...", True, False, "Via VISA"),
    Feature("LAN Socket 5555", "TCP Socket", True, True, "Funcional DHO"),
    Feature("LAN VISA 5025", "TCPIP::5025::SOCKET", True, True, "Via VISA"),
]

def print_matrix():
    print("="*80)
    print("MATRIZ DE COMPATIBILIDADE DHO924S")
    print("="*80)
    for f in MATRIX:
        status = "✅" if f.implemented and f.tested else "⚠️" if f.implemented else "❌"
        print(f"{status} {f.name:25} | {f.scpi_cmd:30} | {f.notes}")
    print("="*80)
    print(f"Implementados: {sum(1 for f in MATRIX if f.implemented)}/{len(MATRIX)}")
    print(f"Testados: {sum(1 for f in MATRIX if f.tested)}/{len(MATRIX)}")

if __name__ == '__main__':
    print_matrix()
