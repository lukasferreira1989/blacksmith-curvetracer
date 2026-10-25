#!/usr/bin/env python3
"""
Janela de cadastro, gerenciamento e comparação de componentes.

A janela é independente do fluxo de captura: recebe dois callbacks da janela
principal para obter a última captura e disparar uma nova aquisição. Toda a
persistência é feita em SQLite por :class:`component_db.ComponentDB`.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

try:
    from component_db import ComponentDB, Capture, detect_image_mime
    from component_compare import compare_curves
except Exception:
    from src.component_db import ComponentDB, Capture, detect_image_mime
    from src.component_compare import compare_curves

LiveCapture = tuple[np.ndarray, np.ndarray, str, str]


class PinMapLabel(QWidget):
    """Prévia da imagem com marcadores de pinos clicáveis.

    As coordenadas dos pinos são normalizadas (0..1) em relação à imagem,
    portanto permanecem válidas quando a janela é redimensionada.
    """

    pinAdded = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._pins: list = []
        self._add_mode = False
        self.setMinimumSize(320, 240)
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def has_image(self) -> bool:
        return self._pixmap is not None and not self._pixmap.isNull()

    def set_image_bytes(self, data: bytes) -> None:
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            raise ValueError("Could not decode the image")
        self._pixmap = pixmap
        self.update()

    def clear_image(self) -> None:
        self._pixmap = None
        self.update()

    def set_pins(self, pins) -> None:
        self._pins = list(pins)
        self.update()

    def set_add_mode(self, enabled: bool) -> None:
        self._add_mode = bool(enabled)
        self.setCursor(
            Qt.CursorShape.CrossCursor if self._add_mode
            else Qt.CursorShape.ArrowCursor
        )

    def is_add_mode(self) -> bool:
        return self._add_mode

    def image_rect(self) -> QRectF:
        """Área ocupada pela imagem dentro do widget (letterbox)."""
        if not self.has_image():
            return QRectF()
        area = self.rect().adjusted(4, 4, -4, -4)
        if area.width() <= 0 or area.height() <= 0:
            return QRectF()
        scale = min(
            area.width() / self._pixmap.width(),
            area.height() / self._pixmap.height(),
        )
        width = self._pixmap.width() * scale
        height = self._pixmap.height() * scale
        left = area.left() + (area.width() - width) / 2.0
        top = area.top() + (area.height() - height) / 2.0
        return QRectF(left, top, width, height)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#f4f4f4"))

        rect = self.image_rect()
        if rect.isEmpty():
            painter.setPen(QColor("#777777"))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "No reference image\n(load a PNG or JPEG)",
            )
            return

        painter.drawPixmap(rect.toRect(), self._pixmap)

        for pin in self._pins:
            if pin.x is None or pin.y is None:
                continue
            px = rect.left() + float(pin.x) * rect.width()
            py = rect.top() + float(pin.y) * rect.height()
            radius = 10.0
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.setBrush(QColor("#d62728"))
            painter.drawEllipse(QRectF(px - radius, py - radius, 2 * radius, 2 * radius))
            painter.setPen(QColor("#ffffff"))
            font = QFont()
            font.setBold(True)
            font.setPointSize(8)
            painter.setFont(font)
            painter.drawText(
                QRectF(px - radius, py - radius, 2 * radius, 2 * radius),
                Qt.AlignmentFlag.AlignCenter,
                str(pin.number),
            )

    def mousePressEvent(self, event) -> None:
        if (
            self._add_mode
            and event.button() == Qt.MouseButton.LeftButton
        ):
            rect = self.image_rect()
            if not rect.isEmpty() and rect.contains(event.position()):
                nx = (event.position().x() - rect.left()) / rect.width()
                ny = (event.position().y() - rect.top()) / rect.height()
                self.pinAdded.emit(float(nx), float(ny))
                return
        super().mousePressEvent(event)


class ComponentManagerDialog(QDialog):
    """Cadastro, capturas e comparação de componentes."""

    def __init__(
        self,
        db_path: str | os.PathLike | None = None,
        get_live_capture: Callable[[], LiveCapture | None] | None = None,
        capture_now: Callable[[], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Component Registry - Curve Tracer OSS")
        self.resize(1280, 860)

        self.db = ComponentDB(db_path)
        self._get_live_capture = get_live_capture
        self._capture_now = capture_now
        self.current_id: int | None = None
        self._loading = False
        self._image_state = "unchanged"  # unchanged | loaded | cleared
        self._image_bytes: bytes | None = None
        self._image_name: str | None = None
        self._image_mime: str | None = None
        self._live_capture: LiveCapture | None = None
        self._last_comparison = None

        self._build_ui()
        self._connect_signals()
        self.refresh_components()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        title = QLabel("<b>Component Registry</b>")
        header.addWidget(title)
        self.db_path_label = QLabel(str(self.db.path))
        self.db_path_label.setToolTip(str(self.db.path))
        self.db_path_label.setStyleSheet("color: #666666;")
        self.db_path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        header.addWidget(self.db_path_label, 1)
        self.new_btn = QPushButton("NEW")
        self.delete_btn = QPushButton("DELETE")
        self.close_btn = QPushButton("CLOSE")
        header.addWidget(self.new_btn)
        header.addWidget(self.delete_btn)
        header.addWidget(self.close_btn)
        layout.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        # ---- left: component list -------------------------------------
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Components"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter by reference, manufacturer or tag")
        left_layout.addWidget(self.search_edit)
        self.component_list = QListWidget()
        left_layout.addWidget(self.component_list, 1)
        self.component_count = QLabel("0 component(s)")
        left_layout.addWidget(self.component_count)
        splitter.addWidget(left)

        # ---- right: tabs ----------------------------------------------
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_profile_tab(), "Profile & Pins")
        self.tabs.addTab(self._build_captures_tab(), "Captures")
        self.tabs.addTab(self._build_compare_tab(), "Compare")
        splitter.addWidget(self.tabs)
        splitter.setSizes([300, 980])

        bottom = QHBoxLayout()
        self.status_label = QLabel("Ready")
        bottom.addWidget(self.status_label, 1)
        layout.addLayout(bottom)

    def _build_profile_tab(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)

        left = QWidget()
        left_layout = QVBoxLayout(left)

        meta_group = QGroupBox("Metadata")
        form = QFormLayout(meta_group)
        self.reference_edit = QLineEdit()
        self.reference_edit.setPlaceholderText("e.g. 2N3904, LM358, J1")
        self.manufacturer_edit = QLineEdit()
        self.package_edit = QLineEdit()
        self.package_edit.setPlaceholderText("e.g. TO-92, SOIC-8")
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("e.g. NPN, BJT, through-hole")
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setMaximumHeight(90)
        form.addRow("Reference *", self.reference_edit)
        form.addRow("Manufacturer", self.manufacturer_edit)
        form.addRow("Package", self.package_edit)
        form.addRow("Tags", self.tags_edit)
        form.addRow("Notes", self.notes_edit)
        left_layout.addWidget(meta_group)

        image_group = QGroupBox("Reference image and pin map")
        image_layout = QVBoxLayout(image_group)
        image_buttons = QHBoxLayout()
        self.load_image_btn = QPushButton("LOAD Image")
        self.clear_image_btn = QPushButton("CLEAR Image")
        self.image_info_label = QLabel("No image")
        self.image_info_label.setStyleSheet("color: #666666;")
        image_buttons.addWidget(self.load_image_btn)
        image_buttons.addWidget(self.clear_image_btn)
        image_buttons.addWidget(self.image_info_label, 1)
        image_layout.addLayout(image_buttons)
        self.pin_map = PinMapLabel()
        image_layout.addWidget(self.pin_map, 1)
        left_layout.addWidget(image_group, 1)
        layout.addWidget(left, 3)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        pin_group = QGroupBox("Pins")
        pin_layout = QVBoxLayout(pin_group)
        pin_buttons = QHBoxLayout()
        self.add_pin_btn = QPushButton("ADD Pin on image")
        self.add_pin_btn.setCheckable(True)
        self.add_pin_no_pos_btn = QPushButton("ADD Pin without position")
        self.remove_pin_btn = QPushButton("REMOVE Pin")
        pin_buttons.addWidget(self.add_pin_btn)
        pin_buttons.addWidget(self.add_pin_no_pos_btn)
        pin_buttons.addWidget(self.remove_pin_btn)
        pin_buttons.addStretch()
        pin_layout.addLayout(pin_buttons)

        self.pin_table = QTableWidget(0, 4)
        self.pin_table.setHorizontalHeaderLabels(["Number", "Label", "X (0..1)", "Y (0..1)"])
        self.pin_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.pin_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.pin_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.pin_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.pin_table.verticalHeader().setVisible(False)
        pin_layout.addWidget(self.pin_table, 1)
        hint = QLabel(
            "Enable ADD Pin on image and click the component photo to place "
            "each pin. Coordinates are stored normalized (0..1), so they "
            "scale with the window."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666666;")
        pin_layout.addWidget(hint)
        right_layout.addWidget(pin_group, 1)

        self.save_profile_btn = QPushButton("SAVE Component Profile")
        right_layout.addWidget(self.save_profile_btn)
        layout.addWidget(right, 2)
        return page

    def _build_captures_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        controls = QGroupBox("Associate a V-I capture with this component")
        grid = QVBoxLayout(controls)
        row = QHBoxLayout()
        row.addWidget(QLabel("Label"))
        self.capture_label_edit = QLineEdit()
        self.capture_label_edit.setPlaceholderText("e.g. B-E forward, C-E breakdown")
        row.addWidget(self.capture_label_edit, 1)
        row.addWidget(QLabel("Pin A"))
        self.capture_pin_a_combo = QComboBox()
        row.addWidget(self.capture_pin_a_combo)
        row.addWidget(QLabel("Pin B"))
        self.capture_pin_b_combo = QComboBox()
        row.addWidget(self.capture_pin_b_combo)
        grid.addLayout(row)

        buttons = QHBoxLayout()
        self.save_capture_btn = QPushButton("SAVE Current Capture")
        self.import_capture_btn = QPushButton("IMPORT CSV")
        self.delete_capture_btn = QPushButton("DELETE Capture")
        buttons.addWidget(self.save_capture_btn)
        buttons.addWidget(self.import_capture_btn)
        buttons.addWidget(self.delete_capture_btn)
        buttons.addStretch()
        grid.addLayout(buttons)
        layout.addWidget(controls)

        self.capture_table = QTableWidget(0, 7)
        self.capture_table.setHorizontalHeaderLabels(
            ["ID", "Label", "Pin A", "Pin B", "Points", "Units", "Created"]
        )
        self.capture_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.capture_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.capture_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.capture_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self.capture_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents
        )
        self.capture_table.horizontalHeader().setSectionResizeMode(
            5, QHeaderView.ResizeMode.ResizeToContents
        )
        self.capture_table.horizontalHeader().setSectionResizeMode(
            6, QHeaderView.ResizeMode.ResizeToContents
        )
        self.capture_table.verticalHeader().setVisible(False)
        self.capture_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.capture_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.capture_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        layout.addWidget(self.capture_table, 1)

        hint = QLabel(
            "Captures keep every acquired sample in acquisition order. "
            "Use the Compare tab to overlay a saved capture with a live one."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666666;")
        layout.addWidget(hint)
        return page

    def _build_compare_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        controls = QGroupBox("Saved reference vs. live capture")
        grid = QVBoxLayout(controls)
        row = QHBoxLayout()
        row.addWidget(QLabel("Saved capture"))
        self.reference_combo = QComboBox()
        row.addWidget(self.reference_combo, 1)
        row.addWidget(QLabel("Tolerance"))
        self.tolerance_spin = QDoubleSpinBox()
        self.tolerance_spin.setRange(0.1, 100.0)
        self.tolerance_spin.setDecimals(1)
        self.tolerance_spin.setValue(5.0)
        self.tolerance_spin.setSuffix(" %")
        self.tolerance_spin.setToolTip(
            "Maximum normalized RMS error relative to the reference Y span"
        )
        row.addWidget(self.tolerance_spin)
        grid.addLayout(row)

        buttons = QHBoxLayout()
        self.use_current_btn = QPushButton("USE Current Capture")
        self.capture_compare_btn = QPushButton("CAPTURE + COMPARE")
        self.compare_btn = QPushButton("COMPARE")
        buttons.addWidget(self.use_current_btn)
        buttons.addWidget(self.capture_compare_btn)
        buttons.addWidget(self.compare_btn)
        buttons.addStretch()
        grid.addLayout(buttons)
        layout.addWidget(controls)

        split = QSplitter(Qt.Orientation.Vertical)
        self.compare_figure = Figure(figsize=(8, 5))
        self.compare_canvas = FigureCanvas(self.compare_figure)
        self.compare_ax = self.compare_figure.add_subplot(111)
        self.compare_ax.set_xlabel("X")
        self.compare_ax.set_ylabel("Y")
        self.compare_ax.grid(True)
        self.compare_ax.set_title("Saved reference vs. live capture")
        self.compare_toolbar = NavigationToolbar(
            self.compare_canvas, page, coordinates=False
        )
        plot_widget = QWidget()
        plot_layout = QVBoxLayout(plot_widget)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        plot_layout.addWidget(self.compare_toolbar)
        plot_layout.addWidget(self.compare_canvas)
        split.addWidget(plot_widget)

        self.metrics_text = QPlainTextEdit()
        self.metrics_text.setReadOnly(True)
        self.metrics_text.setPlaceholderText(
            "Select a saved capture, load a live capture and press COMPARE."
        )
        self.metrics_text.setMaximumHeight(170)
        split.addWidget(self.metrics_text)
        split.setSizes([440, 170])
        layout.addWidget(split, 1)
        return page

    def _connect_signals(self) -> None:
        self.close_btn.clicked.connect(self.accept)
        self.new_btn.clicked.connect(self.new_component)
        self.delete_btn.clicked.connect(self.delete_component)
        self.component_list.currentItemChanged.connect(self._on_component_selected)
        self.search_edit.textChanged.connect(self.refresh_components)
        self.save_profile_btn.clicked.connect(self.save_profile)
        self.load_image_btn.clicked.connect(self.load_image)
        self.clear_image_btn.clicked.connect(self.clear_image)
        self.add_pin_btn.toggled.connect(self._on_add_pin_mode)
        self.add_pin_no_pos_btn.clicked.connect(self.add_pin_without_position)
        self.remove_pin_btn.clicked.connect(self.remove_selected_pin)
        self.pin_map.pinAdded.connect(self._on_pin_map_clicked)
        self.pin_table.itemChanged.connect(self._on_pin_item_changed)
        self.save_capture_btn.clicked.connect(self.save_current_capture)
        self.import_capture_btn.clicked.connect(self.import_capture_csv)
        self.delete_capture_btn.clicked.connect(self.delete_selected_capture)
        self.capture_table.itemSelectionChanged.connect(self._on_capture_selected)
        self.use_current_btn.clicked.connect(self.use_current_capture)
        self.capture_compare_btn.clicked.connect(self.capture_and_compare)
        self.compare_btn.clicked.connect(self.compare_now)

    # ------------------------------------------------------------------
    # Component list / profile
    # ------------------------------------------------------------------
    def refresh_components(self, select_id: int | None = None) -> None:
        if select_id is None:
            select_id = self.current_id
        query = self.search_edit.text().strip().lower() if hasattr(self, "search_edit") else ""

        self._loading = True
        try:
            self.component_list.clear()
            components = self.db.list_components()
            shown = 0
            for component in components:
                haystack = " ".join(
                    (component.reference, component.manufacturer, component.tags)
                ).lower()
                if query and query not in haystack:
                    continue
                shown += 1
                label = component.reference
                if component.manufacturer:
                    label += f"  ·  {component.manufacturer}"
                if component.package:
                    label += f"  ·  {component.package}"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, component.id)
                tooltip = [
                    f"Reference: {component.reference}",
                    f"Pins: {len(component.pins)}",
                    f"Captures: {len(component.captures)}",
                ]
                if component.has_image:
                    tooltip.append("Reference image: yes")
                item.setToolTip("\n".join(tooltip))
                self.component_list.addItem(item)
                if component.id == select_id:
                    self.component_list.setCurrentItem(item)
            self.component_count.setText(
                f"{shown} of {len(components)} component(s)"
                if query else f"{len(components)} component(s)"
            )
        finally:
            self._loading = False

        if select_id is None and self.component_list.count() == 0:
            self._clear_editor()

    def _clear_editor(self) -> None:
        self._loading = True
        try:
            self.current_id = None
            self.reference_edit.clear()
            self.manufacturer_edit.clear()
            self.package_edit.clear()
            self.tags_edit.clear()
            self.notes_edit.clear()
            self.pin_table.setRowCount(0)
            self.capture_table.setRowCount(0)
            self._image_state = "unchanged"
            self._image_bytes = None
            self._image_name = None
            self._image_mime = None
            self.pin_map.clear_image()
            self.pin_map.set_pins([])
            self.image_info_label.setText("No image")
            self._reload_pin_combos()
            self._reload_reference_combo()
            self._last_comparison = None
            self.metrics_text.clear()
            self.compare_ax.clear()
            self.compare_ax.grid(True)
            self.compare_ax.set_title("Saved reference vs. live capture")
            self.compare_canvas.draw_idle()
        finally:
            self._loading = False
        self.status_label.setText("New component (not saved yet)")

    def new_component(self) -> None:
        self.current_id = None
        self.component_list.clearSelection()
        self._clear_editor()
        self.tabs.setCurrentIndex(0)
        self.reference_edit.setFocus()

    def _on_component_selected(self, current, previous=None) -> None:
        if self._loading or current is None:
            return
        component_id = current.data(Qt.ItemDataRole.UserRole)
        if component_id is None:
            return
        self.load_component(int(component_id))

    def load_component(self, component_id: int) -> None:
        component = self.db.get_component(component_id)
        if component is None:
            self.status_label.setText(f"Component {component_id} not found")
            return

        self._loading = True
        try:
            self.current_id = component.id
            self.reference_edit.setText(component.reference)
            self.manufacturer_edit.setText(component.manufacturer)
            self.package_edit.setText(component.package)
            self.tags_edit.setText(component.tags)
            self.notes_edit.setPlainText(component.notes)
            self._reload_pins_table(component.pins)
            self._reload_pin_combos(component.pins)
            self._reload_captures_table(component.captures)

            name, mime, blob = self.db.get_component_image(component.id)
            self._image_state = "unchanged"
            self._image_name = name
            self._image_mime = mime
            self._image_bytes = blob
            if blob:
                try:
                    self.pin_map.set_image_bytes(blob)
                    self.image_info_label.setText(
                        f"{name or 'image'} ({mime or 'unknown'})"
                    )
                except ValueError:
                    self.pin_map.clear_image()
                    self.image_info_label.setText("Stored image could not be decoded")
            else:
                self.pin_map.clear_image()
                self.image_info_label.setText("No image")
            self.pin_map.set_pins(component.pins)
        finally:
            self._loading = False

        self.status_label.setText(
            f"Loaded {component.reference} ({len(component.pins)} pins, "
            f"{len(component.captures)} captures)"
        )

    def save_profile(self, show_messages: bool = True) -> int | None:
        reference = self.reference_edit.text().strip()
        if not reference:
            self.status_label.setText("Reference is required")
            if show_messages:
                QMessageBox.warning(self, "Reference required",
                                    "Enter a component reference before saving.")
            return None

        fields = {
            "reference": reference,
            "manufacturer": self.manufacturer_edit.text().strip(),
            "package": self.package_edit.text().strip(),
            "tags": self.tags_edit.text().strip(),
            "notes": self.notes_edit.toPlainText().strip(),
        }
        try:
            if self.current_id is None:
                self.current_id = self.db.create_component(**fields)
            else:
                self.db.update_component(self.current_id, **fields)

            if self._image_state == "loaded" and self._image_bytes is not None:
                self.db.set_component_image(
                    self.current_id,
                    self._image_bytes,
                    self._image_name or "component.png",
                    self._image_mime,
                )
            elif self._image_state == "cleared":
                self.db.clear_component_image(self.current_id)
            self._image_state = "unchanged"

            component_id = self.current_id
            self.refresh_components(select_id=component_id)
            # refresh_components dispara a seleção e recarrega o formulário
            self.load_component(component_id)
            self.status_label.setText(f"Saved component '{reference}'")
            return component_id
        except Exception as exc:
            self.status_label.setText(f"Save error: {exc}")
            if show_messages:
                QMessageBox.critical(self, "Save error", str(exc))
            return None

    def _ensure_component(self) -> int | None:
        if self.current_id is not None:
            return self.current_id
        return self.save_profile(show_messages=True)

    def delete_component(self) -> None:
        if self.current_id is None:
            self.status_label.setText("No component selected")
            return
        component = self.db.get_component(self.current_id)
        if component is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete component",
            f"Delete '{component.reference}' and all its pins and captures?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.db.delete_component(component.id)
        self.current_id = None
        self.refresh_components(select_id=None)
        self._clear_editor()
        self.status_label.setText(f"Deleted '{component.reference}'")

    # ------------------------------------------------------------------
    # Image
    # ------------------------------------------------------------------
    def load_image(self, filename: str | None = None) -> None:
        if filename is None:
            filename, _ = QFileDialog.getOpenFileName(
                self, "Load component image", "",
                "Images (*.png *.jpg *.jpeg)",
            )
        if not filename:
            return
        try:
            data = Path(filename).read_bytes()
            mime = detect_image_mime(data)
            self.pin_map.set_image_bytes(data)
            self._image_bytes = data
            self._image_name = Path(filename).name
            self._image_mime = mime
            self._image_state = "loaded"
            self.image_info_label.setText(f"{self._image_name} ({mime})")
            self.status_label.setText(
                "Image loaded - press SAVE Component Profile to persist it"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Image error", str(exc))

    def clear_image(self) -> None:
        self.pin_map.clear_image()
        self.pin_map.set_pins([])
        self._image_state = "cleared"
        self._image_bytes = None
        self._image_name = None
        self._image_mime = None
        self.image_info_label.setText("No image")
        self.status_label.setText("Image cleared (save the profile to persist)")

    # ------------------------------------------------------------------
    # Pins
    # ------------------------------------------------------------------
    def _next_pin_number(self, pins=None) -> str:
        pins = list(pins) if pins is not None else self.db.list_pins(self.current_id)
        numbers = {str(pin.number) for pin in pins}
        candidate = 1
        while str(candidate) in numbers:
            candidate += 1
        return str(candidate)

    def _on_add_pin_mode(self, enabled: bool) -> None:
        if enabled and not self.pin_map.has_image():
            self.status_label.setText("Load a reference image before placing pins")
        self.pin_map.set_add_mode(enabled)

    def _on_pin_map_clicked(self, x: float, y: float) -> None:
        component_id = self._ensure_component()
        if component_id is None:
            return
        try:
            number = self._next_pin_number()
            self.db.add_pin(component_id, number, "", x, y)
            self._reload_pins()
            self.status_label.setText(
                f"Pin {number} added at ({x:.3f}, {y:.3f})"
            )
        except Exception as exc:
            self.status_label.setText(f"Pin error: {exc}")

    def add_pin_without_position(self) -> None:
        component_id = self._ensure_component()
        if component_id is None:
            return
        try:
            number = self._next_pin_number()
            self.db.add_pin(component_id, number)
            self._reload_pins()
            self.status_label.setText(f"Pin {number} added (no position)")
        except Exception as exc:
            self.status_label.setText(f"Pin error: {exc}")

    def remove_selected_pin(self) -> None:
        row = self.pin_table.currentRow()
        if row < 0:
            self.status_label.setText("Select a pin to remove")
            return
        item = self.pin_table.item(row, 0)
        pin_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        if pin_id is None:
            return
        self.db.delete_pin(int(pin_id))
        self._reload_pins()
        self.status_label.setText("Pin removed")

    def _reload_pins(self) -> None:
        if self.current_id is None:
            self._reload_pins_table([])
            return
        pins = self.db.list_pins(self.current_id)
        self._reload_pins_table(pins)
        self._reload_pin_combos(pins)
        self.pin_map.set_pins(pins)

    def _reload_pins_table(self, pins) -> None:
        was_loading = self._loading
        self._loading = True
        try:
            self.pin_table.setRowCount(0)
            for pin in pins:
                row = self.pin_table.rowCount()
                self.pin_table.insertRow(row)
                number_item = QTableWidgetItem(str(pin.number))
                number_item.setData(Qt.ItemDataRole.UserRole, pin.id)
                self.pin_table.setItem(row, 0, number_item)
                self.pin_table.setItem(row, 1, QTableWidgetItem(pin.label or ""))
                self.pin_table.setItem(
                    row, 2, QTableWidgetItem("" if pin.x is None else f"{pin.x:.5f}")
                )
                self.pin_table.setItem(
                    row, 3, QTableWidgetItem("" if pin.y is None else f"{pin.y:.5f}")
                )
        finally:
            self._loading = was_loading

    def _on_pin_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading or self.current_id is None:
            return
        row = item.row()
        id_item = self.pin_table.item(row, 0)
        if id_item is None:
            return
        pin_id = id_item.data(Qt.ItemDataRole.UserRole)
        if pin_id is None:
            return

        column = item.column()
        try:
            if column == 0:
                self.db.update_pin(int(pin_id), number=item.text())
            elif column == 1:
                self.db.update_pin(int(pin_id), label=item.text())
            elif column in (2, 3):
                text = item.text().strip()
                value = None if not text else float(text)
                if value is not None and not 0.0 <= value <= 1.0:
                    raise ValueError("coordinate must be between 0 and 1")
                if column == 2:
                    self.db.update_pin(int(pin_id), x=value)
                else:
                    self.db.update_pin(int(pin_id), y=value)
            else:
                return
        except Exception as exc:
            self.status_label.setText(f"Pin update error: {exc}")
            self._reload_pins()
            return

        self._reload_pins()

    def _reload_pin_combos(self, pins=None) -> None:
        if pins is None:
            pins = self.db.list_pins(self.current_id) if self.current_id else []
        for combo in (self.capture_pin_a_combo, self.capture_pin_b_combo):
            previous = combo.currentData()
            combo.clear()
            combo.addItem("—", None)
            for pin in pins:
                text = f"{pin.number}" + (f" · {pin.label}" if pin.label else "")
                combo.addItem(text, pin.id)
            if previous is not None:
                index = combo.findData(previous)
                if index >= 0:
                    combo.setCurrentIndex(index)

    # ------------------------------------------------------------------
    # Captures
    # ------------------------------------------------------------------
    def _reload_captures_table(self, captures) -> None:
        was_loading = self._loading
        self._loading = True
        try:
            self.capture_table.setRowCount(0)
            for capture in captures:
                row = self.capture_table.rowCount()
                self.capture_table.insertRow(row)
                id_item = QTableWidgetItem(str(capture.id))
                id_item.setData(Qt.ItemDataRole.UserRole, capture.id)
                self.capture_table.setItem(row, 0, id_item)
                self.capture_table.setItem(row, 1, QTableWidgetItem(capture.label or ""))
                self.capture_table.setItem(
                    row, 2, QTableWidgetItem(capture.pin_a_number or "—")
                )
                self.capture_table.setItem(
                    row, 3, QTableWidgetItem(capture.pin_b_number or "—")
                )
                self.capture_table.setItem(
                    row, 4, QTableWidgetItem(str(capture.n_points))
                )
                self.capture_table.setItem(
                    row, 5, QTableWidgetItem(f"{capture.x_unit} / {capture.y_unit}")
                )
                self.capture_table.setItem(
                    row, 6, QTableWidgetItem(capture.created_at)
                )
        finally:
            self._loading = was_loading
        self._reload_reference_combo(captures)

    def _reload_reference_combo(self, captures=None) -> None:
        if captures is None:
            captures = (
                self.db.list_captures(self.current_id) if self.current_id else []
            )
        previous = self.reference_combo.currentData()
        self.reference_combo.clear()
        for capture in captures:
            pins = ""
            if capture.pin_a_number or capture.pin_b_number:
                pins = (
                    f" [{capture.pin_a_number or '?'}–"
                    f"{capture.pin_b_number or '?'}]"
                )
            text = f"#{capture.id} · {capture.label or 'capture'}{pins} " \
                   f"({capture.n_points} pts)"
            self.reference_combo.addItem(text, capture.id)
        if previous is not None:
            index = self.reference_combo.findData(previous)
            if index >= 0:
                self.reference_combo.setCurrentIndex(index)

    def save_current_capture(self) -> None:
        component_id = self._ensure_component()
        if component_id is None:
            return
        live = self._get_live_capture() if callable(self._get_live_capture) else None
        if not callable(self._get_live_capture):
            live = self._live_capture
        if live is None:
            QMessageBox.information(
                self, "No live capture",
                "Capture a curve in the main window before saving it.",
            )
            return

        x, y, x_unit, y_unit = live
        label = self.capture_label_edit.text().strip()
        if not label:
            label = f"Capture {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        try:
            capture_id = self.db.add_capture(
                component_id,
                x,
                y,
                label=label,
                pin_a=self.capture_pin_a_combo.currentData(),
                pin_b=self.capture_pin_b_combo.currentData(),
                x_unit=x_unit,
                y_unit=y_unit,
            )
            captures = self.db.list_captures(component_id)
            self._reload_captures_table(captures)
            for row in range(self.capture_table.rowCount()):
                item = self.capture_table.item(row, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) == capture_id:
                    self.capture_table.selectRow(row)
                    break
            self.status_label.setText(
                f"Saved capture #{capture_id} with {len(x)} points"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Capture error", str(exc))

    def import_capture_csv(self, filename: str | None = None) -> None:
        component_id = self._ensure_component()
        if component_id is None:
            return
        if filename is None:
            filename, _ = QFileDialog.getOpenFileName(
                self, "Import capture CSV", "", "CSV Files (*.csv)"
            )
        if not filename:
            return

        try:
            xs: list[float] = []
            ys: list[float] = []
            with open(filename, "r", newline="") as handle:
                reader = csv.reader(handle)
                rows = list(reader)
            if not rows:
                raise ValueError("CSV is empty")

            header = [cell.strip().lower() for cell in rows[0]]
            x_keys = {"voltage_v", "v", "x", "voltage"}
            y_keys = {"current_a", "i", "y", "current"}
            has_header = any(cell in x_keys for cell in header) and any(
                cell in y_keys for cell in header
            )
            if has_header:
                x_index = next(i for i, cell in enumerate(header) if cell in x_keys)
                y_index = next(i for i, cell in enumerate(header) if cell in y_keys)
                data_rows = rows[1:]
            else:
                x_index, y_index = 0, 1
                data_rows = rows

            for row in data_rows:
                if len(row) <= max(x_index, y_index):
                    continue
                try:
                    xs.append(float(row[x_index]))
                    ys.append(float(row[y_index]))
                except (TypeError, ValueError):
                    continue
            if not xs:
                raise ValueError("Could not parse X/Y numeric columns")

            label = self.capture_label_edit.text().strip() or Path(filename).stem
            capture_id = self.db.add_capture(
                component_id,
                xs,
                ys,
                label=label,
                pin_a=self.capture_pin_a_combo.currentData(),
                pin_b=self.capture_pin_b_combo.currentData(),
                x_unit="V",
                y_unit="A",
            )
            captures = self.db.list_captures(component_id)
            self._reload_captures_table(captures)
            self.status_label.setText(
                f"Imported capture #{capture_id} ({len(xs)} points)"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Import error", str(exc))

    def _selected_capture_id(self) -> int | None:
        row = self.capture_table.currentRow()
        if row < 0:
            return None
        item = self.capture_table.item(row, 0)
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return int(value) if value is not None else None

    def _on_capture_selected(self) -> None:
        capture_id = self._selected_capture_id()
        if capture_id is not None:
            index = self.reference_combo.findData(capture_id)
            if index >= 0:
                self.reference_combo.setCurrentIndex(index)

    def delete_selected_capture(self) -> None:
        capture_id = self._selected_capture_id()
        if capture_id is None:
            self.status_label.setText("Select a capture to delete")
            return
        self.db.delete_capture(capture_id)
        if self.current_id is not None:
            self._reload_captures_table(self.db.list_captures(self.current_id))
        self.status_label.setText(f"Deleted capture #{capture_id}")

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------
    def use_current_capture(self) -> None:
        live = self._get_live_capture() if callable(self._get_live_capture) else None
        if live is None:
            QMessageBox.information(
                self, "No live capture",
                "Capture a curve in the main window first.",
            )
            return
        self._live_capture = live
        self.status_label.setText(
            f"Live capture loaded ({len(live[0])} points, "
            f"{live[2]} / {live[3]})"
        )
        if self.reference_combo.currentData() is not None:
            self.compare_now()

    def capture_and_compare(self) -> None:
        if not callable(self._capture_now):
            QMessageBox.information(
                self, "Capture unavailable",
                "This window was opened without an acquisition callback.",
            )
            return
        self._capture_now()
        self.use_current_capture()

    def compare_now(self) -> None:
        capture_id = self.reference_combo.currentData()
        if capture_id is None:
            QMessageBox.information(
                self, "No reference",
                "Select a saved capture to use as reference.",
            )
            return
        reference = self.db.get_capture(int(capture_id))
        if reference is None or reference.x is None or reference.y is None:
            QMessageBox.information(
                self, "Reference unavailable", "Saved capture could not be loaded."
            )
            return
        live = self._get_live_capture() if callable(self._get_live_capture) else None
        if not callable(self._get_live_capture):
            live = self._live_capture
        if live is None:
            QMessageBox.information(
                self, "No live capture",
                "Use the current capture or capture a new curve first.",
            )
            return
        self._live_capture = live

        if (reference.x_unit, reference.y_unit) != (live[2], live[3]):
            QMessageBox.warning(
                self, "Unit mismatch",
                f"Saved capture is in {reference.x_unit}/{reference.y_unit}, "
                f"live capture is in {live[2]}/{live[3]}. Save the live "
                "capture with the same units before comparing.",
            )
            return

        try:
            result = compare_curves(
                reference.x,
                reference.y,
                live[0],
                live[1],
                tolerance=self.tolerance_spin.value() / 100.0,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Comparison error", str(exc))
            return

        self._last_comparison = result
        self._plot_comparison(reference, live, result)
        self._show_metrics(reference, live, result)
        self.status_label.setText(f"Comparison: {result.verdict}")

    def _plot_comparison(self, reference: Capture, live: LiveCapture,
                         result) -> None:
        x_live, y_live, live_x_unit, live_y_unit = live
        self.compare_ax.clear()
        self.compare_ax.plot(
            reference.x, reference.y,
            color="#1f77b4", linewidth=1.4, label="Saved reference",
        )
        self.compare_ax.plot(
            x_live, y_live,
            color="#d62728", linewidth=1.1, alpha=0.85, label="Live capture",
        )
        self.compare_ax.set_xlabel(
            f"X [{reference.x_unit}]   (live: {live_x_unit})"
        )
        self.compare_ax.set_ylabel(
            f"Y [{reference.y_unit}]   (live: {live_y_unit})"
        )
        self.compare_ax.set_title(
            f"{reference.label or 'Saved capture'}  —  {result.verdict}"
        )
        self.compare_ax.grid(True)
        self.compare_ax.legend(loc="best", fontsize=8)
        self.compare_canvas.draw_idle()

    def _show_metrics(self, reference: Capture, live: LiveCapture,
                      result) -> None:
        correlation = (
            "n/a" if result.correlation is None
            else f"{result.correlation:.4f}"
        )
        overlap = (
            "n/a" if result.x_overlap is None
            else f"{result.x_overlap[0]:.6g} .. {result.x_overlap[1]:.6g}"
        )
        if result.method == "interpolation":
            error_detail = (
                f"RMS error: {result.nrmse * result.y_span_reference:.6g} "
                f"{reference.y_unit}   Max error: {result.max_error:.6g} "
                f"{reference.y_unit}   P95: {result.p95_error:.6g} "
                f"{reference.y_unit}"
            )
        else:
            error_detail = (
                f"Max normalized deviation: {result.max_error:.6g}   "
                f"P95: {result.p95_error:.6g} "
                f"(1.0 = reference span)"
            )

        text = (
            f"Verdict: {result.verdict}   "
            f"({'anomaly detected' if result.is_anomaly else 'within tolerance'})\n"
            f"Method: {result.method}   "
            f"Tolerance: {result.tolerance * 100:.1f}% of reference Y span\n"
            f"Samples: reference={result.n_reference}, live={result.n_live}, "
            f"compared={result.n_common}\n"
            f"NRMSE: {result.nrmse * 100:.2f}%   "
            f"Max normalized: {result.max_error_normalized * 100:.2f}%\n"
            f"{error_detail}\n"
            f"Correlation: {correlation}   X overlap: {overlap}\n"
            f"{result.message}"
        )
        self.metrics_text.setPlainText(text)
        colors = {
            "MATCH": ("#e8f5e9", "#1b5e20"),
            "WARNING": ("#fff8e1", "#8d6e00"),
            "DEVIATION": ("#ffebee", "#b71c1c"),
        }
        background, foreground = colors.get(result.verdict, ("#ffffff", "#000000"))
        self.metrics_text.setStyleSheet(
            f"background-color: {background}; color: {foreground};"
        )

    def closeEvent(self, event) -> None:
        self.db.close()
        super().closeEvent(event)

    def accept(self) -> None:
        self.db.close()
        super().accept()
