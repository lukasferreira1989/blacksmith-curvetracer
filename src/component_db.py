#!/usr/bin/env python3
"""
Persistência local de componentes eletrônicos (SQLite).

Um perfil de componente contém:
- metadados (referência, fabricante, encapsulamento, tags, observações);
- imagem de referência (PNG/JPEG armazenada como BLOB);
- pinos, com número, label e coordenadas normalizadas (0..1) na imagem;
- capturas V-I associadas a um par de pinos.

O módulo usa apenas a biblioteca padrão. As capturas são armazenadas em JSON
para manter a ordem temporal e todas as amostras sem transformação.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

DEFAULT_DB_ENV = "CURVETRACER_DB"


def default_db_path() -> Path:
    """Caminho padrão do banco, configurável por ``CURVETRACER_DB``."""
    env = os.environ.get(DEFAULT_DB_ENV)
    if env:
        return Path(env).expanduser()
    return Path.home() / ".curvetracer" / "components.db"


def detect_image_mime(data: bytes) -> str:
    """Detecta PNG/JPEG pelos magic bytes e rejeita outros formatos."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    raise ValueError("Unsupported image format (only PNG and JPEG are accepted)")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Pin:
    id: int
    component_id: int
    number: str
    label: str = ""
    x: float | None = None
    y: float | None = None


@dataclass
class Capture:
    id: int
    component_id: int
    label: str
    pin_a: int | None
    pin_b: int | None
    x_unit: str
    y_unit: str
    n_points: int
    created_at: str
    pin_a_number: str | None = None
    pin_b_number: str | None = None
    x: list[float] | None = None
    y: list[float] | None = None


@dataclass
class Component:
    id: int
    reference: str
    manufacturer: str = ""
    package: str = ""
    tags: str = ""
    notes: str = ""
    image_name: str | None = None
    image_mime: str | None = None
    created_at: str = ""
    updated_at: str = ""
    has_image: bool = False
    pins: list[Pin] = field(default_factory=list)
    captures: list[Capture] = field(default_factory=list)


class ComponentDB:
    """Banco SQLite de perfis de componentes."""

    def __init__(self, path: str | os.PathLike | None = None):
        self.path = Path(path).expanduser() if path is not None else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------
    def _create_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS components (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reference TEXT NOT NULL,
                    manufacturer TEXT NOT NULL DEFAULT '',
                    package TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    image_name TEXT,
                    image_mime TEXT,
                    image_blob BLOB,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS pins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    component_id INTEGER NOT NULL
                        REFERENCES components(id) ON DELETE CASCADE,
                    number TEXT NOT NULL,
                    label TEXT NOT NULL DEFAULT '',
                    x REAL,
                    y REAL,
                    UNIQUE(component_id, number)
                );

                CREATE TABLE IF NOT EXISTS captures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    component_id INTEGER NOT NULL
                        REFERENCES components(id) ON DELETE CASCADE,
                    label TEXT NOT NULL DEFAULT '',
                    pin_a INTEGER REFERENCES pins(id) ON DELETE SET NULL,
                    pin_b INTEGER REFERENCES pins(id) ON DELETE SET NULL,
                    x_unit TEXT NOT NULL DEFAULT 'V',
                    y_unit TEXT NOT NULL DEFAULT 'A',
                    x_json TEXT NOT NULL,
                    y_json TEXT NOT NULL,
                    n_points INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_pins_component
                    ON pins(component_id);
                CREATE INDEX IF NOT EXISTS idx_captures_component
                    ON captures(component_id);
                """
            )

    # ------------------------------------------------------------------
    # Components
    # ------------------------------------------------------------------
    def create_component(
        self,
        reference: str,
        manufacturer: str = "",
        package: str = "",
        tags: str = "",
        notes: str = "",
    ) -> int:
        reference = (reference or "").strip()
        if not reference:
            raise ValueError("Component reference is required")
        now = _now()
        with self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO components
                    (reference, manufacturer, package, tags, notes,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (reference, manufacturer, package, tags, notes, now, now),
            )
        return int(cur.lastrowid)

    def update_component(self, component_id: int, **fields) -> None:
        allowed = {"reference", "manufacturer", "package", "tags", "notes"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unsupported component fields: {sorted(unknown)}")
        if not fields:
            return
        if "reference" in fields and not str(fields["reference"]).strip():
            raise ValueError("Component reference is required")

        assignments = ", ".join(f"{name} = ?" for name in fields)
        values = list(fields.values())
        with self._conn:
            cur = self._conn.execute(
                f"UPDATE components SET {assignments}, updated_at = ? WHERE id = ?",
                (*values, _now(), int(component_id)),
            )
        if cur.rowcount == 0:
            raise KeyError(f"Component {component_id} not found")

    def delete_component(self, component_id: int) -> bool:
        with self._conn:
            cur = self._conn.execute(
                "DELETE FROM components WHERE id = ?", (int(component_id),)
            )
        return cur.rowcount > 0

    def list_components(self) -> list[Component]:
        rows = self._conn.execute(
            """
            SELECT id, reference, manufacturer, package, tags, notes,
                   image_name, image_mime, created_at, updated_at,
                   (image_blob IS NOT NULL) AS has_image
            FROM components
            ORDER BY reference COLLATE NOCASE, id
            """
        ).fetchall()
        return [
            Component(
                id=row["id"],
                reference=row["reference"],
                manufacturer=row["manufacturer"],
                package=row["package"],
                tags=row["tags"],
                notes=row["notes"],
                image_name=row["image_name"],
                image_mime=row["image_mime"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                has_image=bool(row["has_image"]),
            )
            for row in rows
        ]

    def get_component(self, component_id: int) -> Component | None:
        row = self._conn.execute(
            """
            SELECT id, reference, manufacturer, package, tags, notes,
                   image_name, image_mime, created_at, updated_at,
                   (image_blob IS NOT NULL) AS has_image
            FROM components WHERE id = ?
            """,
            (int(component_id),),
        ).fetchone()
        if row is None:
            return None
        component = Component(
            id=row["id"],
            reference=row["reference"],
            manufacturer=row["manufacturer"],
            package=row["package"],
            tags=row["tags"],
            notes=row["notes"],
            image_name=row["image_name"],
            image_mime=row["image_mime"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            has_image=bool(row["has_image"]),
            pins=self.list_pins(component_id),
            captures=self.list_captures(component_id),
        )
        return component

    # ------------------------------------------------------------------
    # Image
    # ------------------------------------------------------------------
    def set_component_image(
        self,
        component_id: int,
        data: bytes,
        name: str,
        mime: str | None = None,
    ) -> None:
        if not data:
            raise ValueError("Empty image data")
        mime = mime or detect_image_mime(data)
        with self._conn:
            cur = self._conn.execute(
                """
                UPDATE components
                SET image_name = ?, image_mime = ?, image_blob = ?, updated_at = ?
                WHERE id = ?
                """,
                (name, mime, sqlite3.Binary(data), _now(), int(component_id)),
            )
        if cur.rowcount == 0:
            raise KeyError(f"Component {component_id} not found")

    def get_component_image(self, component_id: int) -> tuple[str | None, str | None, bytes | None]:
        row = self._conn.execute(
            "SELECT image_name, image_mime, image_blob FROM components WHERE id = ?",
            (int(component_id),),
        ).fetchone()
        if row is None:
            raise KeyError(f"Component {component_id} not found")
        blob = bytes(row["image_blob"]) if row["image_blob"] is not None else None
        return row["image_name"], row["image_mime"], blob

    def clear_component_image(self, component_id: int) -> None:
        with self._conn:
            cur = self._conn.execute(
                """
                UPDATE components
                SET image_name = NULL, image_mime = NULL, image_blob = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (_now(), int(component_id)),
            )
        if cur.rowcount == 0:
            raise KeyError(f"Component {component_id} not found")

    # ------------------------------------------------------------------
    # Pins
    # ------------------------------------------------------------------
    def add_pin(
        self,
        component_id: int,
        number: str,
        label: str = "",
        x: float | None = None,
        y: float | None = None,
    ) -> int:
        number = str(number).strip()
        if not number:
            raise ValueError("Pin number is required")
        if (x is None) != (y is None):
            raise ValueError("Pin coordinates require both x and y")
        if x is not None and not (0.0 <= float(x) <= 1.0 and 0.0 <= float(y) <= 1.0):
            raise ValueError("Pin coordinates must be normalized to 0..1")
        with self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO pins (component_id, number, label, x, y)
                VALUES (?, ?, ?, ?, ?)
                """,
                (int(component_id), number, label, x, y),
            )
        return int(cur.lastrowid)

    def update_pin(
        self,
        pin_id: int,
        number: str | None = None,
        label: str | None = None,
        x: float | None | object = ...,
        y: float | None | object = ...,
    ) -> None:
        assignments: list[str] = []
        values: list[object] = []
        if number is not None:
            number = str(number).strip()
            if not number:
                raise ValueError("Pin number is required")
            assignments.append("number = ?")
            values.append(number)
        if label is not None:
            assignments.append("label = ?")
            values.append(label)
        if x is not ...:
            if x is not None and not 0.0 <= float(x) <= 1.0:
                raise ValueError("Pin x must be normalized to 0..1")
            assignments.append("x = ?")
            values.append(None if x is None else float(x))
        if y is not ...:
            if y is not None and not 0.0 <= float(y) <= 1.0:
                raise ValueError("Pin y must be normalized to 0..1")
            assignments.append("y = ?")
            values.append(None if y is None else float(y))
        if not assignments:
            return
        with self._conn:
            cur = self._conn.execute(
                f"UPDATE pins SET {', '.join(assignments)} WHERE id = ?",
                (*values, int(pin_id)),
            )
        if cur.rowcount == 0:
            raise KeyError(f"Pin {pin_id} not found")

    def delete_pin(self, pin_id: int) -> bool:
        with self._conn:
            cur = self._conn.execute("DELETE FROM pins WHERE id = ?", (int(pin_id),))
        return cur.rowcount > 0

    def list_pins(self, component_id: int) -> list[Pin]:
        rows = self._conn.execute(
            """
            SELECT id, component_id, number, label, x, y
            FROM pins WHERE component_id = ?
            ORDER BY CAST(number AS INTEGER), number COLLATE NOCASE
            """,
            (int(component_id),),
        ).fetchall()
        return [
            Pin(
                id=row["id"],
                component_id=row["component_id"],
                number=row["number"],
                label=row["label"],
                x=row["x"],
                y=row["y"],
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Captures
    # ------------------------------------------------------------------
    def add_capture(
        self,
        component_id: int,
        x: Sequence[float],
        y: Sequence[float],
        label: str = "",
        pin_a: int | None = None,
        pin_b: int | None = None,
        x_unit: str = "V",
        y_unit: str = "A",
    ) -> int:
        x_list = [float(v) for v in x]
        y_list = [float(v) for v in y]
        if len(x_list) != len(y_list):
            raise ValueError("x and y must have the same length")
        if not x_list:
            raise ValueError("Capture cannot be empty")
        if not all(v == v and abs(v) != float("inf") for v in x_list + y_list):
            raise ValueError("Capture contains non-finite values")

        with self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO captures
                    (component_id, label, pin_a, pin_b, x_unit, y_unit,
                     x_json, y_json, n_points, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(component_id),
                    label,
                    pin_a,
                    pin_b,
                    x_unit,
                    y_unit,
                    json.dumps(x_list, separators=(",", ":")),
                    json.dumps(y_list, separators=(",", ":")),
                    len(x_list),
                    _now(),
                ),
            )
        return int(cur.lastrowid)

    def list_captures(
        self, component_id: int, include_data: bool = False
    ) -> list[Capture]:
        if include_data:
            columns = "c.*, pa.number AS pin_a_number, pb.number AS pin_b_number"
        else:
            columns = (
                "c.id, c.component_id, c.label, c.pin_a, c.pin_b, "
                "c.x_unit, c.y_unit, c.n_points, c.created_at, "
                "pa.number AS pin_a_number, pb.number AS pin_b_number"
            )
        rows = self._conn.execute(
            f"""
            SELECT {columns}
            FROM captures c
            LEFT JOIN pins pa ON pa.id = c.pin_a
            LEFT JOIN pins pb ON pb.id = c.pin_b
            WHERE c.component_id = ?
            ORDER BY c.created_at, c.id
            """,
            (int(component_id),),
        ).fetchall()
        return [self._capture_from_row(row, include_data) for row in rows]

    def get_capture(self, capture_id: int) -> Capture | None:
        row = self._conn.execute(
            """
            SELECT c.*, pa.number AS pin_a_number, pb.number AS pin_b_number
            FROM captures c
            LEFT JOIN pins pa ON pa.id = c.pin_a
            LEFT JOIN pins pb ON pb.id = c.pin_b
            WHERE c.id = ?
            """,
            (int(capture_id),),
        ).fetchone()
        if row is None:
            return None
        return self._capture_from_row(row, include_data=True)

    def delete_capture(self, capture_id: int) -> bool:
        with self._conn:
            cur = self._conn.execute(
                "DELETE FROM captures WHERE id = ?", (int(capture_id),)
            )
        return cur.rowcount > 0

    @staticmethod
    def _capture_from_row(row: sqlite3.Row, include_data: bool) -> Capture:
        x = json.loads(row["x_json"]) if include_data else None
        y = json.loads(row["y_json"]) if include_data else None
        return Capture(
            id=row["id"],
            component_id=row["component_id"],
            label=row["label"],
            pin_a=row["pin_a"],
            pin_b=row["pin_b"],
            x_unit=row["x_unit"],
            y_unit=row["y_unit"],
            n_points=row["n_points"],
            created_at=row["created_at"],
            pin_a_number=row["pin_a_number"],
            pin_b_number=row["pin_b_number"],
            x=x,
            y=y,
        )

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def __enter__(self) -> "ComponentDB":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
