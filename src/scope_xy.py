#!/usr/bin/env python3
"""
Rigol DHO800/DHO900 Series Oscilloscope Interface
Curve Tracer OSS - X-Y Mode for Analog Curve Tracer

Comandos SCPI baseados no DHO800900 Programming Guide EN
"""

# pylint: skip-file

import pyvisa
import numpy as np
import time
import socket
import select
import os
import glob
from typing import Tuple, Optional, Dict, Any

# Try to import PyUSBTMC for USB-TMC support (alternative to PyVISA-py)
try:
    import PyUSBTMC
    USBTMC_AVAILABLE = True
except ImportError:
    USBTMC_AVAILABLE = False

# Define socket.timeout exception for compatibility
# In Python, socket.timeout is an exception class
SocketTimeout = socket.timeout


# Comandos SCPI oficiais Rigol DHO800/DHO900
# Referência: DHO800900 Programming Guide EN (rev 00.01.03)

# Comandos de controle de aquisição
CMD_RUN = ":RUN"
CMD_STOP = ":STOP"
CMD_SINGLE = ":SING"

# Comandos de onda (Waveform) - Seção 3.28
CMD_WAV_MODE = ":WAV:MODE"  # NORMal, MAXimum, RAW
CMD_WAV_SOURCE = ":WAV:SOUR"  # CHANnel1, CHANnel2, MATH1, ...
CMD_WAV_FORMAT = ":WAV:FORM"  # WORD, BYTE, ASCii
CMD_WAV_DATA = ":WAV:DATA?"  # Retorna dados
CMD_WAV_PRE = ":WAV:PRE?"  # Retorna preâmbulo (10 parâmetros)
CMD_WAV_START = ":WAV:STARt"  # Posição inicial
CMD_WAV_STOP = ":WAV:STOP"  # Posição final

# Comandos de canal
CMD_CHAN_DISP = ":CHAN{}:DISP"  # ON, OFF
CMD_CHAN_COUPL = ":CHAN{}:COUP"  # AC, DC, GND
CMD_CHAN_SCAL = ":CHAN{}:SCAL"  # Volts por divisão
CMD_CHAN_OFFS = ":CHAN{}:OFFS"  # Offset
CMD_CHAN_PROBE = ":CHAN{}:PROB"  # Valor da sonda (1, 10, 100, etc.)

# Comandos de tempo
CMD_TIME_SCALE = ":TIM:MAIN:SCAL"  # Segundos por divisão
CMD_TIME_OFFS = ":TIM:MAIN:OFFS"  # Offset de tempo
CMD_TIME_XY_ENABLE = ":TIM:XY:ENABle"  # habilita modo XY

# Comandos de trigger
CMD_TRIG_MODE = ":TRIG:MODE"  # EDGE, PULSe, VIDEO, etc.
CMD_TRIG_EDGE_SOURCE = ":TRIG:EDGE:SOURce"
CMD_TRIG_EDGE_SLOPE = ":TRIG:EDGE:SLOPe"  # POSitive, NEGative, EITHer
CMD_TRIG_EDGE_LEVEL = ":TRIG:EDGE:LEVel"

# Comandos system
CMD_IDN = "*IDN?"
CMD_RST = "*RST"
CMD_OSC = "*OSC?"
CMD_ACQUIRE_TYPE = ":ACQ:TYPE"  # NORMal, AVG, PEAK, etc.

# No modo X-Y o DHO800/DHO900 desenha uma grade de 8 x 8 divisões. O modo YT
# usa 10 divisões horizontais, mas o display X-Y é quadrado (8 divisões por eixo).
SCREEN_DIVISIONS = 8.0


def compute_channel_screen_range(scale_v_per_div: float, offset_v: float,
                                 divisions: float = SCREEN_DIVISIONS) -> Tuple[float, float]:
    """Retorna o range de tensão visível de um canal no display do DHO.

    O manual do DHO800/DHO900 define os limites da tela como
    ``±4 x VerticalScale - OFFSet`` (ex.: :HISTogram:RANGe:TOP).  Portanto o
    centro da tela fica em ``-offset``.  Isso também é consistente com a
    fórmula do preâmbulo ``V = (raw - YREFerence - YORigin) * YINCrement``:
    em ``raw == YREFerence`` (centro), ``V == -YORigin * YINCrement``, que é
    ``-offset``.

    Args:
        scale_v_per_div: Volts por divisão do canal (:CHAN<n>:SCAL?).
        offset_v: Offset vertical do canal (:CHAN<n>:OFFS?).
        divisions: Número de divisões verticais da tela (8 no DHO800/DHO900).

    Returns:
        Tupla ``(vmin, vmax)`` em volts, correspondente às 8 divisões da tela.
    """
    scale = float(scale_v_per_div)
    offset = float(offset_v)
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError(f"Invalid vertical scale: {scale_v_per_div}")
    if not np.isfinite(offset):
        raise ValueError(f"Invalid vertical offset: {offset_v}")

    center = -offset
    half_span = (float(divisions) / 2.0) * scale
    return (center - half_span, center + half_span)



class RigolScopeXY:
    """Interface para Rigol DHO800/DHO900 Oscilloscope em modo X-Y"""
    
    # Configurações padrão
    DEFAULT_TIMEOUT = 10000  # ms
    DEFAULT_PROBE = "1"
    WAVEFORM_DELAY = 0.5  # segundos após configurar waveform
    
    def __init__(self, resource_name: str = None, use_socket: bool = False):
        """
        Inicializa a conexão com o osciloscópio
        
        Args:
            resource_name: Resource name VISA (TCPIP::IP::INSTR, USB::...)
            use_socket: Se True, usa porta 5555 socket (alternativa ao VISA)
        """
        self.rm = None
        self.inst = None
        self.sock = None
        self.usbtmc_path = None  # caminho /dev/usbtmc para conexões diretas
        self.use_socket = use_socket
        self.ip = None
        self.connected = False
        self.last_waveform_mode: Optional[str] = None
        self.last_preamble: Dict[str, Any] = {}
        
        if resource_name:
            self.connect(resource_name, use_socket)
    
    def connect(self, resource_name: str, use_socket: bool = False) -> bool:
        """
        Conecta ao osciloscópio
        
        Args:
            resource_name: Resource name VISA, IP, ou caminho /dev/usbtmc
            use_socket: Se True, usa porta 5555 socket
            
        Returns:
            True se conectado com sucesso
        """
        try:
            # Inicializar candidates para os resource names a serem testados
            candidates = []
            
            # Detectar se é um IP TCP
            if resource_name.upper().startswith('TCPIP'):
                try:
                    parts = resource_name.split('::')
                    if len(parts) >= 2:
                        self.ip = parts[1]
                        self.use_socket = use_socket or True  # DHO default to socket 5555
                except Exception as e:
                    print(f"Parse IP failed: {e}")
            elif resource_name and '.' in resource_name and ':' not in resource_name:
                # Raw IP
                self.ip = resource_name
                self.use_socket = True
            # Detectar dispositivo USB-TMC via /dev/usbtmc (não recomendado para novas implementações)
            elif resource_name and ('USB-TMC' in resource_name.upper() or '/dev/usbtmc' in resource_name):
                self.usbtmc_path = resource_name.replace('USB-TMC::', '').replace('USB0::', '').lstrip('/')
                if self.usbtmc_path and not self.usbtmc_path.startswith('/dev/usbtmc'):
                    self.usbtmc_path = '/dev/usbtmc' + self.usbtmc_path
                self.use_socket = False
                return self._connect_usbtmc()
            
            # Inicializar PyVISA ResourceManager (precisa ser feito antes de USB-TMC via PyVISA)
            try:
                self.rm = pyvisa.ResourceManager('@py')
            except Exception as e:
                raise Exception(f"PyVISA ResourceManager failed: {e}")
            
            # Detectar dispositivo USB-TMC via PyVISA-py (USB0::...::INSTR)
            # Depois de inicializar self.rm!
            if resource_name and resource_name.startswith('USB0::'):
                self.usbtmc_path = None  # Usar PyVISA-py USB-TMC
                self.use_socket = False
                return self._connect_pyvisa_usbtmc(resource_name)
            
            # Detectar dispositivo USB-TMC via PyUSBTMC (PyUSBTMC::Vend:Prod)
            if resource_name and resource_name.startswith('PyUSBTMC::'):
                if USBTMC_AVAILABLE:
                    try:
                        # Extrair vendor e product IDs
                        parts = resource_name.split('::')
                        if len(parts) >= 2:
                            vend_prod = parts[1].split(':')
                            if len(vend_prod) >= 2:
                                vid = int(vend_prod[0], 16)
                                pid = int(vend_prod[1], 16)
                                
                                # Buscar dispositivo específico
                                devices = list(PyUSBTMC.find_tmc_devices())
                                for device in devices:
                                    if device.idVendor == vid and device.idProduct == pid:
                                        return self._connect_pyusbtmc(device)
                                
                                raise Exception(f"PyUSBTMC device not found: {resource_name}")
                    except Exception as e:
                        print(f"PyUSBTMC connection error: {e}")
                        raise Exception(f"Failed to connect via PyUSBTMC: {e}")
                else:
                    raise Exception("PyUSBTMC not available")
            
            # Tentar conexão via socket (porta 5555 - Rigol legacy)
            if self.ip:
                try:
                    self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.sock.settimeout(5)
                    self.sock.connect((self.ip, 5555))
                    self.sock.sendall(f"{CMD_IDN}\n".encode())
                    time.sleep(0.2)
                    resp = self.sock.recv(1024).decode(errors='ignore').strip()
                    print(f"Connected via SOCKET 5555: {resp}")
                    self.use_socket = True
                    self.connected = True
                    return True
                except Exception as e:
                    print(f"Socket 5555 failed: {e}")
                    if self.sock:
                        try:
                            self.sock.close()
                        except:
                            pass
                        self.sock = None
            
            # Detectar se já conectamos via PyVISA-py USB-TMC
            if not self.inst and resource_name and not resource_name.startswith('USB0::') and not self.usbtmc_path:
                # Não é USB-TMC e não é /dev/usbtmc, continuar com PyVISA
                candidates.append(resource_name)
                if self.ip:
                    candidates.append(f'TCPIP::{self.ip}::INSTR')
                    candidates.append(f'TCPIP::{self.ip}::5025::SOCKET')
            
            for res in candidates:
                try:
                    self.inst = self.rm.open_resource(res)
                    self.inst.timeout = self.DEFAULT_TIMEOUT
                    try:
                        self.inst.write_termination = '\n'
                        self.inst.read_termination = '\n'
                    except:
                        pass
                    
                    # Verificar conexão com *IDN?
                    idn = self.inst.query(CMD_IDN).strip()
                    print(f"Connected via VISA: {idn}")
                    
                    # Verificar se é um DHO
                    if 'RIGOL' not in idn.upper():
                        print(f"Warning: Device may not be Rigol: {idn}")
                    
                    self.use_socket = False
                    self.connected = True
                    return True
                    
                except Exception as e:
                    print(f"Connection attempt to {res} failed: {e}")
                    try:
                        if self.inst:
                            self.inst.close()
                    except:
                        pass
            
            raise Exception("Failed to connect to oscilloscope")
            
        except pyvisa.VisaIOError as e:
            raise Exception(f"VISA I/O Error: {e}")
        except Exception as e:
            raise Exception(f"Connection error: {e}")
    
    def _connect_pyusbtmc(self, device: Any = None) -> bool:
        """
        Conecta via PyUSBTMC para comunicação USB-TMC direta
        
        O PyUSBTMC é mais confiável que PyVISA-py para USB-TMC no Linux.
        Usa pyusb diretamente para comunicação com dispositivos USB-TMC.
        
        Args:
            device: PyUSB device object (se None, busca o primeiro dispositivo Rigol)
            
        Returns:
            True se conectado com sucesso
        """
        if not USBTMC_AVAILABLE:
            print("PyUSBTMC não disponível")
            return False
            
        try:
            # Se device não for passado, buscar o primeiro dispositivo Rigol
            if device is None:
                devices = list(PyUSBTMC.find_tmc_devices())
                if not devices:
                    raise Exception("Nenhum dispositivo USB-TMC encontrado")
                
                # Filtrar por Rigol se possível
                rigol_devs = [d for d in devices if 'rigol' in str(d).lower()]
                if rigol_devs:
                    device = rigol_devs[0]
                else:
                    device = devices[0]
            
            # Antes de conectar, tentar fazer reattach do kernel driver se estiver ativo
            # Isso libera o dispositivo se ele estava em uso por outro processo
            if device.is_kernel_driver_active(0):
                try:
                    device.detach_kernel_driver(0)
                    print("Kernel driver detached")
                except:
                    pass
            
            # device já é um pyusb Device, precisamos criar USBTMC_device
            # O PyUSBTMC.USBTMC_device aceita um pyusb Device ou um dict
            self.usbtmc_inst = PyUSBTMC.USBTMC_device(device)
            print(f"Connected via PyUSBTMC: {device}")
            
            # Verificar conexão com *IDN? usando write() + read() separados
            #ask() do PyUSBTMC não decodifica bem strings para alguns comandos
            self.usbtmc_inst.write("*IDN?")
            time.sleep(0.5)  # Wait for response
            idn = self.usbtmc_inst.read(requestSize=256, io_timeout=5000)
            if isinstance(idn, bytes):
                idn = idn.decode('utf-8', errors='ignore')
            print(f"IDN: {idn.strip()}")
            
            if idn and 'RIGOL' in idn.upper():
                self.connected = True
                return True
            else:
                raise Exception(f"Unexpected IDN response: {idn}")
                
        except Exception as e:
            print(f"PyUSBTMC connection error: {e}")
            raise Exception(f"Failed to connect via PyUSBTMC: {e}")
    
    def _connect_pyvisa_usbtmc(self, resource_name: str) -> bool:
        """
        Conecta diretamente via /dev/usbtmc (Linux kernel driver)
        
        NI-VISA para Linux não suporta USB-TMC - usar driver do kernel diretamente.
        
        Returns:
            True se conectado com sucesso
        """
        try:
            if not self.usbtmc_path:
                raise Exception("No usbtmc_path specified")
            
            # Verificar se o dispositivo existe
            if not os.path.exists(self.usbtmc_path):
                raise Exception(f"USB-TMC device not found: {self.usbtmc_path}")
            
            # Verificar permissões
            stat_info = os.stat(self.usbtmc_path)
            mode = stat_info.st_mode
            if not (mode & 0o200):  # Check write permission
                print(f"Warning: No write permission on {self.usbtmc_path}")
                print("Try: sudo chmod 666 " + self.usbtmc_path)
            
            # Tentar conectar e ler IDN
            with open(self.usbtmc_path, 'w+b', buffering=0) as f:
                f.write(b'*IDN?\n')
                f.flush()
                time.sleep(0.2)
                resp = f.read(512).decode('utf-8', errors='ignore').strip()
                
                if resp and 'RIGOL' in resp.upper():
                    print(f"Connected via USB-TMC: {resp}")
                    # Manter o arquivo aberto em self.usbtmc_file
                    self.usbtmc_file = open(self.usbtmc_path, 'w+b', buffering=0)
                    self.connected = True
                    return True
                else:
                    raise Exception(f"Unexpected response from {self.usbtmc_path}: {resp}")
                    
        except Exception as e:
            print(f"USB-TMC connection error: {e}")
            raise Exception(f"Failed to connect via USB-TMC: {e}")
    
    def _write(self, cmd: str) -> None:
        """
        Escreve comando SCPI
        
        Args:
            cmd: Comando SCPI (sem o newline final)
        """
        if not self.connected:
            raise Exception("Not connected to oscilloscope")
        
        try:
            if self.use_socket and self.sock:
                msg = f"{cmd}\n"
                self.sock.sendall(msg.encode())
            elif self.inst:
                # PyVISA: usar write_raw para evitar problemas de encoding
                # funciona tanto para USB-TMC quanto TCPIP
                self.inst.write_raw((cmd + '\\n').encode())
            elif self.usbtmc_inst:
                # PyUSBTMC: write() já adiciona terminador automatically
                # Não adicionar \\n manualmente (o PyUSBTMC já faz isso)
                self.usbtmc_inst.write(cmd)
            elif self.usbtmc_file:
                # USB-TMC via /dev/usbtmc (fallback antigo)
                msg = f"{cmd}\n"
                self.usbtmc_file.write(msg.encode())
                self.usbtmc_file.flush()
            else:
                raise Exception("No connection available")
        except Exception as e:
            raise Exception(f"Write error: {cmd} - {e}")
    
    def _drain_socket(self, timeout: float = 0.05) -> None:
        """Descarta bytes pendentes no socket (ex.: terminador após bloco TMC).

        Sem isso, um ``\\n`` remanescente de uma leitura binária pode ser
        retornado como resposta da próxima query, fazendo ``float()`` falhar e
        a GUI cair no valor padrão de escala.
        """
        if not (self.use_socket and self.sock):
            return
        try:
            while True:
                ready, _, _ = select.select([self.sock], [], [], timeout)
                if not ready:
                    break
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
        except (OSError, ValueError):
            pass

    def _query(self, cmd: str) -> str:
        """
        Query SCPI e retorna resposta
        
        Args:
            cmd: Comando SCPI (sem o newline final)
            
        Returns:
            Resposta como string
        """
        if not self.connected:
            raise Exception("Not connected to oscilloscope")
        
        try:
            if self.use_socket and self.sock:
                # Remove qualquer resposta/terminador atrasado antes de enviar
                self._drain_socket(0.05)

                msg = f"{cmd}\n"
                self.sock.sendall(msg.encode())

                data = bytearray()
                self.sock.settimeout(5.0)
                while True:
                    chunk = self.sock.recv(4096)
                    if not chunk:
                        break
                    data.extend(chunk)
                    if b'\n' in chunk:
                        break

                return data.decode(errors='ignore').strip()
            elif self.inst:
                # PyVISA: usar query_raw para evitar problemas de encoding
                self.inst.write_raw((cmd + '\\n').encode())
                time.sleep(0.1)  # Pequeno delay para resposta
                raw_resp = self.inst.read_raw()
                return raw_resp.decode('latin-1').strip()
            elif self.usbtmc_inst:
                # PyUSBTMC: usar write() + read() separados para evitar issues com ask()
                try:
                    self.usbtmc_inst.write(cmd)
                    time.sleep(0.2)
                    resp = self.usbtmc_inst.read(requestSize=1024, io_timeout=5000)
                    if isinstance(resp, bytes):
                        resp = resp.decode('utf-8', errors='ignore')
                    return resp.strip()
                except Exception as e:
                    raise Exception(f"PyUSBTMC query error: {e}")
            elif self.usbtmc_file:
                # USB-TMC via /dev/usbtmc (fallback antigo)
                self._write(cmd)
                time.sleep(0.2)
                resp = self.usbtmc_file.read(4096).decode('utf-8', errors='ignore').strip()
                return resp
            else:
                raise Exception("No connection available")
        except Exception as e:
            raise Exception(f"Query error: {cmd} - {e}")
    
    def _query_binary(self, cmd: str) -> np.ndarray:
        """
        Query binária SCPI para dados de onda
        
        Conforme manual página 425:
        - WORD format: Dados binários 16 bits (2 bytes por ponto)
        - BYTE format: Dados binários 8 bits (1 byte por ponto)
        - ASC format: Valores ASCII separados por vírgulas
        
        O formato TMC header é: #NXXXXXX onde N é o tamanho do campo de comprimento
        e XXXXXX é o comprimento em bytes.
        
        Args:
            cmd: Comando SCPI (sem o newline final)
            
        Returns:
            Array de valores binários (uint8 para BYTE, uint16 para WORD)
        """
        if not self.connected:
            raise Exception("Not connected to oscilloscope")
        
        try:
            if self.use_socket and self.sock:
                # Não deixar lixo de uma leitura anterior contaminar o header TMC
                self._drain_socket(0.05)

                msg = f"{cmd}\n"
                self.sock.sendall(msg.encode())
                data = bytearray()
                self.sock.settimeout(10)

                try:
                    while True:
                        chunk = self.sock.recv(16384)
                        if not chunk:
                            break
                        data.extend(chunk)
                        
                        # Verificar block TMC completo
                        # TMC header: #NXXXXXX where N is length field width
                        if len(data) > 2 and data[0:1] == b'#':
                            try:
                                num = int(chr(data[1]))
                                if num > 0 and len(data) >= 2 + num:
                                    length = int(data[2:2 + num].decode('ascii'))
                                    if len(data) >= 2 + num + length:
                                        break
                            except (ValueError, UnicodeDecodeError):
                                pass
                except SocketTimeout:
                    pass

                # Consome o terminador (\n) que segue o bloco binário
                self._drain_socket(0.05)

                if data[0:1] == b'#':
                    try:
                        num = int(chr(data[1]))
                        length = int(data[2:2 + num].decode('ascii'))
                        start = 2 + num
                        if len(data) < start + length:
                            raise Exception(
                                f"incomplete TMC block: {len(data)} < {start + length} bytes"
                            )
                        raw = bytes(data[start:start + length])

                        # O formato usado é BYTE para WAVE:DATA?
                        return np.frombuffer(raw, dtype=np.uint8)
                    except (ValueError, IndexError, UnicodeDecodeError):
                        pass
                return np.array([])
            
            elif self.inst:
                # PyVISA: usar write_raw + read_raw para dados binários
                # O DHO envia data em formato TMC: #N + N dígitos + dados
                try:
                    self.inst.write_raw((cmd + '\\n').encode())
                    time.sleep(0.2)
                    raw_data = self.inst.read_raw()
                    
                    # Parsing do formato TMC: #N + N dígitos + dados
                    if raw_data.startswith(b'#'):
                        try:
                            if len(raw_data) > 2 and chr(raw_data[1]).isdigit():
                                num_digits = int(chr(raw_data[1]))
                                if len(raw_data) >= 2 + num_digits:
                                    length_str = raw_data[2:2 + num_digits].decode('ascii')
                                    length = int(length_str)
                                    start = 2 + num_digits
                                    if len(raw_data) >= start + length:
                                        raw = raw_data[start:start + length]
                                        return np.frombuffer(raw, dtype=np.uint8)
                        except (ValueError, UnicodeDecodeError):
                            pass
                    return np.array([])
                except Exception as e:
                    print(f"PyVISA binary query error: {e}")
                    return np.array([])
            
            elif self.usbtmc_inst:
                # PyUSBTMC: usar write() + read() separados para dados binários
                # ask() do PyUSBTMC não funciona bem com dados binários grandes
                try:
                    # PyUSBTMC.write() já adiciona terminator automaticamente
                    # Não adicionar \\n manualmente (duas vezes = problema)
                    self.usbtmc_inst.write(cmd)
                    time.sleep(0.5)  # Wait for response
                    
                    # Read data with large buffer
                    # Calculate expected size based on TMC format
                    # Read in chunks to handle large data
                    raw_data = self.usbtmc_inst.read(
                        requestSize=1048576,  # 1MB buffer
                        io_timeout=30000      # 30 second timeout
                    )
                    
                    # Parsing do formato TMC: #N + N dígitos + dados
                    if isinstance(raw_data, bytes) and raw_data.startswith(b'#'):
                        try:
                            if len(raw_data) > 2 and chr(raw_data[1]).isdigit():
                                num_digits = int(chr(raw_data[1]))
                                if len(raw_data) >= 2 + num_digits:
                                    length_str = raw_data[2:2 + num_digits].decode('ascii')
                                    length = int(length_str)
                                    start = 2 + num_digits
                                    if len(raw_data) >= start + length:
                                        raw = raw_data[start:start + length]
                                        # O DHO usa BYTE format (8 bits) por padrão para WAVE:DATA?
                                        # Confirmar com o comando: WAVE:FORMAT BYTE
                                        return np.frombuffer(raw, dtype=np.uint8)
                        except (ValueError, UnicodeDecodeError):
                                            pass
                    return np.array([])
                except Exception as e:
                    print(f"PyUSBTMC binary query error: {e}")
                    return np.array([])
            
            elif self.usbtmc_file:
                # USB-TMC via /dev/usbtmc (fallback antigo)
                # Enviar comando
                self._write(cmd)
                time.sleep(0.2)
                
                # Ler resposta (formato TMC com header)
                data = bytearray()
                max_read = 100000  # 100KB max
                chunk_size = 4096
                
                while len(data) < max_read:
                    chunk = self.usbtmc_file.read(chunk_size)
                    if not chunk:
                        break
                    data.extend(chunk)
                    
                    # Verificar block TMC completo
                    if len(data) > 2 and data[0:1] == b'#':
                        try:
                            num = int(chr(data[1]))
                            if num > 0 and len(data) >= 2 + num:
                                length = int(data[2:2 + num].decode('ascii'))
                                if len(data) >= 2 + num + length:
                                    break
                        except (ValueError, UnicodeDecodeError):
                            pass
                
                if data[0:1] == b'#':
                    try:
                        num = int(chr(data[1]))
                        length = int(data[2:2 + num].decode('ascii'))
                        start = 2 + num
                        if len(data) < start + length:
                            raise Exception(
                                f"incomplete TMC block: {len(data)} < {start + length} bytes"
                            )
                        raw = bytes(data[start:start + length])
                        return np.frombuffer(raw, dtype=np.uint8)
                    except (ValueError, IndexError, UnicodeDecodeError):
                        pass
                return np.array([])
            else:
                raise Exception("No connection available")
        except Exception as e:
            raise Exception(f"Binary query error: {cmd} - {e}")
    
    def _get_waveform_preamble(self) -> Dict[str, Any]:
        """
        Recupera preâmbulo da onda para cálculos de escala
        
        O preâmbulo contém 10 parâmetros (conforme manual página 435):
        <format>,<type>,<points>,<count>,<xincrement>,<xorigin>,<xreference>,
        <yincrement>,<yorigin>,<yreference>
        
        Returns:
            Dicionário com parâmetros de escala:
            - xinc: Incremento de tempo (xincrement)
            - xorig: Origem de tempo (xorigin)
            - xref: Referência X (xreference)
            - yinc: Incremento de tensão (yincrement)
            - yorig: Offset vertical (yorigin)
            - yref: Referência Y (yreference)
            - points: Número de pontos
        """
        try:
            pre_str = self._query(CMD_WAV_PRE)
            pre = pre_str.split(',')
            
            # Preenâmbulo DHO800/DHO900 (10 campos conforme página 435):
            # 0: <format> - 0 (BYTE), 1 (WORD), 2 (ASC)
            # 1: <type> - 0 (NORMal), 1 (MAXimum), 2 (RAW)
            # 2: <points> - número de pontos (1 a 50,000,000)
            # 3: <count> - número de médias (1 em outros modos)
            # 4: <xincrement> - incremento de tempo
            # 5: <xorigin> - tempo inicial
            # 6: <xreference> - referência X (sempre 0 para DHO)
            # 7: <yincrement> - incremento de tensão
            # 8: <yorigin> - offset vertical
            # 9: <yreference> - referência Y (depende do formato)
            
            return {
                'format': int(pre[0]) if len(pre) > 0 else 0,  # 0=BYTE, 1=WORD, 2=ASC
                'type': int(pre[1]) if len(pre) > 1 else 0,  # 0=NORM, 1=MAX, 2=RAW
                'points': int(float(pre[2])) if len(pre) > 2 else 1000,
                'count': int(float(pre[3])) if len(pre) > 3 else 1,
                'xinc': float(pre[4]) if len(pre) > 4 else 1.0,
                'xorig': float(pre[5]) if len(pre) > 5 else 0.0,
                'xref': float(pre[6]) if len(pre) > 6 else 0.0,
                'yinc': float(pre[7]) if len(pre) > 7 else 1.0,
                'yorig': float(pre[8]) if len(pre) > 8 else 0.0,
                'yref': float(pre[9]) if len(pre) > 9 else 0.0,
            }
        except Exception as e:
            raise Exception(f"Failed to get waveform preamble: {e}")
    
    def _get_waveform_data(self, channel: str) -> np.ndarray:
        """
        Captura dados da onda de um canal
        
        Args:
            channel: Nome do canal (CHAN1, CHAN2, MATH1, etc.)
            
        Returns:
            Array de valores de tensão em Volts
        """
        try:
            # Configurar fonte de onda
            self._write(f"{CMD_WAV_SOURCE} {channel}")
            
            # Configurar modo e formato
            self._write(f"{CMD_WAV_MODE} NORM")
            self._write(f"{CMD_WAV_FORMAT} BYTE")
            
            time.sleep(self.WAVEFORM_DELAY)
            
            # Obter preâmbulo
            pre = self._get_waveform_preamble()
            
            # Obter dados binários
            raw = self._query_binary(f"{CMD_WAV_DATA}?")
            
            if len(raw) == 0:
                return np.array([])
            
            # Calcular tensão: V = (raw - yref - yorig) * yinc
            volts = (raw.astype(float) - pre['yref'] - pre['yorig']) * pre['yinc']
            
            return volts
            
        except Exception as e:
            print(f"Error getting waveform from {channel}: {e}")
            return np.array([])
    
    def set_channel_display(self, channel: str, enabled: bool) -> None:
        """
        Habilita/desabilita visualização de canal
        
        Args:
            channel: Nome do canal (CHAN1, CHAN2, etc.)
            enabled: True para ligar, False para desligar
        """
        num = channel.replace('CHAN', '')
        cmd = f"{CMD_CHAN_DISP.format(num)} {'ON' if enabled else 'OFF'}"
        self._write(cmd)
    
    def set_channel_coupling(self, channel: str, coupling: str) -> None:
        """
        Define acoplamento do canal (AC, DC, GND)
        
        Args:
            channel: Nome do canal
            coupling: 'AC', 'DC' ou 'GND'
        """
        num = channel.replace('CHAN', '')
        cmd = f"{CMD_CHAN_COUPL.format(num)} {coupling}"
        self._write(cmd)
    
    def set_channel_scale(self, channel: str, scale_volts: float) -> None:
        """
        Define escala do canal (Volts por divisão)
        
        Args:
            channel: Nome do canal
            scale_volts: Valor em Volts/divisão (ex: 0.1, 1.0, 5.0)
        """
        num = channel.replace('CHAN', '')
        cmd = f"{CMD_CHAN_SCAL.format(num)} {scale_volts}"
        self._write(cmd)
    
    def set_channel_offset(self, channel: str, offset_volts: float) -> None:
        """
        Define offset do canal
        
        Args:
            channel: Nome do canal
            offset_volts: Offset em Volts
        """
        num = channel.replace('CHAN', '')
        cmd = f"{CMD_CHAN_OFFS.format(num)} {offset_volts}"
        self._write(cmd)
    
    def set_channel_probe(self, channel: str, probe_ratio: str) -> None:
        """
        Define relação da sonda
        
        Args:
            channel: Nome do canal
            probe_ratio: '1', '10', '100', etc.
        """
        num = channel.replace('CHAN', '')
        cmd = f"{CMD_CHAN_PROBE.format(num)} {probe_ratio}"
        self._write(cmd)
    
    def set_time_scale(self, scale_seconds: float) -> None:
        """
        Define escala de tempo (segundos por divisão)
        
        Args:
            scale_seconds: Valor em segundos/divisão (ex: 0.001, 0.01)
        """
        cmd = f"{CMD_TIME_SCALE} {scale_seconds}"
        self._write(cmd)
    
    def set_trigger_level(self, channel: str, level: float) -> None:
        """
        Define o canal de trigger e o nível.
        
        Args:
            channel: Canal para trigger (ex: 'CHAN1' ou '1')
            level: Nível em Volts
        """
        source = str(channel).strip()
        if not source:
            raise ValueError("Trigger channel is required")
        if source.isdigit():
            source = f"CHAN{source}"
        self._write(f"{CMD_TRIG_EDGE_SOURCE} {source}")
        self._write(f"{CMD_TRIG_EDGE_LEVEL} {level}")
    
    def run(self) -> None:
        """Inicia aquisição contínua"""
        try:
            self._write(CMD_RUN)
        except Exception as e:
            print(f"Run command failed: {e}")
    
    def stop(self) -> None:
        """Para aquisição"""
        try:
            self._write(CMD_STOP)
        except Exception as e:
            print(f"Stop command failed: {e}")
    
    def single(self) -> None:
        """Executa captura única (single sweep)"""
        try:
            self._write(CMD_SINGLE)
        except Exception as e:
            print(f"Single command failed: {e}")
    
    def reset(self) -> None:
        """Reseta o osciloscópio ao estado padrão"""
        try:
            self._write(CMD_RST)
        except Exception as e:
            print(f"Reset command failed: {e}")
    
    def get_idn(self) -> str:
        """
        Retorna identificação do instrumento
        
        Returns:
            String com identificação (Vendor,Model,Serial, Firm)
        """
        try:
            return self._query(CMD_IDN)
        except Exception as e:
            return f"IDN Error: {e}"
    
    def _configure_waveform(self, channel: str, mode: str) -> Dict[str, Any]:
        """Configura a fonte/modo/formato e retorna o preâmbulo do canal."""
        self._write(f":WAV:SOUR {channel}")
        self._write(f":WAV:MODE {mode}")
        self._write(":WAV:FORM BYTE")
        time.sleep(0.25)
        return self._get_waveform_preamble()

    def _read_channel_waveform(self, channel: str, probe: float = 1.0,
                               mode: str = 'NORM') -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Lê a forma de onda de um canal (aquisição já parada) em um modo específico.
        Retorna os valores em Volts e o preâmbulo usado.
        """
        pre = self._configure_waveform(channel, mode)
        raw = self._query_binary(":WAV:DATA?")
        if len(raw) == 0:
            raise Exception(f"empty waveform data for {channel} in {mode} mode")
        volts = (raw.astype(float) - float(pre['yref']) - float(pre['yorig'])) * float(pre['yinc'])
        volts = volts * float(probe)
        return volts, pre

    def _read_waveform_pair(self, ch_x: str, ch_y: str,
                            probe_x: float = 1.0, probe_y: float = 1.0,
                            ) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any], Dict[str, Any], str]:
        """
        Lê CH_X e CH_Y usando o MESMO modo de aquisição.

        É importante não misturar RAW em um canal e NORM no outro: as duas
        ondas precisam ter a mesma base temporal para que o par (x[i], y[i])
        represente a mesma amostra no display X-Y.
        """
        last_error = None
        for mode in ('RAW', 'MAX', 'NORM'):
            try:
                vx, pre_x = self._read_channel_waveform(ch_x, probe_x, mode)
                vy, pre_y = self._read_channel_waveform(ch_y, probe_y, mode)
                if len(vx) == 0 or len(vy) == 0:
                    last_error = f"empty data in {mode} mode"
                    continue
                return vx, vy, pre_x, pre_y, mode
            except Exception as e:
                last_error = f"{mode}: {e}"
                continue
        raise Exception(f"No waveform data for {ch_x}/{ch_y}: {last_error}")

    def is_xy_enabled(self) -> bool:
        """Retorna True se o modo X-Y estiver habilitado no osciloscópio."""
        try:
            return bool(int(float(self._query(':TIM:XY:ENABle?').strip())))
        except Exception:
            return False

    @staticmethod
    def _normalize_channel(name: str) -> str:
        """Normaliza CHANnel1/CHAN1 para CHAN1."""
        digits = ''.join(c for c in str(name) if c.isdigit())
        return f"CHAN{digits}" if digits else str(name).strip().upper()

    def get_xy_sources(self) -> Tuple[Optional[str], Optional[str]]:
        """Consulta os canais usados como X e Y no display X-Y do DHO.

        Comandos documentados: :TIMebase:XY:X? e :TIMebase:XY:Y?.
        """
        try:
            x = self._normalize_channel(self._query(':TIM:XY:X?'))
            y = self._normalize_channel(self._query(':TIM:XY:Y?'))
            return x, y
        except Exception as e:
            print(f"get_xy_sources error: {e}")
            return None, None

    def set_xy_sources(self, ch_x: str, ch_y: str) -> bool:
        """Ajusta os canais X/Y do display se estiverem diferentes.

        Evita reenviar o comando quando já está correto: no DHO, reenviar
        :TIM:XY:X/Y (mesmo com o mesmo valor) limpa o traço X-Y até a próxima
        aquisição.

        Returns:
            True se houve mudança (o chamador deve rodar/parar para atualizar).
        """
        cur_x, cur_y = self.get_xy_sources()
        want_x = self._normalize_channel(ch_x)
        want_y = self._normalize_channel(ch_y)
        changed = False
        if cur_x and cur_x != want_x:
            self._write(f':TIM:XY:X {want_x}')
            changed = True
        if cur_y and cur_y != want_y:
            self._write(f':TIM:XY:Y {want_y}')
            changed = True
        return changed

    def capture_xy(self, ch_x: str = 'CHAN1', ch_y: str = 'CHAN2', 
                   probe_x: float = 1.0, probe_y: float = 1.0,
                   y_is_direct_current: bool = True,
                   shunt_r: Optional[float] = None,
                   invert_y: bool = False,
                   timeout_seconds: float = 5.0,
                   keep_xy: bool = True,
                   resume_after: bool = True) -> Tuple[np.ndarray, np.ndarray]:
        """
        Captura onda X-Y para curve tracing preservando o modo X-Y do osciloscópio.
        
        Sequência:
        1. Garante modo X-Y ativo (não desativa)
        2. Para a aquisição (frame congelado, igual ao display)
        3. Lê CH_X e CH_Y da MESMA aquisição e no MESMO modo de waveform
        4. Retoma a aquisição em X-Y ao final (padrão), ou mantém parado
        
        Args:
            keep_xy: manter modo X-Y ativo (padrão True)
            resume_after: retomar aquisição contínua após captura (padrão True)
        
        Returns:
            Tuple (vx, vy) em unidades físicas, na ordem temporal original
        """
        if not self.connected:
            raise Exception("Not connected to oscilloscope")
        
        try:
            # Garantir XY ativo (não desligar em nenhum momento)
            if keep_xy and not self.is_xy_enabled():
                self._write(':TIM:XY:ENABle ON')
                time.sleep(0.2)

            # Garantir que o display X-Y usa os mesmos canais que a captura
            sources_changed = False
            if keep_xy:
                try:
                    sources_changed = self.set_xy_sources(ch_x, ch_y)
                except Exception as e:
                    print(f"XY source sync error: {e}")

            # Congelar aquisição para ler os dois canais do mesmo frame
            self.stop()
            if sources_changed:
                # Alterar X/Y limpa o traço X-Y; uma aquisição nova redesenha
                self.run()
                time.sleep(0.35)
                self.stop()
            time.sleep(0.4)
            
            # Garantir canais visíveis. Importante: NÃO reenviar DISP ON se o
            # canal já estiver ligado; no DHO isso limpa o traço do modo X-Y
            # até a próxima aquisição (o usuário precisa comparar com a tela).
            for ch in (ch_x, ch_y):
                try:
                    if self._query(f':{ch}:DISP?').strip() not in ('1', 'ON'):
                        self._write(f':{ch}:DISP ON')
                        time.sleep(0.1)
                except Exception:
                    pass
            
            # Ler os dois canais com o mesmo modo (RAW > MAX > NORM)
            vx, vy, pre_x, pre_y, mode = self._read_waveform_pair(
                ch_x, ch_y, probe_x, probe_y
            )
            self.last_waveform_mode = mode
            self.last_preamble = {'x': pre_x, 'y': pre_y}
            
            if len(vx) == 0 or len(vy) == 0:
                raise Exception(f"Failed to acquire waveforms - vx_len={len(vx)}, vy_len={len(vy)}")
            
            # Ajuste físico de corrente (USAGE.md: se Shunt R > 0, I = V/R)
            if shunt_r and shunt_r > 0:
                vy = vy / shunt_r
            if invert_y:
                vy = -vy
            
            # Sincronizar mantendo a correspondência temporal (mesmo índice).
            # NÃO ordenar, suavizar, fechar ou remover amostras: o par
            # (vx[i], vy[i]) é exatamente a amostra i do frame X-Y.
            n = min(len(vx), len(vy))
            vx = vx[:n].copy()
            vy = vy[:n].copy()
            
            if resume_after:
                self.run()
            
            # O scope não deve sair do modo X-Y durante a captura; se algum
            # comando de waveform o desativou, restaura antes de retornar.
            if keep_xy and not self.is_xy_enabled():
                self._write(':TIM:XY:ENABle ON')
                time.sleep(0.2)
            
            return vx, vy
            
        except SocketTimeout:
            raise Exception(f"Capture timeout after {timeout_seconds}s")
        except Exception as e:
            raise Exception(f"Capture error: {e}")
    
    def get_channel_scale(self, channel: str) -> float:
        """
        Obtém escala atual do canal
        
        Args:
            channel: Nome do canal
            
        Returns:
            Valor em Volts/divisão
        """
        try:
            num = channel.replace('CHAN', '')
            resp = self._query(f"{CMD_CHAN_SCAL.format(num)}?")
            return float(resp.strip())
        except Exception as e:
            print(f"get_scale error {channel}: {e}")
            return 1.0
    
    def get_channel_offset(self, channel: str) -> float:
        """
        Obtém offset atual do canal
        
        Args:
            channel: Nome do canal
            
        Returns:
            Valor em Volts
        """
        try:
            num = channel.replace('CHAN', '')
            resp = self._query(f"{CMD_CHAN_OFFS.format(num)}?")
            return float(resp.strip())
        except Exception as e:
            print(f"get_offset error {channel}: {e}")
            return 0.0
    
    def get_channel_division_range(self, channel: str) -> Tuple[float, float]:
        """
        Obtém o range de tensão das 8 divisões visíveis de um canal.

        O centro da tela do DHO fica em ``-offset`` (ver
        :func:`compute_channel_screen_range` e o manual, que define os limites
        como ``±4 x VerticalScale - OFFSet``).

        Args:
            channel: Nome do canal

        Returns:
            Tuple (min, max) em Volts
        """
        try:
            scale = self.get_channel_scale(channel)
            offset = self.get_channel_offset(channel)
            return compute_channel_screen_range(scale, offset)
        except Exception as e:
            print(f"get_div_range error {channel}: {e}")
            return (-1.0, 1.0)
    
    def get_time_scale(self) -> float:
        """
        Obtém escala de tempo atual
        
        Returns:
            Valor em segundos/divisão
        """
        try:
            resp = self._query(f"{CMD_TIME_SCALE}?")
            return float(resp.strip())
        except Exception as e:
            print(f"get_time_scale error: {e}")
            return 1e-3  # Default: 1ms/div
    
    def close(self) -> None:
        """
        Fecha conexão e limpa recursos
        """
        try:
            # Tentar retomar aquisição
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
            if self.usbtmc_file:
                self.usbtmc_file.close()
        except:
            pass
        
        try:
            if self.rm:
                self.rm.close()
        except:
            pass
        
        try:
            if self.usbtmc_inst:
                # PyUSBTMC não tem método close explícito, mas __del__ chama dispose_resources
                # Para evitar "Resource busy", chamar explicitamente o GC
                device = self.usbtmc_inst.device  # PyUSB device
                if device:
                    try:
                        from usb.util import dispose_resources
                        dispose_resources(device)
                    except:
                        pass
                self.usbtmc_inst = None
        except:
            pass
        
        self.inst = None
        self.sock = None
        self.usbtmc_file = None
        self.rm = None
        self.usbtmc_inst = None
        self.connected = False


def discover_rigol() -> Tuple[Tuple[str, ...], Tuple[Tuple[str, str], ...]]:
    """
    Descobre dispositivos Rigol disponíveis
    
    Returns:
        Tuple de (all_resources, rigol_resources)
        onde rigol_resources é uma lista de (resource, idn) tuples
    """
    all_resources = []
    rigol_resources = []
    
    # 1. Buscar dispositivos USB-TMC via PyUSBTMC (driver direto pyusb) - tem preferência
    if USBTMC_AVAILABLE:
        try:
            pyusbtmc_devices = list(PyUSBTMC.find_tmc_devices())
            for device in pyusbtmc_devices:
                # Adicionar identificador único
                dev_id = f"PyUSBTMC::{device.idVendor:04x}:{device.idProduct:04x}"
                all_resources.append(dev_id)
                
                try:
                    # Criar instância e fazer query
                    usbtmc = PyUSBTMC.USBTMC_device(device)
                    usbtmc.write("*IDN?")
                    time.sleep(0.3)
                    idn = usbtmc.read(requestSize=256, io_timeout=5000)
                    if isinstance(idn, bytes):
                        idn = idn.decode('utf-8', errors='ignore')
                    
                    if idn and 'RIGOL' in idn.upper():
                        rigol_idn = idn.strip()
                        rigol_resources.append((dev_id, rigol_idn))
                        print(f"[DISCOVER] Found Rigol via PyUSBTMC: {dev_id} - {rigol_idn}")
                    
                    # Liberar recursos imediatamente para evitar \"Resource busy\"
                    from usb.util import dispose_resources
                    dispose_resources(usbtmc.device)
                    usbtmc.device = None
                except Exception as e:
                    print(f"[DISCOVER] PyUSBTMC probe error {dev_id}: {e}")
        except Exception as e:
            print(f"[DISCOVER] PyUSBTMC discovery error: {e}")
    
    # 2. Tentar PyVISA (para TCPIP/LXI) apenas se PyUSBTMC não estiver disponível
    if not rigol_resources:
        try:
            rm = pyvisa.ResourceManager('@py')
            all_resources.extend(rm.list_resources())
            
            # Detectar dispositivos TCP/IP via PyVISA
            for res in all_resources:
                if 'TCPIP' in res and 'INSTR' in res:
                    try:
                        inst = rm.open_resource(res)
                        inst.timeout = 5000
                        idn = inst.query('*IDN?').strip()
                        
                        if idn and 'RIGOL' in idn.upper():
                            rigol_resources.append((res, idn))
                            print(f"[DISCOVER] Found Rigol via PyVISA TCPIP: {res} - {idn}")
                        inst.close()
                    except Exception as e:
                        print(f"[DISCOVER] TCPIP probe error {res}: {e}")
            
            rm.close()
        except Exception as e:
            print(f"PyVISA discovery error: {e}")
    
    # 3. Buscar dispositivos USB-TMC via /dev/usbtmc (Linux kernel driver)
    # NI-VISA para Linux não suporta USB-TMC - usar driver do kernel diretamente
    usbtmc_devices = glob.glob('/dev/usbtmc*')
    for dev_path in usbtmc_devices:
        all_resources.append(f"USB-TMC::{dev_path}")
        try:
            # Tentar conectar e ler IDN
            with open(dev_path, 'w+b', buffering=0) as f:
                f.write(b'*IDN?\n')
                f.flush()
                time.sleep(0.2)
                resp = f.read(512).decode('utf-8', errors='ignore').strip()
                if resp and 'RIGOL' in resp.upper():
                    rigol_resources.append((f"USB-TMC::{dev_path}", resp))
                    print(f"[DISCOVER] Found Rigol via /dev/usbtmc: {dev_path}")
        except Exception as e:
            print(f"[DISCOVER] USB-TMC probe error {dev_path}: {e}")
    
    # Filtrar por nomes associados à Rigol - evitar duplicação
    # Converte tuples para string para comparação
    rigol_from_all = [
        r for r in all_resources 
        if ('USB' in r.upper() and 'USB-TMC' not in r) or  # já tratado
           any('RIGOL' in (rr[0] if isinstance(rr, tuple) else rr).upper() for rr in rigol_resources)
    ]
    
    # Converter rigol_from_all para tuples (sem IDN)
    rigol_from_all_tuples = [(r, '') for r in rigol_from_all]
    
    # Unir únicos (evitar duplicação) usando apenas o resource como chave
    seen = set()
    unique_rigol = []
    for rr in rigol_resources + rigol_from_all_tuples:
        resource_key = rr[0] if isinstance(rr, tuple) else rr
        if resource_key not in seen:
            seen.add(resource_key)
            unique_rigol.append(rr)
    
    return tuple(all_resources), tuple(unique_rigol)


def discover_rigol_network(subnets=None, timeout=0.5):
    """
    Descobre Rigol na rede via socket (rápido)
    """
    import socket
    import time
    
    if subnets is None:
        subnets = ['192.168.1.', '192.168.0.', '192.168.68.', '10.0.0.', '172.16.0.']
    
    found = []
    for subnet in subnets:
        for i in range(1, 255):
            ip = f'{subnet}{i}'
            for port in [5555, 5025]:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(timeout)
                    result = sock.connect_ex((ip, port))
                    if result == 0:
                        try:
                            sock.sendall(b'*IDN?\n')
                            time.sleep(0.2)
                            resp = sock.recv(512).decode(errors='ignore').strip()
                            if resp and 'RIGOL' in resp.upper():
                                found.append({
                                    'ip': ip,
                                    'port': port,
                                    'idn': resp
                                })
                                print(f'[DISCOVER] Found {resp} at {ip}:{port}')
                        except:
                            pass
                        sock.close()
                        break
                except:
                    pass
                finally:
                    try:
                        sock.close()
                    except:
                        pass
    
    return found
