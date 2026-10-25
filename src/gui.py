#!/usr/bin/env python3
"""
CurveTracer OSS - Rigol DHO800/DHO900 Oscilloscope X-Y Mode
Analog Curve Tracer Interface

Refatorado para focar exclusivamente em:
- PC Host (Python) + PyVISA
- Rigol DHO Series Oscilloscope
- Analog Curve Tracer (gerador de curvas V-I)
"""

import sys
import os
import json
import csv
from datetime import datetime

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                              QHBoxLayout, QPushButton, QLabel, QComboBox,
                              QSpinBox, QDoubleSpinBox, QGroupBox, QTabWidget,
                              QCheckBox, QLineEdit, QTextEdit, QGridLayout,
                              QFrame, QFileDialog, QMessageBox, QSplitter)
from PyQt6.QtCore import Qt, QTimer
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import numpy as np

try:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from scope_xy import RigolScopeXY, discover_rigol, compute_channel_screen_range
        HAS_SCOPE_XY = True
    except Exception as e:
        from src.scope_xy import RigolScopeXY, discover_rigol, compute_channel_screen_range
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


class CurveTracerMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rigol DHO CurveTracer - Curve Tracer OSS")
        self.setGeometry(50, 50, 1400, 900)
        
        self.scope_xy = None
        self.connected = False
        self.capture_timer = None
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
        self.stop_btn.clicked.connect(self.on_stop)
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
        self.shunt_spin.valueChanged.connect(self._refresh_grid_if_idle)
    
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
        self.update_rate_spin.setValue(0.5)
        self.update_rate_spin.setRange(0.1, 10.0)
        self.update_rate_spin.setDecimals(1)
        self.update_rate_spin.setSuffix(" s")
        acq_layout.addWidget(self.update_rate_spin, 1, 1)
        
        acq_layout.addWidget(QLabel("Update:"), 2, 0)
        self.update_label = QLabel("N/A")
        acq_layout.addWidget(self.update_label, 2, 1)
        
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
        self.resource_edit = QLineEdit()
        self.resource_edit.setPlaceholderText("TCPIP::192.168.68.104::INSTR")
        self.resource_edit.setText("TCPIP::192.168.68.104::INSTR")
        op_layout.addWidget(self.resource_edit)
        self.refresh_btn = QPushButton("Refresh")
        op_layout.addWidget(self.refresh_btn)
        self.connect_btn = QPushButton("CONNECT")
        op_layout.addWidget(self.connect_btn)
        self.capture_btn = QPushButton("CAPTURE")
        op_layout.addWidget(self.capture_btn)
        self.stop_btn = QPushButton("STOP")
        op_layout.addWidget(self.stop_btn)
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
        """Atualiza lista de recursos VISA disponíveis"""
        if not HAS_SCOPE_XY:
            self.status_label.setText("PyVISA not available")
            self.status_label.setStyleSheet("color: red;")
            return
        
        try:
            all_res, rigol_res = discover_rigol()
            
            if rigol_res:
                self.status_label.setText(f"Found {len(rigol_res)} Rigol device(s)")
                self.status_label.setStyleSheet("color: green;")
            else:
                self.status_label.setText("No Rigol devices found")
                self.status_label.setStyleSheet("color: orange;")
                
        except Exception as e:
            self.status_label.setText(f"Discovery error: {e}")
            self.status_label.setStyleSheet("color: red;")
    
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
        
        # Conectar
        resource = self.resource_edit.text().strip()
        if not resource:
            QMessageBox.warning(self, "Error", "Please enter VISA resource name")
            return
        
        try:
            self.scope_xy = RigolScopeXY(resource)
            self.connected = True
            self.connect_btn.setText("DISCONNECT")
            self.status_label.setText(f"Connected: {self.scope_xy.get_idn()}")
            self.status_label.setStyleSheet("color: green;")

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
            self.status_label.setText(f"Connection error: {e}")
            self.status_label.setStyleSheet("color: red;")
            QMessageBox.critical(self, "Connection Error", str(e))
    
    def on_capture(self):
        """Executa captura de curva (uma vez)"""
        if not self.connected or not self.scope_xy:
            QMessageBox.warning(self, "Error", "Not connected to oscilloscope")
            return
        
        # Verificar modo
        if self.update_mode_combo.currentText() == "Real-time":
            self.start_realtime()
            return
        
        # Captura única
        self.capture_btn.setEnabled(False)
        self.status_label.setText("Capturing...")
        
        try:
            ch_x = self.ch_x_combo.currentText()
            ch_y = self.ch_y_combo.currentText()
            probe_x = self.probe_x_spin.value()
            probe_y = self.probe_y_spin.value()
            y_direct = self.y_direct_check.isChecked()
            shunt = self.shunt_spin.value() if self.shunt_spin.value() > 0 else None
            invert = self.invert_y_check.isChecked()
            
            # Capturar dados (mantém X-Y ativo e retoma a aquisição ao final)
            vx, vy = self.scope_xy.capture_xy(
                ch_x=ch_x, ch_y=ch_y,
                probe_x=probe_x, probe_y=probe_y,
                y_is_direct_current=y_direct,
                shunt_r=shunt,
                invert_y=invert,
                keep_xy=True,
                resume_after=True
            )

            # Plotar
            if len(vx) > 0 and len(vy) > 0:
                self.plot_curve(vx, vy)
                self.last_data = (vx, vy)
                xy_state = self.scope_xy.is_xy_enabled()
                xy_msg = "X-Y ON" if xy_state else "X-Y OFF"
                self.status_label.setText(
                    f"Captured {len(vx)} points ({self.scope_xy.last_waveform_mode}) "
                    f"- scope running, {xy_msg}"
                )
                self.status_label.setStyleSheet("color: green;")
            else:
                self.status_label.setText("Capture failed - no data")
                
        except Exception as e:
            self.status_label.setText(f"Capture error: {e}")
            self.status_label.setStyleSheet("color: red;")
            QMessageBox.critical(self, "Capture Error", str(e))
        finally:
            self.capture_btn.setEnabled(True)
    
    def on_stop(self):
        """Para aquisição em tempo real"""
        self.stop_realtime()
        if self.connected and self.scope_xy:
            try:
                self.scope_xy.stop()
                self.status_label.setText("Stopped")
            except:
                pass
    
    def start_realtime(self):
        """Inicia atualização em tempo real"""
        if not HAS_SCOPE_XY:
            QMessageBox.warning(self, "Error", "Real-time requires scope_xy module")
            return
        
        if not self.connected or not self.scope_xy:
            QMessageBox.warning(self, "Error", "Not connected to oscilloscope")
            return
        
        self.capture_btn.setText("STOP Real-time")
        
        # Iniciar timer de atualização
        interval = int(self.update_rate_spin.value() * 1000)
        self.capture_timer = QTimer()
        self.capture_timer.timeout.connect(self.update_realtime)
        self.capture_timer.start(interval)
    
    def stop_realtime(self):
        """Para atualização em tempo real"""
        if self.capture_timer:
            self.capture_timer.stop()
            self.capture_timer = None
        
        if self.connected and self.scope_xy:
            try:
                self.scope_xy.run()
            except:
                pass
        
        self.capture_btn.setText("CAPTURE")
    
    def update_realtime(self):
        """Atualiza dados em tempo real"""
        if not self.connected or not self.scope_xy:
            return
        
        try:
            ch_x = self.ch_x_combo.currentText()
            ch_y = self.ch_y_combo.currentText()
            probe_x = self.probe_x_spin.value()
            probe_y = self.probe_y_spin.value()
            y_direct = self.y_direct_check.isChecked()
            shunt = self.shunt_spin.value() if self.shunt_spin.value() > 0 else None
            invert = self.invert_y_check.isChecked()
            
            # Capturar e já retomar a aquisição no mesmo modo X-Y
            vx, vy = self.scope_xy.capture_xy(
                ch_x=ch_x, ch_y=ch_y,
                probe_x=probe_x, probe_y=probe_y,
                y_is_direct_current=y_direct,
                shunt_r=shunt,
                invert_y=invert,
                keep_xy=True,
                resume_after=True
            )
            
            if len(vx) > 0 and len(vy) > 0:
                self.plot_curve(vx, vy)
                self.last_data = (vx, vy)
                
                # Calcular taxa de atualização
                self.update_label.setText(f"{1000/self.update_rate_spin.value():.1f} fps")
                
        except Exception as e:
            print(f"Real-time error: {e}")
    
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

        try:
            scale_x = float(self.scope_xy.get_channel_scale(ch_x))
            scale_y = float(self.scope_xy.get_channel_scale(ch_y))
            offset_x = float(self.scope_xy.get_channel_offset(ch_x))
            offset_y = float(self.scope_xy.get_channel_offset(ch_y))

            # Se há shunt, capture_xy devolve corrente (V/R); a escala e o
            # centro do eixo Y também precisam ser convertidos para A.
            shunt = float(self.shunt_spin.value()) if hasattr(self, 'shunt_spin') else 0.0
            y_unit = 'A' if shunt > 0 else 'V'
            scale_y_plot = scale_y / shunt if shunt > 0 else scale_y
            offset_y_plot = offset_y / shunt if shunt > 0 else offset_y

            x_min, x_max = compute_channel_screen_range(scale_x, offset_x)
            y_min, y_max = compute_channel_screen_range(scale_y_plot, offset_y_plot)
        except Exception as e:
            print(f"Plot scale error: {e}")
            return None

        return {
            'ch_x': ch_x, 'ch_y': ch_y,
            'scale_x': scale_x, 'scale_y': scale_y,
            'offset_x': offset_x, 'offset_y': offset_y,
            'scale_y_plot': scale_y_plot, 'offset_y_plot': offset_y_plot,
            'y_unit': y_unit,
            'x_min': x_min, 'x_max': x_max, 'y_min': y_min, 'y_max': y_max,
        }

    def _apply_scope_axes(self, geom):
        """Aplica limites, ticks, grade e rótulos de 8x8 divisões."""
        self.ax.set_xlim(geom['x_min'], geom['x_max'])
        self.ax.set_ylim(geom['y_min'], geom['y_max'])

        # Ticks e linhas de grade em cada divisão (9 linhas = 8 divisões)
        x_ticks = np.linspace(geom['x_min'], geom['x_max'], 9)
        y_ticks = np.linspace(geom['y_min'], geom['y_max'], 9)
        x_factor, x_tick_unit = self._tick_unit(geom['x_max'] - geom['x_min'], 'V')
        y_factor, y_tick_unit = self._tick_unit(geom['y_max'] - geom['y_min'], geom['y_unit'])
        self.ax.set_xticks(x_ticks)
        self.ax.set_yticks(y_ticks)
        self.ax.set_xticklabels([f"{v * x_factor:.4g}" for v in x_ticks], fontsize=8)
        self.ax.set_yticklabels([f"{v * y_factor:.4g}" for v in y_ticks], fontsize=8)

        # Área de plotagem quadrada: 1 divisão X ocupa o mesmo espaço que
        # 1 divisão Y, exatamente como na tela 8x8 do DHO em modo X-Y.
        try:
            self.ax.set_box_aspect(1)
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
        self.ax.set_title("RIGOL DHO - X-Y (8 x 8 divisões)")

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

    def plot_curve(self, vx, vy):
        """
        Plota a curva X-Y reproduzindo a grade do osciloscópio.

        - 8 divisões em cada eixo (grade quadrada)
        - span de cada eixo = 8 x Volts/div do respectivo canal
        - centro de cada eixo = -offset (convenção do DHO)
        - dados em unidades físicas, na ordem temporal original, sem
          normalização artificial entre os eixos
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

        geom = self._scope_geometry()
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
                capture_now=self.on_capture,
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
                'resource': self.resource_edit.text(),
                'ch_x': self.ch_x_combo.currentText(),
                'ch_y': self.ch_y_combo.currentText(),
                'probe_x': self.probe_x_spin.value(),
                'probe_y': self.probe_y_spin.value(),
                'y_direct': self.y_direct_check.isChecked(),
                'shunt': self.shunt_spin.value(),
                'invert': self.invert_y_check.isChecked(),
                'update_mode': self.update_mode_combo.currentText(),
                'update_rate': self.update_rate_spin.value(),
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
            if 'resource' in data:
                self.resource_edit.setText(data['resource'])
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


def main():
    app = QApplication(sys.argv)
    window = CurveTracerMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
