"""Parser de C y auxiliares que comparten el detector y sus reglas por tipo de nodo."""

from pathlib import Path
from typing import Iterator, Optional, Tuple

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


def lenguaje_c() -> Language:
    get_c_parser()
    assert _C_LANGUAGE is not None
    return _C_LANGUAGE


def descendientes(raiz: Node, sin_entrar_a: Tuple[str, ...] = ()) -> Iterator[Node]:
    """El nodo y sus descendientes en preorden. Con una pila propia: un programa muy anidado agotaba
    la del intérprete. Los tipos de `sin_entrar_a` no se visitan, ni ellos ni lo que tienen adentro."""
    pendientes = [raiz]
    while pendientes:
        nodo = pendientes.pop()
        if nodo.type in sin_entrar_a:
            continue
        yield nodo
        pendientes.extend(reversed(nodo.children))


def _find_identifier(node: Node) -> Optional[str]:
    for nodo in descendientes(node):
        if nodo.type in ("identifier", "type_identifier", "field_identifier"):
            return (nodo.text or b"").decode("utf-8", errors="replace")
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
