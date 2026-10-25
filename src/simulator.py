#!/usr/bin/env python3
"""
Instrument Simulator for testing without hardware
Simulates DHO924S responses based on documented SCPI
"""

import numpy as np
import time
from typing import Tuple, Dict, Any


class SimulatedDHO:
    """Simulated Rigol DHO for testing"""
    
    def __init__(self):
        self.connected = True
        self.running = True
        self.channels = {'CHAN1': {'scale': 1.0, 'offset': 0.0}, 
                        'CHAN2': {'scale': 1.0, 'offset': 0.0}}
        self.waveform_data = {}
        self.idn = "RIGOL TECHNOLOGIES,DHO924S,SIMULATED,00.01.04"
        
    def query(self, cmd: str) -> str:
        cmd = cmd.strip()
        if cmd == '*IDN?':
            return self.idn
        elif cmd == ':SYST:ERR?':
            return '0,"No error"'
        elif ':WAV:PRE?' in cmd:
            return '0,2,1000,1,1.0e-6,0,0,0.001,0,128'
        elif ':CHAN1:SCAL?' in cmd:
            return str(self.channels['CHAN1']['scale'])
        elif ':CHAN2:SCAL?' in cmd:
            return str(self.channels['CHAN2']['scale'])
        elif ':TIM:MAIN:SCAL?' in cmd:
            return '1.0e-3'
        return ''
    
    def write(self, cmd: str):
        cmd = cmd.strip()
        if cmd == ':RUN':
            self.running = True
        elif cmd == ':STOP':
            self.running = False
    
    def query_binary_values(self, cmd: str, datatype='B', container=np.array):
        if ':WAV:DATA?' in cmd:
            # Generate synthetic waveform
            t = np.linspace(0, 2*np.pi, 1000)
            # Simulate different patterns based on context
            data = (np.sin(t) * 64 + 128).astype(np.uint8)
            return container(data)
        return container([])
    
    def generate_curve(self, curve_type='diode'):
        """Generate synthetic I-V curve"""
        if curve_type == 'diode':
            vx = np.linspace(-1, 0.8, 500)
            vy = np.where(vx < 0.7, 1e-6, np.exp((vx-0.7)/0.026)*1e-6)
            return vx, vy
        elif curve_type == 'resistor':
            vx = np.linspace(-5, 5, 1000)
            vy = vx / 1000  # 1k
            return vx, vy
        elif curve_type == 'capacitor':
            t = np.linspace(0, 2*np.pi, 1000)
            vx = np.sin(t) * 5
            vy = np.cos(t) * 0.001  # 90 degrees out of phase
            return vx, vy
        elif curve_type == 'bjt':
            vx = np.linspace(0, 10, 200)
            vy = []
            for ib in [10e-6, 20e-6, 50e-6, 100e-6]:
                vy_curve = np.minimum(vx * ib * 100, 0.01)
                vy.append(vy_curve)
            return vx, vy
        return np.array([]), np.array([])
    
    def close(self):
        self.connected = False


class CurveTracerSimulator:
    """Full simulator for CurveTracer"""
    
    def __init__(self):
        self.scope = SimulatedDHO()
        
    def get_idn(self):
        return self.scope.query('*IDN?')
    
    def capture_xy(self, ch_x='CHAN1', ch_y='CHAN2', **kwargs):
        curve_type = kwargs.get('curve_type', 'capacitor')
        vx, vy = self.scope.generate_curve(curve_type)
        # Add some noise
        vx += np.random.normal(0, 0.001, len(vx))
        vy += np.random.normal(0, 1e-9, len(vy))
        return vx, vy
