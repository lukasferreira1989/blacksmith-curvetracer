#!/usr/bin/env python3
"""
CurveTracer OSS - Faithful reproduction of Yokogawa GS610/GS820 CurveTracer Software
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
    import pyvisa
    HAS_PYVISA = True
except Exception as e:
    HAS_PYVISA = False
    print(f"PyVISA not available: {e}")

try:
    from scope_xy import RigolScopeXY, discover_rigol
    HAS_SCOPE_XY = True
except Exception as e:
    HAS_SCOPE_XY = False
    print(f"scope_xy not available: {e}")

try:
    from curve_tracer import CurveTracer
    HAS_CURVE_TRACER = True
except Exception as e:
    HAS_CURVE_TRACER = False
    print(f"curve_tracer not available: {e}")


class CurveTracerMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GS820_CurveTracer - CurveTracer OSS")
        self.setGeometry(50, 50, 1400, 900)
        
        self.rm = None
        self.inst = None
        self.connected = False
        self.sweeping = False
        self.scope_xy = None
        self.curve_tracer = None
        self.last_data = None  # (x, y)
        self.realtime_timer = QTimer()
        self.realtime_timer.timeout.connect(self.update_realtime)
        
        self.initUI()
        self.connect_signals()
        self.refresh_visa()
    
    def initUI(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        
        # Left panel - Settings
        left_panel = self.create_left_panel()
        main_layout.addWidget(left_panel)
        
        # Right panel - Graph and controls
        right_panel = self.create_right_panel()
        main_layout.addWidget(right_panel)
    
    def connect_signals(self):
        self.connect_btn.clicked.connect(self.on_connect)
        self.sweep_btn.clicked.connect(self.on_sweep)
        self.stop_btn.clicked.connect(self.on_stop)
        self.mode_combo.currentTextChanged.connect(self.on_mode_changed)
        self.save_setup_btn.clicked.connect(self.on_save_setup)
        self.load_setup_btn.clicked.connect(self.on_load_setup)
        self.save_data_btn.clicked.connect(self.on_save_data)
        self.load_data_btn.clicked.connect(self.on_load_data)
        self.print_screen_btn.clicked.connect(self.on_print_screen)
        self.cal_btn.clicked.connect(self.on_cal)
        self.refresh_btn.clicked.connect(self.refresh_visa)
        self.realtime_check.toggled.connect(self.toggle_realtime)
    
    def create_left_panel(self):
        panel = QWidget()
        panel.setMaximumWidth(420)
        panel.setMinimumWidth(380)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(2, 2, 2, 2)
        
        # Setup load/save
        setup_layout = QHBoxLayout()
        self.save_setup_btn = QPushButton("SAVE Setup")
        self.load_setup_btn = QPushButton("LOAD Setup")
        setup_layout.addWidget(self.save_setup_btn)
        setup_layout.addWidget(self.load_setup_btn)
        layout.addLayout(setup_layout)
        
        # Basic source and sweep settings
        basic_group = QGroupBox("Basic")
        basic_layout = QGridLayout(basic_group)
        
        basic_layout.addWidget(QLabel("Channel"), 0, 0)
        self.channel_combo = QComboBox()
        self.channel_combo.addItems(["Ch1 : Ch2", "Ch2 : Ch1"])
        basic_layout.addWidget(self.channel_combo, 0, 1)
        
        basic_layout.addWidget(QLabel("Function"), 1, 0)
        self.function_combo = QComboBox()
        self.function_combo.addItems(["VSweep/IMeas", "ISweep/VMeas", "VSweep -(Vsrc)/IMeas", 
                                       "ISweep -(Isrc)/VMeas", "VSweep -(ISrc)/VMeas", "ISweep/VMeas -ISweep"])
        basic_layout.addWidget(self.function_combo, 1, 1)
        
        basic_layout.addWidget(QLabel("Plot"), 2, 0)
        self.plot_combo = QComboBox()
        self.plot_combo.addItems(["Current - Voltage", "Voltage - Current", "Measure - Time", 
                                   "Gain - Measure", "Gain - Sweep", "Measure - Sweep"])
        basic_layout.addWidget(self.plot_combo, 2, 1)
        
        basic_layout.addWidget(QLabel("Sweep Form"), 3, 0)
        self.sweep_form_combo = QComboBox()
        self.sweep_form_combo.addItems(["Linear Ramp", "Log Ramp", "Linear Triangle", 
                                         "Log Triangle", "Pulse"])
        basic_layout.addWidget(self.sweep_form_combo, 3, 1)
        
        basic_layout.addWidget(QLabel("Sweep Points"), 4, 0)
        self.sweep_points_spin = QSpinBox()
        self.sweep_points_spin.setRange(5, 1000)
        self.sweep_points_spin.setValue(101)
        basic_layout.addWidget(self.sweep_points_spin, 4, 1)
        
        basic_layout.addWidget(QLabel("Average"), 5, 0)
        self.average_check = QCheckBox()
        basic_layout.addWidget(self.average_check, 5, 1)
        basic_layout.addWidget(QLabel("AveCount"), 6, 0)
        self.avecount_spin = QSpinBox()
        self.avecount_spin.setValue(3)
        self.avecount_spin.setRange(2, 100)
        basic_layout.addWidget(self.avecount_spin, 6, 1)
        
        layout.addWidget(basic_group)
        
        # Sweep settings
        sweep_group = QGroupBox("Sweep")
        sweep_layout = QGridLayout(sweep_group)
        
        sweep_layout.addWidget(QLabel("Start"), 0, 0)
        self.sweep_start = QDoubleSpinBox()
        self.sweep_start.setRange(-200, 200)
        self.sweep_start.setDecimals(4)
        self.sweep_start.setValue(0.0)
        sweep_layout.addWidget(self.sweep_start, 0, 1)
        sweep_layout.addWidget(QLabel("(V)"), 0, 2)
        
        sweep_layout.addWidget(QLabel("Stop"), 1, 0)
        self.sweep_stop = QDoubleSpinBox()
        self.sweep_stop.setRange(-200, 200)
        self.sweep_stop.setValue(5.0)
        self.sweep_stop.setDecimals(4)
        sweep_layout.addWidget(self.sweep_stop, 1, 1)
        sweep_layout.addWidget(QLabel("(V)"), 1, 2)
        
        sweep_layout.addWidget(QLabel("Range"), 2, 0)
        self.sweep_range_combo = QComboBox()
        self.sweep_range_combo.addItems(["Auto", "Fixed"])
        sweep_layout.addWidget(self.sweep_range_combo, 2, 1)
        
        sweep_layout.addWidget(QLabel("Response"), 3, 0)
        self.response_combo = QComboBox()
        self.response_combo.addItems(["Normal", "Fast", "Slow"])
        sweep_layout.addWidget(self.response_combo, 3, 1)
        
        sweep_layout.addWidget(QLabel("Limiter"), 4, 0)
        self.limiter_check = QCheckBox()
        sweep_layout.addWidget(self.limiter_check, 4, 1)
        sweep_layout.addWidget(QLabel("Level"), 5, 0)
        self.limiter_level = QDoubleSpinBox()
        self.limiter_level.setValue(0.1)
        self.limiter_level.setDecimals(4)
        sweep_layout.addWidget(self.limiter_level, 5, 1)
        sweep_layout.addWidget(QLabel("(A)"), 5, 2)
        
        layout.addWidget(sweep_group)
        
        # Measure settings
        measure_group = QGroupBox("Measure")
        measure_layout = QGridLayout(measure_group)
        
        measure_layout.addWidget(QLabel("Range"), 0, 0)
        self.meas_range_combo = QComboBox()
        self.meas_range_combo.addItems(["Auto", "10A", "1A", "100mA", "10mA", "1mA", "100uA", "10uA", "1uA"])
        measure_layout.addWidget(self.meas_range_combo, 0, 1)
        
        measure_layout.addWidget(QLabel("Int.Time"), 1, 0)
        self.inttime_combo = QComboBox()
        self.inttime_combo.addItems(["1PLC", "10PLC", "100PLC", "0.01ms", "0.1ms", "1ms", "10ms"])
        measure_layout.addWidget(self.inttime_combo, 1, 1)
        
        measure_layout.addWidget(QLabel("Delay"), 2, 0)
        self.delay_combo = QComboBox()
        self.delay_combo.addItems(["0s", "100us", "200us", "500us", "1ms", "10ms", "100ms", "1s"])
        measure_layout.addWidget(self.delay_combo, 2, 1)
        
        measure_layout.addWidget(QLabel("Auto Zero"), 3, 0)
        self.autozero_check = QCheckBox()
        self.autozero_check.setChecked(True)
        measure_layout.addWidget(self.autozero_check, 3, 1)
        
        layout.addWidget(measure_group)
        
        # Sub-condition
        sub_group = QGroupBox("Sub-Condition")
        sub_layout = QGridLayout(sub_group)
        sub_layout.addWidget(QLabel("Wiring"), 0, 0)
        self.sub_wiring_combo = QComboBox()
        self.sub_wiring_combo.addItems(["2Wire", "4Wire"])
        sub_layout.addWidget(self.sub_wiring_combo, 0, 1)
        sub_layout.addWidget(QLabel("Response"), 1, 0)
        self.sub_response_combo = QComboBox()
        self.sub_response_combo.addItems(["Normal", "Stable"])
        sub_layout.addWidget(self.sub_response_combo, 1, 1)
        sub_layout.addWidget(QLabel("Level"), 2, 0)
        self.sub_level = QDoubleSpinBox()
        self.sub_level.setDecimals(4)
        sub_layout.addWidget(self.sub_level, 2, 1)
        layout.addWidget(sub_group)
        
        layout.addStretch()
        return panel
    
    def create_right_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(2, 2, 2, 2)
        
        # Operation control area
        op_layout = QHBoxLayout()
        op_layout.addWidget(QLabel("VISA"))
        self.visa_edit = QLineEdit()
        self.visa_edit.setPlaceholderText("TCPIP::192.168.1.150::INSTR")
        self.visa_edit.setText("TCPIP::192.168.1.150::INSTR")
        op_layout.addWidget(self.visa_edit)
        self.refresh_btn = QPushButton("Refresh")
        op_layout.addWidget(self.refresh_btn)
        self.connect_btn = QPushButton("CONNECT")
        op_layout.addWidget(self.connect_btn)
        self.sweep_btn = QPushButton("SWEEP")
        op_layout.addWidget(self.sweep_btn)
        self.stop_btn = QPushButton("STOP")
        op_layout.addWidget(self.stop_btn)
        op_layout.addWidget(QLabel("Update:"))
        self.update_rate_label = QLabel("0.0s")
        op_layout.addWidget(self.update_rate_label)
        op_layout.addStretch()
        layout.addLayout(op_layout)
        
        # Mode selection
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["SMU (GS610/GS820)", "Analog Curve Tracer (X-Y via Osciloscópio)"])
        mode_layout.addWidget(self.mode_combo)
        self.realtime_check = QCheckBox("Real-time")
        self.realtime_check.setChecked(False)
        mode_layout.addWidget(self.realtime_check)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)
        
        # X-Y oscilloscope settings
        self.xy_group = QGroupBox("X-Y Oscilloscope Settings")
        xy_layout = QGridLayout(self.xy_group)
        xy_layout.addWidget(QLabel("CH X"), 0, 0)
        self.xy_chx_combo = QComboBox()
        self.xy_chx_combo.addItems(["CHAN1", "CHAN2"])
        xy_layout.addWidget(self.xy_chx_combo, 0, 1)
        xy_layout.addWidget(QLabel("CH Y"), 0, 2)
        self.xy_chy_combo = QComboBox()
        self.xy_chy_combo.addItems(["CHAN2", "CHAN1"])
        xy_layout.addWidget(self.xy_chy_combo, 0, 3)
        xy_layout.addWidget(QLabel("Probe X"), 1, 0)
        self.xy_probex_spin = QDoubleSpinBox()
        self.xy_probex_spin.setValue(1.0)
        self.xy_probex_spin.setRange(0.001, 10000)
        xy_layout.addWidget(self.xy_probex_spin, 1, 1)
        xy_layout.addWidget(QLabel("Probe Y"), 1, 2)
        self.xy_probey_spin = QDoubleSpinBox()
        self.xy_probey_spin.setValue(1.0)
        self.xy_probey_spin.setRange(0.001, 10000)
        xy_layout.addWidget(self.xy_probey_spin, 1, 3)
        xy_layout.addWidget(QLabel("Y direct current"), 2, 0)
        self.xy_direct_cur_check = QCheckBox()
        self.xy_direct_cur_check.setChecked(True)
        xy_layout.addWidget(self.xy_direct_cur_check, 2, 1)
        xy_layout.addWidget(QLabel("Shunt R (Ω)"), 2, 2)
        self.xy_shunt_spin = QDoubleSpinBox()
        self.xy_shunt_spin.setRange(0.001, 1000000)
        self.xy_shunt_spin.setValue(0.0)
        xy_layout.addWidget(self.xy_shunt_spin, 2, 3)
        xy_layout.addWidget(QLabel("Invert Y"), 3, 0)
        self.xy_invert_check = QCheckBox()
        xy_layout.addWidget(self.xy_invert_check, 3, 1)
        layout.addWidget(self.xy_group)
        self.xy_group.setVisible(False)
        
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
        self.cal_btn = QPushButton("CAL")
        graph_ctrl_layout.addWidget(self.save_data_btn)
        graph_ctrl_layout.addWidget(self.load_data_btn)
        graph_ctrl_layout.addWidget(self.print_screen_btn)
        graph_ctrl_layout.addWidget(self.cal_btn)
        
        graph_layout.addLayout(graph_ctrl_layout)
        
        self.figure = Figure(figsize=(10, 7))
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_xlabel('Voltage (V) / X')
        self.ax.set_ylabel('Current (A) / Y')
        self.ax.grid(True)
        self.ax.set_title('I-V Curve')
        
        self.toolbar = NavigationToolbar(self.canvas, graph_widget)
        graph_layout.addWidget(self.toolbar)
        graph_layout.addWidget(self.canvas)
        
        layout.addWidget(graph_widget)
        
        # Plot legend area
        legend_group = QGroupBox("Plot Legend")
        legend_layout = QHBoxLayout(legend_group)
        legend_layout.addWidget(QLabel("Plot 0"))
        legend_layout.addStretch()
        layout.addWidget(legend_group)
        
        return panel
    
    def toggle_realtime(self, checked):
        if checked and self.connected and "X-Y" in self.mode_combo.currentText():
            self.realtime_timer.start(500)  # Update every 500ms
            self.statusBar().showMessage("Real-time enabled", 2000)
        else:
            self.realtime_timer.stop()
            if checked:
                self.statusBar().showMessage("Real-time only works in X-Y mode with connection", 3000)
    
    def update_realtime(self):
        if not self.connected or not self.scope_xy or "X-Y" not in self.mode_combo.currentText():
            self.realtime_timer.stop()
            self.realtime_check.setChecked(False)
            return
        try:
            ch_x = self.xy_chx_combo.currentText()
            ch_y = self.xy_chy_combo.currentText()
            probe_x = self.xy_probex_spin.value()
            probe_y = self.xy_probey_spin.value()
            y_direct = self.xy_direct_cur_check.isChecked()
            shunt = self.xy_shunt_spin.value() if self.xy_shunt_spin.value() > 0 else None
            invert = self.xy_invert_check.isChecked()
            
            x, y = self.scope_xy.capture_xy(ch_x, ch_y, probe_x, probe_y, y_direct, shunt, invert)
            
            if len(x) > 0:
                mask = (np.abs(x) < 1e6) & (np.abs(y) < 1e6)
                x = x[mask]
                y = y[mask]
            
            self.ax.clear()
            self.ax.plot(x, y, 'r-', linewidth=0.6)
            self.ax.set_xlabel(f'{ch_x} (V)')
            self.ax.set_ylabel(f'{ch_y} (V)' if not (shunt and shunt > 0) else f'{ch_y} (A)')
            self.ax.grid(self.grid_check.isChecked())
            self.ax.set_title('I-V Curve (Real-time)')
            try:
                sx = self.scope_xy.get_scale(ch_x)
                sy = self.scope_xy.get_scale(ch_y)
                ox = self.scope_xy.get_offset(ch_x)
                oy = self.scope_xy.get_offset(ch_y)
                px = self.xy_probex_spin.value()
                py = self.xy_probey_spin.value()
                divs = 5.0
                xspan = sx * px * divs
                yspan = sy * py * divs
                self.ax.set_xlim(-xspan + ox, xspan + ox)
                self.ax.set_ylim(-yspan + oy, yspan + oy)
                self.ax.set_autoscalex_on(False)
                self.ax.set_autoscaley_on(False)
                self.ax.set_aspect('auto')
                print(f"DEBUG_RT {ch_x}:{sx}*{px}@{ox:.4f} {ch_y}:{sy}*{py}@{oy:.4f} divs:{divs}")
            except Exception as e:
                print(f"scale error: {e}")
                self.ax.relim()
                self.ax.autoscale(enable=True, axis='both', tight=False)
                self.ax.margins(x=0.15, y=0.15)
            self.canvas.draw()
            
            self.last_data = (x, y)
        except Exception as e:
            print(f"Realtime error: {e}")
    
    def refresh_visa(self):
        if not HAS_PYVISA:
            self.statusBar().showMessage("PyVISA not available", 3000)
            return
        try:
            if self.rm is None:
                self.rm = pyvisa.ResourceManager('@py')
            resources = self.rm.list_resources()
            if resources:
                self.statusBar().showMessage(f"Found: {', '.join(resources)}", 5000)
            else:
                self.statusBar().showMessage("No devices auto-discovered. Enter IP manually.", 3000)
        except Exception as e:
            self.statusBar().showMessage(f"Discovery error: {e}", 5000)
    
    def on_mode_changed(self, text):
        if "X-Y" in text:
            self.xy_group.setVisible(True)
        else:
            self.xy_group.setVisible(False)
            self.realtime_timer.stop()
            self.realtime_check.setChecked(False)
    
    def on_connect(self):
        if self.connected:
            try:
                self.realtime_timer.stop()
                self.realtime_check.setChecked(False)
                if self.inst:
                    self.inst.close()
                if self.scope_xy:
                    self.scope_xy.close()
                self.scope_xy = None
                self.inst = None
            except Exception as e:
                pass
            self.connected = False
            self.connect_btn.setText("CONNECT")
            self.statusBar().showMessage("Disconnected", 3000)
            return
        
        resource = self.visa_edit.text().strip()
        if not resource:
            QMessageBox.warning(self, "Error", "Enter VISA resource name/IP")
            return
        
        mode = self.mode_combo.currentText()
        try:
            if "X-Y" in mode and HAS_SCOPE_XY:
                self.scope_xy = RigolScopeXY(resource)
                self.connected = True
                self.connect_btn.setText("DISCONNECT")
                self.statusBar().showMessage(f"Connected to scope: {resource}", 5000)
                return
            elif HAS_PYVISA:
                if self.rm is None:
                    self.rm = pyvisa.ResourceManager('@py')
                self.inst = self.rm.open_resource(resource)
                self.inst.timeout = 10000
                try:
                    self.inst.write_termination = '\n'
                    self.inst.read_termination = '\n'
                except:
                    pass
                try:
                    idn = self.inst.query('*IDN?').strip()
                    self.statusBar().showMessage(f"Connected: {idn}", 5000)
                except Exception as e:
                    self.statusBar().showMessage(f"Connected (no IDN): {e}", 3000)
                self.connected = True
                self.connect_btn.setText("DISCONNECT")
                return
            else:
                QMessageBox.warning(self, "Error", "PyVISA not available")
        except Exception as e:
            QMessageBox.critical(self, "Connection Error", str(e))
    
    def on_sweep(self):
        self.realtime_timer.stop()
        self.realtime_check.setChecked(False)
        mode = self.mode_combo.currentText()
        if "X-Y" in mode:
            self.capture_xy()
        else:
            self.sweep_smu()
    
    def on_stop(self):
        self.realtime_timer.stop()
        self.realtime_check.setChecked(False)
        if self.scope_xy:
            try:
                self.scope_xy.run()
            except:
                pass
        self.statusBar().showMessage("Stopped", 2000)
    
    def capture_xy(self):
        if not self.connected or not self.scope_xy:
            QMessageBox.warning(self, "Error", "Not connected to oscilloscope")
            return
        try:
            self.sweep_btn.setEnabled(False)
            self.statusBar().showMessage("Capturing X-Y...", 2000)
            QApplication.processEvents()
            
            ch_x = self.xy_chx_combo.currentText()
            ch_y = self.xy_chy_combo.currentText()
            probe_x = self.xy_probex_spin.value()
            probe_y = self.xy_probey_spin.value()
            y_direct = self.xy_direct_cur_check.isChecked()
            shunt = self.xy_shunt_spin.value() if self.xy_shunt_spin.value() > 0 else None
            invert = self.xy_invert_check.isChecked()
            
            x, y = self.scope_xy.capture_xy(ch_x, ch_y, probe_x, probe_y, y_direct, shunt, invert)
            
            if len(x) > 0:
                # Remove obvious outliers and use raw plotting
                mask = (np.abs(x) < 1e6) & (np.abs(y) < 1e6)
                x = x[mask]
                y = y[mask]
            
            self.ax.clear()
            self.ax.plot(x, y, 'b-', linewidth=0.6)
            self.ax.set_xlabel(f'{ch_x} (V)')
            self.ax.set_ylabel(f'{ch_y} (V)' if not (shunt and shunt > 0) else f'{ch_y} (A)')
            self.ax.grid(self.grid_check.isChecked())
            self.ax.set_title('I-V Curve (X-Y)')
            try:
                sx = self.scope_xy.get_scale(ch_x)
                sy = self.scope_xy.get_scale(ch_y)
                ox = self.scope_xy.get_offset(ch_x)
                oy = self.scope_xy.get_offset(ch_y)
                px = self.xy_probex_spin.value()
                py = self.xy_probey_spin.value()
                divs = 5.0
                xspan = sx * px * divs
                yspan = sy * py * divs
                self.ax.set_xlim(-xspan + ox, xspan + ox)
                self.ax.set_ylim(-yspan + oy, yspan + oy)
                self.ax.set_autoscalex_on(False)
                self.ax.set_autoscaley_on(False)
                self.ax.set_aspect('auto')
                print(f"DEBUG_SCALE {ch_x}:{sx}*{px}@{ox:.4f} {ch_y}:{sy}*{py}@{oy:.4f} divs:{divs} => X[{ -xspan+ox:.3f},{xspan+ox:.3f}] Y[{ -yspan+oy:.3f},{yspan+oy:.3f}]")
            except Exception as e:
                print(f"scale error: {e}")
                self.ax.relim()
                self.ax.autoscale(enable=True, axis='both', tight=False)
                self.ax.margins(x=0.15, y=0.15)
            self.canvas.draw()
            
            self.last_data = (x, y)
            self.statusBar().showMessage(f"Captured {len(x)} points", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Capture Error", str(e))
        finally:
            self.sweep_btn.setEnabled(True)
    
    def sweep_smu(self):
        QMessageBox.information(self, "Info", "SMU sweep mode - implement based on curve_tracer.py")
    
    def on_save_setup(self):
        try:
            filename, _ = QFileDialog.getSaveFileName(self, "Save Setup", "", "JSON Files (*.json)")
            if not filename:
                return
            data = {
                'visa': self.visa_edit.text(),
                'mode': self.mode_combo.currentText(),
                'channel': self.channel_combo.currentText(),
                'function': self.function_combo.currentText(),
                'plot': self.plot_combo.currentText(),
                'sweep_form': self.sweep_form_combo.currentText(),
                'sweep_points': self.sweep_points_spin.value(),
                'sweep_start': self.sweep_start.value(),
                'sweep_stop': self.sweep_stop.value(),
                'ch_x': self.xy_chx_combo.currentText(),
                'ch_y': self.xy_chy_combo.currentText(),
                'probe_x': self.xy_probex_spin.value(),
                'probe_y': self.xy_probey_spin.value(),
                'shunt': self.xy_shunt_spin.value(),
                'invert': self.xy_invert_check.isChecked(),
                'direct_current': self.xy_direct_cur_check.isChecked(),
            }
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
            self.statusBar().showMessage(f"Setup saved: {filename}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
    
    def on_load_setup(self):
        try:
            filename, _ = QFileDialog.getOpenFileName(self, "Load Setup", "", "JSON Files (*.json)")
            if not filename:
                return
            with open(filename, 'r') as f:
                data = json.load(f)
            if 'visa' in data:
                self.visa_edit.setText(data['visa'])
            if 'mode' in data:
                idx = self.mode_combo.findText(data['mode'])
                if idx >= 0:
                    self.mode_combo.setCurrentIndex(idx)
            if 'ch_x' in data:
                idx = self.xy_chx_combo.findText(data['ch_x'])
                if idx >= 0:
                    self.xy_chx_combo.setCurrentIndex(idx)
            if 'ch_y' in data:
                idx = self.xy_chy_combo.findText(data['ch_y'])
                if idx >= 0:
                    self.xy_chy_combo.setCurrentIndex(idx)
            if 'shunt' in data:
                self.xy_shunt_spin.setValue(data['shunt'])
            if 'invert' in data:
                self.xy_invert_check.setChecked(data['invert'])
            if 'direct_current' in data:
                self.xy_direct_cur_check.setChecked(data['direct_current'])
            self.statusBar().showMessage(f"Setup loaded: {filename}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
    
    def on_save_data(self):
        if self.last_data is None:
            QMessageBox.warning(self, "Error", "No data to save")
            return
        try:
            filename, _ = QFileDialog.getSaveFileName(self, "Save Data", "", "CSV Files (*.csv)")
            if not filename:
                return
            x, y = self.last_data
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['X_V', 'Y_A'])
                for xi, yi in zip(x, y):
                    writer.writerow([xi, yi])
            self.statusBar().showMessage(f"Data saved: {filename}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
    
    def on_load_data(self):
        try:
            filename, _ = QFileDialog.getOpenFileName(self, "Load Data", "", "CSV Files (*.csv)")
            if not filename:
                return
            x, y = [], []
            with open(filename, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        x.append(float(row.get('X_V') or row.get('X') or row.get('x') or row.get('V') or 0))
                        y.append(float(row.get('Y_A') or row.get('Y') or row.get('y') or row.get('I') or 0))
                    except:
                        pass
            if not x:
                QMessageBox.warning(self, "Error", "Could not parse data")
                return
            x = np.array(x)
            y = np.array(y)
            self.ax.clear()
            self.ax.plot(x, y, 'r-', linewidth=1)
            self.ax.set_xlabel('X (V)')
            self.ax.set_ylabel('Y (A/V)')
            self.ax.grid(self.grid_check.isChecked())
            self.ax.set_title('Loaded Data')
            self.canvas.draw()
            self.last_data = (x, y)
            self.statusBar().showMessage(f"Loaded {len(x)} points", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
    
    def on_print_screen(self):
        try:
            filename, _ = QFileDialog.getSaveFileName(self, "Save Screenshot", "", "PNG Files (*.png);;JPG Files (*.jpg);;BMP Files (*.bmp)")
            if not filename:
                return
            self.figure.savefig(filename, dpi=150, bbox_inches='tight')
            self.statusBar().showMessage(f"Screenshot saved: {filename}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
    
    def on_cal(self):
        QMessageBox.information(self, "Calibration", "Calibration not implemented for this mode.")


def main():
    app = QApplication(sys.argv)
    window = CurveTracerMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
