#!/usr/bin/env python3
"""
CurveTracer OSS - Open source curve tracer for SMU instruments
"""

import pyvisa
import numpy as np
from typing import Dict, List, Tuple, Optional
import time


class SMU:
    """Base class for Source Measure Unit instruments"""
    
    def __init__(self, resource_name: str = None):
        self.rm = pyvisa.ResourceManager()
        self.instrument = None
        if resource_name:
            self.connect(resource_name)
    
    def connect(self, resource_name: str):
        self.instrument = self.rm.open_resource(resource_name)
        self.instrument.timeout = 5000
        self.instrument.write_termination = '\n'
        self.instrument.read_termination = '\n'
    
    def write(self, cmd: str):
        if self.instrument:
            self.instrument.write(cmd)
    
    def query(self, cmd: str) -> str:
        if self.instrument:
            return self.instrument.query(cmd)
        return ""
    
    def close(self):
        if self.instrument:
            self.instrument.close()
        self.rm.close()


class YokogawaGS(SMU):
    """Yokogawa GS610/GS820 CurveTracer interface"""
    
    def __init__(self, resource_name: str = None):
        super().__init__(resource_name)
    
    def idn(self) -> str:
        return self.query("*IDN?")
    
    def set_channel(self, channel: int = 1):
        """Set active channel"""
        self.write(f":CHAN{channel}")
    
    def set_voltage(self, voltage: float):
        """Set source voltage"""
        self.write(f":SOUR:VOLT {voltage}")
    
    def set_current(self, current: float):
        """Set source current"""
        self.write(f":SOUR:CURR {current}")
    
    def measure_voltage(self) -> float:
        """Measure voltage"""
        return float(self.query(":MEAS:VOLT?"))
    
    def measure_current(self) -> float:
        """Measure current"""
        return float(self.query(":MEAS:CURR?"))
    
    def set_voltage_range(self, range_val: float):
        self.write(f":SENS:VOLT:RANG {range_val}")
    
    def set_current_range(self, range_val: float):
        self.write(f":SENS:CURR:RANG {range_val}")


class CurveTracer:
    """Curve tracing measurement engine"""
    
    def __init__(self, smu: SMU):
        self.smu = smu
    
    def diode_trace(self, start_v: float = 0, stop_v: float = 1.0, 
                   points: int = 101, compliance_i: float = 0.1) -> Tuple[np.ndarray, np.ndarray]:
        """Diode I-V characteristic curve"""
        voltages = np.linspace(start_v, stop_v, points)
        currents = np.zeros(points)
        
        self.smu.write(f":SENS:CURR:PROT {compliance_i}")
        self.smu.write(":SOUR:FUNC VOLT")
        self.smu.write(":SENS:FUNC CURR")
        
        for i, v in enumerate(voltages):
            self.smu.set_voltage(v)
            self.smu.write(":OUTP ON")
            time.sleep(0.01)
            currents[i] = self.smu.measure_current()
        
        self.smu.write(":OUTP OFF")
        return voltages, currents
    
    def fet_output(self, vds_start: float = 0, vds_stop: float = 5.0,
                   vgs_values: List[float] = None, points: int = 51) -> Dict:
        """FET output characteristics (Id vs Vds for different Vgs)"""
        if vgs_values is None:
            vgs_values = [0, 1, 2, 3, 4]
        
        results = {}
        vds = np.linspace(vds_start, vds_stop, points)
        
        for vgs in vgs_values:
            ids = np.zeros(points)
            # Set gate voltage (assuming channel 2)
            # This is simplified - real implementation needs 2-channel SMU
            for i, vd in enumerate(vds):
                # Measure
                ids[i] = 0.0  # Placeholder
            results[f'Vgs={vgs}V'] = (vds, ids)
        
        return results
    
    def npn_output(self, vce_start: float = 0, vce_stop: float = 5.0,
                   ib_values: List[float] = None, points: int = 51) -> Dict:
        """NPN transistor output characteristics (Ic vs Vce for different Ib)"""
        if ib_values is None:
            ib_values = [10e-6, 20e-6, 30e-6, 40e-6, 50e-6]
        
        results = {}
        vce = np.linspace(vce_start, vce_stop, points)
        
        for ib in ib_values:
            ic = np.zeros(points)
            # Simplified measurement
            for i, vc in enumerate(vce):
                ic[i] = 0.0  # Placeholder
            results[f'Ib={ib*1e6}uA'] = (vce, ic)
        
        return results
