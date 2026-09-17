"""Plugin de SPUNKMEYER para integración transparente con RIPLEY."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from spunkmeyer import __version__
from spunkmeyer.core.detector import auditar_archivos


class SpunkmeyerPlugin:
    """Plugin detector de antipatrones para Ripley."""

    name = "antipatterns"
    version = __version__

    def is_available(self) -> bool:
        return True

    def execute(self, workspace: Path, manifest_config: Dict[str, Any]) -> Dict[str, Any]:
        reporte = auditar_archivos([workspace])
        observaciones = []

        for ap in reporte.antipatrones:
            observaciones.append({
                "codigo": ap.codigo,
                "severidad": "WARNING",
                "archivo": str(ap.archivo),
                "linea": ap.linea,
                "columna": ap.columna,
                "mensaje": f"{ap.nombre}: {ap.mensaje}",
                "sugerencia": ap.sugerencia,
            })

        return {
            "ok": reporte.ok,
            "total_antipatrones": len(reporte.antipatrones),
            "observaciones": observaciones,
        }
