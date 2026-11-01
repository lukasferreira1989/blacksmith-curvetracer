#!/usr/bin/env python3
"""
Rigol DHO800/DHO900 and MSO5000 Series Oscilloscope Interface
Blacksmith CurveTracer - X-Y Mode for Analog Curve Tracer

Comandos SCPI baseados nos guias:
- DHO800900_ProgrammingGuide_EN.pdf
- MSO5_programming_guide.pdf
"""

# pylint: skip-file

import pyvisa
import numpy as np
import time
import socket
import select
import os
import glob
import ipaddress
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Tuple, Optional, Dict, Any, Iterable, List

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



def _open_visa_resource_manager():
    """Abre o ResourceManager do VISA preferindo a biblioteca do sistema.

    No Windows é o NI-VISA (ou o driver VISA do fabricante) que conversa com o
    USB-TMC do instrumento. O backend puro Python (pyvisa-py) fica como
    alternativa quando não há VISA instalado — e é ele que usa pyusb/libusb.
    """
    try:
        return pyvisa.ResourceManager()
    except Exception as e:
        print(f"System VISA unavailable ({e}); falling back to pyvisa-py")
        return pyvisa.ResourceManager('@py')


def _parse_tcpip_resource(resource_name: Optional[str]) -> Tuple[Optional[str], Optional[int]]:
    """Extrai ``(ip, porta)`` de um recurso TCP/IP ou de um IP digitado.

    Formatos aceitos::

        TCPIP::192.168.68.104::INSTR          -> (ip, None)
        TCPIP0::192.168.68.104::5555::SOCKET  -> (ip, 5555)
        TCPIP::192.168.68.104::SOCKET         -> (ip, 5555)
        192.168.68.104                        -> (ip, None)
        192.168.68.104:5555                   -> (ip, 5555)

    Quando nenhuma porta é informada, ``None`` é devolvido e o ``connect()``
    usa a porta padrão do Rigol (5555).
    """
    text = (resource_name or '').strip()
    if not text:
        return None, None

    if text.upper().startswith('TCPIP'):
        parts = text.split('::')
        if len(parts) < 2:
            return None, None
        ip = parts[1].strip()
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            return None, None

        port = None
        for token in parts[2:]:
            token = token.strip()
            if token.isdigit():
                port = int(token)
                break
            if token.upper() in ('INSTR', 'SOCKET', 'HISLIP'):
                if token.upper() == 'SOCKET':
                    port = 5555
                break
        return ip, port

    # IP puro, opcionalmente com ":porta"
    host, sep, port_text = text.partition(':')
    try:
        ipaddress.ip_address(host.strip())
    except ValueError:
        return None, None
    port = int(port_text) if sep and port_text.strip().isdigit() else None
    return host.strip(), port


class RigolScopeXY:
    """Interface para Rigol DHO800/DHO900 Oscilloscope em modo X-Y"""
    
    # Configurações padrão
    DEFAULT_TIMEOUT = 10000  # ms
    DEFAULT_PROBE = "1"
    WAVEFORM_DELAY = 0.5  # segundos após configurar waveform
    WAVEFORM_MAX_POINTS = 10000  # pontos lidos por canal no modo RAW
    MSO_CAPTURE_MDEPTH = '10k'  # profundidade que faz o RAW cobrir a tela
    
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
        self.usbtmc_inst = None  # PyUSBTMC.USBTMC_device
        self.usbtmc_file = None  # arquivo /dev/usbtmc
        self.use_socket = use_socket
        self.ip = None
        self.port = None
        self.connected = False
        self.idn = ''
        self.model = ''
        self.last_waveform_mode: Optional[str] = None
        self.last_preamble: Dict[str, Any] = {}
        
        if resource_name:
            self.connect(resource_name, use_socket)

    def _set_identity(self, idn: str) -> None:
        """Guarda a resposta de ``*IDN?`` e o modelo para escolher o dialeto SCPI.

        O DHO800/DHO900 e o MSO5000 compartilham a maior parte dos comandos,
        mas o modo X-Y e a leitura de waveform têm diferenças. Guardar o
        modelo logo na conexão evita consultas inválidas (que geram timeout)
        no equipamento errado.
        """
        self.idn = (idn or '').strip()
        parts = [p.strip() for p in self.idn.split(',')]
        self.model = parts[1] if len(parts) > 1 else ''

    def _is_mso_family(self) -> bool:
        """True para a família MSO5000 (ex.: MSO5074).

        A família MSO5000 usa ``:TIMebase:MODE XY`` para entrar no modo X-Y e
        não possui os comandos ``:TIMebase:XY:*`` do DHO800/DHO900. Modelos
        desconhecidos continuam usando o dialeto DHO para manter o
        comportamento anterior.
        """
        text = f"{getattr(self, 'model', '')} {getattr(self, 'idn', '')}".upper()
        return 'MSO5' in text

    def get_screen_divisions(self) -> Tuple[float, float]:
        """Número de divisões (X, Y) da área X-Y do display.

        Tanto o DHO800/DHO900 quanto o MSO5000 usam uma área X-Y de
        8 x 8 divisões (o MSO troca a grade YT de 10 colunas por uma grade
        quadrada no modo X-Y; confirmado pela captura de tela do MSO5074).
        """
        return SCREEN_DIVISIONS, SCREEN_DIVISIONS
    
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
            
            # Detectar se é um IP TCP (TCPIP::IP::[porta]::SOCKET, TCPIP::IP::INSTR
            # ou IP puro, com ou sem ":porta")
            net_ip, net_port = _parse_tcpip_resource(resource_name)
            if net_ip:
                self.ip = net_ip
                self.port = net_port
                self.use_socket = use_socket or True
            # Detectar dispositivo USB-TMC via PyVISA-py (USB0::...::INSTR) - PRIMEIRO
            # para evitar falsos positivos com /dev/usbtmc
            elif resource_name and resource_name.startswith('USB0::'):
                pass  # Já inicializaremos o PyVISA ResourceManager abaixo
            # Detectar dispositivo USB-TMC via /dev/usbtmc (não recomendado para novas implementações)
            elif resource_name and ('USB-TMC' in resource_name.upper() or '/dev/usbtmc' in resource_name):
                self.usbtmc_path = resource_name.replace('USB-TMC::', '').replace('USB0::', '').lstrip('/')
                if self.usbtmc_path and not self.usbtmc_path.startswith('/dev/usbtmc'):
                    self.usbtmc_path = '/dev/usbtmc' + self.usbtmc_path
                self.use_socket = False
                return self._connect_usbtmc()
            
            # Inicializar PyVISA ResourceManager (precisa ser feito antes de USB-TMC via PyVISA)
            try:
                self.rm = _open_visa_resource_manager()
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
                vid = pid = None
                try:
                    # Extrair vendor e product IDs
                    parts = resource_name.split('::')
                    if len(parts) >= 2:
                        vend_prod = parts[1].split(':')
                        if len(vend_prod) >= 2:
                            vid = int(vend_prod[0], 16)
                            pid = int(vend_prod[1], 16)
                except Exception as e:
                    print(f"PyUSBTMC resource parse error: {e}")

                if USBTMC_AVAILABLE and vid is not None:
                    try:
                        devices = list(PyUSBTMC.find_tmc_devices())
                        for device in devices:
                            if device.idVendor == vid and device.idProduct == pid:
                                try:
                                    return self._connect_pyusbtmc(device)
                                except Exception as e:
                                    print(f"PyUSBTMC connection error: {e}")
                                    self._dispose_usbtmc()
                    except Exception as e:
                        print(f"PyUSBTMC discovery error: {e}")

                # Fallback: o mesmo aparelho pode ser acessado pelo VISA
                # (NI-VISA no Windows, pyvisa-py no Linux). Útil quando o
                # backend PyUSBTMC está indisponível ou o dispositivo ficou
                # momentaneamente ocupado.
                try:
                    if self.rm is None:
                        self.rm = _open_visa_resource_manager()
                    for res in self.rm.list_resources():
                        if not res.startswith('USB0::'):
                            continue
                        try:
                            parts = res.split('::')
                            rv = int(parts[1], 0)
                            rp = int(parts[2], 0)
                        except Exception:
                            continue
                        if vid is not None and (rv, rp) != (vid, pid):
                            continue
                        try:
                            return self._connect_pyvisa_usbtmc(res)
                        except Exception as e:
                            print(f"PyVISA USB fallback failed for {res}: {e}")
                except Exception as e:
                    print(f"PyVISA USB fallback unavailable: {e}")

                if not USBTMC_AVAILABLE:
                    raise Exception(
                        "PyUSBTMC not available and no VISA USB fallback"
                    )
                raise Exception(
                    f"Failed to connect via PyUSBTMC: {resource_name}. "
                    "Se houve um timeout anterior, desligue o osciloscópio, "
                    "aguarde 10 s e ligue-o novamente com o cabo USB "
                    "conectado (o USBTMC pode ter ficado com uma "
                    "transferência pendente). Alternativamente, use a "
                    "conexão LAN (TCPIP::<ip>::5555::SOCKET)."
                )
            
            # Tentar conexão via socket (Rigol usa 5555; VISA socket usa 5025)
            if self.ip:
                ports_to_try = []
                for candidate_port in (self.port, 5555, 5025):
                    if candidate_port and candidate_port not in ports_to_try:
                        ports_to_try.append(candidate_port)

                for candidate_port in ports_to_try:
                    try:
                        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        self.sock.settimeout(5)
                        self.sock.connect((self.ip, candidate_port))
                        self.sock.sendall(f"{CMD_IDN}\n".encode())
                        time.sleep(0.2)
                        resp = self.sock.recv(1024).decode(errors='ignore').strip()
                        print(f"Connected via SOCKET {candidate_port}: {resp}")
                        self._set_identity(resp)
                        self.port = candidate_port
                        self.use_socket = True
                        self.connected = True
                        return True
                    except Exception as e:
                        print(f"Socket {candidate_port} failed: {e}")
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
                    candidates.append(
                        f'TCPIP::{self.ip}::{self.port or 5025}::SOCKET'
                    )
            
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
                    
                    self._set_identity(idn)
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
    
    def _dispose_usbtmc(self) -> None:
        """Libera o PyUSBTMC/pyusb sem deixar a interface USB presa."""
        inst = self.usbtmc_inst
        self.usbtmc_inst = None
        if inst is None:
            return
        try:
            from usb.util import dispose_resources
            device = getattr(inst, 'device', None)
            if device is not None:
                dispose_resources(device)
                inst.device = None
        except Exception:
            pass

    @staticmethod
    def _open_pyusbtmc_lite(device: Any):
        """Cria um USBTMC_device sem o GET_CAPABILITIES (classe/controle).

        O MSO5074 pode deixar de responder ao GET_CAPABILITIES depois de um
        timeout de USB, embora os endpoints bulk continuem funcionando. O
        PyUSBTMC chama esse request no construtor e falha antes de qualquer
        comunicação SCPI. Aqui montamos apenas o necessário para ``write``/
        ``read`` (endpoints bulk), que é o que o driver usa.
        """
        import PyUSBTMC

        inst = object.__new__(PyUSBTMC.USBTMC_device)
        inst.device = device

        try:
            if device.is_kernel_driver_active(0):
                device.detach_kernel_driver(0)
        except Exception:
            pass

        device.set_configuration()
        device.set_interface_altsetting()

        for config in device:
            for intf in config:
                if (intf.bInterfaceClass == 0xFE
                        and intf.bInterfaceSubClass == 3):
                    inst.__init_data__()
                    inst.getendpoints(config, intf)
                    return inst

        raise Exception("USBTMC interface not found")

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
            
            # Criar o objeto USBTMC. O construtor padrão do PyUSBTMC chama
            # GET_CAPABILITIES; no MSO5074 esse request pode ficar sem
            # resposta mesmo com os endpoints bulk funcionando. Tentamos
            # primeiro o modo "lite" (sem capabilities), que é suficiente
            # para write()/read().
            try:
                self.usbtmc_inst = self._open_pyusbtmc_lite(device)
                print(f"Connected via PyUSBTMC (lite): {device}")
            except Exception as lite_error:
                print(f"PyUSBTMC lite init failed: {lite_error}; "
                      f"trying standard init")
                self.usbtmc_inst = PyUSBTMC.USBTMC_device(device)
                print(f"Connected via PyUSBTMC: {device}")
            
            # Verificar conexão com *IDN? usando write() + read() separados.
            # O ask() do PyUSBTMC ativa o caractere de terminação, o que é
            # mais confiável no MSO5000 do que uma leitura "cega".
            #
            # Importante: se uma sessão anterior deixou uma resposta pendente
            # (por exemplo, um :WAV:DATA? que deu timeout), ela chega antes do
            # IDN. Escrevemos o IDN UMA vez e lemos até encontrá-lo, sem
            # reenviar o comando (reenviar criaria respostas duplicadas e
            # desalinharia todas as queries seguintes).
            self._drain_usbtmc_raw()
            self.usbtmc_inst.write("*IDN?")
            idn = ''
            last_error = None
            for attempt in range(6):
                time.sleep(0.2 if attempt == 0 else 0.05)
                try:
                    try:
                        resp = self.usbtmc_inst.read(
                            requestSize=256, io_timeout=5000,
                            flag=True, termChar='\n',
                        )
                    except TypeError:
                        resp = self.usbtmc_inst.read(
                            requestSize=256, io_timeout=5000,
                        )
                except Exception as e:
                    last_error = e
                    break
                if isinstance(resp, bytes):
                    resp = resp.decode('utf-8', errors='ignore')
                resp = (resp or '').strip()
                if resp and 'RIGOL' in resp.upper():
                    idn = resp
                    break
            print(f"IDN: {idn}")
            self._set_identity(idn)
            
            if idn and 'RIGOL' in idn.upper():
                self.connected = True
                return True
            if last_error is not None:
                raise Exception(f"Unexpected IDN response: {idn} ({last_error})")
            raise Exception(f"Unexpected IDN response: {idn}")
                
        except Exception as e:
            print(f"PyUSBTMC connection error: {e}")
            self._dispose_usbtmc()
            raise Exception(f"Failed to connect via PyUSBTMC: {e}")
    
    def _connect_pyvisa_usbtmc(self, resource_name: str) -> bool:
        """Conecta a um recurso USB-TMC via PyVISA (NI-VISA ou pyvisa-py).

        É o caminho usado no Windows, onde o NI-VISA fala com o driver
        USB-TMC instalado pelo fabricante.

        Returns:
            True se conectado com sucesso
        """
        try:
            if self.rm is None:
                self.rm = _open_visa_resource_manager()

            inst = self.rm.open_resource(resource_name)
            inst.timeout = self.DEFAULT_TIMEOUT
            try:
                inst.write_termination = '\n'
                inst.read_termination = '\n'
            except Exception:
                pass

            idn = inst.query(CMD_IDN).strip()
            if not idn:
                raise Exception("empty *IDN? response")
            if 'RIGOL' not in idn.upper():
                print(f"Warning: device may not be Rigol: {idn}")
            print(f"Connected via VISA USB-TMC: {idn}")

            self._set_identity(idn)
            self.inst = inst
            self.usbtmc_path = None
            self.use_socket = False
            self.connected = True
            return True

        except Exception as e:
            print(f"USB-TMC connection error: {e}")
            raise Exception(f"Failed to connect via USB-TMC: {e}")

    def _connect_usbtmc(self) -> bool:
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
                    self._set_identity(resp)
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
                self.inst.write_raw((cmd + '\n').encode())
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
                self.inst.write_raw((cmd + '\n').encode())
                time.sleep(0.1)  # Pequeno delay para resposta
                raw_resp = self.inst.read_raw()
                return raw_resp.decode('latin-1').strip()
            elif self.usbtmc_inst:
                # PyUSBTMC: write() + read() com TermChar habilitado. O MSO5000
                # responde de forma mais consistente quando o caractere de
                # terminação é usado (mesmo caminho do ask() da biblioteca).
                last_error = None
                for attempt in range(2):
                    try:
                        self.usbtmc_inst.write(cmd)
                        time.sleep(0.1)
                        try:
                            resp = self.usbtmc_inst.read(
                                requestSize=256, io_timeout=5000,
                                flag=True, termChar='\n',
                            )
                        except TypeError:
                            # Versões antigas de PyUSBTMC não aceitam flag/termChar
                            resp = self.usbtmc_inst.read(
                                requestSize=256, io_timeout=5000,
                            )
                    except Exception as e:
                        # Não reenviar depois de um timeout: a leitura
                        # anterior continuaria pendente no USBTMC e poderia
                        # travar o aparelho.
                        last_error = e
                        break
                    if isinstance(resp, bytes):
                        resp = resp.decode('utf-8', errors='ignore')
                    resp = resp.strip()
                    # Um \n remanescente de uma leitura binária anterior
                    # pode ser devolvido como resposta vazia; nesse caso
                    # repetimos a query uma vez.
                    if resp or attempt:
                        return resp
                if last_error is not None:
                    raise Exception(f"PyUSBTMC query error: {last_error}")
                return ''
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
    
    def _drain_usbtmc_raw(self, timeout: int = 200, max_reads: int = 64) -> None:
        """Descarta bytes já enviados pelo instrumento no endpoint bulk-IN.

        Usado antes de uma nova sessão/resync. Lê direto do endpoint (sem
        interpretar cabeçalho USBTMC), então funciona mesmo se a leitura
        anterior foi interrompida no meio de um bloco binário.
        """
        inst = getattr(self, 'usbtmc_inst', None)
        bulk_in = getattr(inst, 'bulk_in', None)
        if bulk_in is None:
            return
        for _ in range(max_reads):
            try:
                chunk = bulk_in.read(65536, timeout=timeout)
            except Exception:
                break
            if not chunk:
                break

    def _resync_pyusbtmc(self, attempts: int = 6) -> bool:
        """Descarta respostas pendentes e realinha o buffer do PyUSBTMC.

        Depois de um timeout (por exemplo, um ``:WAV:DATA?`` interrompido),
        a resposta pode chegar atrasada e ser devolvida pela query seguinte,
        deslocando todas as leituras. Enviamos um ``*IDN?`` e lemos até
        encontrar a resposta do instrumento, descartando o lixo anterior.
        """
        inst = getattr(self, 'usbtmc_inst', None)
        if inst is None:
            return False
        self._drain_usbtmc_raw()
        try:
            inst.write('*IDN?')
        except Exception:
            return False
        for _ in range(attempts):
            try:
                try:
                    resp = inst.read(
                        requestSize=256, io_timeout=1500,
                        flag=True, termChar='\n',
                    )
                except TypeError:
                    resp = inst.read(requestSize=256, io_timeout=1500)
            except Exception:
                return False
            if isinstance(resp, bytes):
                resp = resp.decode('utf-8', errors='ignore')
            if 'RIGOL' in (resp or '').upper():
                return True
        return False

    def _pyusbtmc_read_binary(self, cmd: str) -> bytes:
        """Lê um bloco TMC via PyUSBTMC, juntando pacotes curtos.

        O MSO5074 envia, por exemplo, 10.012 bytes de um bloco TMC em vários
        pacotes USB (8.180 + 1.832). O ``read()`` do PyUSBTMC confia no
        ``TransferSize`` do cabeçalho USBTMC e devolve só o primeiro pacote,
        truncando a waveform. Aqui lemos o cabeçalho com ``device_read`` e
        continuamos lendo do endpoint bulk até completar o tamanho anunciado.
        """
        inst = self.usbtmc_inst
        inst.write(cmd)
        time.sleep(0.1)

        # O pedido MSGIN precisa ser grande o bastante para o bloco inteiro;
        # se pedirmos 256 bytes o instrumento envia só 256 e o restante nunca
        # chega, deixando o TMC incompleto.
        request_size = max(65536, int(self.WAVEFORM_MAX_POINTS) + 64)
        resp = inst.device_read(request_size, timeout=30000)
        payload = bytes(resp.data)
        expected = int(resp.TransferSize)

        while len(payload) < expected:
            missing = expected - len(payload)
            try:
                chunk = inst.bulk_in.read(
                    min(missing + 16, 65536), timeout=30000
                )
            except Exception:
                break
            if not chunk:
                break
            payload += bytes(chunk)

        return payload[:expected]

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
                    self.inst.write_raw((cmd + '\n').encode())
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
                # PyUSBTMC: o read() padrão pode truncar blocos TMC grandes
                # quando o instrumento os envia em pacotes USB curtos.
                try:
                    raw_data = self._pyusbtmc_read_binary(cmd)
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
            # Fonte/modo/formato documentados para DHO e MSO5000.
            pre = self._configure_waveform(self._normalize_channel(channel), 'NORM')

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
        num = self._channel_number(channel)
        cmd = f"{CMD_CHAN_DISP.format(num)} {'ON' if enabled else 'OFF'}"
        self._write(cmd)
    
    def set_channel_coupling(self, channel: str, coupling: str) -> None:
        """
        Define acoplamento do canal (AC, DC, GND)
        
        Args:
            channel: Nome do canal
            coupling: 'AC', 'DC' ou 'GND'
        """
        num = self._channel_number(channel)
        cmd = f"{CMD_CHAN_COUPL.format(num)} {coupling}"
        self._write(cmd)
    
    def set_channel_scale(self, channel: str, scale_volts: float) -> None:
        """
        Define escala do canal (Volts por divisão)
        
        Args:
            channel: Nome do canal
            scale_volts: Valor em Volts/divisão (ex: 0.1, 1.0, 5.0)
        """
        num = self._channel_number(channel)
        cmd = f"{CMD_CHAN_SCAL.format(num)} {scale_volts}"
        self._write(cmd)
    
    def set_channel_offset(self, channel: str, offset_volts: float) -> None:
        """
        Define offset do canal
        
        Args:
            channel: Nome do canal
            offset_volts: Offset em Volts
        """
        num = self._channel_number(channel)
        cmd = f"{CMD_CHAN_OFFS.format(num)} {offset_volts}"
        self._write(cmd)
    
    def set_channel_probe(self, channel: str, probe_ratio: str) -> None:
        """
        Define relação da sonda
        
        Args:
            channel: Nome do canal
            probe_ratio: '1', '10', '100', etc.
        """
        num = self._channel_number(channel)
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
        """Configura a fonte/modo/formato e retorna o preâmbulo do canal.

        DHO800/DHO900 e MSO5000 usam os mesmos comandos curtos (``:WAV:*``).
        Em RAW ambos exigem ``:WAV:STAR``/``:WAV:STOP``; em NORM/MAX usamos
        1000 pontos (limite documentado do modo NORM) para não herdar um STOP
        grande de uma captura RAW anterior.
        """
        self._write(f":WAV:SOUR {self._normalize_channel(channel)}")
        self._write(f":WAV:MODE {mode}")
        self._write(":WAV:FORM BYTE")
        if str(mode).upper().startswith('RAW'):
            points = self._waveform_read_points()
        else:
            points = 1000
        self._write(":WAV:STAR 1")
        self._write(f":WAV:STOP {points}")
        time.sleep(0.25)
        return self._get_waveform_preamble()

    def _waveform_read_points(self) -> int:
        """Número de pontos RAW a ler, limitado pela memória do instrumento."""
        try:
            depth = float(self._query(':ACQ:MDEP?'))
        except Exception:
            depth = 0.0
        if not np.isfinite(depth) or depth <= 0:
            depth = float(self.WAVEFORM_MAX_POINTS)
        return max(1000, int(min(depth, self.WAVEFORM_MAX_POINTS)))

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
        # Escolhe RAW (10k pontos) ou NORM (dados da tela) conforme a
        # profundidade de memória: ver _waveform_modes_for_capture().
        modes = self._waveform_modes_for_capture()
        for mode in modes:
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
        """Retorna True se o modo X-Y estiver habilitado no osciloscópio.

        MSO5000: ``:TIMebase:MODE?`` retorna ``XY`` no modo X-Y.
        DHO800/DHO900: o guia documenta ``:TIMebase:MODE?`` retornando apenas
        MAIN/ROLL mesmo em X-Y, por isso a consulta principal é
        ``:TIMebase:XY:ENABle?``.
        """
        if self._is_mso_family():
            try:
                return self._query(':TIM:MODE?').strip().upper().startswith('XY')
            except Exception as e:
                print(f"is_xy_enabled error: {e}")
                return False

        try:
            resp = self._query(':TIM:XY:ENABle?').strip().upper()
            if resp in ('ON', '1'):
                return True
            if resp in ('OFF', '0'):
                return False
            return bool(int(float(resp)))
        except Exception:
            # Fallback para firmwares que só expõem :TIM:MODE?
            try:
                return self._query(':TIM:MODE?').strip().upper().startswith('XY')
            except Exception:
                return False

    def set_xy_enabled(self, enabled: bool) -> None:
        """Liga/desliga o modo X-Y no dialeto correto do equipamento.

        O DHO800/DHO900 tem ``:TIMebase:XY:ENABle``; o MSO5000 entra em X-Y
        por ``:TIMebase:MODE XY`` (o mesmo comando também existe no DHO).
        """
        if self._is_mso_family():
            self._write(f":TIM:MODE {'XY' if enabled else 'MAIN'}")
        else:
            self._write(f":TIM:XY:ENABle {'ON' if enabled else 'OFF'}")

    @staticmethod
    def _normalize_channel(name: str) -> str:
        """Normaliza CHANnel1/CHAN1 para CHAN1 (mantém MATH/D0 como estão)."""
        text = str(name).strip().upper()
        if text.startswith('CHAN'):
            digits = ''.join(c for c in text if c.isdigit())
            return f"CHAN{digits}" if digits else text
        return text

    @classmethod
    def _channel_number(cls, channel: str) -> str:
        """Extrai o número de um canal (CHAN1, CHANnel1 ou 1)."""
        digits = ''.join(c for c in str(channel) if c.isdigit())
        if not digits:
            raise ValueError(f"Invalid channel: {channel}")
        return digits

    def get_xy_sources(self) -> Tuple[Optional[str], Optional[str]]:
        """Consulta os canais usados como X e Y no display X-Y.

        No MSO5000 o modo X-Y é fixo em CH1 (X) e CH2 (Y); os comandos
        ``:TIMebase:XY:X/Y`` não existem nessa família. Consultá-los geraria
        timeout, então devolvemos o par documentado sem tocar no instrumento.
        """
        if self._is_mso_family():
            return 'CHAN1', 'CHAN2'

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

        No MSO5000 as fontes X/Y são fixas (CH1/CH2) e não há comando SCPI
        para alterá-las; nada é escrito nesse caso.

        Returns:
            True se houve mudança (o chamador deve rodar/parar para atualizar).
        """
        if self._is_mso_family():
            return False

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

    def _memory_depth(self) -> float:
        """Profundidade de memória atual em pontos (0.0 se indisponível)."""
        try:
            return float(self._query(':ACQ:MDEP?'))
        except Exception:
            return 0.0

    def configure_for_capture(self) -> None:
        """Ajusta o MSO5000 para entregar 10.000 pontos cobrindo a tela.

        No MSO, ``RAW`` lê o início da memória interna. Com a profundidade
        padrão (25 Mpts, por exemplo), 10.000 pontos são só alguns
        microssegundos da tela. Reduzindo a profundidade para 10k antes da
        aquisição, 10.000 pontos passam a cobrir toda a janela exibida — a
        mesma curva vista no display, com a resolução pedida.
        """
        if not self._is_mso_family():
            return
        if getattr(self, '_mso_mdepth_configured', False):
            return
        try:
            self._write(f':ACQ:MDEP {self.MSO_CAPTURE_MDEPTH}')
            time.sleep(0.2)
            self._mso_mdepth_configured = True
            print(f"MSO memory depth -> {self.MSO_CAPTURE_MDEPTH}")
        except Exception as e:
            print(f"MSO memory depth config error: {e}")

    def restore_acquisition_config(self) -> None:
        """Restaura a profundidade de memória do MSO ao padrão AUTO."""
        if not getattr(self, '_mso_mdepth_configured', False):
            return
        try:
            self._write(':ACQ:MDEP AUTO')
            print("MSO memory depth -> AUTO")
        except Exception as e:
            print(f"MSO memory depth restore error: {e}")
        finally:
            self._mso_mdepth_configured = False

    def _waveform_modes_for_capture(self) -> Tuple[str, ...]:
        """Ordem dos modos de waveform conforme a profundidade de memória.

        Se a memória tem mais pontos do que o bloco que lemos, ``RAW``
        cobriria só o começo da aquisição; nesse caso preferimos ``NORM``
        (dados da tela), que sempre representa a janela exibida. Com a
        memória reduzida a 10k (MSO configurado), ``RAW`` é preferido por
        entregar os 10.000 pontos.
        """
        depth = self._memory_depth()
        if depth <= 0:
            if self._is_mso_family():
                return ('NORM', 'MAX', 'RAW')
            return ('RAW', 'MAX', 'NORM')
        if depth > self.WAVEFORM_MAX_POINTS:
            return ('NORM', 'MAX', 'RAW')
        return ('RAW', 'MAX', 'NORM')

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
        
        ch_x = self._normalize_channel(ch_x)
        ch_y = self._normalize_channel(ch_y)

        try:
            # Garantir XY ativo (não desligar em nenhum momento)
            if keep_xy and not self.is_xy_enabled():
                self.set_xy_enabled(True)
                time.sleep(0.2)

            # Garantir que o display X-Y usa os mesmos canais que a captura
            sources_changed = False
            if keep_xy:
                try:
                    sources_changed = self.set_xy_sources(ch_x, ch_y)
                except Exception as e:
                    print(f"XY source sync error: {e}")

            # No MSO, reduz a profundidade de memória para 10k na primeira
            # captura, para que RAW entregue 10.000 pontos cobrindo a tela.
            reconfigure = False
            if self._is_mso_family() and not getattr(self, '_mso_mdepth_configured', False):
                self.configure_for_capture()
                reconfigure = True

            # Congelar aquisição para ler os dois canais do mesmo frame
            self.stop()
            if sources_changed or reconfigure:
                # Alterar X/Y (ou a profundidade) limpa o traço X-Y; uma
                # aquisição nova redesenha com a configuração atual.
                self.run()
                time.sleep(0.6 if reconfigure else 0.35)
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
            
            # Ler os dois canais com o mesmo modo (RAW > MAX; DHO também NORM)
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
                self.set_xy_enabled(True)
                time.sleep(0.2)
            
            return vx, vy
            
        except SocketTimeout:
            raise Exception(f"Capture timeout after {timeout_seconds}s")
        except Exception as e:
            # Um timeout de waveform pode deixar uma resposta binária
            # pendente; realinha o buffer antes da próxima captura.
            try:
                self._resync_pyusbtmc()
            except Exception:
                pass
            raise Exception(f"Capture error: {e}")
    
    def get_channel_scale(self, channel: str) -> float:
        """
        Obtém escala atual do canal
        
        Args:
            channel: Nome do canal (CHAN1, CHANnel1, 1...)
            
        Returns:
            Valor em Volts/divisão
        """
        digits = ''.join(c for c in str(channel) if c.isdigit())
        if not digits:
            print(f"get_scale error {channel}: invalid channel")
            return 1.0

        # DHO800/DHO900 e MSO5000 documentam :CHANnel<n>:SCALe? (a forma
        # curta :CHAN<n>:SCAL? é equivalente em SCPI). Uma única tentativa
        # evita somar timeouts quando o instrumento está ocupado.
        try:
            resp = self._query(f":CHANnel{digits}:SCALe?").strip()
            if resp:
                return float(resp)
        except Exception as e:
            print(f"get_scale error {channel}: {e}")
        return 1.0
    
    def get_channel_offset(self, channel: str) -> float:
        """
        Obtém offset atual do canal
        
        Args:
            channel: Nome do canal (CHAN1, CHANnel1, 1...)
            
        Returns:
            Valor em Volts
        """
        digits = ''.join(c for c in str(channel) if c.isdigit())
        if not digits:
            print(f"get_offset error {channel}: invalid channel")
            return 0.0

        try:
            resp = self._query(f":CHANnel{digits}:OFFSet?").strip()
            if resp:
                return float(resp)
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
            # Restaurar configurações temporárias (MSO: mem depth AUTO)
            self.restore_acquisition_config()
        except Exception:
            pass

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
            self._dispose_usbtmc()
        except Exception:
            pass
        
        self.inst = None
        self.sock = None
        self.usbtmc_file = None
        self.rm = None
        self.usbtmc_inst = None
        self.ip = None
        self.port = None
        self.connected = False


def _idn_serial(idn: str) -> str:
    """Extrai o número de série do campo 3 de uma resposta *IDN?."""
    parts = [p.strip() for p in (idn or '').split(',')]
    return parts[2] if len(parts) > 2 else ''


def discover_rigol() -> Tuple[Tuple[str, ...], Tuple[Tuple[str, str], ...]]:
    """
    Descobre dispositivos Rigol disponíveis.

    Cada instrumento físico aparece uma única vez no resultado: as diferentes
    formas de acessar o mesmo aparelho (PyUSBTMC, PyVISA USB, /dev/usbtmc) são
    agrupadas por vendor/product/serial.

    Returns:
        Tuple de (all_resources, rigol_resources)
        onde rigol_resources é uma lista de (resource, idn) tuples
    """
    all_resources = []
    rigol_resources = []
    seen = set()             # chaves físicas já adicionadas (vid:pid:serial)
    seen_resources = set()   # resource names já adicionados

    def device_key(vid: int, pid: int, serial: str) -> str:
        return f"{vid:04x}:{pid:04x}:{(serial or 'unknown').upper()}"

    def is_seen(vid: int, pid: int, serial: str) -> bool:
        """True se este instrumento (ou um sem serial conhecido) já foi achado."""
        prefix = f"{vid:04x}:{pid:04x}:"
        serial = (serial or '').upper()
        for key in seen:
            if not key.startswith(prefix):
                continue
            key_serial = key.split(':', 2)[2]
            if not serial or key_serial == 'UNKNOWN' or key_serial == serial:
                return True
        return False

    def add_rigol(resource: str, idn: str, vid: int, pid: int, serial: str) -> None:
        if resource in seen_resources or is_seen(vid, pid, serial):
            return
        serial = serial or _idn_serial(idn)
        seen.add(device_key(vid, pid, serial))
        seen_resources.add(resource)
        rigol_resources.append((resource, idn))
        print(f"[DISCOVER] Found Rigol: {resource} - {idn}")

    # 1. Listar dispositivos USB-TMC Rigol via PyUSBTMC (driver direto pyusb).
    # Não abrimos a interface USBTMC durante a descoberta: abrir/fechar duas
    # vezes (descoberta + connect) pode deixar o MSO5000 ocupado. Modelo e
    # serial vêm dos descritores USB, que não exigem claim da interface.
    if USBTMC_AVAILABLE:
        try:
            pyusbtmc_devices = list(PyUSBTMC.find_tmc_devices())
            for device in pyusbtmc_devices:
                vid, pid = device.idVendor, device.idProduct
                dev_id = f"PyUSBTMC::{vid:04x}:{pid:04x}"
                all_resources.append(dev_id)

                try:
                    serial = device.serial_number or ''
                except Exception:
                    serial = ''
                try:
                    product = device.product or ''
                except Exception:
                    product = ''
                try:
                    manufacturer = device.manufacturer or ''
                except Exception:
                    manufacturer = ''

                is_rigol = (
                    vid == 0x1AB1
                    or 'RIGOL' in manufacturer.upper()
                    or 'RIGOL' in product.upper()
                )
                if is_rigol:
                    # IDN sintético a partir dos descritores; o IDN real é
                    # confirmado no connect().
                    idn = (
                        f"RIGOL TECHNOLOGIES,{product},{serial},"
                        if product else ''
                    )
                    add_rigol(dev_id, idn, vid, pid, serial)
        except Exception as e:
            print(f"[DISCOVER] PyUSBTMC discovery error: {e}")

    # 2. Tentar PyVISA (USB0:: e TCPIP/LXI) - sempre tentar, independente de PyUSBTMC
    try:
        rm = _open_visa_resource_manager()
        visa_resources = rm.list_resources()
        all_resources.extend(visa_resources)

        # Detectar dispositivos USB via PyVISA (mesmo aparelho já visto via PyUSBTMC?)
        for res in visa_resources:
            if not res.startswith('USB0::'):
                continue
            try:
                parts = res.split('::')
                # pyvisa-py usa decimal (USB0::6833::1100::...) e o NI-VISA usa
                # hexadecimal (USB0::0x1AB1::0x044C::...) - aceitar os dois.
                vid = int(parts[1], 0)
                pid = int(parts[2], 0)
                serial = parts[3] if len(parts) > 3 else ''
            except Exception:
                continue

            if is_seen(vid, pid, serial):
                continue  # já listado via PyUSBTMC

            try:
                inst = rm.open_resource(res)
                inst.timeout = 5000
                idn = inst.query('*IDN?').strip()
                inst.close()
                if idn and 'RIGOL' in idn.upper():
                    add_rigol(res, idn, vid, pid, serial)
            except Exception as e:
                print(f"[DISCOVER] USB probe error {res}: {e}")
                if vid == 0x1AB1:
                    add_rigol(res, '', vid, pid, serial)

        # Detectar dispositivos TCP/IP via PyVISA
        for res in visa_resources:
            if 'TCPIP' in res and 'INSTR' in res:
                try:
                    inst = rm.open_resource(res)
                    inst.timeout = 5000
                    idn = inst.query('*IDN?').strip()

                    if idn and 'RIGOL' in idn.upper():
                        serial = _idn_serial(idn)
                        rigol_resources.append((res, idn))
                        seen_resources.add(res)
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
        resource = f"USB-TMC::{dev_path}"
        all_resources.append(resource)
        try:
            # Tentar conectar e ler IDN
            with open(dev_path, 'w+b', buffering=0) as f:
                f.write(b'*IDN?\n')
                f.flush()
                time.sleep(0.2)
                resp = f.read(512).decode('utf-8', errors='ignore').strip()
                if resp and 'RIGOL' in resp.upper():
                    # Sem vid/pid aqui: deduplicar pelo serial do IDN
                    serial = _idn_serial(resp)
                    duplicate = serial and any(
                        key.endswith(f":{serial.upper()}") for key in seen
                    )
                    if not duplicate and resource not in seen_resources:
                        seen_resources.add(resource)
                        rigol_resources.append((resource, resp))
                        print(f"[DISCOVER] Found Rigol via /dev/usbtmc: {dev_path}")
        except Exception as e:
            print(f"[DISCOVER] USB-TMC probe error {dev_path}: {e}")

    return tuple(all_resources), tuple(rigol_resources)


#: Porta TCP usada pelos instrumentos Rigol (SCPI raw socket).
RIGOL_TCP_PORTS = (5555,)

#: Limites para a varredura automática (mantém a GUI responsiva mesmo em /16).
_MAX_SCAN_HOSTS = 1024
_SCAN_WORKERS = 128


def _is_virtual_interface(name: str) -> bool:
    """Diz se a interface é virtual (docker, VPN, bridge...) e deve ser ignorada."""
    name = (name or '').lower()
    if name in ('lo', 'loopback'):
        return True
    virtual = (
        'docker', 'veth', 'virbr', 'br-', 'vmnet', 'vboxnet', 'tun', 'tap',
        'zt', 'wg', 'tailscale', 'ham', 'dummy',
    )
    return name.startswith(virtual)


def _local_ipv4_networks() -> List[ipaddress.IPv4Network]:
    """Lista as redes IPv4 das interfaces físicas ativas.

    No Windows e no Linux o ``psutil`` fornece endereço + máscara. Interfaces
    virtuais (Docker, VPN, bridges) são descartadas para não varrer redes que
    não têm o osciloscópio. Se o psutil não estiver disponível ou não houver
    interface física, cai para a rota padrão.
    """
    try:
        import psutil
    except Exception:
        return _fallback_local_network()

    try:
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
    except Exception:
        return _fallback_local_network()

    networks: List[ipaddress.IPv4Network] = []
    for interface, entries in addrs.items():
        info = stats.get(interface)
        if info is not None and not info.isup:
            continue
        if _is_virtual_interface(interface):
            continue
        for entry in entries:
            if entry.family != socket.AF_INET:
                continue
            address = (entry.address or '').strip()
            netmask = (entry.netmask or '').strip()
            if not address or not netmask or address.startswith('127.'):
                continue
            try:
                network = ipaddress.ip_network(
                    f"{address}/{netmask}", strict=False
                )
            except ValueError:
                continue
            if network.is_loopback or network.is_link_local:
                continue
            if network not in networks:
                networks.append(network)

    return networks or _fallback_local_network()


def _fallback_local_network() -> List[ipaddress.IPv4Network]:
    """Descobre a rede local pela rota padrão (usado sem psutil)."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Não envia pacotes: só faz o SO escolher a interface de saída.
        probe.connect(('8.8.8.8', 80))
        address = probe.getsockname()[0]
    except Exception:
        return []
    finally:
        try:
            probe.close()
        except Exception:
            pass
    if not address or address.startswith('127.'):
        return []
    
    try:
        # Usar ip route para obter a rede correta
        import subprocess
        try:
            # Obter a rota padrão e a máscara de sub-rede
            result = subprocess.run(
                ['ip', '-o', 'route', 'show', 'default'],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0 and result.stdout.strip():
                # Exemplo de saída:
                # "default via 192.168.68.1 dev wlp11s0 src 192.168.68.107 metric 600"
                line = result.stdout.strip()
                
                # Se tiver "src" na saída, obter a rede a partir do ip addr
                if 'src' in line:
                    # Extrair a interface de saída
                    parts = line.split()
                    interface = None
                    for i, part in enumerate(parts):
                        if part == 'dev':
                            interface = parts[i+1] if i+1 < len(parts) else None
                            break
                    
                    if interface:
                        # Obter o IP e máscara da interface específica
                        addr_result = subprocess.run(
                            ['ip', '-o', 'addr', 'show', interface],
                            capture_output=True, text=True, timeout=2
                        )
                        if addr_result.returncode == 0:
                            # Exemplo: "2: wlp11s0    inet 192.168.68.107/22 scope global dynamic"
                            for line in addr_result.stdout.split('\n'):
                                if 'inet ' in line:
                                    parts = line.split()
                                    for part in parts:
                                        if '/' in part and part != 'inet':
                                            # part é no formato IP/máscara (ex: 192.168.68.107/22)
                                            try:
                                                net = ipaddress.ip_network(part, strict=False)
                                                if not net.is_loopback:
                                                    return [net]
                                            except ValueError:
                                                pass
                
                # Fallback: extrair a rede baseada no gateway
                parts = line.split()
                gateway = None
                for i, part in enumerate(parts):
                    if part == 'via' and i+1 < len(parts):
                        gateway = parts[i+1]
                        break
                
                if gateway:
                    # Se tem gateway, construir uma rede /24 baseada no IP atual
                    # Isso funciona para a maioria dos casos domésticos
                    octets = address.rsplit('.', 1)[0]
                    # Usar /24 como fallback padrão
                    net = ipaddress.ip_network(f"{octets}.0/24", strict=False)
                    return [net]
        except Exception:
            pass  # Falha ao usar ip route, usar método alternativo
        
        # Último fallback: /24 baseado no IP atual
        octets = address.rsplit('.', 1)[0]
        return [ipaddress.ip_network(f"{octets}.0/24", strict=False)]
    except ValueError:
        return []


def _scan_hosts(subnets=None, max_hosts: int = _MAX_SCAN_HOSTS) -> List[str]:
    """Monta a lista de IPs a verificar.

    ``subnets`` mantém a compatibilidade com o formato antigo (prefixos como
    ``'192.168.1.'``). Sem ele, as redes são derivadas das interfaces locais.
    """
    hosts: List[str] = []
    if subnets:
        for subnet in subnets:
            prefix = str(subnet).strip()
            if not prefix:
                continue
            base = prefix if prefix.endswith('.') else prefix + '.'
            hosts.extend(f"{base}{i}" for i in range(1, 255))
    else:
        for network in _local_ipv4_networks():
            try:
                hosts.extend(str(host) for host in network.hosts())
            except (ValueError, TypeError):
                continue

    unique: List[str] = []
    seen = set()
    for host in hosts:
        if host not in seen:
            seen.add(host)
            unique.append(host)
    return unique[:max_hosts]


def _probe_rigol_socket(ip: str, port: int, timeout: float = 0.3) -> Optional[str]:
    """Abre um socket curto e devolve o *IDN?* quando o aparelho é Rigol."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        if sock.connect_ex((ip, port)) != 0:
            return None
        sock.settimeout(max(timeout, 0.5))
        sock.sendall(f"{CMD_IDN}\n".encode('ascii'))
        response = sock.recv(512).decode('utf-8', errors='ignore').strip()
        if response and 'RIGOL' in response.upper():
            return response
        return None
    except OSError:
        return None
    finally:
        try:
            sock.close()
        except OSError:
            pass


def discover_rigol_network(
    subnets=None,
    timeout: float = 0.3,
    ports: Optional[Iterable[int]] = None,
    max_hosts: int = _MAX_SCAN_HOSTS,
    stop_event=None,
) -> List[Dict[str, Any]]:
    """Descobre osciloscópios Rigol na rede local.

    A varredura é paralela e usa apenas as redes das interfaces físicas — não
    os prefixos fixos antigos, que podiam levar minutos e nunca incluíam a
    sub-rede real. Retorna uma lista de dicionários::

        {'ip': '192.168.68.104', 'port': 5555, 'idn': 'RIGOL TECHNOLOGIES,...',
         'resource': 'TCPIP::192.168.68.104::5555::SOCKET'}

    ``stop_event`` permite interromper a varredura ao fechar a janela.
    """
    if ports is None:
        ports = RIGOL_TCP_PORTS
    ports = tuple(dict.fromkeys(int(port) for port in ports))

    hosts = _scan_hosts(subnets, max_hosts)
    if not hosts:
        print("[DISCOVER] Nenhuma rede local para varrer")
        return []

    targets = [(ip, port) for ip in hosts for port in ports]
    print(
        f"[DISCOVER] Varrendo {len(hosts)} host(s) em {len(ports)} porta(s) "
        f"({', '.join(str(p) for p in ports)})"
    )

    found: List[Dict[str, Any]] = []
    workers = min(_SCAN_WORKERS, max(1, len(targets)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_probe_rigol_socket, ip, port, timeout): (ip, port)
            for ip, port in targets
        }
        for future in as_completed(futures):
            if stop_event is not None and stop_event.is_set():
                for pending in futures:
                    pending.cancel()
                break
            ip, port = futures[future]
            try:
                idn = future.result()
            except Exception:
                idn = None
            if not idn:
                continue
            item = {
                'ip': ip,
                'port': port,
                'idn': idn,
                'resource': f'TCPIP::{ip}::{port}::SOCKET',
            }
            found.append(item)
            print(f"[DISCOVER] Found {idn} at {ip}:{port}")

    found.sort(key=lambda item: (ipaddress.ip_address(item['ip']), item['port']))
    return found
