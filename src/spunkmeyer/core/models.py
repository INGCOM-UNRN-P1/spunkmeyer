"""Modelos de datos para el detector de antipatrones en SPUNKMEYER."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


class RuleCode(str):
    """Representa un código de regla de cátedra (ej. '0x300Ah') con alias didáctico ('AP001')."""

    def __new__(cls, code: str, alias: Optional[str] = None):
        obj = super().__new__(cls, code)
        obj._alias = alias or ""
        return obj

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return super().__eq__(other) or (bool(getattr(self, "_alias", None)) and self._alias.lower() == other.lower())
        return super().__eq__(other)

    def __hash__(self) -> int:
        return super().__hash__()


@dataclass
class AntipatronDetectado:
    """Representa una instancia de un antipatrón didáctico detectado en el código."""
    codigo: RuleCode | str      # 0x300Ah, 0x4002h, AP001...
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
            "codigo": str(self.codigo),
            "alias": getattr(self.codigo, "_alias", ""),
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
