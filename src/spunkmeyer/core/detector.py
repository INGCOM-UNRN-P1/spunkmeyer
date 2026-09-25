from typing import Dict, List, Optional, Set, Any, Tuple
from pathlib import Path
import re
from tree_sitter import Language, Parser, Node
import tree_sitter_c as tsc
from spunkmeyer.core.models import AntipatronDetectado, ReporteAntipatrones, RuleCode
from spunkmeyer.core.catalog import (
    CATALOGO_ANTIPATRONES,
    ALIAS_MAP,
    MAPA_ANTIPATRONES,
    obtener_antipatron,
    cargar_reglas_personalizadas_yaml,
)
from spunkmeyer.core.preprocessor import (
    enmascarar_comentarios,
    enmascarar_codigo_inactivo,
)
from spunkmeyer.core.exporters import (
    generar_sarif_210_spunkmeyer,
    generar_seccion_markdown,
    correlacionar_con_hal,
    comparar_antipatrones_entre_versiones,
)


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



def auditar_archivo(archivo: Path) -> List[AntipatronDetectado]:
    """Analiza un archivo C y detecta los 20+ antipatrones didácticos usando Tree-Sitter AST."""
    archivo = Path(archivo)
    if not archivo.is_file():
        return []

    try:
        contenido = archivo.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    lineas = contenido.splitlines()
    contenido_auditado = enmascarar_codigo_inactivo(enmascarar_comentarios(contenido))
    source_bytes = contenido_auditado.encode("utf-8")
    parser = get_c_parser()
    tree = parser.parse(source_bytes)

    antipatrones: List[AntipatronDetectado] = []

    # Auditoría complementaria de macros que ofuscan sintaxis (AP034)
    re_macro_ofuscada = re.compile(r"^[ \t]*#\s*define\s+([a-zA-Z_]\w*)[ \t]+([^\n\r]+)", re.MULTILINE)
    for m in re_macro_ofuscada.finditer(contenido_auditado):
        m_name = m.group(1)
        m_body = m.group(2).strip()
        if m_name in ("BEGIN", "END", "AND", "OR", "THEN") or m_body in ("{", "}", "&&", "||"):
            line_no = contenido[:m.start()].count("\n") + 1
            antipatrones.append(_make_antipatron(
                "0x0039h",
                archivo,
                line_no,
                1,
                lineas[line_no - 1] if line_no <= len(lineas) else "",
                f"Macro '{m_name}' enmascara sintaxis nativa de C.",
            ))

    # Auditoría complementaria de macros de preprocesador (AP017)
    re_macro_multi = re.compile(r"^[ \t]*#\s*define\s+([a-zA-Z_]\w*)\s*\(([^)]+)\)\s*(.+)$", re.MULTILINE)
    for m in re_macro_multi.finditer(contenido_auditado):
        m_name = m.group(1)
        params = [p.strip() for p in m.group(2).split(",") if p.strip()]
        body = m.group(3)
        for p in params:
            # Buscar ocurrencias del parámetro en el cuerpo
            occ = len(re.findall(rf"\b{re.escape(p)}\b", body))
            if occ >= 2:
                line_no = contenido[:m.start()].count("\n") + 1
                antipatrones.append(_make_antipatron(
                    "0x500Ah",
                    archivo,
                    line_no,
                    1,
                    lineas[line_no - 1] if line_no <= len(lineas) else "",
                    f"Macro '{m_name}' evalúa el parámetro '{p}' {occ} veces en su cuerpo.",
                ))
                break

    # Recolección previa de etiquetas para detección de backward goto (AP048)
    etiquetas_lineas: Dict[str, int] = {}
    def _collect_labels(n: Node) -> None:
        if n.type == "labeled_statement":
            lbl_n = n.child_by_field_name("label") or next((c for c in n.children if c.type == "statement_identifier"), None)
            if lbl_n:
                etiquetas_lineas[lbl_n.text.decode("utf-8", "replace")] = n.start_point.row + 1
        for ch in n.children:
            _collect_labels(ch)

    _collect_labels(tree.root_node)

    has_stdlib = bool(re.search(r'#\s*include\s*[<"]stdlib\.h[>"]', contenido_auditado))

    # Recolección previa de tipos para detección de strict aliasing (AP047) y no-punteros (AP046/AP052/AP053/AP055/AP058/AP060)
    var_types: Dict[str, str] = {}
    local_arrays: Set[str] = set()
    malloc_vars: Set[str] = set()
    uninit_pointers: Set[str] = set()

    def _collect_var_types(n: Node) -> None:
        if n.type == "declaration":
            t_n = n.child_by_field_name("type")
            t_text = t_n.text.decode("utf-8", "replace") if t_n else ""
            for ch in n.children:
                if ch.type == "init_declarator":
                    d_c = ch.child_by_field_name("declarator")
                    v_c = ch.child_by_field_name("value")
                    if d_c:
                        is_ptr = d_c.type == "pointer_declarator"
                        is_arr = d_c.type == "array_declarator"
                        v_id = _find_identifier(d_c)
                        if v_id:
                            var_types[v_id] = f"{t_text}*" if is_ptr else (f"{t_text}[]" if is_arr else t_text)
                            if is_arr:
                                local_arrays.add(v_id)
                            if is_ptr:
                                if v_c:
                                    c_expr = v_c
                                    if v_c.type == "cast_expression":
                                        c_expr = v_c.child_by_field_name("value")
                                    if c_expr and c_expr.type == "call_expression":
                                        fn_c = c_expr.child_by_field_name("function")
                                        if fn_c and _find_identifier(fn_c) in ("malloc", "calloc"):
                                            malloc_vars.add(v_id)
                                else:
                                    uninit_pointers.add(v_id)
                elif ch.type == "pointer_declarator":
                    v_id = _find_identifier(ch)
                    if v_id:
                        var_types[v_id] = f"{t_text}*"
                        uninit_pointers.add(v_id)
                elif ch.type == "array_declarator":
                    v_id = _find_identifier(ch)
                    if v_id:
                        var_types[v_id] = f"{t_text}[]"
                        local_arrays.add(v_id)
                elif ch.type == "identifier":
                    var_types[ch.text.decode("utf-8", "replace")] = t_text
        elif n.type == "parameter_declaration":
            t_n = n.child_by_field_name("type")
            t_text = t_n.text.decode("utf-8", "replace") if t_n else ""
            d_c = n.child_by_field_name("declarator")
            if d_c:
                is_ptr = d_c.type == "pointer_declarator"
                v_id = _find_identifier(d_c)
                if v_id:
                    var_types[v_id] = f"{t_text}*" if is_ptr else t_text
        elif n.type == "assignment_expression":
            l_n = n.child_by_field_name("left")
            r_n = n.child_by_field_name("right")
            l_id = _find_identifier(l_n) if l_n else None
            if l_id and r_n:
                call_target = r_n
                if r_n.type == "cast_expression":
                    call_target = r_n.child_by_field_name("value")
                if call_target and call_target.type == "call_expression":
                    fn = call_target.child_by_field_name("function")
                    if fn and _find_identifier(fn) in ("malloc", "calloc"):
                        malloc_vars.add(l_id)
                        uninit_pointers.discard(l_id)
        for ch in n.children:
            _collect_var_types(ch)

    _collect_var_types(tree.root_node)

    def _traverse(node: Node) -> None:
        idx = node.start_point.row + 1
        col = node.start_point.column + 1
        linea_cod = lineas[node.start_point.row] if node.start_point.row < len(lineas) else ""

        # AP001 (0x300Ah) & AP047 (0x3020h): Casteos
        if node.type == "cast_expression":
            val_node = node.child_by_field_name("value")
            if val_node and val_node.type == "call_expression":
                fn_node = val_node.child_by_field_name("function")
                if fn_node and _find_identifier(fn_node) in ("malloc", "calloc"):
                    antipatrones.append(_make_antipatron("0x300Ah", archivo, idx, col, linea_cod))
                    if not has_stdlib:
                        antipatrones.append(_make_antipatron(
                            "0x3028h",
                            archivo,
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
                if val_id and val_id in var_types:
                    orig_type = var_types[val_id].replace(" ", "").replace("*", "")
                    incompatibles = {
                        ("int", "float"), ("float", "int"),
                        ("int", "double"), ("double", "int"),
                        ("long", "float"), ("float", "long"),
                        ("long", "double"), ("double", "long"),
                    }
                    t_desc = type_n.text.decode("utf-8", errors="replace")
                    if (cast_type_txt, orig_type) in incompatibles:
                        antipatrones.append(_make_antipatron(
                            "0x3020h",
                            archivo,
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
                        antipatrones.append(_make_antipatron(
                            "0x302Ah",
                            archivo,
                            idx,
                            col,
                            linea_cod,
                            f"Casteo forzado de constante numérica '{v_str}' a tipo puntero '{t_str}'.",
                        ))

        # AP048 (0x1019h): Salto goto hacia atrás (desestructurado)
        elif node.type == "goto_statement":
            lbl_n = node.child_by_field_name("label") or next((c for c in node.children if c.type == "statement_identifier"), None)
            if lbl_n:
                lbl_name = lbl_n.text.decode("utf-8", errors="replace")
                if lbl_name in etiquetas_lineas and etiquetas_lineas[lbl_name] <= idx:
                    antipatrones.append(_make_antipatron(
                        "0x1019h",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        f"Salto 'goto {lbl_name}' hacia atrás en la línea {etiquetas_lineas[lbl_name]} simulando un lazo desestructurado.",
                    ))

        # AP002 (0x4002h) & AP006 (0x1001h) & AP043 (0x1016h): while statements
        elif node.type == "while_statement":
            cond_node = node.child_by_field_name("condition")
            body_node = node.child_by_field_name("body")
            if body_node and body_node.type == "expression_statement" and body_node.text.decode("utf-8").strip() == ";":
                antipatrones.append(_make_antipatron(
                    "0x1001h",
                    archivo,
                    idx,
                    col,
                    linea_cod,
                    "Punto y coma accidental tras la condición del while (cuerpo vacío).",
                ))
            if cond_node:
                raw_cond = cond_node.text.decode("utf-8", errors="replace")
                if "feof" in raw_cond and "!" in raw_cond:
                    antipatrones.append(_make_antipatron("0x4002h", archivo, idx, col, linea_cod))

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
                    antipatrones.append(_make_antipatron(
                        "0x1016h",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        "Uso de operador a nivel de bits ('&' o '|') en condición lógica en lugar de operador booleano.",
                    ))

                # AP050: strcmp() directo como condición booleana
                cond_clean = raw_cond.strip(" ()")
                if re.match(r"^!?\s*strcmp\s*\(", cond_clean) and not re.search(r"==|!=|<|>", cond_clean):
                    antipatrones.append(_make_antipatron(
                        "0x101Ah",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        "Uso de 'strcmp()' como condición booleana directa sin comparación explícita contra 0.",
                    ))

            if body_node:
                b_txt = body_node.text.decode("utf-8", errors="replace")
                # AP057: malloc en bucle sin liberación ante fallos parciales
                if re.search(r"\[[^\]]+\]\s*=\s*(?:malloc|calloc)\s*\(", b_txt) and "free(" not in b_txt:
                    antipatrones.append(_make_antipatron(
                        "0x3024h",
                        archivo,
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
                            antipatrones.append(_make_antipatron(
                                "0x101Ch",
                                archivo,
                                idx,
                                col,
                                linea_cod,
                                "Bucle infinito con terminación forzada exclusivamente por 'exit()'.",
                            ))

        # AP003 (0x3002h): Retorno de puntero a variable local
        elif node.type == "return_statement":
            raw_ret = node.text.decode("utf-8", errors="replace")
            if "&" in raw_ret:
                m = re.search(r"&\s*([a-zA-Z_][a-zA-Z0-9_]*)", raw_ret)
                var_name = m.group(1) if m else "var"
                antipatrones.append(_make_antipatron(
                    "0x3002h",
                    archivo,
                    idx,
                    col,
                    linea_cod,
                    f"Retorno de dirección de variable local '&{var_name}'.",
                ))

        # AP004, AP005, AP016, AP014, AP023, AP006, AP043, AP044, AP045: if statements
        elif node.type == "if_statement":
            cond_node = node.child_by_field_name("condition")
            body_node = node.child_by_field_name("consequence")
            alt_node = node.child_by_field_name("alternative")

            # AP006: Punto y coma accidental tras condición
            if body_node and body_node.type == "expression_statement" and body_node.text.decode("utf-8").strip() == ";":
                antipatrones.append(_make_antipatron(
                    "0x1001h",
                    archivo,
                    idx,
                    col,
                    linea_cod,
                    "Punto y coma accidental tras la condición del if (cuerpo vacío).",
                ))

            # AP044 (0x1017h): Ramas then y else idénticas
            if body_node and alt_node:
                else_stmt = next((c for c in alt_node.children if c.type != "else"), None)
                if else_stmt and body_node.text.decode("utf-8").strip() == else_stmt.text.decode("utf-8").strip():
                    antipatrones.append(_make_antipatron(
                        "0x1017h",
                        archivo,
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
                    antipatrones.append(_make_antipatron(
                        "0x1018h",
                        archivo,
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
                    antipatrones.append(_make_antipatron("0x3008h", archivo, idx, col, linea_cod))

            if cond_node:
                cond_text = cond_node.text.decode("utf-8", errors="replace")
                # AP005: if (cond == true) o if (cond == 1)
                if "== true" in cond_text or "== 1" in cond_text or "== TRUE" in cond_text:
                    antipatrones.append(_make_antipatron("0x1005h", archivo, idx, col, linea_cod))

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
                    antipatrones.append(_make_antipatron(
                        "0x1016h",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        "Uso de operador a nivel de bits ('&' o '|') en condición lógica en lugar de operador booleano.",
                    ))

                # AP016: if (x = 5) - asignación en condicional
                for child in cond_node.children:
                    if child.type == "assignment_expression":
                        antipatrones.append(_make_antipatron(
                            "0x100Ah",
                            archivo,
                            idx,
                            col,
                            linea_cod,
                            f"Asignación accidental en condición lógica '{child.text.decode('utf-8', errors='replace')}'.",
                        ))
                    elif child.type == "parenthesized_expression":
                        for sub in child.children:
                            if sub.type == "assignment_expression":
                                antipatrones.append(_make_antipatron(
                                    "0x100Ah",
                                    archivo,
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
                                    antipatrones.append(_make_antipatron(
                                        "0x300Dh",
                                        archivo,
                                        idx,
                                        col,
                                        linea_cod,
                                        f"Número mágico '{num_str}' utilizado directamente en condición lógica.",
                                    ))

                # AP023: Expresión tautológica (x && !x, x || !x, x || true)
                if re.search(r"\b([a-zA-Z_]\w*)\s*&&\s*!\s*\1\b|\b([a-zA-Z_]\w*)\s*\|\|\s*!\s*\2\b|\|\|\s*true\b|&&\s*false\b", cond_text, re.IGNORECASE):
                    antipatrones.append(_make_antipatron("0x100Eh", archivo, idx, col, linea_cod))

                # AP050: strcmp() directo como condición booleana
                cond_clean = cond_text.strip(" ()")
                if re.match(r"^!?\s*strcmp\s*\(", cond_clean) and not re.search(r"==|!=|<|>", cond_clean):
                    antipatrones.append(_make_antipatron(
                        "0x101Ah",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        "Uso de 'strcmp()' como condición booleana directa sin comparación explícita contra 0.",
                    ))

            # AP060: Desreferencia condicional de puntero local sin inicializar
            if body_node and uninit_pointers:
                b_text = body_node.text.decode("utf-8", errors="replace")
                for u_p in sorted(uninit_pointers):
                    if re.search(rf"\*\s*{re.escape(u_p)}\b", b_text):
                        antipatrones.append(_make_antipatron(
                            "0x3026h",
                            archivo,
                            idx,
                            col,
                            linea_cod,
                            f"Desreferencia condicional del puntero local no inicializado '{u_p}'.",
                        ))

        # AP009 (0x100Dh) & AP027 (0x100Fh) & AP006 (0x1001h) & AP039 (0x1014h) & AP040 (0x1015h): for statements
        elif node.type == "for_statement":
            body_node = node.child_by_field_name("body")
            # AP006: Punto y coma accidental tras for (cuerpo vacío)
            if body_node and body_node.type == "expression_statement" and body_node.text.decode("utf-8").strip() == ";":
                antipatrones.append(_make_antipatron(
                    "0x1001h",
                    archivo,
                    idx,
                    col,
                    linea_cod,
                    "Punto y coma accidental tras la condición del for (cuerpo vacío).",
                ))

            # AP039: Invocación a strlen() en condición de parada
            cond_node = node.child_by_field_name("condition")
            if cond_node and re.search(r"\bstrlen\s*\(", cond_node.text.decode("utf-8", errors="replace")):
                antipatrones.append(_make_antipatron(
                    "0x1014h",
                    archivo,
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
                    antipatrones.append(_make_antipatron(
                        "0x100Dh",
                        archivo,
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
                    antipatrones.append(_make_antipatron(
                        "0x1015h",
                        archivo,
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
                        antipatrones.append(_make_antipatron(
                            "0x100Fh",
                            archivo,
                            idx,
                            col,
                            linea_cod,
                            f"Posible error off-by-one: condición de parada '<= {limit_num}' excede los límites del arreglo.",
                        ))

            if body_node:
                b_txt = body_node.text.decode("utf-8", errors="replace")
                # AP057: malloc en bucle sin liberación ante fallos parciales
                if re.search(r"\[[^\]]+\]\s*=\s*(?:malloc|calloc)\s*\(", b_txt) and "free(" not in b_txt:
                    antipatrones.append(_make_antipatron(
                        "0x3024h",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        "Reserva dinámica en bucle sin liberación de elementos previos ante fallos parciales.",
                    ))

                # AP062: Bucle infinito con salida condicionada exclusivamente por exit()
                cond_n = node.child_by_field_name("condition")
                if not cond_n:
                    if re.search(r"\bexit\s*\(", b_txt) and not re.search(r"\b(?:break|return)\b", b_txt):
                        antipatrones.append(_make_antipatron(
                            "0x101Ch",
                            archivo,
                            idx,
                            col,
                            linea_cod,
                            "Bucle infinito con terminación forzada exclusivamente por 'exit()'.",
                        ))

        # AP020 (0x5004h) & AP031 (0x1011h) & AP026 (0x3019h): binary expressions
        elif node.type == "binary_expression":
            bin_text = node.text.decode("utf-8", errors="replace")
            bin_op = next((c.text.decode("utf-8") for c in node.children if c.type in ("==", "!=")), "")
            if bin_op:
                left_n = node.child_by_field_name("left")
                right_n = node.child_by_field_name("right")
                if (left_n and left_n.type == "string_literal") or (right_n and right_n.type == "string_literal"):
                    antipatrones.append(_make_antipatron(
                        "0x5004b",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        f"Comparación de cadenas con operador relacional '{bin_text}'.",
                    ))
                # AP031: igualdad estricta con float
                if re.search(r"\b\d+\.\d+f?\b", bin_text):
                    antipatrones.append(_make_antipatron(
                        "0x1011h",
                        archivo,
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
                if l_id and r_id and l_id in var_types and r_id in var_types:
                    t1 = var_types[l_id].replace(" ", "").replace("*", "")
                    t2 = var_types[r_id].replace(" ", "").replace("*", "")
                    signed_set = {"int", "short", "long", "int32_t", "int64_t", "ssize_t"}
                    unsigned_set = {"size_t", "unsigned", "unsignedint", "unsignedlong", "uint32_t", "uint64_t"}
                    if (t1 in signed_set and t2 in unsigned_set) or (t1 in unsigned_set and t2 in signed_set):
                        antipatrones.append(_make_antipatron(
                            "0x101Bh",
                            archivo,
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
                    antipatrones.append(_make_antipatron(
                        "0x301Dh",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        f"Comparación sintáctica errónea de puntero '{right_n.text.decode('utf-8', 'replace')}' con '\\0' en lugar de desreferenciar.",
                    ))
                elif _is_null_char(right_n) and left_n and left_n.type == "identifier":
                    antipatrones.append(_make_antipatron(
                        "0x301Dh",
                        archivo,
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
                            antipatrones.append(_make_antipatron(
                                "0x3019h",
                                archivo,
                                idx,
                                col,
                                linea_cod,
                                f"Pointer decay al usar sizeof sobre el parámetro '{p_name}'.",
                            ))

        # AP007, AP008, AP013, AP019, AP025, AP036: llamadas a función
        elif node.type == "call_expression":
            fn_node = node.child_by_field_name("function")
            fn_name = _find_identifier(fn_node) if fn_node else None
            args_node = next((c for c in node.children if c.type == "argument_list"), None)
            raw_args = args_node.text.decode("utf-8", errors="replace") if args_node else ""

            # AP019: gets()
            if fn_name == "gets":
                antipatrones.append(_make_antipatron(
                    "0x5008h",
                    archivo,
                    idx,
                    col,
                    linea_cod,
                    "Invocación de la función prohibida 'gets()'.",
                ))

            # AP025: printf / sprintf formato mismatch
            if fn_name in ("printf", "sprintf"):
                if re.search(r'"[^"]*%d[^"]*"\s*,\s*\d+\.\d+', raw_args) or re.search(r'"[^"]*%s[^"]*"\s*,\s*\d+\b', raw_args):
                    antipatrones.append(_make_antipatron(
                        "0x4008h",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        "Desajuste entre el especificador de formato y el tipo de dato del argumento.",
                    ))

            # AP013: strcpy, strcat, sprintf
            elif fn_name in ("strcpy", "strcat", "sprintf"):
                antipatrones.append(_make_antipatron(
                    "0x5004h",
                    archivo,
                    idx,
                    col,
                    linea_cod,
                    f"Uso de función insegura '{fn_name}()' sin limitación de longitud.",
                ))

            # AP007: fflush(stdin)
            elif fn_name == "fflush" and "stdin" in raw_args:
                antipatrones.append(_make_antipatron("0x4006h", archivo, idx, col, linea_cod))

            # AP036: memset(ptr, 0, sizeof(ptr))
            elif fn_name == "memset":
                m_ms = re.search(r"\(\s*([a-zA-Z_]\w*)\s*,\s*[^,]+,\s*sizeof\s*\(\s*([a-zA-Z_]\w*)\s*\)", raw_args)
                if m_ms and m_ms.group(1) == m_ms.group(2):
                    antipatrones.append(_make_antipatron(
                        "0x301Ah",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        f"Tamaño insuficiente en memset: 'sizeof({m_ms.group(1)})' limpia solo el puntero.",
                    ))

            # AP049: scanf/fscanf sin limitador de ancho con %s
            elif fn_name in ("scanf", "fscanf") and args_node:
                if re.search(r'"[^"]*%s', raw_args):
                    antipatrones.append(_make_antipatron(
                        "0x400Ah",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        f"Lectura con '{fn_name}()' usando especificador '%s' sin límite de ancho.",
                    ))

            # AP008 & AP042 (0x301Eh) & AP061 (0x3027h): malloc/calloc
            elif fn_name in ("malloc", "calloc") and args_node:
                # AP042: malloc(strlen(s)) sin espacio para byte nulo '\0'
                if re.search(r"\bstrlen\s*\(", raw_args) and not re.search(r"\+\s*(?:1|sizeof\s*\(\s*char\s*\))", raw_args):
                    antipatrones.append(_make_antipatron(
                        "0x301Eh",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        "Reserva de memoria con 'malloc(strlen(...))' sin espacio para el byte terminador '\\0'.",
                    ))

                # AP061: malloc(sizeof(struct ...) + n) sin sizeof(elemento)
                m_flex = re.search(r"sizeof\s*\(\s*struct\s+\w+\s*\)\s*\+\s*([a-zA-Z_]\w*|\d+)\s*\)", raw_args)
                if m_flex and "sizeof" not in raw_args[m_flex.start(1):]:
                    antipatrones.append(_make_antipatron(
                        "0x3027h",
                        archivo,
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
                        antipatrones.append(_make_antipatron(
                            "0x300Fh",
                            archivo,
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
                        antipatrones.append(_make_antipatron(
                            "0x301Ch",
                            archivo,
                            idx,
                            col,
                            linea_cod,
                            "Casteo redundante de puntero en invocación a 'free()'.",
                        ))
                        break

                # AP053: Invocación a free() sobre memoria estática o stack (&var o local_arr)
                for arg_c in args_node.children:
                    if arg_c.type == "pointer_expression" and arg_c.text.decode("utf-8", "replace").startswith("&"):
                        antipatrones.append(_make_antipatron(
                            "0x3021h",
                            archivo,
                            idx,
                            col,
                            linea_cod,
                            f"Invocación a 'free()' sobre dirección de memoria de pila '{arg_c.text.decode('utf-8', 'replace')}'.",
                        ))
                        break
                    elif arg_c.type == "identifier":
                        a_name = arg_c.text.decode("utf-8", "replace")
                        if a_name in local_arrays:
                            antipatrones.append(_make_antipatron(
                                "0x3021h",
                                archivo,
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
                                    antipatrones.append(_make_antipatron(
                                        "0x3002b",
                                        archivo,
                                        idx,
                                        col,
                                        linea_cod,
                                        f"Puntero '{arg_id}' liberado con free() pero no anulado con NULL posteriormente.",
                                    ))

        # AP010 (0x3001h) & AP015 (0x200Bh) & AP018 (0x2009h) & AP054 (0x500Bh)
        elif node.type == "function_definition":
            decl_node = node.child_by_field_name("declarator")
            body_node = node.child_by_field_name("body")
            fn_name = _find_identifier(decl_node) if decl_node else None

            # AP054: Redefinición de funciones estándar de biblioteca C
            if fn_name in ("abs", "min", "max", "index", "labs", "puts", "abort"):
                antipatrones.append(_make_antipatron(
                    "0x500Bh",
                    archivo,
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
                        antipatrones.append(_make_antipatron(
                            "0x200Bh",
                            archivo,
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
                        antipatrones.append(_make_antipatron(
                            "0x2009h",
                            archivo,
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
                        antipatrones.append(_make_antipatron(
                            "0x2007h",
                            archivo,
                            v_row,
                            v_col,
                            lineas[v_row - 1] if v_row <= len(lineas) else "",
                            f"Variable local '{v_name}' declarada pero no utilizada en el cuerpo de la función.",
                        ))

        # AP021 (0x100Ch): switch case sin break
        elif node.type == "case_statement":
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
                            antipatrones.append(_make_antipatron("0x100Ch", archivo, idx, col, linea_cod))

        # AP022 (0x0003h) & AP056 (0x3023h) & AP059 (0x400Bh): compound_statement
        elif node.type == "compound_statement":
            saw_exec = False
            for child in node.children:
                if child.type in ("expression_statement", "if_statement", "while_statement", "for_statement", "switch_statement"):
                    saw_exec = True
                elif child.type == "declaration" and saw_exec:
                    antipatrones.append(_make_antipatron(
                        "0x0003b",
                        archivo,
                        child.start_point.row + 1,
                        child.start_point.column + 1,
                        lineas[child.start_point.row] if child.start_point.row < len(lineas) else "",
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
                        if ptr_var and ptr_var in var_types and "*" in var_types[ptr_var] and ptr_var not in derefed_ptrs:
                            derefed_ptrs[ptr_var] = child.start_point.row + 1

                if child.type == "if_statement":
                    cond_c = child.child_by_field_name("condition")
                    if cond_c:
                        c_str = cond_c.text.decode("utf-8", errors="replace")
                        for ptr_var, d_line in list(derefed_ptrs.items()):
                            if re.search(rf"\b{re.escape(ptr_var)}\s*(?:==|!=)\s*NULL\b|\bNULL\s*(?:==|!=)\s*{re.escape(ptr_var)}\b|!\s*{re.escape(ptr_var)}\b", c_str):
                                antipatrones.append(_make_antipatron(
                                    "0x3023h",
                                    archivo,
                                    child.start_point.row + 1,
                                    child.start_point.column + 1,
                                    lineas[child.start_point.row] if child.start_point.row < len(lineas) else "",
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
                        antipatrones.append(_make_antipatron(
                            "0x400Bh",
                            archivo,
                            child.start_point.row + 1,
                            child.start_point.column + 1,
                            lineas[child.start_point.row] if child.start_point.row < len(lineas) else "",
                            f"Uso de descriptor de archivo '{f_v}' devuelto por fopen() en línea {f_line} sin comprobación previa de NULL.",
                        ))
                        del fopen_vars[f_v]

        # AP051 (0x2013h): Descarte del valor retornado por funciones de conversión numérica
        elif node.type == "expression_statement":
            for ch in node.children:
                if ch.type == "call_expression":
                    fn_c = ch.child_by_field_name("function")
                    fn_name_c = _find_identifier(fn_c) if fn_c else None
                    if fn_name_c in ("strtol", "strtoul", "strtod"):
                        antipatrones.append(_make_antipatron(
                            "0x2013h",
                            archivo,
                            idx,
                            col,
                            linea_cod,
                            f"Descarte del valor retornado por '{fn_name_c}()' sin verificación de errores.",
                        ))

        # AP058 (0x3025h): Modificación directa de puntero base retornado por malloc (update_expression)
        elif node.type == "update_expression":
            u_id = _find_identifier(node)
            if u_id and u_id in malloc_vars:
                antipatrones.append(_make_antipatron(
                    "0x3025h",
                    archivo,
                    idx,
                    col,
                    linea_cod,
                    f"Modificación directa del puntero base '{u_id}' retornado por malloc/calloc.",
                ))

        # AP024 (0x3015h) & AP055 (0x3022h) & AP058 (0x3025h): ptr = realloc(ptr, size), asignación
        elif node.type == "assignment_expression":
            left_node = node.child_by_field_name("left")
            right_node = node.child_by_field_name("right")
            if left_node and right_node:
                l_name = _find_identifier(left_node)
                # AP055: Asignación de arreglo local a parámetro de salida
                l_txt = left_node.text.decode("utf-8", errors="replace")
                if l_txt.startswith("*"):
                    r_id = _find_identifier(right_node)
                    if (r_id and r_id in local_arrays) or (right_node.type == "pointer_expression" and right_node.text.decode("utf-8", errors="replace").startswith("&") and r_id in var_types and "*" not in var_types.get(r_id, "")):
                        antipatrones.append(_make_antipatron(
                            "0x3022h",
                            archivo,
                            idx,
                            col,
                            linea_cod,
                            f"Asignación de variable o arreglo local '{r_id}' a parámetro de salida por referencia.",
                        ))

                # AP058: Modificación directa de puntero base retornado por malloc (+=, -=)
                eq_op = next((c.text.decode("utf-8") for c in node.children if c.type in ("+=", "-=")), "")
                if eq_op and l_name in malloc_vars:
                    antipatrones.append(_make_antipatron(
                        "0x3025h",
                        archivo,
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
                            antipatrones.append(_make_antipatron(
                                "0x1010h",
                                archivo,
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
                                antipatrones.append(_make_antipatron(
                                    "0x3015h",
                                    archivo,
                                    idx,
                                    col,
                                    linea_cod,
                                    f"Sobreescritura directa de puntero '{l_name}' en llamada a realloc.",
                                ))
                    elif fn_name_a in ("malloc", "calloc") and l_name:
                        if var_types.get(l_name) in ("int", "long", "short", "unsigned int", "unsigned long", "int32_t", "uint32_t"):
                            antipatrones.append(_make_antipatron(
                                "0x301Fh",
                                archivo,
                                idx,
                                col,
                                linea_cod,
                                f"Asignación de retorno de '{fn_name_a}()' a variable no puntero '{l_name}'.",
                            ))

        # AP028 (0x5009h) & AP046 (0x301Fh): Declaraciones e inicializaciones
        elif node.type in ("init_declarator", "declaration"):
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
                                    antipatrones.append(_make_antipatron(
                                        "0x301Fh",
                                        archivo,
                                        idx,
                                        col,
                                        linea_cod,
                                        f"Asignación de retorno de '{fn_name_c}()' a variable no puntero '{decl_c.text.decode('utf-8', errors='replace')}'.",
                                    ))

            if re.search(r"\b(?:float|double)\b", raw_text) and "=" in raw_text:
                m_div = re.search(r"=\s*([0-9]+)\s*/\s*([0-9]+)", raw_text)
                if m_div:
                    antipatrones.append(_make_antipatron(
                        "0x5009h",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        f"División entera '{m_div.group(1)} / {m_div.group(2)}' asignada a variable flotante.",
                    ))


        # AP070 (0x3029h): Desreferencia directa tras retorno de realloc (*realloc(...) o realloc(...)[i] o realloc(...)->field)
        elif node.type in ("pointer_expression", "subscript_expression", "field_expression"):
            n_txt = node.text.decode("utf-8", "replace")
            if "realloc(" in n_txt:
                # Comprobar si realloc está inmediatamente desreferenciado
                if node.type == "pointer_expression" and n_txt.startswith("*"):
                    arg_c = node.child_by_field_name("argument")
                    if arg_c and ("realloc" in arg_c.text.decode("utf-8", "replace")):
                        antipatrones.append(_make_antipatron(
                            "0x3029h",
                            archivo,
                            idx,
                            col,
                            linea_cod,
                            "Desreferencia directa inmediata del retorno de realloc() sin validación previa de NULL.",
                        ))
                elif node.type == "subscript_expression":
                    arg_c = node.child_by_field_name("argument")
                    if arg_c and ("realloc" in arg_c.text.decode("utf-8", "replace")):
                        antipatrones.append(_make_antipatron(
                            "0x3029h",
                            archivo,
                            idx,
                            col,
                            linea_cod,
                            "Acceso por subíndice directo sobre el retorno de realloc() sin validación previa de NULL.",
                        ))
                elif node.type == "field_expression":
                    arg_c = node.child_by_field_name("argument")
                    if arg_c and ("realloc" in arg_c.text.decode("utf-8", "replace")):
                        antipatrones.append(_make_antipatron(
                            "0x3029h",
                            archivo,
                            idx,
                            col,
                            linea_cod,
                            "Acceso directo a campo sobre el retorno de realloc() sin validación previa de NULL.",
                        ))

        for child in node.children:
            _traverse(child)

    _traverse(tree.root_node)

    # Filtro de supresión de falsos positivos en línea: // spunkmeyer:ignore 0xXXXXh [o APXXX o SP0xXXXXh]
    # Mapeo de líneas que contienen directivas de supresión
    supresiones_por_linea: Dict[int, Set[str]] = {}
    re_ignore = re.compile(r"//\s*spunkmeyer:ignore\s+([A-Za-z0-9_,\s]+)", re.IGNORECASE)
    for num_linea, l_texto in enumerate(lineas, start=1):
        m_ign = re_ignore.search(l_texto)
        if m_ign:
            tokens = {tok.strip().lower() for tok in m_ign.group(1).replace(",", " ").split() if tok.strip()}
            supresiones_por_linea[num_linea] = tokens

    antipatrones_filtrados = []
    for ap in antipatrones:
        ign_tokens = supresiones_por_linea.get(ap.linea, set())
        c_low = str(ap.codigo).lower()
        alias_low = getattr(ap.codigo, "_alias", "").lower()
        sp_low = getattr(ap.codigo, "_sp_code", "").lower()
        if not (c_low in ign_tokens or alias_low in ign_tokens or sp_low in ign_tokens or "all" in ign_tokens):
            antipatrones_filtrados.append(ap)

    antipatrones_filtrados.sort(key=lambda a: (a.linea, a.columna))
    return antipatrones_filtrados


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
        try:
            todos.extend(auditar_archivo(arch))
        except Exception:
            continue

    return ReporteAntipatrones(
        total_archivos=len(archivos_objetivo),
        antipatrones=todos,
    )


