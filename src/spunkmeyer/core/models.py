"""Modelos de datos para el detector de antipatrones en SPUNKMEYER."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class AntipatronDetectado:
    """Representa una instancia de un antipatrón didáctico detectado en el código."""
    codigo: str                 # AP001, AP002...
    nombre: str
    archivo: Path
    linea: int
    columna: int
    mensaje: str
    explicacion: str
    sugerencia: str
    codigo_linea: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "codigo": self.codigo,
            "nombre": self.nombre,
            "archivo": str(self.archivo),
            "linea": self.linea,
            "columna": self.columna,
            "mensaje": self.mensaje,
            "explicacion": self.explicacion,
            "sugerencia": self.sugerencia,
            "codigo_linea": self.codigo_linea,
        }


@dataclass
class ReporteAntipatrones:
    """Reporte consolidado de antipatrones encontrados."""
    total_archivos: int
    antipatrones: List[AntipatronDetectado] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.antipatrones) == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "total_archivos": self.total_archivos,
            "total_antipatrones": len(self.antipatrones),
            "antipatrones": [a.to_dict() for a in self.antipatrones],
        }
