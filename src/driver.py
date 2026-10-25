#!/usr/bin/env python3
"""
Rigol DHO800/DHO900 Driver - Centralized SCPI Communication
Based on DHO800900 Programming Guide EN
"""

import pyvisa
import socket
import time
import threading
import logging
from typing import Tuple, Optional, Dict, Any, List
from datetime import datetime
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SocketTimeout = socket.timeout


class RigolDriverError(Exception):
    """Base exception for Rigol driver"""
    pass


class ConnectionError(RigolDriverError):
    """Connection related errors"""
    pass


class CommunicationError(RigolDriverError):
    """Communication related errors"""
    pass


class AcquisitionError(RigolDriverError):
    """Acquisition related errors"""
    pass


class RigolDHODriver:
    """
    Centralized driver for Rigol DHO800/DHO900 series oscilloscopes
    Handles all SCPI communication, error checking, and state management
    """
    
    # SCPI Commands from DHO800900 Programming Guide
    CMD_IDN = "*IDN?"
    CMD_RST = "*RST"
    CMD_CLS = "*CLS"
    CMD_ESR = "*ESR?"
    CMD_OPC = "*OPC?"
    CMD_OPC_SET = "*OPC"
    CMD_ERR = ":SYST:ERR?"
    
    CMD_RUN = ":RUN"
    CMD_STOP = ":STOP"
    CMD_SINGLE = ":SING"
    CMD_AUTO = ":AUToset"
    
    CMD_ACQ_TYPE = ":ACQ:TYPE"
    CMD_ACQ_MODE = ":ACQ:MODE"
    CMD_ACQ_DEPMEM = ":ACQ:MEMDepth"
    CMD_ACQ_SRATE = ":ACQ:SRATe?"
    
    CMD_WAV_SOURCE = ":WAV:SOUR"
    CMD_WAV_MODE = ":WAV:MODE"
    CMD_WAV_FORMAT = ":WAV:FORM"
    CMD_WAV_DATA = ":WAV:DATA?"
    CMD_WAV_PRE = ":WAV:PRE?"
    CMD_WAV_START = ":WAV:STARt"
    CMD_WAV_STOP = ":WAV:STOP"
    CMD_WAV_POINTS = ":WAV:POINts"
    
    CMD_CHAN_DISP = ":CHAN{}:DISP"
    CMD_CHAN_COUPL = ":CHAN{}:COUP"
    CMD_CHAN_SCAL = ":CHAN{}:SCAL"
    CMD_CHAN_OFFS = ":CHAN{}:OFFS"
    CMD_CHAN_PROB = ":CHAN{}:PROB"
    CMD_CHAN_BW = ":CHAN{}:BWLimit"
    
    CMD_TIME_SCALE = ":TIM:MAIN:SCAL"
    CMD_TIME_OFFS = ":TIM:MAIN:OFFS"
    
    CMD_TRIG_MODE = ":TRIG:MODE"
    CMD_TRIG_SOURCE = ":TRIG:SOURce"
    CMD_TRIG_LEVEL = ":TRIG:LEVel"
    CMD_TRIG_EDGE_SLOPE = ":TRIG:EDGE:SLOPe"
    
    DEFAULT_TIMEOUT = 10000
    SOCKET_TIMEOUT = 5
    CMD_DELAY = 0.05
    
    def __init__(self, resource_name: str = None, use_socket: bool = None):
        self.rm = None
        self.inst = None
        self.sock = None
        self.use_socket = use_socket
        self.ip = None
        self.port = 5555
        self.connected = False
        self.resource_name = resource_name
        self.lock = threading.Lock()
        self.command_log = []
        self.error_log = []
        self.model = None
        self.serial = None
        self.firmware = None
        
        if resource_name:
            self.connect(resource_name)
    
    def connect(self, resource_name: str = None) -> bool:
        """Connect to oscilloscope with automatic detection"""
        if resource_name:
            self.resource_name = resource_name
        
        try:
            with self.lock:
                # Parse resource
                if self.resource_name.upper().startswith('TCPIP'):
                    parts = self.resource_name.split('::')
                    if len(parts) >= 2:
                        self.ip = parts[1]
                        self.use_socket = True if self.use_socket is None else self.use_socket
                elif self.resource_name and '.' in self.resource_name and ':' not in self.resource_name:
                    self.ip = self.resource_name
                    self.use_socket = True if self.use_socket is None else self.use_socket
                
                # Try socket connection first for DHO (port 5555)
                if self.ip:
                    try:
                        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        self.sock.settimeout(self.SOCKET_TIMEOUT)
                        self.sock.connect((self.ip, self.port))
                        self._log_command(f"*IDN?")
                        self.sock.sendall(f"*IDN?\n".encode())
                        time.sleep(0.3)
                        resp = self.sock.recv(1024).decode(errors='ignore').strip()
                        self._log_response(resp)
                        if 'RIGOL' in resp.upper():
                            self.connected = True
                            self.use_socket = True
                            self._parse_idn(resp)
                            self._clear_errors()
                            print(f"Connected via SOCKET {self.port}: {resp}")
                            return True
                    except Exception as e:
                        print(f"Socket {self.port} failed: {e}")
                        if self.sock:
                            try:
                                self.sock.close()
                            except:
                                pass
                            self.sock = None
                
                # Try VISA
                try:
                    self.rm = pyvisa.ResourceManager('@py')
                except Exception as e:
                    raise ConnectionError(f"PyVISA ResourceManager failed: {e}")
                
                candidates = []
                if self.resource_name:
                    candidates.append(self.resource_name)
                if self.ip:
                    candidates.extend([
                        f'TCPIP::{self.ip}::INSTR',
                        f'TCPIP::{self.ip}::5025::SOCKET',
                    ])
                
                for res in candidates:
                    try:
                        self.inst = self.rm.open_resource(res)
                        self.inst.timeout = self.DEFAULT_TIMEOUT
                        try:
                            self.inst.write_termination = '\n'
                            self.inst.read_termination = '\n'
                        except:
                            pass
                        
                        idn = self._query_visa("*IDN?")
                        if 'RIGOL' in idn.upper():
                            self.connected = True
                            self.use_socket = False
                            self._parse_idn(idn)
                            self._clear_errors()
                            logger.info(f"Connected via VISA: {idn}")
                            return True
                    except Exception as e:
                        logger.debug(f"VISA {res} failed: {e}")
                        try:
                            if self.inst:
                                self.inst.close()
                        except:
                            pass
                        self.inst = None
                
                raise ConnectionError("Failed to connect to oscilloscope")
                
        except ConnectionError:
            raise
        except Exception as e:
            raise ConnectionError(f"Connection error: {e}")
    
    def _parse_idn(self, idn: str):
        """Parse *IDN? response: RIGOL TECHNOLOGIES,DHO924S,SERIAL,FW"""
        try:
            parts = idn.split(',')
            if len(parts) >= 4:
                self.model = parts[1].strip()
                self.serial = parts[2].strip()
                self.firmware = parts[3].strip()
        except:
            pass
    
    def _log_command(self, cmd: str):
        self.command_log.append({
            'time': datetime.now().isoformat(),
            'type': 'cmd',
            'data': cmd
        })
        if len(self.command_log) > 1000:
            self.command_log = self.command_log[-1000:]
    
    def _log_response(self, resp: str):
        self.command_log.append({
            'time': datetime.now().isoformat(),
            'type': 'resp',
            'data': resp[:200]
        })
    
    def _log_error(self, err: str):
        self.error_log.append({
            'time': datetime.now().isoformat(),
            'data': err
        })
    
    def write(self, cmd: str) -> None:
        """Write SCPI command"""
        if not self.connected:
            raise ConnectionError("Not connected")
        
        with self.lock:
            try:
                self._log_command(cmd)
                if self.use_socket and self.sock:
                    self.sock.sendall(f"{cmd}\n".encode())
                    time.sleep(self.CMD_DELAY)
                elif self.inst:
                    self.inst.write(cmd)
                    time.sleep(self.CMD_DELAY)
                else:
                    raise CommunicationError("No connection")
            except Exception as e:
                raise CommunicationError(f"Write error: {cmd} - {e}")
    
    def query(self, cmd: str) -> str:
        """Query SCPI command"""
        if not self.connected:
            raise ConnectionError("Not connected")
        
        with self.lock:
            try:
                self._log_command(cmd)
                if self.use_socket and self.sock:
                    self.sock.sendall(f"{cmd}\n".encode())
                    time.sleep(0.15)
                    data = self.sock.recv(4096)
                    resp = data.decode(errors='ignore').strip()
                    self._log_response(resp)
                    return resp
                elif self.inst:
                    resp = self.inst.query(cmd).strip()
                    self._log_response(resp)
                    return resp
                else:
                    raise CommunicationError("No connection")
            except Exception as e:
                raise CommunicationError(f"Query error: {cmd} - {e}")
    
    def _query_visa(self, cmd: str) -> str:
        return self.inst.query(cmd).strip()
    
    def query_binary(self, cmd: str) -> np.ndarray:
        """Query binary waveform data"""
        if not self.connected:
            raise ConnectionError("Not connected")
        
        with self.lock:
            try:
                self._log_command(cmd)
                if self.use_socket and self.sock:
                    self.sock.sendall(f"{cmd}\n".encode())
                    time.sleep(0.3)
                    self.sock.settimeout(10)
                    data = bytearray()
                    try:
                        while True:
                            chunk = self.sock.recv(16384)
                            if not chunk:
                                break
                            data.extend(chunk)
                            if len(data) > 10 and b'#' in data:
                                idx = data.find(b'#')
                                if idx + 1 < len(data):
                                    try:
                                        num = int(chr(data[idx+1]))
                                        if idx + 2 + num <= len(data):
                                            length_str = data[idx+2:idx+2+num].decode('ascii')
                                            length = int(length_str)
                                            if len(data) >= idx + 2 + num + length:
                                                break
                                    except:
                                        pass
                    except SocketTimeout:
                        pass
                    
                    if b'#' in data:
                        idx = data.find(b'#')
                        if idx + 1 < len(data):
                            try:
                                num = int(chr(data[idx+1]))
                                if idx + 2 + num <= len(data):
                                    length_str = data[idx+2:idx+2+num].decode('ascii')
                                    length = int(length_str)
                                    start = idx + 2 + num
                                    raw = bytes(data[start:start+length])
                                    return np.frombuffer(raw, dtype=np.uint8)
                            except Exception as e:
                                logger.debug(f"Binary parse error: {e}")
                    return np.array([], dtype=np.uint8)
                elif self.inst:
                    return self.inst.query_binary_values(cmd, datatype='B', container=np.array)
                else:
                    raise CommunicationError("No connection")
            except Exception as e:
                raise CommunicationError(f"Binary query error: {cmd} - {e}")
    
    def get_error(self) -> str:
        """Read error queue"""
        try:
            err = self.query(self.CMD_ERR)
            if err and err != '0,"No error"':
                self._log_error(err)
            return err
        except Exception as e:
            return f"Error reading error queue: {e}"
    
    def get_all_errors(self) -> List[str]:
        """Read all errors from queue"""
        errors = []
        for _ in range(10):
            try:
                err = self.get_error()
                if not err or err.startswith('0') or 'No error' in err:
                    break
                errors.append(err)
                time.sleep(0.01)
            except:
                break
        return errors
    
    def _clear_errors(self):
        """Clear error queue"""
        try:
            self.write(self.CMD_CLS)
        except:
            pass
    
    def check_errors(self):
        """Check and log errors"""
        errors = self.get_all_errors()
        for e in errors:
            logger.warning(f"Instrument error: {e}")
        return errors
    
    def get_idn(self) -> str:
        return self.query(self.CMD_IDN)
    
    def run(self):
        self.write(self.CMD_RUN)
    
    def stop(self):
        self.write(self.CMD_STOP)
    
    def single(self):
        self.write(self.CMD_SINGLE)
    
    def reset(self):
        self.write(self.CMD_RST)
        time.sleep(1)
    
    def get_acquisition_rate(self) -> float:
        try:
            resp = self.query(self.CMD_ACQ_SRATE)
            return float(resp)
        except:
            return 0.0
    
    def get_waveform_preamble(self) -> Dict[str, Any]:
        try:
            pre_str = self.query(self.CMD_WAV_PRE)
            pre = pre_str.split(',')
            return {
                'format': int(pre[0]) if len(pre) > 0 else 0,
                'type': int(pre[1]) if len(pre) > 1 else 0,
                'points': int(float(pre[2])) if len(pre) > 2 else 0,
                'count': int(float(pre[3])) if len(pre) > 3 else 1,
                'xinc': float(pre[4]) if len(pre) > 4 else 1.0,
                'xorig': float(pre[5]) if len(pre) > 5 else 0.0,
                'xref': float(pre[6]) if len(pre) > 6 else 0.0,
                'yinc': float(pre[7]) if len(pre) > 7 else 1.0,
                'yorig': float(pre[8]) if len(pre) > 8 else 0.0,
                'yref': float(pre[9]) if len(pre) > 9 else 0.0,
            }
        except Exception as e:
            raise AcquisitionError(f"Failed to get preamble: {e}")
    
    def capture_waveform(self, channel: str, mode: str = 'RAW') -> Tuple[np.ndarray, Dict]:
        """Capture single channel waveform"""
        try:
            self.stop()
            time.sleep(0.2)
            self.write(f"{self.CMD_WAV_SOURCE} {channel}")
            self.write(f"{self.CMD_WAV_MODE} {mode}")
            self.write(f"{self.CMD_WAV_FORMAT} BYTE")
            time.sleep(0.8)
            
            pre = self.get_waveform_preamble()
            raw = self.query_binary(f"{self.CMD_WAV_DATA}?")
            
            if len(raw) == 0:
                raise AcquisitionError(f"Empty data from {channel}")
            
            volts = (raw.astype(float) - float(pre['yref']) - float(pre['yorig'])) * float(pre['yinc'])
            return volts, pre
        except AcquisitionError:
            raise
        except Exception as e:
            raise AcquisitionError(f"Capture failed: {e}")
    
    def capture_xy(self, ch_x: str = 'CHAN1', ch_y: str = 'CHAN2',
                   probe_x: float = 1.0, probe_y: float = 1.0,
                   shunt_r: float = None, invert_y: bool = False) -> Tuple[np.ndarray, np.ndarray]:
        """Capture X-Y for curve tracing - preserves original order"""
        try:
            self.stop()
            time.sleep(0.2)
            
            # Capture X
            self.write(f"{self.CMD_WAV_SOURCE} {ch_x}")
            self.write(f"{self.CMD_WAV_MODE} RAW")
            self.write(f"{self.CMD_WAV_FORMAT} BYTE")
            time.sleep(1.0)
            pre_x = self.get_waveform_preamble()
            raw_x = self.query_binary(f"{self.CMD_WAV_DATA}?")
            if len(raw_x) == 0:
                raise AcquisitionError("No data from X channel")
            vx = (raw_x.astype(float) - float(pre_x['yref']) - float(pre_x['yorig'])) * float(pre_x['yinc']) * float(probe_x)
            
            # Capture Y
            self.write(f"{self.CMD_WAV_SOURCE} {ch_y}")
            self.write(f"{self.CMD_WAV_MODE} RAW")
            self.write(f"{self.CMD_WAV_FORMAT} BYTE")
            time.sleep(1.0)
            pre_y = self.get_waveform_preamble()
            raw_y = self.query_binary(f"{self.CMD_WAV_DATA}?")
            if len(raw_y) == 0:
                raise AcquisitionError("No data from Y channel")
            vy = (raw_y.astype(float) - float(pre_y['yref']) - float(pre_y['yorig'])) * float(pre_y['yinc']) * float(probe_y)
            
            # Process Y
            if shunt_r and shunt_r > 0:
                vy = vy / shunt_r
            if invert_y:
                vy = -vy
            
            # Sync
            n = min(len(vx), len(vy))
            vx = vx[:n]
            vy = vy[:n]
            
            # Remove only exact duplicates, preserve order
            if len(vx) > 1:
                mask = np.ones(len(vx), dtype=bool)
                for i in range(1, len(vx)):
                    if abs(vx[i] - vx[i-1]) < 1e-12 and abs(vy[i] - vy[i-1]) < 1e-12:
                        mask[i] = False
                vx = vx[mask]
                vy = vy[mask]
            
            self.check_errors()
            return vx, vy
        except AcquisitionError:
            try:
                self.run()
            except:
                pass
            raise
        except Exception as e:
            try:
                self.run()
            except:
                pass
            raise AcquisitionError(f"XY capture error: {e}")
    
    def test_connection(self) -> Dict[str, Any]:
        """Test connection without starting measurement"""
        result = {
            'connected': self.connected,
            'idn': None,
            'model': self.model,
            'serial': self.serial,
            'firmware': self.firmware,
            'errors': []
        }
        if not self.connected:
            return result
        try:
            result['idn'] = self.get_idn()
            result['errors'] = self.get_all_errors()
        except Exception as e:
            result['errors'].append(str(e))
        return result
    
    def get_state(self) -> Dict[str, Any]:
        """Get instrument state"""
        state = {
            'connected': self.connected,
            'use_socket': self.use_socket,
            'ip': self.ip,
            'model': self.model,
            'serial': self.serial,
            'firmware': self.firmware,
            'resource': self.resource_name
        }
        if self.connected:
            try:
                state['errors'] = self.get_all_errors()
            except:
                state['errors'] = []
        return state
    
    def close(self):
        """Close connection and cleanup"""
        try:
            self.run()
        except:
            pass
        try:
            if self.inst:
                self.inst.close()
        except:
            pass
        try:
            if self.sock:
                self.sock.close()
        except:
            pass
        try:
            if self.rm:
                self.rm.close()
        except:
            pass
        self.inst = None
        self.sock = None
        self.rm = None
        self.connected = False
        logger.info("Connection closed")


def discover_all():
    """Discover all Rigol devices"""
    results = {
        'visa': [],
        'network': []
    }
    try:
        rm = pyvisa.ResourceManager('@py')
        results['visa'] = list(rm.list_resources())
        rm.close()
    except:
        pass
    
    try:
        from .discovery import RigolDiscovery
        d = RigolDiscovery()
        results['network'] = d.discover_all()
    except:
        pass
    
    return results
