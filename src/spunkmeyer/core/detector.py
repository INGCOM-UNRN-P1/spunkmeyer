from typing import Dict, List, Set, Any, Tuple
from pathlib import Path
import re
from tree_sitter import Node
from spunkmeyer.core.models import AntipatronDetectado, ReporteAntipatrones, RuleCode  # noqa: F401
from spunkmeyer.core.catalog import (
    CATALOGO_ANTIPATRONES,  # noqa: F401 — lo importan los tests y otras herramientas desde acá
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


# Parser y auxiliares compartidos con las reglas por tipo de nodo; se importan acá también para que
# `from spunkmeyer.core.detector import get_c_parser` siga funcionando.
from spunkmeyer.core.nodos import _find_identifier, _make_antipatron, get_c_parser  # noqa: E402,F401
from spunkmeyer.core.reglas_nodos import DESPACHO, Contexto  # noqa: E402


def _auditar_macros(archivo: Path, contenido: str, contenido_auditado: str, lineas: List[str]) -> List[AntipatronDetectado]:
    """Reglas sobre el texto de los #define (AP034, AP017): no necesitan el árbol."""
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
    return antipatrones


def _recolectar_etiquetas(raiz: Node) -> Dict[str, int]:
    """Línea de cada etiqueta, para detectar los goto hacia atrás (AP048)."""
    etiquetas_lineas: Dict[str, int] = {}
    def _collect_labels(n: Node) -> None:
        if n.type == "labeled_statement":
            lbl_n = n.child_by_field_name("label") or next((c for c in n.children if c.type == "statement_identifier"), None)
            if lbl_n:
                etiquetas_lineas[lbl_n.text.decode("utf-8", "replace")] = n.start_point.row + 1
        for ch in n.children:
            _collect_labels(ch)

    _collect_labels(raiz)
    return etiquetas_lineas


def _recolectar_tipos(raiz: Node) -> Tuple[Dict[str, str], Set[str], Set[str], Set[str]]:
    """Tipos de las variables, arreglos locales, punteros de malloc y punteros sin inicializar."""
    # Para strict aliasing (AP047) y las reglas de punteros (AP046/AP052/AP053/AP055/AP058/AP060).
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

    _collect_var_types(raiz)
    return var_types, local_arrays, malloc_vars, uninit_pointers


def _recorrer(node: Node, ctx: Contexto) -> None:
    """Aplica a cada nodo las reglas de su tipo (reglas_nodos.DESPACHO) y sigue por sus hijos."""
    revisar = DESPACHO.get(node.type)
    if revisar is not None:
        fila = node.start_point.row
        linea_cod = ctx.lineas[fila] if fila < len(ctx.lineas) else ""
        revisar(node, ctx, fila + 1, node.start_point.column + 1, linea_cod)
    for child in node.children:
        _recorrer(child, ctx)


def _filtrar_supresiones(antipatrones: List[AntipatronDetectado], lineas: List[str]) -> List[AntipatronDetectado]:
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
    return antipatrones_filtrados


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
    raiz = get_c_parser().parse(contenido_auditado.encode("utf-8")).root_node

    var_types, local_arrays, malloc_vars, uninit_pointers = _recolectar_tipos(raiz)
    ctx = Contexto(
        archivo=archivo,
        lineas=lineas,
        contenido=contenido,
        contenido_auditado=contenido_auditado,
        has_stdlib=bool(re.search(r'#\s*include\s*[<"]stdlib\.h[>"]', contenido_auditado)),
        etiquetas_lineas=_recolectar_etiquetas(raiz),
        var_types=var_types,
        local_arrays=local_arrays,
        malloc_vars=malloc_vars,
        uninit_pointers=uninit_pointers,
        antipatrones=_auditar_macros(archivo, contenido, contenido_auditado, lineas),
    )
    _recorrer(raiz, ctx)

    antipatrones_filtrados = _filtrar_supresiones(ctx.antipatrones, lineas)
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


