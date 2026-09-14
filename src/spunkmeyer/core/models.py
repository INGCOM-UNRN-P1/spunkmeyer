"""Modelos de datos para el detector de antipatrones en SPUNKMEYER."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


class RuleCode(str):
    """Representa un código de regla de cátedra unificado con alias didáctico ('AP001') y soporte de retrocompatibilidad."""

    def __new__(
        cls,
        code: str,
        alias: Optional[str] = None,
        sp_code: Optional[str] = None,
        codigo_anterior: Optional[str] = None,
    ):
        obj = super().__new__(cls, code)
        obj._alias = alias or ""
        obj._sp_code = sp_code or (f"SP{code}" if code.startswith("0x") else "")
        obj._codigo_anterior = codigo_anterior or ""
        return obj

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            other_low = other.lower()
            return (
                super().__eq__(other)
                or self.lower() == other_low
                or (bool(getattr(self, "_alias", None)) and self._alias.lower() == other_low)
                or (bool(getattr(self, "_sp_code", None)) and self._sp_code.lower() == other_low)
                or (bool(getattr(self, "_codigo_anterior", None)) and self._codigo_anterior.lower() == other_low)
                or (bool(getattr(self, "_codigo_anterior", None)) and f"ap-{self._codigo_anterior.lower()}" == other_low)
            )
        return super().__eq__(other)

    @property
    def alias(self) -> str:
        return getattr(self, "_alias", "")

    @property
    def sp_codigo(self) -> str:
        return getattr(self, "_sp_code", "")

    @property
    def codigo_anterior(self) -> str:
        return getattr(self, "_codigo_anterior", "")

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
    ejemplo_incorrecto: str = ""
    ejemplo_correcto: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "codigo": str(self.codigo),
            "alias": getattr(self.codigo, "_alias", ""),
            "sp_codigo": getattr(self.codigo, "_sp_code", f"SP{self.codigo}" if str(self.codigo).startswith("0x") else ""),
            "nombre": self.nombre,
            "archivo": str(self.archivo),
            "linea": self.linea,
            "columna": self.columna,
            "mensaje": self.mensaje,
            "explicacion": self.explicacion,
            "sugerencia": self.sugerencia,
            "codigo_linea": self.codigo_linea,
            "ejemplo_incorrecto": self.ejemplo_incorrecto,
            "ejemplo_correcto": self.ejemplo_correcto,
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
