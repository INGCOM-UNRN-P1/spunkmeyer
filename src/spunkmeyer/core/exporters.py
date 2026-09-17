"""Exportadores y utilidades de integración para SPUNKMEYER (SARIF, Markdown/Dredd, HAL, Diff)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Set

from spunkmeyer import __version__
from spunkmeyer.core.models import AntipatronDetectado, ReporteAntipatrones


def generar_seccion_markdown(reporte: ReporteAntipatrones) -> str:
    """Genera la sección Markdown estandarizada para incrustar en el informe de Dredd."""
    lines = [
        "<!-- spunkmeyer:section:v1 -->",
        "## Antipatrones Didácticos (SPUNKMEYER)",
        "",
    ]
    if reporte.ok:
        lines.append("✓ No se detectaron antipatrones pedagógicos en el código analizado.")
        lines.append("")
    else:
        lines.append(f"⚠️ Se detectaron **{len(reporte.antipatrones)}** malas prácticas didácticas:")
        lines.append("")
        lines.append("| Archivo | Línea | Código | Nombre | Explicación | Sugerencia |")
        lines.append("|---|---|---|---|---|---|")
        for ap in reporte.antipatrones:
            arch_name = ap.archivo.name.replace("|", "\\|")
            cod = str(ap.codigo).replace("|", "\\|")
            nom = ap.nombre.replace("|", "\\|")
            exp = ap.explicacion.replace("|", "\\|")
            sug = ap.sugerencia.replace("|", "\\|")
            lines.append(f"| `{arch_name}` | {ap.linea} | `{cod}` | **{nom}** | {exp} | {sug} |")
        lines.append("")
    return "\n".join(lines)


def generar_sarif_210_spunkmeyer(reporte: ReporteAntipatrones) -> Dict[str, Any]:
    """Genera informe en formato estándar OASIS SARIF 2.1.0 con severidad calibrada (error/warning)."""
    sarif_rules = []
    reglas_vistas = set()
    results = []

    for ap in reporte.antipatrones:
        c_str = str(ap.codigo)
        level = getattr(ap, "severidad", "warning")
        if c_str not in reglas_vistas:
            reglas_vistas.add(c_str)
            sarif_rules.append({
                "id": c_str,
                "name": ap.nombre,
                "shortDescription": {"text": ap.nombre},
                "fullDescription": {"text": ap.explicacion},
                "defaultConfiguration": {"level": level},
            })

        results.append({
            "ruleId": c_str,
            "level": level,
            "message": {"text": f"{ap.mensaje} Sugerencia: {ap.sugerencia}"},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": str(ap.archivo)},
                        "region": {"startLine": max(1, ap.linea), "startColumn": max(1, ap.columna)},
                    }
                }
            ],
        })

    return {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "spunkmeyer",
                        "version": __version__,
                        "informationUri": "https://github.com/unsam/spunkmeyer",
                        "rules": sarif_rules,
                    }
                },
                "results": results,
            }
        ],
    }


def correlacionar_con_hal(reporte: ReporteAntipatrones, crash_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Cruza los hallazgos estáticos con el informe forense dinámico de HAL."""
    correlaciones = []
    # Soporta tanto formato nativo de crash ('archivo_falla', 'linea_falla') como modelos hal ('archivo', 'linea')
    crash_file = crash_data.get("archivo_falla") or crash_data.get("archivo")
    crash_line = crash_data.get("linea_falla") if "linea_falla" in crash_data else crash_data.get("linea")

    if not crash_file or crash_line is None:
        return correlaciones

    for ap in reporte.antipatrones:
        # Correlación por proximidad de línea (+- 3 líneas) o coincidencia en el mismo archivo
        mismo_archivo = (ap.archivo.name == Path(str(crash_file)).name)
        linea_valida = (ap.linea > 0 and int(crash_line) > 0)
        cerca_de_linea = linea_valida and abs(ap.linea - int(crash_line)) <= 3

        if mismo_archivo and cerca_de_linea:
            correlaciones.append({
                "antipatron": ap.to_dict(),
                "diagnostico_cruzado": f"El antipatrón '{ap.nombre}' ({ap.codigo}) en línea {ap.linea} está directamente relacionado con la caída detectada por HAL en línea {crash_line}.",
            })
    return correlaciones


def comparar_antipatrones_entre_versiones(rep_ant: ReporteAntipatrones, rep_act: ReporteAntipatrones) -> Dict[str, Any]:
    """Compara los antipatrones entre dos entregas o versiones de código."""
    ant_set = {(str(a.codigo), a.archivo.name, a.linea) for a in rep_ant.antipatrones}
    act_set = {(str(a.codigo), a.archivo.name, a.linea) for a in rep_act.antipatrones}

    resueltos = ant_set - act_set
    nuevos = act_set - ant_set
    persistentes = ant_set & act_set

    return {
        "total_version_anterior": len(rep_ant.antipatrones),
        "total_version_actual": len(rep_act.antipatrones),
        "antipatrones_resueltos": len(resueltos),
        "antipatrones_nuevos": len(nuevos),
        "antipatrones_persistentes": len(persistentes),
        "mejora_neta": len(resueltos) - len(nuevos),
    }
