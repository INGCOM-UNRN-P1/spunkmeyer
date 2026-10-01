"""Parser de C y auxiliares que comparten el detector y sus reglas por tipo de nodo."""

from pathlib import Path
from typing import Optional

import tree_sitter_c as tsc
from tree_sitter import Language, Node, Parser

from spunkmeyer.core.catalog import CATALOGO_ANTIPATRONES
from spunkmeyer.core.models import AntipatronDetectado, RuleCode

_C_LANGUAGE = None
_PARSER = None


def get_c_parser() -> Parser:
    global _C_LANGUAGE, _PARSER
    if _PARSER is None:
        _C_LANGUAGE = Language(tsc.language())
        _PARSER = Parser(_C_LANGUAGE)
    return _PARSER


def _find_identifier(node: Node) -> Optional[str]:
    if node.type in ("identifier", "type_identifier", "field_identifier"):
        return node.text.decode("utf-8", errors="replace")
    for child in node.children:
        res = _find_identifier(child)
        if res:
            return res
    return None


def _make_antipatron(cod_key: str, archivo: Path, linea: int, columna: int, linea_cod: str, detalle_msg: Optional[str] = None) -> AntipatronDetectado:
    info = CATALOGO_ANTIPATRONES[cod_key]
    alias_val = info.get("alias", "")
    cod_nuevo = info.get("codigo", cod_key)
    cod_ant = info.get("codigo_anterior", cod_key if cod_key.startswith("0x") else "")
    sp_val = info.get("sp_codigo", f"SP{cod_nuevo}" if cod_nuevo.startswith("0x") else "")
    return AntipatronDetectado(
        codigo=RuleCode(cod_nuevo, alias_val, sp_val, codigo_anterior=cod_ant),
        nombre=info["nombre"],
        archivo=archivo,
        linea=linea,
        columna=columna,
        mensaje=detalle_msg or info["mensaje"],
        explicacion=info["explicacion"],
        sugerencia=info["sugerencia"],
        codigo_linea=linea_cod,
        ejemplo_incorrecto=info.get("ejemplo_incorrecto", ""),
        ejemplo_correcto=info.get("ejemplo_correcto", ""),
    )
