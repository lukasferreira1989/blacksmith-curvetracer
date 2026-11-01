#!/usr/bin/env python3
"""
Blacksmith CurveTracer - Rigol DHO800/DHO900 and MSO5000 Oscilloscope X-Y Mode
Analog Curve Tracer Interface

Refatorado para focar exclusivamente em:
- PC Host (Python) + PyVISA / PyUSBTMC / socket
- Rigol DHO800/DHO900 e MSO5000
- Analog Curve Tracer (gerador de curvas V-I)
"""

import sys
import os
import json
import csv
import socket
import threading
from datetime import datetime

import pyvisa

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                              QHBoxLayout, QPushButton, QLabel, QComboBox,
                              QSpinBox, QDoubleSpinBox, QGroupBox, QTabWidget,
                              QCheckBox, QLineEdit, QTextEdit, QGridLayout,
                              QFrame, QFileDialog, QMessageBox, QSplitter)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import numpy as np

# Tenta importar PyUSBTMC para descoberta de dispositivos
try:
    import PyUSBTMC
    HAS_USB_TMC = True
except Exception:
    HAS_USB_TMC = False

try:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from scope_xy import (
            RigolScopeXY, discover_rigol, discover_rigol_network,
            compute_channel_screen_range, _parse_tcpip_resource,
        )
        HAS_SCOPE_XY = True
    except Exception as e:
        from src.scope_xy import (
            RigolScopeXY, discover_rigol, discover_rigol_network,
            compute_channel_screen_range, _parse_tcpip_resource,
        )
        HAS_SCOPE_XY = True
except Exception as e:
    HAS_SCOPE_XY = False
    print(f"scope_xy not available: {e}")

try:
    try:
        from component_gui import ComponentManagerDialog
    except Exception:
        from src.component_gui import ComponentManagerDialog
    HAS_COMPONENT_GUI = True
except Exception as e:
    HAS_COMPONENT_GUI = False
    print(f"component module not available: {e}")


class CaptureWorker(QThread):
    """Executa uma captura única fora da thread da GUI.

    ``job_fn`` roda inteiramente nesta thread e devolve o payload já calculado
    (dados, geometria e estado do osciloscópio), para que a GUI só desenhe.
    """

    capture_done = pyqtSignal(object)
    capture_failed = pyqtSignal(str)

    def __init__(self, job_fn, parent=None):
        super().__init__(parent)
        self._job_fn = job_fn

    def run(self):
        try:
            self.capture_done.emit(self._job_fn())
        except Exception as e:
            self.capture_failed.emit(str(e))


class RealtimeWorker(QThread):
    """Executa as capturas do modo Real-time fora da thread da GUI.

    Todas as chamadas ao osciloscópio ficam nesta thread, então a interface
    continua respondendo mesmo quando uma captura demora (transferência de
    waveform, timeout do VISA, etc.).
    """

    frame_ready = pyqtSignal(object)
    capture_failed = pyqtSignal(str)

    def __init__(self, capture_fn, geometry_fn, interval_s, parent=None):
        super().__init__(parent)
        self._capture_fn = capture_fn
        self._geometry_fn = geometry_fn
        self._interval = max(0.05, float(interval_s))
        self._stop_event = threading.Event()

    def stop(self):
        """Pede o encerramento; a captura em andamento termina sozinha."""
        self._stop_event.set()

    def run(self):
        while not self._stop_event.is_set():
            try:
                vx, vy = self._capture_fn()
                try:
                    geom = self._geometry_fn()
                except Exception:
                    geom = None
                self.frame_ready.emit({'vx': vx, 'vy': vy, 'geom': geom})
            except Exception as e:
                self.capture_failed.emit(str(e))
            # Espera interrompível: o STOP não precisa aguardar o intervalo todo
            if self._stop_event.wait(self._interval):
                break


class CurveTracerMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Blacksmith CurveTracer - Rigol DHO/MSO")
        self.setGeometry(50, 50, 1400, 900)
        
        self.scope_xy = None
        self.connected = False
        self._capture_worker = None
        self._pending_capture_done = None
        self._pending_capture_errors = True
        self._rt_worker = None
        self._rt_interval = 0.0
        self._rt_error = False
        self.last_data = None  # (vx, vy)
        self._view_state = "empty"  # empty | grid | data
        self._plot_units = ("V", "V")
        self._cursor_vline = None
        self._cursor_hline = None
        self._cursor_marker = None
        self._cursor_annot = None
        self._components_dialog = None

        self.initUI()
        self.connect_signals()
        self.show_placeholder()
        try:
            import os as _os
            if not (_os.environ.get('CURVETRACER_SKIP_DISCOVERY') or _os.environ.get('CURVETRACER_NO_DISCOVERY')):
                self.refresh_resources()
        except Exception:
            self.refresh_resources()
    
    def initUI(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        
        # Painel esquerdo - Configurações
        left_panel = self.create_left_panel()
        main_layout.addWidget(left_panel)
        
        # Painel direito - Gráfico e controles
        right_panel = self.create_right_panel()
        main_layout.addWidget(right_panel)
    
    def connect_signals(self):
        self.connect_btn.clicked.connect(self.on_connect)
        self.capture_btn.clicked.connect(self.on_capture)
        self.save_setup_btn.clicked.connect(self.on_save_setup)
        self.load_setup_btn.clicked.connect(self.on_load_setup)
        self.save_data_btn.clicked.connect(self.on_save_data)
        self.load_data_btn.clicked.connect(self.on_load_data)
        self.print_screen_btn.clicked.connect(self.on_print_screen)
        self.refresh_btn.clicked.connect(self.refresh_resources)
        self.components_btn.clicked.connect(self.on_open_components)
        self.cursor_combo.currentTextChanged.connect(self.on_cursor_mode_changed)
        self.canvas.mpl_connect('motion_notify_event', self.on_mouse_move)
        self.canvas.mpl_connect('button_press_event', self.on_mouse_click)

        # Conectado e sem captura: manter a grade fiel ao canal/escala atual
        self.ch_x_combo.currentTextChanged.connect(self._refresh_grid_if_idle)
        self.ch_y_combo.currentTextChanged.connect(self._refresh_grid_if_idle)
        self.shunt_spin.valueChanged.connect(self._on_shunt_changed)
        self.mem_depth_combo.currentTextChanged.connect(self._on_mem_depth_changed)
    
    def closeEvent(self, event):
        """Handle window close event to properly disconnect scope"""
        worker = self._rt_worker
        if worker is not None:
            worker.stop()
            if not worker.wait(10000):
                print("Real-time worker did not finish in time")
            self._rt_worker = None
        capture_worker = self._capture_worker
        if capture_worker is not None:
            if not capture_worker.wait(10000):
                print("Capture worker did not finish in time")
            self._capture_worker = None
        if self.connected and self.scope_xy:
            try:
                close = getattr(self.scope_xy, "close", None)
                if callable(close):
                    close()
            except Exception as e:
                print(f"Error closing scope on exit: {e}")
            finally:
                self.scope_xy = None
                self.connected = False
        event.accept()
    
    def create_left_panel(self):
        panel = QWidget()
        panel.setMaximumWidth(400)
        panel.setMinimumWidth(350)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(2, 2, 2, 2)
        
        # Setup load/save
        setup_layout = QHBoxLayout()
        self.save_setup_btn = QPushButton("SAVE Setup")
        self.load_setup_btn = QPushButton("LOAD Setup")
        setup_layout.addWidget(self.save_setup_btn)
        setup_layout.addWidget(self.load_setup_btn)
        layout.addLayout(setup_layout)
        
        # Group: Oscilloscope Configuration
        osc_group = QGroupBox("Oscilloscope Configuration")
        osc_layout = QGridLayout(osc_group)
        
        osc_layout.addWidget(QLabel("CH X (Voltage)"), 0, 0)
        self.ch_x_combo = QComboBox()
        self.ch_x_combo.addItems(["CHAN1", "CHAN2"])
        self.ch_x_combo.setCurrentText("CHAN1")
        osc_layout.addWidget(self.ch_x_combo, 0, 1)
        
        osc_layout.addWidget(QLabel("CH Y (Current)"), 1, 0)
        self.ch_y_combo = QComboBox()
        self.ch_y_combo.addItems(["CHAN1", "CHAN2"])
        self.ch_y_combo.setCurrentText("CHAN2")
        osc_layout.addWidget(self.ch_y_combo, 1, 1)
        
        osc_layout.addWidget(QLabel("Probe X"), 2, 0)
        self.probe_x_spin = QDoubleSpinBox()
        self.probe_x_spin.setValue(1.0)
        self.probe_x_spin.setRange(0.001, 10000)
        self.probe_x_spin.setDecimals(3)
        osc_layout.addWidget(self.probe_x_spin, 2, 1)
        
        osc_layout.addWidget(QLabel("Probe Y"), 3, 0)
        self.probe_y_spin = QDoubleSpinBox()
        self.probe_y_spin.setValue(1.0)
        self.probe_y_spin.setRange(0.001, 10000)
        self.probe_y_spin.setDecimals(3)
        osc_layout.addWidget(self.probe_y_spin, 3, 1)
        
        osc_layout.addWidget(QLabel("Y is Direct Current"), 4, 0)
        self.y_direct_check = QCheckBox()
        self.y_direct_check.setChecked(True)
        osc_layout.addWidget(self.y_direct_check, 4, 1)
        
        osc_layout.addWidget(QLabel("Shunt R (Ω)"), 5, 0)
        self.shunt_spin = QDoubleSpinBox()
        self.shunt_spin.setRange(0.0, 1000000)  # 0 = sem shunt (não converter)
        self.shunt_spin.setValue(0.0)
        self.shunt_spin.setDecimals(6)
        self.shunt_spin.setSpecialValueText("None")
        self.shunt_spin.setToolTip(
            "0 = Y em volts. Com R > 0, a corrente é I = V/R na próxima captura."
        )
        osc_layout.addWidget(self.shunt_spin, 5, 1)
        
        osc_layout.addWidget(QLabel("Invert Y"), 6, 0)
        self.invert_y_check = QCheckBox()
        self.invert_y_check.setChecked(False)
        osc_layout.addWidget(self.invert_y_check, 6, 1)
        
        layout.addWidget(osc_group)
        
        # Group: Acquisition Settings
        acq_group = QGroupBox("Acquisition Settings")
        acq_layout = QGridLayout(acq_group)
        
        acq_layout.addWidget(QLabel("Update Mode"), 0, 0)
        self.update_mode_combo = QComboBox()
        self.update_mode_combo.addItems(["Single Capture", "Real-time"])
        self.update_mode_combo.setCurrentText("Single Capture")
        acq_layout.addWidget(self.update_mode_combo, 0, 1)
        
        acq_layout.addWidget(QLabel("Update Rate"), 1, 0)
        self.update_rate_spin = QDoubleSpinBox()
        self.update_rate_spin.setValue(5.0)
        self.update_rate_spin.setRange(0.1, 10.0)
        self.update_rate_spin.setDecimals(1)
        self.update_rate_spin.setSuffix(" s")
        acq_layout.addWidget(self.update_rate_spin, 1, 1)
        
        acq_layout.addWidget(QLabel("Update:"), 2, 0)
        self.update_label = QLabel("N/A")
        acq_layout.addWidget(self.update_label, 2, 1)

        acq_layout.addWidget(QLabel("Mem Depth"), 3, 0)
        self.mem_depth_combo = QComboBox()
        self.mem_depth_combo.addItems([
            "Auto", "1k", "10k", "100k", "1M", "5M", "10M",
            "25M", "50M", "100M", "200M",
        ])
        self.mem_depth_combo.setCurrentText("Auto")
        self.mem_depth_combo.setToolTip(
            "Profundidade de memória do osciloscópio. Auto usa o padrão do "
            "instrumento; valores explícitos até 1M são lidos em RAW."
        )
        acq_layout.addWidget(self.mem_depth_combo, 3, 1)
        
        layout.addWidget(acq_group)
        
        layout.addStretch()
        return panel
    
    def create_right_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(2, 2, 2, 2)
        
        # Operation control area
        op_layout = QHBoxLayout()
        op_layout.addWidget(QLabel("Resource:"))
        self.resource_combo = QComboBox()
        self.resource_combo.setEditable(True)
        self.resource_combo.setToolTip(
            "Select a discovered device or type a VISA/socket resource"
        )
        op_layout.addWidget(self.resource_combo)
        self.refresh_btn = QPushButton("Refresh")
        op_layout.addWidget(self.refresh_btn)
        self.connect_btn = QPushButton("CONNECT")
        op_layout.addWidget(self.connect_btn)
        self.capture_btn = QPushButton("CAPTURE")
        op_layout.addWidget(self.capture_btn)
        
        self.components_btn = QPushButton("COMPONENTS")
        self.components_btn.setToolTip(
            "Register components, pin maps and saved V-I captures; compare "
            "a saved reference with the current capture"
        )
        op_layout.addWidget(self.components_btn)
        op_layout.addStretch()
        layout.addLayout(op_layout)
        
        # Group: Status
        status_group = QGroupBox("Status")
        status_layout = QHBoxLayout(status_group)
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: green;")
        status_layout.addWidget(self.status_label)
        layout.addWidget(status_group)
        
        # Graph area
        graph_widget = QWidget()
        graph_layout = QVBoxLayout(graph_widget)
        
        # Graph controls
        graph_ctrl_layout = QHBoxLayout()
        graph_ctrl_layout.addWidget(QLabel("Grid"))
        self.grid_check = QCheckBox()
        self.grid_check.setChecked(True)
        self.grid_check.toggled.connect(lambda checked: self.ax.grid(checked) or self.canvas.draw())
        graph_ctrl_layout.addWidget(self.grid_check)
        
        graph_ctrl_layout.addWidget(QLabel("Cursor"))
        self.cursor_combo = QComboBox()
        self.cursor_combo.addItems(["Off", "Free", "Single-Plot"])
        graph_ctrl_layout.addWidget(self.cursor_combo)
        
        graph_ctrl_layout.addStretch()
        
        # Report features
        self.save_data_btn = QPushButton("SAVE Data")
        self.load_data_btn = QPushButton("LOAD Data")
        self.print_screen_btn = QPushButton("PRINT Screen")
        graph_ctrl_layout.addWidget(self.save_data_btn)
        graph_ctrl_layout.addWidget(self.load_data_btn)
        graph_ctrl_layout.addWidget(self.print_screen_btn)
        
        graph_layout.addLayout(graph_ctrl_layout)
        
        self.figure = Figure(figsize=(10, 7))
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_xlabel('Voltage (V)')
        self.ax.set_ylabel('Current (A)')
        self.ax.grid(True)
        self.ax.set_title('I-V Curve - Curve Tracer')
        self._placeholder_text = self.figure.text(
            0.5, 0.5,
            "No data\nConnect to the oscilloscope and capture",
            ha='center', va='center', fontsize=12, color='#777777',
        )
        
        # coordinates=False remove o rótulo "(x, y) = (, )" no canto do
        # toolbar; a leitura de coordenadas é feita pelo cursor da GUI.
        self.toolbar = NavigationToolbar(self.canvas, graph_widget, coordinates=False)
        graph_layout.addWidget(self.toolbar)
        graph_layout.addWidget(self.canvas)
        
        layout.addWidget(graph_widget)
        
        # Info area
        info_group = QGroupBox("Info")
        info_layout = QVBoxLayout(info_group)
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMaximumHeight(80)
        self.info_text.setText("CH1: Voltage (X)\nCH2: Current via Shunt (Y)")
        info_layout.addWidget(self.info_text)
        layout.addWidget(info_group)
        
        return panel
    
    def refresh_resources(self):
        """Atualiza lista de recursos VISA disponíveis e preenche o combo box"""
        import os as _os
        if _os.environ.get('CURVETRACER_SKIP_DISCOVERY') or _os.environ.get('CURVETRACER_NO_DISCOVERY'):
            self.status_label.setText("Discovery skipped")
            self.status_label.setStyleSheet("color: gray;")
            return
        if not HAS_SCOPE_XY:
            self.status_label.setText("PyVISA not available")
            self.status_label.setStyleSheet("color: red;")
            return
        
        try:
            # Limpar combo box
            self.resource_combo.clear()
            
            # Primeiro, buscar dispositivos USB/via VISA
            all_res, rigol_usb_res = discover_rigol()
            
            # Depois, buscar dispositivos na rede TCP/IP
            rigol_net_res = discover_rigol_network()
            
            # Combinar todos os dispositivos ( USB da descoberta VISA + TCP/IP da descoberta de rede)
            all_rigol_res = []
            
            # Adicionar dispositivos USB ao combo box e à lista combinada
            for resource, idn in rigol_usb_res:
                # Tipo de conexão
                if 'PyUSBTMC' in resource or 'USB-TMC' in resource:
                    transport = 'USB-TMC'
                elif resource.startswith('USB0::'):
                    transport = 'USB (VISA)'
                else:
                    transport = 'USB'
                
                # Mostrar modelo e serial do IDN, quando disponível
                model = serial = ''
                if idn:
                    parts = [p.strip() for p in idn.split(',')]
                    if len(parts) > 1:
                        model = parts[1]
                    if len(parts) > 2:
                        serial = parts[2]
                
                name = model or 'Rigol'
                if serial:
                    display = f"{name} ({serial}) - {transport}"
                else:
                    display = f"{name} - {transport}"
                
                self.resource_combo.addItem(display, userData=resource)
                all_rigol_res.append((resource, idn))
            
            # Adicionar dispositivos de rede ao combo
            for device in rigol_net_res:
                ip = device.get('ip', 'unknown')
                port = device.get('port', 5555)
                idn = device.get('idn', '')
                resource = device.get('resource', f'TCPIP::{ip}::{port}::SOCKET')
                
                # Tentar extrair info do IDN
                model = serial = ''
                if idn:
                    parts = [p.strip() for p in idn.split(',')]
                    if len(parts) > 1:
                        model = parts[1]
                    if len(parts) > 2:
                        serial = parts[2]
                
                name = model or 'Rigol'
                if serial:
                    display = f"{name} ({serial}) - TCP/IP ({ip})"
                else:
                    display = f"{name} - TCP/IP ({ip})"
                
                self.resource_combo.addItem(display, userData=resource)
                all_rigol_res.append((resource, idn))
            
            if all_rigol_res:
                self.status_label.setText(f"Found {len(all_rigol_res)} Rigol device(s)")
                self.status_label.setStyleSheet("color: green;")
                
                # Selecionar o primeiro item por padrão
                if self.resource_combo.count() > 0:
                    self.resource_combo.setCurrentIndex(0)
            else:
                self.status_label.setText("No Rigol devices found")
                self.status_label.setStyleSheet("color: orange;")
                   
        except Exception as e:
            self.status_label.setText(f"Discovery error: {e}")
            self.status_label.setStyleSheet("color: red;")
    
    def _populate_memory_depths(self) -> None:
        """Ajusta a lista de memórias disponíveis conforme a família."""
        mso_depths = ["Auto", "1k", "10k", "100k", "1M", "10M",
                      "25M", "50M", "100M", "200M"]
        dho_depths = ["Auto", "1k", "10k", "100k", "1M", "5M", "10M"]
        try:
            is_mso = self.scope_xy._is_mso_family()
        except Exception:
            is_mso = False
        depths = mso_depths if is_mso else dho_depths
        current = self.mem_depth_combo.currentText()
        self.mem_depth_combo.blockSignals(True)
        self.mem_depth_combo.clear()
        self.mem_depth_combo.addItems(depths)
        index = self.mem_depth_combo.findText(current)
        self.mem_depth_combo.setCurrentIndex(index if index >= 0 else 0)
        self.mem_depth_combo.blockSignals(False)

    def _apply_memory_depth(self) -> None:
        """Aplica a profundidade selecionada ao instrumento conectado."""
        if not (self.connected and self.scope_xy):
            return
        value = self.mem_depth_combo.currentText()
        try:
            self.scope_xy.set_memory_depth(value)
        except Exception as e:
            print(f"Memory depth apply error: {e}")

    def _on_mem_depth_changed(self, *args) -> None:
        if self.connected and self._rt_worker is None and self._capture_worker is None:
            self._apply_memory_depth()

    def on_connect(self):
        """Conecta ou desconecta do osciloscópio"""
        if self.connected:
            # Desconectar
            try:
                if self.scope_xy:
                    self.scope_xy.close()
                self.scope_xy = None
            except Exception as e:
                print(f"Disconnect error: {e}")
            
            self.connected = False
            self.connect_btn.setText("CONNECT")
            self.status_label.setText("Disconnected")
            self.status_label.setStyleSheet("color: red;")
            self.show_placeholder(clear_data=True)
            return
        
        # Obter resource selecionado no combo box
        selected_idx = self.resource_combo.currentIndex()
        if selected_idx < 0:
            self.status_label.setText("No device selected")
            self.status_label.setStyleSheet("color: orange;")
            return
        
        resource = (self.resource_combo.currentData()
                    or self.resource_combo.currentText().strip())
        if not resource:
            self.status_label.setText("No device selected")
            self.status_label.setStyleSheet("color: orange;")
            return
        
        try:
            self.scope_xy = RigolScopeXY(resource)
            self.connected = True
            self.connect_btn.setText("DISCONNECT")
            # O IDN já foi lido durante connect(); reutilizar evita uma
            # segunda query (e um possível timeout em USB instável).
            idn = getattr(self.scope_xy, 'idn', '') or self.scope_xy.get_idn()
            self.status_label.setText(f"Connected: {idn}")
            self.status_label.setStyleSheet("color: green;")

            # Memória: padrão Auto, com opções explícitas na GUI.
            self._populate_memory_depths()
            self._apply_memory_depth()

            # Sincroniza os seletores da GUI com os canais X/Y configurados
            # no próprio osciloscópio (:TIMebase:XY:X/Y).
            try:
                xy_x, xy_y = self.scope_xy.get_xy_sources()
                if xy_x:
                    self.ch_x_combo.setCurrentText(xy_x)
                if xy_y:
                    self.ch_y_combo.setCurrentText(xy_y)
            except Exception as e:
                print(f"XY source query failed: {e}")

            # Conectado, mas ainda sem captura: mostra somente a grade 8x8
            # com a escala/centro atuais do instrumento (sem traço).
            self.show_scope_grid()
        except Exception as e:
            self.status_label.setText(str(e))
            self.status_label.setStyleSheet("color: red;")
            QMessageBox.critical(self, "Connection Error", str(e))

    def on_capture(self):
        """Botão CAPTURE: captura única ou inicia/para o modo Real-time."""
        # Com o tempo real rodando, o botão sempre para — independentemente de
        # o combo Update Mode ter sido alterado no meio da execução.
        if self._rt_worker is not None:
            self.stop_realtime()
            return
        if self.update_mode_combo.currentText() == "Real-time":
            self.start_realtime()
            return
        self.capture_single()

    def capture_single(self, on_done=None) -> bool:
        """Executa uma única captura e atualiza a GUI (com diálogos de erro)."""
        return self._capture_single(show_errors=True, on_done=on_done)

    def _capture_single(self, show_errors: bool = True, on_done=None) -> bool:
        """Inicia uma captura única em thread separada.

        Retorna ``True`` se a captura foi iniciada. Ao terminar, a GUI é
        atualizada e ``on_done(success)`` é chamado na thread da GUI. É usado
        pelo botão CAPTURE e pela janela de componentes (CAPTURE Now + SAVE /
        CAPTURE + COMPARE), independentemente do modo de atualização
        selecionado. Com ``show_errors=False`` quem chamou mostra o erro.
        """
        if not self.connected or not self.scope_xy:
            self.status_label.setText("Not connected to oscilloscope")
            self.status_label.setStyleSheet("color: red;")
            if show_errors:
                QMessageBox.warning(self, "Error", "Not connected to oscilloscope")
            return False

        if self._rt_worker is not None:
            # Nunca capturar na thread da GUI com o worker usando o mesmo
            # recurso VISA: isso trava o programa.
            self.status_label.setText("Real-time running - stop it first")
            self.status_label.setStyleSheet("color: orange;")
            return False

        if self._capture_worker is not None:
            self.status_label.setText("Capture already in progress")
            self.status_label.setStyleSheet("color: orange;")
            return False

        # Snapshot das configurações: widgets só podem ser lidos na thread da GUI
        ch_x = self.ch_x_combo.currentText()
        ch_y = self.ch_y_combo.currentText()
        probe_x = self.probe_x_spin.value()
        probe_y = self.probe_y_spin.value()
        y_direct = self.y_direct_check.isChecked()
        shunt_val = self.shunt_spin.value()
        shunt = shunt_val if shunt_val > 0 else None
        invert = self.invert_y_check.isChecked()
        scope = self.scope_xy

        def job():
            # Toda a conversa com o instrumento acontece nesta thread
            vx, vy = scope.capture_xy(
                ch_x=ch_x, ch_y=ch_y,
                probe_x=probe_x, probe_y=probe_y,
                y_is_direct_current=y_direct,
                shunt_r=shunt,
                invert_y=invert,
                keep_xy=True,
                resume_after=True,
            )
            try:
                geom = self._query_geometry(ch_x, ch_y, shunt_val)
            except Exception:
                geom = None
            return {
                'vx': vx,
                'vy': vy,
                'geom': geom,
                'mode': getattr(scope, 'last_waveform_mode', 'N/A'),
                'xy_on': scope.is_xy_enabled(),
            }

        worker = CaptureWorker(job, parent=self)
        worker.capture_done.connect(self._on_capture_done)
        worker.capture_failed.connect(self._on_capture_failed)

        self._capture_worker = worker
        self._pending_capture_done = on_done
        self._pending_capture_errors = show_errors

        self.capture_btn.setEnabled(False)
        self._set_scope_controls(False)
        self.status_label.setText("Capturing...")
        self.status_label.setStyleSheet("color: black;")
        worker.start()
        return True

    def _finish_capture_job(self):
        """Libera o worker de captura única e devolve o controle à GUI."""
        worker = self._capture_worker
        self._capture_worker = None
        if worker is not None:
            worker.deleteLater()
        self.capture_btn.setEnabled(True)
        self._set_scope_controls(True)
        callback = self._pending_capture_done
        self._pending_capture_done = None
        return callback

    def _on_capture_done(self, payload) -> None:
        """Recebe o frame capturado na thread de trabalho e atualiza a GUI."""
        show_errors = self._pending_capture_errors
        callback = self._finish_capture_job()

        vx = payload.get('vx') if payload else None
        vy = payload.get('vy') if payload else None

        if vx is None or vy is None or len(vx) == 0 or len(vy) == 0:
            self.status_label.setText("Capture failed - no data")
            self.status_label.setStyleSheet("color: red;")
            if show_errors:
                QMessageBox.warning(self, "Error", "Capture failed - no data")
            if callable(callback):
                callback(False)
            return

        self.plot_curve(vx, vy, geom=payload.get('geom'))
        self.last_data = (vx, vy)
        xy_msg = "X-Y ON" if payload.get('xy_on') else "X-Y OFF"
        self.status_label.setText(
            f"Captured {len(vx)} points ({payload.get('mode')}) "
            f"- scope running, {xy_msg}"
        )
        self.status_label.setStyleSheet("color: green;")
        if callable(callback):
            callback(True)

    def _on_capture_failed(self, message: str) -> None:
        """Trata falha de captura única."""
        show_errors = self._pending_capture_errors
        callback = self._finish_capture_job()
        self.status_label.setText(f"Capture error: {message}")
        self.status_label.setStyleSheet("color: red;")
        if show_errors:
            QMessageBox.critical(self, "Capture Error", message)
        if callable(callback):
            callback(False)
    

    def start_realtime(self):
        """Inicia a atualização em tempo real (capturas em thread separada)."""
        if self._rt_worker is not None:
            return
        if self._capture_worker is not None:
            return
        if not HAS_SCOPE_XY:
            QMessageBox.warning(self, "Error", "Real-time requires scope_xy module")
            return
        
        if not self.connected or not self.scope_xy:
            QMessageBox.warning(self, "Error", "Not connected to oscilloscope")
            return
        
        # Snapshot das configurações: widgets só podem ser lidos na thread da GUI
        ch_x = self.ch_x_combo.currentText()
        ch_y = self.ch_y_combo.currentText()
        probe_x = self.probe_x_spin.value()
        probe_y = self.probe_y_spin.value()
        y_direct = self.y_direct_check.isChecked()
        shunt_val = self.shunt_spin.value()
        shunt = shunt_val if shunt_val > 0 else None
        invert = self.invert_y_check.isChecked()
        interval = float(self.update_rate_spin.value())
        scope = self.scope_xy
        
        def capture():
            return scope.capture_xy(
                ch_x=ch_x, ch_y=ch_y,
                probe_x=probe_x, probe_y=probe_y,
                y_is_direct_current=y_direct,
                shunt_r=shunt,
                invert_y=invert,
                keep_xy=True,
                resume_after=True,
            )
        
        def geometry():
            return self._query_geometry(ch_x, ch_y, shunt_val)
        
        worker = RealtimeWorker(capture, geometry, interval, parent=self)
        worker.frame_ready.connect(self._on_realtime_frame)
        worker.capture_failed.connect(self._on_realtime_error)
        worker.finished.connect(self._on_realtime_finished)
        
        self._rt_worker = worker
        self._rt_interval = interval
        self._rt_error = False
        
        self.capture_btn.setText("STOP Real-time")
        self._set_scope_controls(False)
        self.status_label.setText("Real-time started")
        self.status_label.setStyleSheet("color: green;")
        worker.start()
    
    def stop_realtime(self):
        """Solicita a parada do modo tempo real (assíncrona)."""
        worker = self._rt_worker
        if worker is None:
            return
        self.capture_btn.setEnabled(False)
        self.capture_btn.setText("Stopping...")
        worker.stop()
    
    def _set_scope_controls(self, enabled: bool) -> None:
        """Bloqueia comandos concorrentes no osciloscópio enquanto há captura."""
        for widget in (self.connect_btn, self.refresh_btn, self.resource_combo,
                       self.load_setup_btn, self.load_data_btn,
                       self.components_btn, self.update_mode_combo,
                       self.update_rate_spin, self.mem_depth_combo):
            widget.setEnabled(enabled)
    
    def _on_realtime_frame(self, frame) -> None:
        """Recebe um frame capturado na thread de trabalho e plota na GUI."""
        vx = frame.get('vx')
        vy = frame.get('vy')
        if vx is None or vy is None or len(vx) == 0 or len(vy) == 0:
            return
        self.plot_curve(vx, vy, geom=frame.get('geom'))
        self.last_data = (vx, vy)
        if self._rt_interval > 0:
            self.update_label.setText(f"{1.0 / self._rt_interval:.1f} fps")
    
    def _on_realtime_error(self, message: str) -> None:
        """Mostra erro de captura sem interromper o modo tempo real."""
        self._rt_error = True
        self.status_label.setText(f"Real-time error: {message}")
        self.status_label.setStyleSheet("color: red;")
    
    def _on_realtime_finished(self) -> None:
        """Limpeza após o encerramento da thread de tempo real."""
        worker = self._rt_worker
        self._rt_worker = None
        if worker is not None:
            worker.deleteLater()
        self.capture_btn.setEnabled(True)
        self.capture_btn.setText("CAPTURE")
        self._set_scope_controls(True)
        self.update_label.setText("N/A")
        
        # Retoma a aquisição contínua no osciloscópio. A profundidade de
        # memória selecionada na GUI permanece até desconectar.
        if self.connected and self.scope_xy:
            try:
                self.scope_xy.run()
            except Exception:
                pass
        
        if not self._rt_error:
            self.status_label.setText("Real-time stopped")
            self.status_label.setStyleSheet("color: green;")
    
    @staticmethod
    def _format_eng(value: float, unit: str = 'V') -> str:
        """Formata um valor com prefixo SI (V, mV, µV / A, mA, µA)."""
        av = abs(value)
        if av >= 1.0:
            return f"{value:.4g} {unit}"
        if av >= 1e-3:
            return f"{value * 1e3:.4g} m{unit}"
        if av >= 1e-6:
            return f"{value * 1e6:.4g} µ{unit}"
        return f"{value:.3g} {unit}"

    @classmethod
    def _format_volts(cls, value: float) -> str:
        return cls._format_eng(value, 'V')

    @staticmethod
    def _format_scale(scale_per_div: float, unit: str = 'V') -> str:
        """Formata a escala como no painel do osciloscópio (ex.: 200 mV/div)."""
        if abs(scale_per_div) < 1.0:
            return f"{scale_per_div * 1e3:g} m{unit}/div"
        return f"{scale_per_div:g} {unit}/div"

    @staticmethod
    def _tick_unit(span: float, unit: str = 'V'):
        """Escolhe a unidade dos ticks para manter os rótulos curtos."""
        if span < 1e-3:
            return 1e6, 'µ' + unit
        if span < 2.0:
            return 1e3, 'm' + unit
        return 1.0, unit

    def _query_geometry(self, ch_x, ch_y, shunt):
        """Lê escala/offset do instrumento e calcula o range das 8 divisões.

        Não acessa widgets: pode ser chamado da thread de captura. Cada query
        tem um valor de fallback para que uma falha isolada (timeout de USB,
        comando não suportado) não derrube a captura nem a grade.
        """
        try:
            scale_x = float(self.scope_xy.get_channel_scale(ch_x))
        except Exception as e:
            print(f"scale query failed for {ch_x}: {e}")
            scale_x = 1.0
        try:
            scale_y = float(self.scope_xy.get_channel_scale(ch_y))
        except Exception as e:
            print(f"scale query failed for {ch_y}: {e}")
            scale_y = 1.0
        try:
            offset_x = float(self.scope_xy.get_channel_offset(ch_x))
        except Exception as e:
            print(f"offset query failed for {ch_x}: {e}")
            offset_x = 0.0
        try:
            offset_y = float(self.scope_xy.get_channel_offset(ch_y))
        except Exception as e:
            print(f"offset query failed for {ch_y}: {e}")
            offset_y = 0.0

        if not np.isfinite(scale_x) or scale_x <= 0:
            scale_x = 1.0
        if not np.isfinite(scale_y) or scale_y <= 0:
            scale_y = 1.0
        if not np.isfinite(offset_x):
            offset_x = 0.0
        if not np.isfinite(offset_y):
            offset_y = 0.0

        # Se há shunt, capture_xy devolve corrente (V/R); a escala e o
        # centro do eixo Y também precisam ser convertidos para A.
        shunt = float(shunt or 0.0)
        y_unit = 'A' if shunt > 0 else 'V'
        scale_y_plot = scale_y / shunt if shunt > 0 else scale_y
        offset_y_plot = offset_y / shunt if shunt > 0 else offset_y

        # O MSO5000 usa 10 colunas x 8 linhas no display X-Y; o DHO usa 8x8.
        try:
            x_div, y_div = self.scope_xy.get_screen_divisions()
        except Exception:
            x_div = y_div = 8.0

        x_min, x_max = compute_channel_screen_range(scale_x, offset_x, x_div)
        y_min, y_max = compute_channel_screen_range(scale_y_plot, offset_y_plot, y_div)

        return {
            'ch_x': ch_x, 'ch_y': ch_y,
            'scale_x': scale_x, 'scale_y': scale_y,
            'offset_x': offset_x, 'offset_y': offset_y,
            'scale_y_plot': scale_y_plot, 'offset_y_plot': offset_y_plot,
            'y_unit': y_unit,
            'x_div': x_div, 'y_div': y_div,
            'x_min': x_min, 'x_max': x_max, 'y_min': y_min, 'y_max': y_max,
        }

    def _scope_geometry(self):
        """Lê escala/offset do instrumento e calcula o range das 8 divisões.

        Retorna ``None`` se não houver osciloscópio conectado ou se as queries
        falharem. Nesse caso o chamador usa o range dos dados (LOAD Data) ou o
        placeholder (sem conexão).
        """
        if not self.scope_xy:
            return None

        ch_x = self.ch_x_combo.currentText()
        ch_y = self.ch_y_combo.currentText()
        shunt = float(self.shunt_spin.value()) if hasattr(self, 'shunt_spin') else 0.0

        try:
            return self._query_geometry(ch_x, ch_y, shunt)
        except Exception as e:
            print(f"Plot scale error: {e}")
            return None

    def _apply_scope_axes(self, geom):
        """Aplica limites, ticks, grade e rótulos conforme o display do scope."""
        self.ax.set_xlim(geom['x_min'], geom['x_max'])
        self.ax.set_ylim(geom['y_min'], geom['y_max'])

        x_div = float(geom.get('x_div', 8.0))
        y_div = float(geom.get('y_div', 8.0))

        # Ticks e linhas de grade em cada divisão
        x_ticks = np.linspace(geom['x_min'], geom['x_max'], int(x_div) + 1)
        y_ticks = np.linspace(geom['y_min'], geom['y_max'], int(y_div) + 1)
        x_factor, x_tick_unit = self._tick_unit(geom['x_max'] - geom['x_min'], 'V')
        y_factor, y_tick_unit = self._tick_unit(geom['y_max'] - geom['y_min'], geom['y_unit'])
        self.ax.set_xticks(x_ticks)
        self.ax.set_yticks(y_ticks)
        self.ax.set_xticklabels([f"{v * x_factor:.4g}" for v in x_ticks], fontsize=8)
        self.ax.set_yticklabels([f"{v * y_factor:.4g}" for v in y_ticks], fontsize=8)

        # Células quadradas como na tela: 8x8 no DHO, 10x8 no MSO5000.
        try:
            self.ax.set_box_aspect(y_div / x_div)
        except Exception:
            self.ax.set_aspect('auto')

        self.ax.grid(self.grid_check.isChecked())

        ch_x, ch_y = geom['ch_x'], geom['ch_y']
        self.ax.set_xlabel(
            f"{ch_x} [{x_tick_unit}]   {self._format_scale(geom['scale_x'])}   "
            f"centro {self._format_volts(-geom['offset_x'])}"
        )
        self.ax.set_ylabel(
            f"{ch_y} [{y_tick_unit}]   {self._format_scale(geom['scale_y_plot'], geom['y_unit'])}   "
            f"centro {self._format_eng(-geom['offset_y_plot'], geom['y_unit'])}"
        )
        model = getattr(self.scope_xy, 'model', '') or 'Rigol'
        self.ax.set_title(
            f"RIGOL {model} - X-Y ({int(x_div)} x {int(y_div)} divisões)"
        )

        self._plot_units = ('V', geom['y_unit'])

    def show_placeholder(self, clear_data: bool = False):
        """Estado inicial: nenhum gráfico, apenas um aviso central."""
        if clear_data:
            self.last_data = None
        self.ax.clear()
        self.ax.set_visible(False)
        self._reset_cursor_artists()
        self._placeholder_text.set_visible(True)
        self._view_state = "empty"
        self._plot_units = ('V', 'V')
        self.info_text.setText(
            "Sem dados. Conecte ao osciloscópio e clique CAPTURE."
        )
        self.canvas.draw_idle()

    def show_scope_grid(self):
        """Conectado sem captura: somente a grade 8x8 do instrumento."""
        geom = self._scope_geometry()
        if geom is None:
            self.show_placeholder()
            return

        self.ax.clear()
        self.ax.set_visible(True)
        self._placeholder_text.set_visible(False)
        self._reset_cursor_artists()
        self._apply_scope_axes(geom)
        self._view_state = "grid"
        self.info_text.setText(
            f"{geom['ch_x']}: {self._format_scale(geom['scale_x'])}, "
            f"centro {self._format_volts(-geom['offset_x'])}\n"
            f"{geom['ch_y']}: {self._format_scale(geom['scale_y_plot'], geom['y_unit'])}, "
            f"centro {self._format_eng(-geom['offset_y_plot'], geom['y_unit'])}\n"
            "Aguardando captura (grade do osciloscópio)"
        )
        self.canvas.draw()

    def _refresh_grid_if_idle(self, *args):
        """Atualiza a grade vazia quando canal/escala/shunt muda antes da captura."""
        if self.connected and self._view_state == "grid":
            self.show_scope_grid()

    def _on_shunt_changed(self, *args):
        """O shunt só é aplicado durante a captura; avisa se já há curva na tela."""
        if self._view_state == "data":
            self.status_label.setText(
                "Shunt R changed - press CAPTURE to apply"
            )
            self.status_label.setStyleSheet("color: orange;")
            return
        self._refresh_grid_if_idle()

    def plot_curve(self, vx, vy, geom=None):
        """
        Plota a curva X-Y reproduzindo a grade do osciloscópio.

        - 8 divisões em cada eixo (grade quadrada)
        - span de cada eixo = 8 x Volts/div do respectivo canal
        - centro de cada eixo = -offset (convenção do DHO)
        - dados em unidades físicas, na ordem temporal original, sem
          normalização artificial entre os eixos

        ``geom`` permite passar a geometria já consultada (ex.: lida na thread
        de captura) e evitar novas queries ao osciloscópio na thread da GUI.
        """
        vx = np.asarray(vx)
        vy = np.asarray(vy)
        if len(vx) == 0 or len(vy) == 0:
            self.show_placeholder()
            return

        self.ax.clear()
        self.ax.set_visible(True)
        self._placeholder_text.set_visible(False)
        self._reset_cursor_artists()
        self.ax.plot(vx, vy, 'b-', linewidth=1.0)

        geom = geom if geom is not None else self._scope_geometry()
        if geom is not None:
            self._apply_scope_axes(geom)
            self.info_text.setText(
                f"{geom['ch_x']}: {self._format_scale(geom['scale_x'])}, "
                f"centro {self._format_volts(-geom['offset_x'])}\n"
                f"{geom['ch_y']}: {self._format_scale(geom['scale_y_plot'], geom['y_unit'])}, "
                f"centro {self._format_eng(-geom['offset_y_plot'], geom['y_unit'])}\n"
                f"Modo waveform: {getattr(self.scope_xy, 'last_waveform_mode', 'N/A')}"
            )
        else:
            # Fallback (ex.: LOAD Data sem osciloscópio): usa o range dos
            # dados, sem normalizar nem forçar proporção entre os eixos.
            x_min, x_max = float(np.min(vx)), float(np.max(vx))
            y_min, y_max = float(np.min(vy)), float(np.max(vy))
            if x_max <= x_min:
                x_min, x_max = x_min - 1.0, x_max + 1.0
            if y_max <= y_min:
                y_min, y_max = y_min - 1.0, y_max + 1.0
            x_pad = (x_max - x_min) * 0.05
            y_pad = (y_max - y_min) * 0.05
            x_min, x_max = x_min - x_pad, x_max + x_pad
            y_min, y_max = y_min - y_pad, y_max + y_pad

            self.ax.set_xlim(x_min, x_max)
            self.ax.set_ylim(y_min, y_max)
            x_ticks = np.linspace(x_min, x_max, 9)
            y_ticks = np.linspace(y_min, y_max, 9)
            x_factor, x_tick_unit = self._tick_unit(x_max - x_min, 'V')
            y_factor, y_tick_unit = self._tick_unit(y_max - y_min, 'V')
            self.ax.set_xticks(x_ticks)
            self.ax.set_yticks(y_ticks)
            self.ax.set_xticklabels([f"{v * x_factor:.4g}" for v in x_ticks], fontsize=8)
            self.ax.set_yticklabels([f"{v * y_factor:.4g}" for v in y_ticks], fontsize=8)
            try:
                self.ax.set_box_aspect(1)
            except Exception:
                pass
            self.ax.grid(self.grid_check.isChecked())
            self.ax.set_xlabel(f"{self.ch_x_combo.currentText()} [{x_tick_unit}]")
            self.ax.set_ylabel(f"{self.ch_y_combo.currentText()} [{y_tick_unit}]")
            self.ax.set_title("X-Y Curve (escala dos dados)")
            self._plot_units = ('V', 'V')
            self.info_text.setText("Escala do osciloscópio indisponível; usando range dos dados.")

        self._view_state = "data"
        self.canvas.draw()

    # ------------------------------------------------------------------
    # Cursor (posição X/Y)
    # ------------------------------------------------------------------
    def _reset_cursor_artists(self):
        """Após ax.clear(), os artistas do cursor deixam de existir."""
        self._cursor_vline = None
        self._cursor_hline = None
        self._cursor_marker = None
        self._cursor_annot = None

    def _ensure_cursor_artists(self):
        if self._cursor_annot is not None:
            return
        self._cursor_vline = self.ax.axvline(
            0.0, color='#999999', lw=0.8, ls='--', visible=False, zorder=5
        )
        self._cursor_hline = self.ax.axhline(
            0.0, color='#999999', lw=0.8, ls='--', visible=False, zorder=5
        )
        self._cursor_marker, = self.ax.plot(
            [], [], marker='o', ms=6, mfc='none', mec='#d62728', mew=1.4,
            ls='none', visible=False, zorder=6
        )
        self._cursor_annot = self.ax.annotate(
            "", xy=(0.0, 0.0), xytext=(12, 12), textcoords='offset points',
            fontsize=9, color='#222222', visible=False, zorder=7,
            bbox=dict(boxstyle='round,pad=0.3', fc='white', ec='#999999', alpha=0.95),
        )

    def _show_cursor(self, x: float, y: float):
        self._ensure_cursor_artists()
        self._cursor_vline.set_xdata([x, x])
        self._cursor_hline.set_ydata([y, y])
        self._cursor_marker.set_data([x], [y])
        self._cursor_annot.xy = (x, y)
        self._cursor_annot.set_text(
            f"X: {self._format_eng(x, self._plot_units[0])}\n"
            f"Y: {self._format_eng(y, self._plot_units[1])}"
        )
        for artist in (
            self._cursor_vline, self._cursor_hline,
            self._cursor_marker, self._cursor_annot,
        ):
            artist.set_visible(True)
        self.canvas.draw_idle()

    def _hide_cursor(self):
        changed = False
        for artist in (
            self._cursor_vline, self._cursor_hline,
            self._cursor_marker, self._cursor_annot,
        ):
            if artist is not None and artist.get_visible():
                artist.set_visible(False)
                changed = True
        if changed:
            self.canvas.draw_idle()

    def on_cursor_mode_changed(self, mode: str):
        self._hide_cursor()

    def _toolbar_mode_active(self) -> bool:
        mode = getattr(self.toolbar, 'mode', '')
        return bool(getattr(mode, 'value', mode))

    def on_mouse_move(self, event):
        if self.cursor_combo.currentText() != 'Free':
            return
        if self._toolbar_mode_active():
            self._hide_cursor()
            return
        if (self._view_state == 'empty' or event.inaxes is not self.ax
                or event.xdata is None or event.ydata is None):
            self._hide_cursor()
            return
        self._show_cursor(float(event.xdata), float(event.ydata))

    def on_mouse_click(self, event):
        if self.cursor_combo.currentText() != 'Single-Plot':
            return
        if event.button != 1 or event.inaxes is not self.ax:
            return
        if (event.xdata is None or event.ydata is None
                or self._view_state == 'empty'
                or self._toolbar_mode_active()):
            return
        self._show_cursor(float(event.xdata), float(event.ydata))
    
    # ------------------------------------------------------------------
    # Component registry
    # ------------------------------------------------------------------
    def get_live_capture(self):
        """Última captura exibida, com as unidades físicas dos eixos.

        Usada pela janela de componentes para salvar/comparar a captura
        atual. Retorna ``None`` quando ainda não há dados.
        """
        if self.last_data is None:
            return None
        vx, vy = self.last_data
        if len(vx) == 0 or len(vy) == 0:
            return None
        return (
            np.asarray(vx, dtype=float),
            np.asarray(vy, dtype=float),
            self._plot_units[0],
            self._plot_units[1],
        )

    def on_open_components(self):
        """Abre (ou reutiliza) a janela de cadastro/comparação."""
        if not HAS_COMPONENT_GUI:
            QMessageBox.warning(
                self, "Component module",
                "Component registry is not available (missing dependencies).",
            )
            return

        dialog = getattr(self, "_components_dialog", None)
        if dialog is not None:
            try:
                if dialog.isVisible():
                    dialog.raise_()
                    dialog.activateWindow()
                    return
                dialog.deleteLater()
            except RuntimeError:
                pass
            self._components_dialog = None

        try:
            dialog = ComponentManagerDialog(
                get_live_capture=self.get_live_capture,
                capture_now=lambda on_done=None: self._capture_single(
                    show_errors=False, on_done=on_done
                ),
                parent=self,
            )
            dialog.show()
            self._components_dialog = dialog
        except Exception as e:
            QMessageBox.critical(self, "Component registry", str(e))

    def on_save_setup(self):
        """Salva configuração atual"""
        try:
            filename, _ = QFileDialog.getSaveFileName(self, "Save Setup", "", "JSON Files (*.json)")
            if not filename:
                return
            
            data = {
                'resource': (self.resource_combo.currentData()
                             or self.resource_combo.currentText()),
                'ch_x': self.ch_x_combo.currentText(),
                'ch_y': self.ch_y_combo.currentText(),
                'probe_x': self.probe_x_spin.value(),
                'probe_y': self.probe_y_spin.value(),
                'y_direct': self.y_direct_check.isChecked(),
                'shunt': self.shunt_spin.value(),
                'invert': self.invert_y_check.isChecked(),
                'update_mode': self.update_mode_combo.currentText(),
                'update_rate': self.update_rate_spin.value(),
                'mem_depth': self.mem_depth_combo.currentText(),
            }
            
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
            
            self.status_label.setText(f"Setup saved: {filename}")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
    
    def on_load_setup(self):
        """Carrega configuração"""
        try:
            filename, _ = QFileDialog.getOpenFileName(self, "Load Setup", "", "JSON Files (*.json)")
            if not filename:
                return
            
            with open(filename, 'r') as f:
                data = json.load(f)
            
            # Aplicar configurações
            if 'resource' in data and data['resource']:
                resource = str(data['resource'])
                idx = self.resource_combo.findData(resource)
                if idx < 0:
                    idx = self.resource_combo.findText(resource)
                if idx < 0:
                    self.resource_combo.addItem(resource, userData=resource)
                    idx = self.resource_combo.count() - 1
                self.resource_combo.setCurrentIndex(idx)
            if 'ch_x' in data:
                idx = self.ch_x_combo.findText(data['ch_x'])
                if idx >= 0:
                    self.ch_x_combo.setCurrentIndex(idx)
            if 'ch_y' in data:
                idx = self.ch_y_combo.findText(data['ch_y'])
                if idx >= 0:
                    self.ch_y_combo.setCurrentIndex(idx)
            if 'probe_x' in data:
                self.probe_x_spin.setValue(data['probe_x'])
            if 'probe_y' in data:
                self.probe_y_spin.setValue(data['probe_y'])
            if 'y_direct' in data:
                self.y_direct_check.setChecked(data['y_direct'])
            if 'shunt' in data:
                self.shunt_spin.setValue(data['shunt'])
            if 'invert' in data:
                self.invert_y_check.setChecked(data['invert'])
            if 'update_mode' in data:
                idx = self.update_mode_combo.findText(data['update_mode'])
                if idx >= 0:
                    self.update_mode_combo.setCurrentIndex(idx)
            if 'update_rate' in data:
                self.update_rate_spin.setValue(data['update_rate'])
            if 'mem_depth' in data:
                value = str(data['mem_depth'])
                idx = self.mem_depth_combo.findText(value)
                if idx < 0:
                    self.mem_depth_combo.addItem(value)
                    idx = self.mem_depth_combo.count() - 1
                self.mem_depth_combo.setCurrentIndex(idx)
                if self.connected:
                    self._apply_memory_depth()
            
            self.status_label.setText(f"Setup loaded: {filename}")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
    
    def on_save_data(self):
        """Salva dados da curva atual"""
        if self.last_data is None:
            QMessageBox.warning(self, "Error", "No data to save - capture first")
            return
        
        try:
            filename, _ = QFileDialog.getSaveFileName(self, "Save Data", "", "CSV Files (*.csv)")
            if not filename:
                return
            
            vx, vy = self.last_data
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Voltage_V', 'Current_A'])
                for v, i in zip(vx, vy):
                    writer.writerow([v, i])
            
            self.status_label.setText(f"Data saved: {filename}")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
    
    def on_load_data(self):
        """Carrega dados de curva"""
        try:
            filename, _ = QFileDialog.getOpenFileName(self, "Load Data", "", "CSV Files (*.csv)")
            if not filename:
                return
            
            vx, vy = [], []
            with open(filename, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        vx.append(float(row.get('Voltage_V') or row.get('V') or row.get('X') or 0))
                        vy.append(float(row.get('Current_A') or row.get('I') or row.get('Y') or 0))
                    except:
                        pass
            
            if not vx:
                QMessageBox.warning(self, "Error", "Could not parse data")
                return
            
            vx = np.array(vx)
            vy = np.array(vy)
            
            self.plot_curve(vx, vy)
            self.last_data = (vx, vy)
            self.status_label.setText(f"Loaded {len(vx)} points")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
    
    def on_print_screen(self):
        """Salva screenshot"""
        try:
            filename, _ = QFileDialog.getSaveFileName(self, "Save Screenshot", "", 
                                                      "PNG Files (*.png);;JPG Files (*.jpg)")
            if not filename:
                return
            self.figure.savefig(filename, dpi=150, bbox_inches='tight')
            self.status_label.setText(f"Screenshot saved: {filename}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
    


def _application_icon_path():
    """Caminho do ícone da janela no código-fonte ou no executável congelado."""
    if getattr(sys, 'frozen', False):
        base = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        return os.path.join(base, 'assets', 'blacksmith.jpeg')
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, 'docs', 'images', 'blacksmith.jpeg')


def main():
    # Workaround para evitar erros do GTK no Linux. Não se aplica ao Windows:
    # forçar xcb lá impede o Qt de encontrar o plugin de plataforma.
    import os
    if sys.platform.startswith('linux'):
        os.environ.setdefault('QT_QPA_PLATFORM', 'xcb')  # Force X11 backend
        os.environ['QT_ACCESSIBILITY'] = '0'   # Disable accessibility to avoid GNOME settings queries
    
    app = QApplication(sys.argv)
    icon_path = _application_icon_path()
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    window = CurveTracerMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
