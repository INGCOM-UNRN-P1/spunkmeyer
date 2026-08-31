"""Motor de detección de antipatrones y vicios didácticos en SPUNKMEYER usando Tree-Sitter AST."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set

import tree_sitter_c as tsc
from tree_sitter import Language, Parser, Node

from spunkmeyer.core.models import AntipatronDetectado, ReporteAntipatrones, RuleCode

_C_LANGUAGE: Optional[Language] = None
_PARSER: Optional[Parser] = None


def get_c_parser() -> Parser:
    global _C_LANGUAGE, _PARSER
    if _PARSER is None:
        _C_LANGUAGE = Language(tsc.language())
        _PARSER = Parser(_C_LANGUAGE)
    return _PARSER


CATALOGO_ANTIPATRONES: Dict[str, Dict[str, str]] = {
    "0x300Ah": {
        "codigo": "0x300Ah",
        "alias": "AP001",
        "nombre": "Casteo redundante de malloc()",
        "mensaje": "Castear el retorno de 'malloc()' es innecesario en C y puede enmascarar la falta de #include <stdlib.h>.",
        "explicacion": "En C, 'void*' se promociona automáticamente a cualquier tipo de puntero. Castear '(tipo*)malloc()' proviene de C++ y es una mala práctica en C.",
        "sugerencia": "Escribí 'ptr = malloc(sizeof(*ptr) * n);' directamente.",
    },
    "0x4002h": {
        "codigo": "0x4002h",
        "alias": "AP002",
        "nombre": "Control de lectura con while(!feof())",
        "mensaje": "Usar '!feof(f)' como condición del bucle provoca procesar el último registro dos veces.",
        "explicacion": "'feof()' solo devuelve verdadero DESPUÉS de que una lectura previa intentó leer más allá del fin de archivo y falló.",
        "sugerencia": "Controlá el bucle con el valor de retorno de la función de lectura: 'while (fread(...) == 1)' o 'while (fgets(...) != NULL)'.",
    },
    "0x3002h": {
        "codigo": "0x3002h",
        "alias": "AP003",
        "nombre": "Retorno de puntero a variable local (Dangling Pointer)",
        "mensaje": "Se detectó el retorno de la dirección de una variable local en la pila.",
        "explicacion": "Al finalizar la función, su frame de pila se destruye. El puntero retornado apuntará a memoria inválida/basura.",
        "sugerencia": "Asigná memoria dinámica con malloc() o pasá el búfer como parámetro por referencia.",
    },
    "0x3008h": {
        "codigo": "0x3008h",
        "alias": "AP004",
        "nombre": "Chequeo innecesario antes de free()",
        "mensaje": "Comprobar 'if (ptr != NULL)' antes de invocar 'free(ptr)' es redundante.",
        "explicacion": "La especificación del estándar C garantiza que 'free(NULL)' no realiza ninguna acción y es 100% seguro.",
        "sugerencia": "Invocá 'free(ptr);' directamente sin envolverlo en un if.",
    },
    "0x1005h": {
        "codigo": "0x1005h",
        "alias": "AP005",
        "nombre": "Comparación booleana explícita redundante",
        "mensaje": "Comparar explícitamente 'if (cond == 1)' o 'if (cond == true)' es redundante.",
        "explicacion": "En C cualquier valor distinto de 0 evalúa a verdadero en estructuras de control.",
        "sugerencia": "Escribí 'if (cond)' o 'if (!cond)' directamente.",
    },
    "0x1001h": {
        "codigo": "0x1001h",
        "alias": "AP006",
        "nombre": "Punto y coma accidental tras condición de control",
        "mensaje": "Punto y coma ';' detectado inmediatamente después de 'if (...)', 'for (...)' o 'while (...)'.",
        "explicacion": "El punto y coma crea una sentencia vacía, haciendo que el bloque que le sigue se ejecute incondicionalmente.",
        "sugerencia": "Eliminá el ';' al final de la condición de control.",
    },
    "0x4006h": {
        "codigo": "0x4006h",
        "alias": "AP007",
        "nombre": "Uso de fflush(stdin) para limpiar buffer",
        "mensaje": "Invocación de 'fflush(stdin)' detectada.",
        "explicacion": "Según el estándar ISO C, 'fflush()' solo está definido para streams de salida. Aplicarlo sobre 'stdin' produce comportamiento indefinido.",
        "sugerencia": "Consumí los caracteres restantes del buffer con 'while ((c = getchar()) != '\\n' && c != EOF);'.",
    },
    "0x300Fh": {
        "codigo": "0x300Fh",
        "alias": "AP008",
        "nombre": "Uso de sizeof(puntero) en reserva dinámica",
        "mensaje": "Se detectó 'sizeof(ptr)' en lugar de 'sizeof(*ptr)' o 'sizeof(tipo)' en malloc/calloc.",
        "explicacion": "'sizeof(ptr)' devuelve el tamaño del puntero (4 u 8 bytes) en lugar del tamaño de la estructura apuntada, provocando reservas insuficientes.",
        "sugerencia": "Escribí 'malloc(sizeof(*ptr) * n)' o 'malloc(sizeof(struct tipo))'.",
    },
}

# Alias retrocompatibles
ALIAS_MAP: Dict[str, str] = {
    "AP001": "0x300Ah",
    "AP002": "0x4002h",
    "AP003": "0x3002h",
    "AP004": "0x3008h",
    "AP005": "0x1005h",
    "AP006": "0x1001h",
    "AP007": "0x4006h",
    "AP008": "0x300Fh",
}
for k, v in ALIAS_MAP.items():
    if v in CATALOGO_ANTIPATRONES:
        CATALOGO_ANTIPATRONES[k] = CATALOGO_ANTIPATRONES[v]


def _find_identifier(node: Node) -> Optional[str]:
    if node.type in ("identifier", "type_identifier", "field_identifier"):
        return node.text.decode("utf-8", errors="replace")
    for child in node.children:
        res = _find_identifier(child)
        if res:
            return res
    return None


def auditar_archivo(archivo: Path) -> List[AntipatronDetectado]:
    """Analiza un archivo C y detecta antipatrones didácticos usando Tree-Sitter AST."""
    archivo = Path(archivo)
    if not archivo.is_file():
        return []

    try:
        contenido = archivo.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    lineas = contenido.splitlines()
    source_bytes = contenido.encode("utf-8")
    parser = get_c_parser()
    tree = parser.parse(source_bytes)

    antipatrones: List[AntipatronDetectado] = []

    def _traverse(node: Node) -> None:
        idx = node.start_point.row + 1
        col = node.start_point.column + 1
        linea_cod = lineas[node.start_point.row] if node.start_point.row < len(lineas) else ""

        # 0x300Ah (AP001): Casteo redundante de malloc
        if node.type == "cast_expression":
            val_node = node.child_by_field_name("value")
            if val_node and val_node.type == "call_expression":
                fn_node = val_node.child_by_field_name("function")
                if fn_node and _find_identifier(fn_node) in ("malloc", "calloc"):
                    info = CATALOGO_ANTIPATRONES["0x300Ah"]
                    antipatrones.append(AntipatronDetectado(
                        codigo=RuleCode("0x300Ah", "AP001"),
                        nombre=info["nombre"],
                        archivo=archivo,
                        linea=idx,
                        columna=col,
                        mensaje=info["mensaje"],
                        explicacion=info["explicacion"],
                        sugerencia=info["sugerencia"],
                        codigo_linea=linea_cod,
                    ))

        # 0x4002h (AP002): while(!feof())
        elif node.type == "while_statement":
            cond_node = node.child_by_field_name("condition")
            if cond_node:
                raw_cond = cond_node.text.decode("utf-8", errors="replace")
                if "feof" in raw_cond and "!" in raw_cond:
                    info = CATALOGO_ANTIPATRONES["0x4002h"]
                    antipatrones.append(AntipatronDetectado(
                        codigo=RuleCode("0x4002h", "AP002"),
                        nombre=info["nombre"],
                        archivo=archivo,
                        linea=idx,
                        columna=col,
                        mensaje=info["mensaje"],
                        explicacion=info["explicacion"],
                        sugerencia=info["sugerencia"],
                        codigo_linea=linea_cod,
                    ))

        # 0x3002h (AP003): Retorno de puntero a variable local
        elif node.type == "return_statement":
            raw_ret = node.text.decode("utf-8", errors="replace")
            if "&" in raw_ret:
                import re
                m = re.search(r"&\s*([a-zA-Z_][a-zA-Z0-9_]*)", raw_ret)
                var_name = m.group(1) if m else "var"
                info = CATALOGO_ANTIPATRONES["0x3002h"]
                antipatrones.append(AntipatronDetectado(
                    codigo=RuleCode("0x3002h", "AP003"),
                    nombre=info["nombre"],
                    archivo=archivo,
                    linea=idx,
                    columna=col,
                    mensaje=f"Retorno de dirección de variable local '&{var_name}'.",
                    explicacion=info["explicacion"],
                    sugerencia=info["sugerencia"],
                    codigo_linea=linea_cod,
                ))

        # 0x3008h (AP004): if (ptr != NULL) free(ptr);
        elif node.type == "if_statement":
            cond_node = node.child_by_field_name("condition")
            body_node = node.child_by_field_name("consequence")
            if cond_node and body_node:
                cond_text = cond_node.text.decode("utf-8", errors="replace")
                body_text = body_node.text.decode("utf-8", errors="replace")
                if ("!= NULL" in cond_text or "!= 0" in cond_text) and "free(" in body_text:
                    info = CATALOGO_ANTIPATRONES["0x3008h"]
                    antipatrones.append(AntipatronDetectado(
                        codigo=RuleCode("0x3008h", "AP004"),
                        nombre=info["nombre"],
                        archivo=archivo,
                        linea=idx,
                        columna=col,
                        mensaje=info["mensaje"],
                        explicacion=info["explicacion"],
                        sugerencia=info["sugerencia"],
                        codigo_linea=linea_cod,
                    ))

            # 0x1005h (AP005): if (cond == true) o if (cond == 1)
            if cond_node:
                cond_text = cond_node.text.decode("utf-8", errors="replace")
                if "== true" in cond_text or "== 1" in cond_text or "== TRUE" in cond_text:
                    info = CATALOGO_ANTIPATRONES["0x1005h"]
                    antipatrones.append(AntipatronDetectado(
                        codigo=RuleCode("0x1005h", "AP005"),
                        nombre=info["nombre"],
                        archivo=archivo,
                        linea=idx,
                        columna=col,
                        mensaje=info["mensaje"],
                        explicacion=info["explicacion"],
                        sugerencia=info["sugerencia"],
                        codigo_linea=linea_cod,
                    ))

        # 0x4006h (AP007): fflush(stdin) & 0x300Fh (AP008): sizeof(ptr)
        elif node.type == "call_expression":
            fn_node = node.child_by_field_name("function")
            fn_name = _find_identifier(fn_node) if fn_node else None
            args_node = node.child_by_field_name("arguments")
            if fn_name == "fflush" and args_node:
                raw_args = args_node.text.decode("utf-8", errors="replace")
                if "stdin" in raw_args:
                    info = CATALOGO_ANTIPATRONES["0x4006h"]
                    antipatrones.append(AntipatronDetectado(
                        codigo=RuleCode("0x4006h", "AP007"),
                        nombre=info["nombre"],
                        archivo=archivo,
                        linea=idx,
                        columna=col,
                        mensaje=info["mensaje"],
                        explicacion=info["explicacion"],
                        sugerencia=info["sugerencia"],
                        codigo_linea=linea_cod,
                    ))
            elif fn_name in ("malloc", "calloc") and args_node:
                raw_args = args_node.text.decode("utf-8", errors="replace")
                # Detectar sizeof(p) donde p es un identificador sin * y sin struct/tipo basico
                import re
                m_sz = re.search(r"sizeof\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)", raw_args)
                if m_sz:
                    id_name = m_sz.group(1)
                    tipos_base = {"int", "char", "float", "double", "long", "short", "size_t", "void", "uint8_t", "int32_t", "uint32_t", "int64_t", "uint64_t"}
                    if not (id_name.endswith("_t") or id_name.startswith("t_") or id_name in tipos_base):
                        info = CATALOGO_ANTIPATRONES["0x300Fh"]
                        antipatrones.append(AntipatronDetectado(
                            codigo=RuleCode("0x300Fh", "AP008"),
                            nombre=info["nombre"],
                            archivo=archivo,
                            linea=idx,
                            columna=col,
                            mensaje=f"Uso de 'sizeof({id_name})' donde '{id_name}' es presumiblemente un puntero.",
                            explicacion=info["explicacion"],
                            sugerencia=f"Escribí 'sizeof(*{id_name})' o pasá el tipo estructurado completo.",
                            codigo_linea=linea_cod,
                        ))

        for child in node.children:
            _traverse(child)

    _traverse(tree.root_node)
    return antipatrones


def auditar_archivos(rutas: List[Path]) -> ReporteAntipatrones:
    """Audita una lista de archivos o directorios."""
    archivos_objetivo: Set[Path] = set()
    for r in rutas:
        p = Path(r)
        if p.is_file() and p.suffix.lower() in (".c", ".h"):
            archivos_objetivo.add(p)
        elif p.is_dir():
            for sub in p.rglob("*"):
                if sub.is_file() and sub.suffix.lower() in (".c", ".h"):
                    archivos_objetivo.add(sub)

    todos: List[AntipatronDetectado] = []
    for arch in sorted(archivos_objetivo):
        todos.extend(auditar_archivo(arch))

    return ReporteAntipatrones(
        total_archivos=len(archivos_objetivo),
        antipatrones=todos,
    )
