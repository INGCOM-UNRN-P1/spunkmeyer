"""Plugin de SPUNKMEYER para integración transparente con RIPLEY."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from spunkmeyer import __version__
from spunkmeyer.core.compartidos import comparte_con_otro_analizador, dueno_regla
from spunkmeyer.core.detector import auditar_archivos


class SpunkmeyerPlugin:
    """Plugin detector de antipatrones para Ripley."""

    name = "antipatterns"
    version = __version__

    def is_available(self) -> bool:
        return True

    def execute(self, workspace: Path, manifest_config: Dict[str, Any]) -> Dict[str, Any]:
        reporte = auditar_archivos([workspace])
        sin_compartidos = bool(manifest_config.get("sin_compartidos", False))
        antipatrones = [
            ap for ap in reporte.antipatrones
            if not (sin_compartidos and comparte_con_otro_analizador(str(ap.codigo)))
        ]
        observaciones = []

        for ap in antipatrones:
            observaciones.append({
                "codigo": ap.codigo,
                "dueno": dueno_regla(str(ap.codigo)),
                "severidad": "WARNING",
                "archivo": str(ap.archivo),
                "linea": ap.linea,
                "columna": ap.columna,
                "mensaje": f"{ap.nombre}: {ap.mensaje}",
                "sugerencia": ap.sugerencia,
            })

        return {
            "ok": len(antipatrones) == 0,
            "total_antipatrones": len(antipatrones),
            "observaciones": observaciones,
        }
