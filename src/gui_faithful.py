#!/usr/bin/env python3
"""
CurveTracer OSS - Faithful reproduction of Yokogawa GS610/GS820 CurveTracer Software
"""

import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                              QHBoxLayout, QPushButton, QLabel, QComboBox,
                              QSpinBox, QDoubleSpinBox, QGroupBox, QTabWidget,
                              QCheckBox, QLineEdit, QTextEdit, QGridLayout,
                              QFrame, QFileDialog, QMessageBox, QSplitter)
from PyQt6.QtCore import Qt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import numpy as np


class CurveTracerMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GS820_CurveTracer - CurveTracer OSS")
        self.setGeometry(50, 50, 1400, 900)
        self.initUI()
    
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
        
        # Sub-condition (for dual channel)
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
        self.visa_combo = QComboBox()
        self.visa_combo.addItems(["USB::0xB21::0x39::123456::INSTR", "TCPIP::192.168.1.100::INSTR"])
        op_layout.addWidget(self.visa_combo)
        self.connect_btn = QPushButton("CONNECT")
        op_layout.addWidget(self.connect_btn)
        self.sweep_btn = QPushButton("SWEEP")
        op_layout.addWidget(self.sweep_btn)
        op_layout.addWidget(QLabel("Update:"))
        self.update_rate_label = QLabel("0.0s")
        op_layout.addWidget(self.update_rate_label)
        op_layout.addStretch()
        layout.addLayout(op_layout)
        
        # Mode selection (add X-Y oscilloscope mode)
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["SMU (GS610/GS820)", "Analog Curve Tracer (X-Y via Oscilloscope)"])
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)
        
        # X-Y oscilloscope settings (initially hidden conceptually)
        xy_group = QGroupBox("X-Y Oscilloscope Settings")
        xy_layout = QGridLayout(xy_group)
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
        xy_layout.addWidget(self.xy_shunt_spin, 2, 3)
        xy_layout.addWidget(QLabel("Invert Y"), 3, 0)
        self.xy_invert_check = QCheckBox()
        xy_layout.addWidget(self.xy_invert_check, 3, 1)
        layout.addWidget(xy_group)
        
        # Graph area
        graph_widget = QWidget()
        graph_layout = QVBoxLayout(graph_widget)
        
        # Graph controls
        graph_ctrl_layout = QHBoxLayout()
        graph_ctrl_layout.addWidget(QLabel("Grid"))
        self.grid_check = QCheckBox()
        self.grid_check.setChecked(True)
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


def main():
    app = QApplication(sys.argv)
    window = CurveTracerMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
