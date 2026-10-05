"""Qué antipatrones de spunkmeyer también detecta gaff, y su forma en la taxonomía común.

Mapa explícito (paso previo al catálogo único, revisión 07 §3): 56 de los antipatrones de
spunkmeyer tienen como código canónico una regla del apunte que gaff también implementa. Cuando
ripley corre los dos, el mismo error aparecería dos veces; ripley los une por (archivo, línea,
código), y con `spunkmeyer detect --sin-compartidos` spunkmeyer los omite directamente. La lista
se generó cruzando el catálogo con las reglas implementadas de gaff; tests/test_compartidos.py la
vuelve a comparar cuando gaff está instalado.
"""

from __future__ import annotations

from typing import Any, Dict

from yutani.hallazgos import hallazgo

CODIGOS_COMPARTIDOS_CON_GAFF = frozenset({
    "0x1001h", "0x1002h", "0x1003h", "0x1005h", "0x1006h", "0x1008h", "0x1009h", "0x100Dh",
    "0x1012h", "0x1013h", "0x2006h", "0x200Ah", "0x3001h", "0x3002h", "0x3008h", "0x300Ah",
    "0x300Bh", "0x300Dh", "0x3013h", "0x3015h", "0x3016h", "0x4001h", "0x4004h", "0x4006h",
    "0x5004h", "0x5006h", "0x5008h", "0x5009h", "0x500Ah", "0x500Dh", "0x7001h",
})

# Antipatrones propios, sin página de regla en el apunte: se identifican por su alias.
SIN_PAGINA_EN_EL_APUNTE = frozenset({"0x2019h", "0x4010h", "0x101Dh"})

# Familia de la regla (primer dígito del código) → categoría común.
_CATEGORIA_POR_FAMILIA = {
    "0": "estilo", "1": "control", "2": "funciones", "3": "memoria", "4": "archivos",
    "5": "seguridad", "6": "compilacion", "7": "funciones", "8": "pruebas",
}


def comparte_con_gaff(codigo: str) -> bool:
    return str(codigo) in CODIGOS_COMPARTIDOS_CON_GAFF


def a_hallazgo(antipatron: Any) -> Dict[str, Any]:
    """Un antipatrón en la forma común del ecosistema (yutani.hallazgos)."""
    codigo = str(antipatron.codigo)
    alias = getattr(antipatron.codigo, "alias", "") or codigo
    categoria = _CATEGORIA_POR_FAMILIA.get(codigo[2:3], "estilo") if codigo.startswith("0x") else "estilo"
    datos: Dict[str, Any] = hallazgo(
        "spunkmeyer", alias if codigo in SIN_PAGINA_EN_EL_APUNTE else codigo, categoria,
        antipatron.severidad, antipatron.mensaje, archivo=str(antipatron.archivo),
        linea=antipatron.linea, columna=antipatron.columna, sugerencia=antipatron.sugerencia or None,
    )
    datos["tambien_en_gaff"] = comparte_con_gaff(codigo)
    return datos
