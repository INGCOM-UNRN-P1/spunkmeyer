"""Reglas de spunkmeyer por tipo de nodo de tree-sitter (N-SPUNK-01).

`auditar_archivo` era una función de 1.237 líneas con un `_traverse` anidado de 1.071: un if/elif
por tipo de nodo con todas las reglas adentro. Cada rama es ahora una función de este módulo y
`DESPACHO` la asocia a su tipo de nodo; el estado que comparten (el archivo, los tipos de las
variables, los malloc, las etiquetas de goto…) viaja en `Contexto`. Los hallazgos y su orden no
cambiaron: lo verifica tests/test_caracterizacion.py, generado antes de partir la función.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

from tree_sitter import Node

from spunkmeyer.core.models import AntipatronDetectado
from spunkmeyer.core.nodos import _find_identifier, _make_antipatron


@dataclass
class Contexto:
    """Lo que las reglas necesitan del archivo, y la lista donde anotan lo que encuentran."""

    archivo: Path
    lineas: List[str]
    contenido: str
    contenido_auditado: str
    has_stdlib: bool
    etiquetas_lineas: Dict[str, int]
    var_types: Dict[str, str]
    local_arrays: Set[str]
    malloc_vars: Set[str]
    uninit_pointers: Set[str]
    antipatrones: List[AntipatronDetectado] = field(default_factory=list)


# AP001 (0x300Ah) & AP047 (0x3020h): Casteos
def _en_cast_expression(node: Node, ctx: Contexto, idx: int, col: int, linea_cod: str) -> None:
    val_node = node.child_by_field_name("value")
    if val_node and val_node.type == "call_expression":
        fn_node = val_node.child_by_field_name("function")
        if fn_node and _find_identifier(fn_node) in ("malloc", "calloc"):
            ctx.antipatrones.append(_make_antipatron("0x300Ah", ctx.archivo, idx, col, linea_cod))
            if not ctx.has_stdlib:
                ctx.antipatrones.append(_make_antipatron(
                    "0x3028h",
                    ctx.archivo,
                    idx,
                    col,
                    linea_cod,
                    "Casteo explícito de 'malloc()' en archivo sin inclusión obligatoria de '<stdlib.h>'.",
                ))

    # AP047 (0x3020h): Violación de Strict Aliasing (ej. (int *)&float_var)
    type_n = node.child_by_field_name("type")
    if type_n and val_node and val_node.type == "pointer_expression":
        cast_type_txt = type_n.text.decode("utf-8", errors="replace").replace(" ", "").replace("*", "")
        val_id = _find_identifier(val_node)
        if val_id and val_id in ctx.var_types:
            orig_type = ctx.var_types[val_id].replace(" ", "").replace("*", "")
            incompatibles = {
                ("int", "float"), ("float", "int"),
                ("int", "double"), ("double", "int"),
                ("long", "float"), ("float", "long"),
                ("long", "double"), ("double", "long"),
            }
            t_desc = type_n.text.decode("utf-8", errors="replace")
            if (cast_type_txt, orig_type) in incompatibles:
                ctx.antipatrones.append(_make_antipatron(
                    "0x3020h",
                    ctx.archivo,
                    idx,
                    col,
                    linea_cod,
                    f"Casteo forzado entre punteros incompatibles '({t_desc})&{val_id}' (violación de strict aliasing).",
                ))

    # AP073 (0x302Ah): Casteo forzado de tipos numéricos a punteros (int *p = (int *)0x1000)
    if type_n and val_node:
        t_str = type_n.text.decode("utf-8", "replace")
        v_str = val_node.text.decode("utf-8", "replace").strip()
        if "*" in t_str and (val_node.type == "number_literal" or re.match(r"^0x[0-9a-fA-F]+$|^\d+$", v_str)):
            if v_str not in ("0", "0x0"):
                ctx.antipatrones.append(_make_antipatron(
                    "0x302Ah",
                    ctx.archivo,
                    idx,
                    col,
                    linea_cod,
                    f"Casteo forzado de constante numérica '{v_str}' a tipo puntero '{t_str}'.",
                ))


# AP048 (0x1019h): Salto goto hacia atrás (desestructurado)
def _en_goto_statement(node: Node, ctx: Contexto, idx: int, col: int, linea_cod: str) -> None:
    lbl_n = node.child_by_field_name("label") or next((c for c in node.children if c.type == "statement_identifier"), None)
    if lbl_n:
        lbl_name = lbl_n.text.decode("utf-8", errors="replace")
        if lbl_name in ctx.etiquetas_lineas and ctx.etiquetas_lineas[lbl_name] <= idx:
            ctx.antipatrones.append(_make_antipatron(
                "0x1019h",
                ctx.archivo,
                idx,
                col,
                linea_cod,
                f"Salto 'goto {lbl_name}' hacia atrás en la línea {ctx.etiquetas_lineas[lbl_name]} simulando un lazo desestructurado.",
            ))


# AP002 (0x4002h) & AP006 (0x1001h) & AP043 (0x1016h): while statements
def _en_while_statement(node: Node, ctx: Contexto, idx: int, col: int, linea_cod: str) -> None:
    cond_node = node.child_by_field_name("condition")
    body_node = node.child_by_field_name("body")
    if body_node and body_node.type == "expression_statement" and body_node.text.decode("utf-8").strip() == ";":
        ctx.antipatrones.append(_make_antipatron(
            "0x1001h",
            ctx.archivo,
            idx,
            col,
            linea_cod,
            "Punto y coma accidental tras la condición del while (cuerpo vacío).",
        ))
    if cond_node:
        raw_cond = cond_node.text.decode("utf-8", errors="replace")
        if "feof" in raw_cond and "!" in raw_cond:
            ctx.antipatrones.append(_make_antipatron("0x4002h", ctx.archivo, idx, col, linea_cod))

        # AP043: Operador bit a bit & o | en condición lógica
        def _has_bitwise_while(n: Node) -> bool:
            if n.type == "binary_expression":
                op = next((c.text.decode("utf-8") for c in n.children if c.type in ("&", "|")), None)
                if op:
                    curr = n.parent
                    in_cmp = False
                    while curr and curr != cond_node.parent:
                        if curr.type == "binary_expression":
                            c_op = next((c.text.decode("utf-8") for c in curr.children if c.type in ("==", "!=", "<", ">", "<=", ">=")), None)
                            if c_op:
                                in_cmp = True
                                break
                        curr = curr.parent
                    if not in_cmp:
                        return True
            for ch in n.children:
                if _has_bitwise_while(ch):
                    return True
            return False

        if _has_bitwise_while(cond_node):
            ctx.antipatrones.append(_make_antipatron(
                "0x1016h",
                ctx.archivo,
                idx,
                col,
                linea_cod,
                "Uso de operador a nivel de bits ('&' o '|') en condición lógica en lugar de operador booleano.",
            ))

        # AP050: strcmp() directo como condición booleana
        cond_clean = raw_cond.strip(" ()")
        if re.match(r"^!?\s*strcmp\s*\(", cond_clean) and not re.search(r"==|!=|<|>", cond_clean):
            ctx.antipatrones.append(_make_antipatron(
                "0x101Ah",
                ctx.archivo,
                idx,
                col,
                linea_cod,
                "Uso de 'strcmp()' como condición booleana directa sin comparación explícita contra 0.",
            ))

    if body_node:
        b_txt = body_node.text.decode("utf-8", errors="replace")
        # AP057: malloc en bucle sin liberación ante fallos parciales
        if re.search(r"\[[^\]]+\]\s*=\s*(?:malloc|calloc)\s*\(", b_txt) and "free(" not in b_txt:
            ctx.antipatrones.append(_make_antipatron(
                "0x3024h",
                ctx.archivo,
                idx,
                col,
                linea_cod,
                "Reserva dinámica en bucle sin liberación de elementos previos ante fallos parciales.",
            ))

        # AP062: Bucle infinito con salida condicionada exclusivamente por exit()
        if cond_node:
            c_txt = cond_node.text.decode("utf-8", errors="replace").strip("()")
            if c_txt in ("1", "true", "TRUE"):
                if re.search(r"\bexit\s*\(", b_txt) and not re.search(r"\b(?:break|return)\b", b_txt):
                    ctx.antipatrones.append(_make_antipatron(
                        "0x101Ch",
                        ctx.archivo,
                        idx,
                        col,
                        linea_cod,
                        "Bucle infinito con terminación forzada exclusivamente por 'exit()'.",
                    ))


# AP003 (0x3002h): Retorno de puntero a variable local
def _en_return_statement(node: Node, ctx: Contexto, idx: int, col: int, linea_cod: str) -> None:
    raw_ret = node.text.decode("utf-8", errors="replace")
    if "&" in raw_ret:
        m = re.search(r"&\s*([a-zA-Z_][a-zA-Z0-9_]*)", raw_ret)
        var_name = m.group(1) if m else "var"
        ctx.antipatrones.append(_make_antipatron(
            "0x3002h",
            ctx.archivo,
            idx,
            col,
            linea_cod,
            f"Retorno de dirección de variable local '&{var_name}'.",
        ))


# AP004, AP005, AP016, AP014, AP023, AP006, AP043, AP044, AP045: if statements
def _en_if_statement(node: Node, ctx: Contexto, idx: int, col: int, linea_cod: str) -> None:
    cond_node = node.child_by_field_name("condition")
    body_node = node.child_by_field_name("consequence")
    alt_node = node.child_by_field_name("alternative")

    # AP006: Punto y coma accidental tras condición
    if body_node and body_node.type == "expression_statement" and body_node.text.decode("utf-8").strip() == ";":
        ctx.antipatrones.append(_make_antipatron(
            "0x1001h",
            ctx.archivo,
            idx,
            col,
            linea_cod,
            "Punto y coma accidental tras la condición del if (cuerpo vacío).",
        ))

    # AP044 (0x1017h): Ramas then y else idénticas
    if body_node and alt_node:
        else_stmt = next((c for c in alt_node.children if c.type != "else"), None)
        if else_stmt and body_node.text.decode("utf-8").strip() == else_stmt.text.decode("utf-8").strip():
            ctx.antipatrones.append(_make_antipatron(
                "0x1017h",
                ctx.archivo,
                idx,
                col,
                linea_cod,
                "Las ramas 'then' y 'else' de la estructura condicional son idénticas.",
            ))

    # AP045 (0x1018h): Dangling else por omitir llaves en if anidado
    if body_node and body_node.type == "if_statement":
        inner_has_else = body_node.child_by_field_name("alternative") is not None
        outer_has_else = alt_node is not None
        if inner_has_else or outer_has_else:
            ctx.antipatrones.append(_make_antipatron(
                "0x1018h",
                ctx.archivo,
                idx,
                col,
                linea_cod,
                "Sentencia 'if' anidada sin llaves delimitadoras con cláusula 'else' ambigua (dangling else).",
            ))

    if cond_node and body_node:
        cond_text = cond_node.text.decode("utf-8", errors="replace")
        body_text = body_node.text.decode("utf-8", errors="replace")

        # AP004: if (ptr != NULL) free(ptr);
        if ("!= NULL" in cond_text or "!= 0" in cond_text) and "free(" in body_text:
            ctx.antipatrones.append(_make_antipatron("0x3008h", ctx.archivo, idx, col, linea_cod))

    if cond_node:
        cond_text = cond_node.text.decode("utf-8", errors="replace")
        # AP005: if (cond == true) o if (cond == 1)
        if "== true" in cond_text or "== 1" in cond_text or "== TRUE" in cond_text:
            ctx.antipatrones.append(_make_antipatron("0x1005h", ctx.archivo, idx, col, linea_cod))

        # AP043: Operador bit a bit & o | en condición lógica
        def _has_bitwise_if(n: Node) -> bool:
            if n.type == "binary_expression":
                op = next((c.text.decode("utf-8") for c in n.children if c.type in ("&", "|")), None)
                if op:
                    curr = n.parent
                    in_cmp = False
                    while curr and curr != cond_node.parent:
                        if curr.type == "binary_expression":
                            c_op = next((c.text.decode("utf-8") for c in curr.children if c.type in ("==", "!=", "<", ">", "<=", ">=")), None)
                            if c_op:
                                in_cmp = True
                                break
                        curr = curr.parent
                    if not in_cmp:
                        return True
            for ch in n.children:
                if _has_bitwise_if(ch):
                    return True
            return False

        if _has_bitwise_if(cond_node):
            ctx.antipatrones.append(_make_antipatron(
                "0x1016h",
                ctx.archivo,
                idx,
                col,
                linea_cod,
                "Uso de operador a nivel de bits ('&' o '|') en condición lógica en lugar de operador booleano.",
            ))

        # AP016: if (x = 5) - asignación en condicional
        for child in cond_node.children:
            if child.type == "assignment_expression":
                ctx.antipatrones.append(_make_antipatron(
                    "0x100Ah",
                    ctx.archivo,
                    idx,
                    col,
                    linea_cod,
                    f"Asignación accidental en condición lógica '{child.text.decode('utf-8', errors='replace')}'.",
                ))
            elif child.type == "parenthesized_expression":
                for sub in child.children:
                    if sub.type == "assignment_expression":
                        ctx.antipatrones.append(_make_antipatron(
                            "0x100Ah",
                            ctx.archivo,
                            idx,
                            col,
                            linea_cod,
                            f"Asignación accidental en condición lógica '{sub.text.decode('utf-8', errors='replace')}'.",
                        ))

        # AP014: Número mágico en condición
        for child in cond_node.children:
            if child.type == "binary_expression":
                for operand in child.children:
                    if operand.type == "number_literal":
                        num_str = operand.text.decode("utf-8", errors="replace")
                        if num_str not in ("0", "1", "2", "-1", "0.0", "1.0"):
                            ctx.antipatrones.append(_make_antipatron(
                                "0x300Dh",
                                ctx.archivo,
                                idx,
                                col,
                                linea_cod,
                                f"Número mágico '{num_str}' utilizado directamente en condición lógica.",
                            ))

        # AP023: Expresión tautológica (x && !x, x || !x, x || true)
        if re.search(r"\b([a-zA-Z_]\w*)\s*&&\s*!\s*\1\b|\b([a-zA-Z_]\w*)\s*\|\|\s*!\s*\2\b|\|\|\s*true\b|&&\s*false\b", cond_text, re.IGNORECASE):
            ctx.antipatrones.append(_make_antipatron("0x100Eh", ctx.archivo, idx, col, linea_cod))

        # AP050: strcmp() directo como condición booleana
        cond_clean = cond_text.strip(" ()")
        if re.match(r"^!?\s*strcmp\s*\(", cond_clean) and not re.search(r"==|!=|<|>", cond_clean):
            ctx.antipatrones.append(_make_antipatron(
                "0x101Ah",
                ctx.archivo,
                idx,
                col,
                linea_cod,
                "Uso de 'strcmp()' como condición booleana directa sin comparación explícita contra 0.",
            ))

    # AP060: Desreferencia condicional de puntero local sin inicializar
    if body_node and ctx.uninit_pointers:
        b_text = body_node.text.decode("utf-8", errors="replace")
        for u_p in sorted(ctx.uninit_pointers):
            if re.search(rf"\*\s*{re.escape(u_p)}\b", b_text):
                ctx.antipatrones.append(_make_antipatron(
                    "0x3026h",
                    ctx.archivo,
                    idx,
                    col,
                    linea_cod,
                    f"Desreferencia condicional del puntero local no inicializado '{u_p}'.",
                ))


# AP009 (0x100Dh) & AP027 (0x100Fh) & AP006 (0x1001h) & AP039 (0x1014h) & AP040 (0x1015h): for statements
def _en_for_statement(node: Node, ctx: Contexto, idx: int, col: int, linea_cod: str) -> None:
    body_node = node.child_by_field_name("body")
    # AP006: Punto y coma accidental tras for (cuerpo vacío)
    if body_node and body_node.type == "expression_statement" and body_node.text.decode("utf-8").strip() == ";":
        ctx.antipatrones.append(_make_antipatron(
            "0x1001h",
            ctx.archivo,
            idx,
            col,
            linea_cod,
            "Punto y coma accidental tras la condición del for (cuerpo vacío).",
        ))

    # AP039: Invocación a strlen() en condición de parada
    cond_node = node.child_by_field_name("condition")
    if cond_node and re.search(r"\bstrlen\s*\(", cond_node.text.decode("utf-8", errors="replace")):
        ctx.antipatrones.append(_make_antipatron(
            "0x1014h",
            ctx.archivo,
            idx,
            col,
            linea_cod,
            "Invocación a 'strlen()' dentro de la condición de parada del bucle for (complejidad O(n^2)).",
        ))

    # AP040: Modificación de variable de control dentro del cuerpo
    ctrl_var = None
    init_node = node.child_by_field_name("initializer")
    if init_node:
        init_text = init_node.text.decode("utf-8", errors="replace")
        if re.match(r"^\s*(?:float|double)\b", init_text):
            ctx.antipatrones.append(_make_antipatron(
                "0x100Dh",
                ctx.archivo,
                idx,
                col,
                linea_cod,
                f"Contador de bucle de tipo coma flotante '{init_text}'.",
            ))
        for c in init_node.children:
            if c.type == "init_declarator":
                d_id = c.child_by_field_name("declarator")
                ctrl_var = _find_identifier(d_id or c)
                break
            elif c.type == "assignment_expression":
                l_id = c.child_by_field_name("left")
                ctrl_var = _find_identifier(l_id or c)
                break

    if not ctrl_var:
        upd_node = node.child_by_field_name("update")
        if upd_node:
            ctrl_var = _find_identifier(upd_node)

    if ctrl_var and body_node:
        def _check_ctrl_mod(n: Node) -> bool:
            if n.type in ("for_statement", "function_definition"):
                return False
            if n.type == "assignment_expression":
                l_id = n.child_by_field_name("left")
                if l_id and _find_identifier(l_id) == ctrl_var:
                    return True
            elif n.type == "update_expression":
                if _find_identifier(n) == ctrl_var:
                    return True
            for ch in n.children:
                if _check_ctrl_mod(ch):
                    return True
            return False

        if _check_ctrl_mod(body_node):
            ctx.antipatrones.append(_make_antipatron(
                "0x1015h",
                ctx.archivo,
                idx,
                col,
                linea_cod,
                f"Variable de control '{ctrl_var}' modificada dentro del cuerpo del bucle for.",
            ))

    # AP027: off-by-one en bucle for
    for_text = node.text.decode("utf-8", errors="replace")
    m_off = re.search(r"<=\s*(\d+)", for_text)
    if m_off:
        limit_num = m_off.group(1)
        curr = node.parent
        while curr and curr.type != "function_definition":
            curr = curr.parent
        if curr:
            f_text = curr.text.decode("utf-8", errors="replace")
            if f"[{limit_num}]" in f_text:
                ctx.antipatrones.append(_make_antipatron(
                    "0x100Fh",
                    ctx.archivo,
                    idx,
                    col,
                    linea_cod,
                    f"Posible error off-by-one: condición de parada '<= {limit_num}' excede los límites del arreglo.",
                ))

    if body_node:
        b_txt = body_node.text.decode("utf-8", errors="replace")
        # AP057: malloc en bucle sin liberación ante fallos parciales
        if re.search(r"\[[^\]]+\]\s*=\s*(?:malloc|calloc)\s*\(", b_txt) and "free(" not in b_txt:
            ctx.antipatrones.append(_make_antipatron(
                "0x3024h",
                ctx.archivo,
                idx,
                col,
                linea_cod,
                "Reserva dinámica en bucle sin liberación de elementos previos ante fallos parciales.",
            ))

        # AP062: Bucle infinito con salida condicionada exclusivamente por exit()
        cond_n = node.child_by_field_name("condition")
        if not cond_n:
            if re.search(r"\bexit\s*\(", b_txt) and not re.search(r"\b(?:break|return)\b", b_txt):
                ctx.antipatrones.append(_make_antipatron(
                    "0x101Ch",
                    ctx.archivo,
                    idx,
                    col,
                    linea_cod,
                    "Bucle infinito con terminación forzada exclusivamente por 'exit()'.",
                ))


# AP020 (0x5004h) & AP031 (0x1011h) & AP026 (0x3019h): binary expressions
_RELACIONALES = ("<", ">", "<=", ">=")
_LAZOS = ("for_statement", "while_statement", "do_statement")


def _dentro_de_lazo(node: Node) -> bool:
    padre = node.parent
    while padre is not None and padre.type != "function_definition":
        if padre.type in _LAZOS:
            return True
        padre = padre.parent
    return False


def _operador(node: Optional[Node]) -> str:
    if node is None or node.type != "binary_expression":
        return ""
    op = node.child_by_field_name("operator")
    return op.text.decode("utf-8") if op is not None else ""


def _en_binary_expression(node: Node, ctx: Contexto, idx: int, col: int, linea_cod: str) -> None:
    bin_text = node.text.decode("utf-8", errors="replace")

    # AP081 (QoL #940): `a < b < c` se evalúa como `(a < b) < c`
    if _operador(node) in _RELACIONALES and _operador(node.child_by_field_name("left")) in _RELACIONALES:
        ctx.antipatrones.append(_make_antipatron(
            "0x101Dh", ctx.archivo, idx, col, linea_cod,
            f"Comparaciones encadenadas en '{bin_text}': se evalúa como '({node.child_by_field_name('left').text.decode('utf-8', 'replace')}) ...'.",
        ))

    # AP080 (QoL #921): comparar contra EOF una variable char
    if _operador(node) in ("==", "!="):
        lados = [node.child_by_field_name("left"), node.child_by_field_name("right")]
        textos = [n.text.decode("utf-8", "replace").strip() if n is not None else "" for n in lados]
        if "EOF" in textos:
            otro = lados[1 - textos.index("EOF")]
            nombre = _find_identifier(otro) if otro is not None else None
            if nombre and ctx.var_types.get(nombre, "").replace("unsigned", "").replace("signed", "").strip() == "char":
                ctx.antipatrones.append(_make_antipatron(
                    "0x4010h", ctx.archivo, idx, col, linea_cod,
                    f"'{nombre}' es char y se compara contra EOF: getchar() devuelve int.",
                ))
    bin_op = next((c.text.decode("utf-8") for c in node.children if c.type in ("==", "!=")), "")
    if bin_op:
        left_n = node.child_by_field_name("left")
        right_n = node.child_by_field_name("right")
        if (left_n and left_n.type == "string_literal") or (right_n and right_n.type == "string_literal"):
            ctx.antipatrones.append(_make_antipatron(
                "0x5004b",
                ctx.archivo,
                idx,
                col,
                linea_cod,
                f"Comparación de cadenas con operador relacional '{bin_text}'.",
            ))
        # AP031: igualdad estricta con float
        if re.search(r"\b\d+\.\d+f?\b", bin_text):
            ctx.antipatrones.append(_make_antipatron(
                "0x1011h",
                ctx.archivo,
                idx,
                col,
                linea_cod,
                "Comparación de igualdad estricta ('==') sobre tipo de coma flotante.",
            ))

    # AP052: Comparación entre tipos con y sin signo
    bin_rel_op = next((c.text.decode("utf-8") for c in node.children if c.type in ("<", ">", "<=", ">=", "==", "!=")), "")
    if bin_rel_op:
        left_n = node.child_by_field_name("left")
        right_n = node.child_by_field_name("right")
        l_id = _find_identifier(left_n) if left_n else None
        r_id = _find_identifier(right_n) if right_n else None
        if l_id and r_id and l_id in ctx.var_types and r_id in ctx.var_types:
            t1 = ctx.var_types[l_id].replace(" ", "").replace("*", "")
            t2 = ctx.var_types[r_id].replace(" ", "").replace("*", "")
            signed_set = {"int", "short", "long", "int32_t", "int64_t", "ssize_t"}
            unsigned_set = {"size_t", "unsigned", "unsignedint", "unsignedlong", "uint32_t", "uint64_t"}
            if (t1 in signed_set and t2 in unsigned_set) or (t1 in unsigned_set and t2 in signed_set):
                ctx.antipatrones.append(_make_antipatron(
                    "0x101Bh",
                    ctx.archivo,
                    idx,
                    col,
                    linea_cod,
                    f"Comparación entre tipos con signo ('{t1}') y sin signo ('{t2}') entre '{l_id}' y '{r_id}'.",
                ))

        # AP041 (0x301Dh): Comparación sintáctica de puntero con carácter nulo '\0'
        def _is_null_char(n: Optional[Node]) -> bool:
            if not n or n.type != "char_literal":
                return False
            txt = n.text.decode("utf-8", "replace").strip("'")
            return txt in ("\\0", "")

        if _is_null_char(left_n) and right_n and right_n.type == "identifier":
            ctx.antipatrones.append(_make_antipatron(
                "0x301Dh",
                ctx.archivo,
                idx,
                col,
                linea_cod,
                f"Comparación sintáctica errónea de puntero '{right_n.text.decode('utf-8', 'replace')}' con '\\0' en lugar de desreferenciar.",
            ))
        elif _is_null_char(right_n) and left_n and left_n.type == "identifier":
            ctx.antipatrones.append(_make_antipatron(
                "0x301Dh",
                ctx.archivo,
                idx,
                col,
                linea_cod,
                f"Comparación sintáctica errónea de puntero '{left_n.text.decode('utf-8', 'replace')}' con '\\0' en lugar de desreferenciar.",
            ))

    # AP026: pointer decay sizeof
    if "/" in bin_text and "sizeof" in bin_text:
        m_decay = re.search(r"sizeof\s*\(\s*([a-zA-Z_]\w*)\s*\)\s*/\s*sizeof", bin_text)
        if m_decay:
            p_name = m_decay.group(1)
            curr = node.parent
            while curr and curr.type != "function_definition":
                curr = curr.parent
            if curr:
                decl_node = curr.child_by_field_name("declarator")
                if decl_node and p_name in decl_node.text.decode("utf-8"):
                    ctx.antipatrones.append(_make_antipatron(
                        "0x3019h",
                        ctx.archivo,
                        idx,
                        col,
                        linea_cod,
                        f"Pointer decay al usar sizeof sobre el parámetro '{p_name}'.",
                    ))


# AP007, AP008, AP013, AP019, AP025, AP036: llamadas a función
def _en_call_expression(node: Node, ctx: Contexto, idx: int, col: int, linea_cod: str) -> None:
    fn_node = node.child_by_field_name("function")
    fn_name = _find_identifier(fn_node) if fn_node else None
    args_node = next((c for c in node.children if c.type == "argument_list"), None)
    raw_args = args_node.text.decode("utf-8", errors="replace") if args_node else ""

    # AP078 (QoL #919): srand() dentro de un bucle
    if fn_name == "srand" and _dentro_de_lazo(node):
        ctx.antipatrones.append(_make_antipatron("0x2019h", ctx.archivo, idx, col, linea_cod))

    # AP019: gets()
    if fn_name == "gets":
        ctx.antipatrones.append(_make_antipatron(
            "0x5008h",
            ctx.archivo,
            idx,
            col,
            linea_cod,
            "Invocación de la función prohibida 'gets()'.",
        ))

    # AP025: printf / sprintf formato mismatch
    if fn_name in ("printf", "sprintf"):
        if re.search(r'"[^"]*%d[^"]*"\s*,\s*\d+\.\d+', raw_args) or re.search(r'"[^"]*%s[^"]*"\s*,\s*\d+\b', raw_args):
            ctx.antipatrones.append(_make_antipatron(
                "0x4008h",
                ctx.archivo,
                idx,
                col,
                linea_cod,
                "Desajuste entre el especificador de formato y el tipo de dato del argumento.",
            ))

    # AP013: strcpy, strcat, sprintf
    elif fn_name in ("strcpy", "strcat", "sprintf"):
        ctx.antipatrones.append(_make_antipatron(
            "0x5004h",
            ctx.archivo,
            idx,
            col,
            linea_cod,
            f"Uso de función insegura '{fn_name}()' sin limitación de longitud.",
        ))

    # AP007: fflush(stdin)
    elif fn_name == "fflush" and "stdin" in raw_args:
        ctx.antipatrones.append(_make_antipatron("0x4006h", ctx.archivo, idx, col, linea_cod))

    # AP036: memset(ptr, 0, sizeof(ptr))
    elif fn_name == "memset":
        m_ms = re.search(r"\(\s*([a-zA-Z_]\w*)\s*,\s*[^,]+,\s*sizeof\s*\(\s*([a-zA-Z_]\w*)\s*\)", raw_args)
        if m_ms and m_ms.group(1) == m_ms.group(2):
            ctx.antipatrones.append(_make_antipatron(
                "0x301Ah",
                ctx.archivo,
                idx,
                col,
                linea_cod,
                f"Tamaño insuficiente en memset: 'sizeof({m_ms.group(1)})' limpia solo el puntero.",
            ))

    # AP049: scanf/fscanf sin limitador de ancho con %s
    elif fn_name in ("scanf", "fscanf") and args_node:
        if re.search(r'"[^"]*%s', raw_args):
            ctx.antipatrones.append(_make_antipatron(
                "0x400Ah",
                ctx.archivo,
                idx,
                col,
                linea_cod,
                f"Lectura con '{fn_name}()' usando especificador '%s' sin límite de ancho.",
            ))

    # AP008 & AP042 (0x301Eh) & AP061 (0x3027h): malloc/calloc
    elif fn_name in ("malloc", "calloc") and args_node:
        # AP042: malloc(strlen(s)) sin espacio para byte nulo '\0'
        if re.search(r"\bstrlen\s*\(", raw_args) and not re.search(r"\+\s*(?:1|sizeof\s*\(\s*char\s*\))", raw_args):
            ctx.antipatrones.append(_make_antipatron(
                "0x301Eh",
                ctx.archivo,
                idx,
                col,
                linea_cod,
                "Reserva de memoria con 'malloc(strlen(...))' sin espacio para el byte terminador '\\0'.",
            ))

        # AP061: malloc(sizeof(struct ...) + n) sin sizeof(elemento)
        m_flex = re.search(r"sizeof\s*\(\s*struct\s+\w+\s*\)\s*\+\s*([a-zA-Z_]\w*|\d+)\s*\)", raw_args)
        if m_flex and "sizeof" not in raw_args[m_flex.start(1):]:
            ctx.antipatrones.append(_make_antipatron(
                "0x3027h",
                ctx.archivo,
                idx,
                col,
                linea_cod,
                "Cálculo erróneo de struct dinámico con miembro flexible: falta multiplicar por 'sizeof(tipo_elemento)'.",
            ))

        m_sz = re.search(r"sizeof\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)", raw_args)
        if m_sz:
            id_name = m_sz.group(1)
            tipos_base = {"int", "char", "float", "double", "long", "short", "size_t", "void", "uint8_t", "int32_t", "uint32_t", "int64_t", "uint64_t"}
            if not (id_name.endswith("_t") or id_name.startswith("t_") or id_name in tipos_base):
                ctx.antipatrones.append(_make_antipatron(
                    "0x300Fh",
                    ctx.archivo,
                    idx,
                    col,
                    linea_cod,
                    f"Uso de 'sizeof({id_name})' donde probablemente se requería 'sizeof(*{id_name})'.",
                ))

    # AP011 & AP038 (0x301Ch) & AP053 (0x3021h): free(ptr)
    elif fn_name == "free" and args_node:
        # AP038: Casteo redundante en llamada a free()
        for arg_c in args_node.children:
            if arg_c.type == "cast_expression":
                ctx.antipatrones.append(_make_antipatron(
                    "0x301Ch",
                    ctx.archivo,
                    idx,
                    col,
                    linea_cod,
                    "Casteo redundante de puntero en invocación a 'free()'.",
                ))
                break

        # AP053: Invocación a free() sobre memoria estática o stack (&var o local_arr)
        for arg_c in args_node.children:
            if arg_c.type == "pointer_expression" and arg_c.text.decode("utf-8", "replace").startswith("&"):
                ctx.antipatrones.append(_make_antipatron(
                    "0x3021h",
                    ctx.archivo,
                    idx,
                    col,
                    linea_cod,
                    f"Invocación a 'free()' sobre dirección de memoria de pila '{arg_c.text.decode('utf-8', 'replace')}'.",
                ))
                break
            elif arg_c.type == "identifier":
                a_name = arg_c.text.decode("utf-8", "replace")
                if a_name in ctx.local_arrays:
                    ctx.antipatrones.append(_make_antipatron(
                        "0x3021h",
                        ctx.archivo,
                        idx,
                        col,
                        linea_cod,
                        f"Invocación a 'free()' sobre arreglo local de pila '{a_name}'.",
                    ))
                    break

        arg_id = _find_identifier(args_node)
        if arg_id:
            curr = node.parent
            while curr and curr.type not in ("compound_statement", "function_definition"):
                curr = curr.parent
            if curr and curr.type == "compound_statement":
                comp_text = curr.text.decode("utf-8", errors="replace")
                pos_free = comp_text.find(f"free({arg_id})")
                if pos_free != -1:
                    sub_after = comp_text[pos_free:]
                    if not re.search(rf"\b{re.escape(arg_id)}\s*=\s*NULL\b", sub_after):
                        if not re.search(r"return\b", sub_after[:80]):
                            ctx.antipatrones.append(_make_antipatron(
                                "0x3002b",
                                ctx.archivo,
                                idx,
                                col,
                                linea_cod,
                                f"Puntero '{arg_id}' liberado con free() pero no anulado con NULL posteriormente.",
                            ))


# AP010 (0x3001h) & AP015 (0x200Bh) & AP018 (0x2009h) & AP054 (0x500Bh)
def _en_function_definition(node: Node, ctx: Contexto, idx: int, col: int, linea_cod: str) -> None:
    decl_node = node.child_by_field_name("declarator")
    body_node = node.child_by_field_name("body")
    fn_name = _find_identifier(decl_node) if decl_node else None

    # AP054: Redefinición de funciones estándar de biblioteca C
    if fn_name in ("abs", "min", "max", "index", "labs", "puts", "abort"):
        ctx.antipatrones.append(_make_antipatron(
            "0x500Bh",
            ctx.archivo,
            idx,
            col,
            linea_cod,
            f"Redefinición de identificador de función estándar '{fn_name}'.",
        ))

    # AP015: más de 5 parámetros
    if decl_node:
        param_list = None
        for c in decl_node.children:
            if c.type == "parameter_list":
                param_list = c
                break
        if param_list:
            params = [c for c in param_list.children if c.type == "parameter_declaration"]
            if len(params) > 5:
                ctx.antipatrones.append(_make_antipatron(
                    "0x200Bh",
                    ctx.archivo,
                    idx,
                    col,
                    linea_cod,
                    f"Función '{fn_name}' declara {len(params)} parámetros (máximo recomendado: 5).",
                ))

    # AP018: recursión sin caso base
    if fn_name and body_node:
        body_text = body_node.text.decode("utf-8", errors="replace")
        if re.search(rf"\b{re.escape(fn_name)}\s*\(", body_text):
            has_if = any(c.type == "if_statement" for c in body_node.children)
            if not has_if and "if" not in body_text and "?" not in body_text:
                ctx.antipatrones.append(_make_antipatron(
                    "0x2009h",
                    ctx.archivo,
                    idx,
                    col,
                    linea_cod,
                    f"Función recursiva '{fn_name}' sin condicional aparente para caso base (riesgo de recursión infinita).",
                ))

    # AP012: Variable local declarada pero no utilizada
    if body_node and body_node.type == "compound_statement":
        declared_vars = []
        for stmt in body_node.children:
            if stmt.type == "declaration":
                for decl_child in stmt.children:
                    if decl_child.type == "init_declarator":
                        id_node = decl_child.child_by_field_name("declarator")
                        v_name = _find_identifier(id_node or decl_child)
                        if v_name:
                            declared_vars.append((v_name, stmt.start_point.row + 1, stmt.start_point.column + 1))
                    elif decl_child.type == "identifier":
                        v_name = decl_child.text.decode("utf-8", errors="replace")
                        declared_vars.append((v_name, stmt.start_point.row + 1, stmt.start_point.column + 1))

        for v_name, v_row, v_col in declared_vars:
            occ = len(re.findall(rf"\b{re.escape(v_name)}\b", body_text))
            if occ <= 1:
                ctx.antipatrones.append(_make_antipatron(
                    "0x2007h",
                    ctx.archivo,
                    v_row,
                    v_col,
                    ctx.lineas[v_row - 1] if v_row <= len(ctx.lineas) else "",
                    f"Variable local '{v_name}' declarada pero no utilizada en el cuerpo de la función.",
                ))


# AP021 (0x100Ch): switch case sin break
def _en_case_statement(node: Node, ctx: Contexto, idx: int, col: int, linea_cod: str) -> None:
    statements = [c for c in node.children if c.type in ("expression_statement", "compound_statement", "return_statement", "break_statement", "goto_statement")]
    if statements:
        last_stmt = statements[-1]
        if last_stmt.type not in ("break_statement", "return_statement", "goto_statement"):
            has_term = False
            if last_stmt.type == "compound_statement":
                sub_stmts = [c for c in last_stmt.children if c.type in ("break_statement", "return_statement")]
                if sub_stmts:
                    has_term = True
            if not has_term:
                case_text = node.text.decode("utf-8", errors="replace")
                if "fallthrough" not in case_text.lower():
                    ctx.antipatrones.append(_make_antipatron("0x100Ch", ctx.archivo, idx, col, linea_cod))


# AP022 (0x0003h) & AP056 (0x3023h) & AP059 (0x400Bh): compound_statement
def _en_compound_statement(node: Node, ctx: Contexto, idx: int, col: int, linea_cod: str) -> None:
    saw_exec = False
    for child in node.children:
        if child.type in ("expression_statement", "if_statement", "while_statement", "for_statement", "switch_statement"):
            saw_exec = True
        elif child.type == "declaration" and saw_exec:
            ctx.antipatrones.append(_make_antipatron(
                "0x0003b",
                ctx.archivo,
                child.start_point.row + 1,
                child.start_point.column + 1,
                ctx.lineas[child.start_point.row] if child.start_point.row < len(ctx.lineas) else "",
            ))
            break

    # AP056: Comprobación de puntero nulo posterior a su desreferencia
    derefed_ptrs: Dict[str, int] = {}
    for child in node.children:
        ch_text = child.text.decode("utf-8", errors="replace")
        if child.type in ("expression_statement", "assignment_expression"):
            m_derefs = re.findall(r"(?:\*([a-zA-Z_]\w*)|([a-zA-Z_]\w*)->)", ch_text)
            for g1, g2 in m_derefs:
                ptr_var = g1 or g2
                if ptr_var and ptr_var in ctx.var_types and "*" in ctx.var_types[ptr_var] and ptr_var not in derefed_ptrs:
                    derefed_ptrs[ptr_var] = child.start_point.row + 1

        if child.type == "if_statement":
            cond_c = child.child_by_field_name("condition")
            if cond_c:
                c_str = cond_c.text.decode("utf-8", errors="replace")
                for ptr_var, d_line in list(derefed_ptrs.items()):
                    if re.search(rf"\b{re.escape(ptr_var)}\s*(?:==|!=)\s*NULL\b|\bNULL\s*(?:==|!=)\s*{re.escape(ptr_var)}\b|!\s*{re.escape(ptr_var)}\b", c_str):
                        ctx.antipatrones.append(_make_antipatron(
                            "0x3023h",
                            ctx.archivo,
                            child.start_point.row + 1,
                            child.start_point.column + 1,
                            ctx.lineas[child.start_point.row] if child.start_point.row < len(ctx.lineas) else "",
                            f"Comprobación de puntero nulo '{ptr_var}' posterior a su desreferencia en la línea {d_line}.",
                        ))

    # AP059: Omisión de verificación de retorno NULL en fopen()
    fopen_vars: Dict[str, int] = {}
    for child in node.children:
        ch_text = child.text.decode("utf-8", errors="replace")
        m_fo = re.search(r"\b([a-zA-Z_]\w*)\s*=\s*fopen\s*\(", ch_text)
        if m_fo:
            fopen_vars[m_fo.group(1)] = child.start_point.row + 1
            continue
        for f_v, f_line in list(fopen_vars.items()):
            if child.type == "if_statement":
                c_n = child.child_by_field_name("condition")
                if c_n and f_v in c_n.text.decode("utf-8", errors="replace"):
                    del fopen_vars[f_v]
            elif re.search(rf"\b(?:fread|fgets|fgetc|fscanf|fprintf|fputs|fwrite|fclose)\s*\([^)]*\b{re.escape(f_v)}\b", ch_text):
                ctx.antipatrones.append(_make_antipatron(
                    "0x400Bh",
                    ctx.archivo,
                    child.start_point.row + 1,
                    child.start_point.column + 1,
                    ctx.lineas[child.start_point.row] if child.start_point.row < len(ctx.lineas) else "",
                    f"Uso de descriptor de archivo '{f_v}' devuelto por fopen() en línea {f_line} sin comprobación previa de NULL.",
                ))
                del fopen_vars[f_v]


# AP051 (0x2013h): Descarte del valor retornado por funciones de conversión numérica
def _en_expression_statement(node: Node, ctx: Contexto, idx: int, col: int, linea_cod: str) -> None:
    for ch in node.children:
        if ch.type == "call_expression":
            fn_c = ch.child_by_field_name("function")
            fn_name_c = _find_identifier(fn_c) if fn_c else None
            if fn_name_c in ("strtol", "strtoul", "strtod"):
                ctx.antipatrones.append(_make_antipatron(
                    "0x2013h",
                    ctx.archivo,
                    idx,
                    col,
                    linea_cod,
                    f"Descarte del valor retornado por '{fn_name_c}()' sin verificación de errores.",
                ))


# AP058 (0x3025h): Modificación directa de puntero base retornado por malloc (update_expression)
def _en_update_expression(node: Node, ctx: Contexto, idx: int, col: int, linea_cod: str) -> None:
    u_id = _find_identifier(node)
    if u_id and u_id in ctx.malloc_vars:
        ctx.antipatrones.append(_make_antipatron(
            "0x3025h",
            ctx.archivo,
            idx,
            col,
            linea_cod,
            f"Modificación directa del puntero base '{u_id}' retornado por malloc/calloc.",
        ))


# AP024 (0x3015h) & AP055 (0x3022h) & AP058 (0x3025h): ptr = realloc(ptr, size), asignación
def _en_assignment_expression(node: Node, ctx: Contexto, idx: int, col: int, linea_cod: str) -> None:
    left_node = node.child_by_field_name("left")
    right_node = node.child_by_field_name("right")
    if left_node and right_node:
        l_name = _find_identifier(left_node)
        # AP055: Asignación de arreglo local a parámetro de salida
        l_txt = left_node.text.decode("utf-8", errors="replace")
        if l_txt.startswith("*"):
            r_id = _find_identifier(right_node)
            if (r_id and r_id in ctx.local_arrays) or (right_node.type == "pointer_expression" and right_node.text.decode("utf-8", errors="replace").startswith("&") and r_id in ctx.var_types and "*" not in ctx.var_types.get(r_id, "")):
                ctx.antipatrones.append(_make_antipatron(
                    "0x3022h",
                    ctx.archivo,
                    idx,
                    col,
                    linea_cod,
                    f"Asignación de variable o arreglo local '{r_id}' a parámetro de salida por referencia.",
                ))

        # AP058: Modificación directa de puntero base retornado por malloc (+=, -=)
        eq_op = next((c.text.decode("utf-8") for c in node.children if c.type in ("+=", "-=")), "")
        if eq_op and l_name in ctx.malloc_vars:
            ctx.antipatrones.append(_make_antipatron(
                "0x3025h",
                ctx.archivo,
                idx,
                col,
                linea_cod,
                f"Modificación directa del puntero base '{l_name}' retornado por malloc/calloc.",
            ))
        # AP029 (0x1010h): if (ptr = malloc(...) == NULL)
        if right_node.type == "binary_expression":
            bin_op = next((c.text.decode("utf-8") for c in right_node.children if c.type in ("==", "!=")), "")
            if bin_op:
                r_left = right_node.child_by_field_name("left")
                if r_left and r_left.type == "call_expression":
                    ctx.antipatrones.append(_make_antipatron(
                        "0x1010h",
                        ctx.archivo,
                        idx,
                        col,
                        linea_cod,
                        "Precedencia de operadores errónea: '==' evalúa antes que '='.",
                    ))

        if right_node.type == "call_expression":
            fn_node = right_node.child_by_field_name("function")
            args_node = next((c for c in right_node.children if c.type == "argument_list"), None)
            fn_name_a = _find_identifier(fn_node) if fn_node else None
            if fn_name_a == "realloc" and args_node:
                arg_children = [c for c in args_node.children if c.type not in ("(", ")", ",")]
                if arg_children:
                    first_arg_name = _find_identifier(arg_children[0])
                    if l_name and first_arg_name and l_name == first_arg_name:
                        ctx.antipatrones.append(_make_antipatron(
                            "0x3015h",
                            ctx.archivo,
                            idx,
                            col,
                            linea_cod,
                            f"Sobreescritura directa de puntero '{l_name}' en llamada a realloc.",
                        ))
            elif fn_name_a in ("malloc", "calloc") and l_name:
                if ctx.var_types.get(l_name) in ("int", "long", "short", "unsigned int", "unsigned long", "int32_t", "uint32_t"):
                    ctx.antipatrones.append(_make_antipatron(
                        "0x301Fh",
                        ctx.archivo,
                        idx,
                        col,
                        linea_cod,
                        f"Asignación de retorno de '{fn_name_a}()' a variable no puntero '{l_name}'.",
                    ))


# AP028 (0x5009h) & AP046 (0x301Fh): Declaraciones e inicializaciones
def _en_declaracion(node: Node, ctx: Contexto, idx: int, col: int, linea_cod: str) -> None:
    raw_text = node.text.decode("utf-8", errors="replace")
    # AP046: Asignación de retorno de malloc/calloc a variable no puntero en declaración
    if node.type == "declaration":
        type_n = node.child_by_field_name("type")
        type_txt = type_n.text.decode("utf-8", errors="replace") if type_n else ""
        if type_txt in ("int", "long", "short", "unsigned int", "unsigned long", "int32_t", "uint32_t"):
            for init_c in node.children:
                if init_c.type == "init_declarator":
                    decl_c = init_c.child_by_field_name("declarator")
                    val_c = init_c.child_by_field_name("value")
                    if decl_c and decl_c.type == "identifier" and val_c and val_c.type == "call_expression":
                        fn_c = val_c.child_by_field_name("function")
                        fn_name_c = _find_identifier(fn_c) if fn_c else None
                        if fn_name_c in ("malloc", "calloc"):
                            ctx.antipatrones.append(_make_antipatron(
                                "0x301Fh",
                                ctx.archivo,
                                idx,
                                col,
                                linea_cod,
                                f"Asignación de retorno de '{fn_name_c}()' a variable no puntero '{decl_c.text.decode('utf-8', errors='replace')}'.",
                            ))

    if re.search(r"\b(?:float|double)\b", raw_text) and "=" in raw_text:
        m_div = re.search(r"=\s*([0-9]+)\s*/\s*([0-9]+)", raw_text)
        if m_div:
            ctx.antipatrones.append(_make_antipatron(
                "0x5009h",
                ctx.archivo,
                idx,
                col,
                linea_cod,
                f"División entera '{m_div.group(1)} / {m_div.group(2)}' asignada a variable flotante.",
            ))


# AP070 (0x3029h): Desreferencia directa tras retorno de realloc (*realloc(...) o realloc(...)[i] o realloc(...)->field)
def _en_acceso_a_memoria(node: Node, ctx: Contexto, idx: int, col: int, linea_cod: str) -> None:
    n_txt = node.text.decode("utf-8", "replace")
    if "realloc(" in n_txt:
        # Comprobar si realloc está inmediatamente desreferenciado
        if node.type == "pointer_expression" and n_txt.startswith("*"):
            arg_c = node.child_by_field_name("argument")
            if arg_c and ("realloc" in arg_c.text.decode("utf-8", "replace")):
                ctx.antipatrones.append(_make_antipatron(
                    "0x3029h",
                    ctx.archivo,
                    idx,
                    col,
                    linea_cod,
                    "Desreferencia directa inmediata del retorno de realloc() sin validación previa de NULL.",
                ))
        elif node.type == "subscript_expression":
            arg_c = node.child_by_field_name("argument")
            if arg_c and ("realloc" in arg_c.text.decode("utf-8", "replace")):
                ctx.antipatrones.append(_make_antipatron(
                    "0x3029h",
                    ctx.archivo,
                    idx,
                    col,
                    linea_cod,
                    "Acceso por subíndice directo sobre el retorno de realloc() sin validación previa de NULL.",
                ))
        elif node.type == "field_expression":
            arg_c = node.child_by_field_name("argument")
            if arg_c and ("realloc" in arg_c.text.decode("utf-8", "replace")):
                ctx.antipatrones.append(_make_antipatron(
                    "0x3029h",
                    ctx.archivo,
                    idx,
                    col,
                    linea_cod,
                    "Acceso directo a campo sobre el retorno de realloc() sin validación previa de NULL.",
                ))


# Tipo de nodo de tree-sitter -> la función con sus reglas.
DESPACHO: Dict[str, Callable[[Node, Contexto, int, int, str], None]] = {
    "cast_expression": _en_cast_expression,
    "goto_statement": _en_goto_statement,
    "while_statement": _en_while_statement,
    "return_statement": _en_return_statement,
    "if_statement": _en_if_statement,
    "for_statement": _en_for_statement,
    "binary_expression": _en_binary_expression,
    "call_expression": _en_call_expression,
    "function_definition": _en_function_definition,
    "case_statement": _en_case_statement,
    "compound_statement": _en_compound_statement,
    "expression_statement": _en_expression_statement,
    "update_expression": _en_update_expression,
    "assignment_expression": _en_assignment_expression,
    "init_declarator": _en_declaracion,
    "declaration": _en_declaracion,
    "pointer_expression": _en_acceso_a_memoria,
    "subscript_expression": _en_acceso_a_memoria,
    "field_expression": _en_acceso_a_memoria,
}
