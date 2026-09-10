"""Motor de detección de antipatrones y vicios didácticos en SPUNKMEYER usando Tree-Sitter AST."""

from __future__ import annotations

import re
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
        "ejemplo_incorrecto": "int *ptr = (int *)malloc(sizeof(int) * 10);",
        "ejemplo_correcto": "int *ptr = malloc(sizeof(*ptr) * 10);",
    },
    "0x4002h": {
        "codigo": "0x4002h",
        "alias": "AP002",
        "nombre": "Control de lectura con while(!feof())",
        "mensaje": "Usar '!feof(f)' como condición del bucle provoca procesar el último registro dos veces.",
        "explicacion": "'feof()' solo devuelve verdadero DESPUÉS de que una lectura previa intentó leer más allá del fin de archivo y falló.",
        "sugerencia": "Controlá el bucle con el valor de retorno de la función de lectura: 'while (fread(...) == 1)' o 'while (fgets(...) != NULL)'.",
        "ejemplo_incorrecto": "while (!feof(f)) {\n    fread(&elem, sizeof(elem), 1, f);\n    procesar(elem);\n}",
        "ejemplo_correcto": "while (fread(&elem, sizeof(elem), 1, f) == 1) {\n    procesar(elem);\n}",
    },
    "0x3002h": {
        "codigo": "0x3002h",
        "alias": "AP003",
        "nombre": "Retorno de puntero a variable local (Dangling Stack Pointer)",
        "mensaje": "Se detectó el retorno de la dirección de una variable local en la pila.",
        "explicacion": "Al finalizar la función, su stack frame se destruye. El puntero retornado apuntará a memoria inválida o sobrescribible.",
        "sugerencia": "Asigná memoria dinámica con malloc() o pasá el buffer como parámetro por referencia.",
        "ejemplo_incorrecto": "int* fn(void) {\n    int local = 42;\n    return &local;\n}",
        "ejemplo_correcto": "int* fn(void) {\n    int *ptr = malloc(sizeof(*ptr));\n    if (ptr) *ptr = 42;\n    return ptr;\n}",
    },
    "0x3008h": {
        "codigo": "0x3008h",
        "alias": "AP004",
        "nombre": "Chequeo innecesario antes de free()",
        "mensaje": "Comprobar 'if (ptr != NULL)' antes de invocar 'free(ptr)' es redundante.",
        "explicacion": "La especificación del estándar ISO C garantiza que 'free(NULL)' es una operación segura y no realiza ninguna acción.",
        "sugerencia": "Invocá 'free(ptr);' directamente sin envolverlo en un if.",
        "ejemplo_incorrecto": "if (ptr != NULL) {\n    free(ptr);\n}",
        "ejemplo_correcto": "free(ptr);",
    },
    "0x1005h": {
        "codigo": "0x1005h",
        "alias": "AP005",
        "nombre": "Comparación booleana explícita redundante",
        "mensaje": "Comparar explícitamente 'if (cond == 1)' o 'if (cond == true)' es redundante.",
        "explicacion": "En C cualquier valor distinto de 0 evalúa a verdadero en estructuras de control.",
        "sugerencia": "Escribí 'if (cond)' o 'if (!cond)' directamente.",
        "ejemplo_incorrecto": "if (es_valido == true) { ... }",
        "ejemplo_correcto": "if (es_valido) { ... }",
    },
    "0x1001h": {
        "codigo": "0x1001h",
        "alias": "AP006",
        "nombre": "Punto y coma accidental tras condición de control",
        "mensaje": "Punto y coma ';' detectado inmediatamente después de 'if (...)', 'for (...)' o 'while (...)'.",
        "explicacion": "El punto y coma crea una sentencia vacía, haciendo que el bloque que le sigue se ejecute incondicionalmente.",
        "sugerencia": "Eliminá el ';' al final de la condición de control.",
        "ejemplo_incorrecto": "if (x > 0);\n{\n    hacer_algo();\n}",
        "ejemplo_correcto": "if (x > 0)\n{\n    hacer_algo();\n}",
    },
    "0x4006h": {
        "codigo": "0x4006h",
        "alias": "AP007",
        "nombre": "Uso de fflush(stdin) para limpiar buffer",
        "mensaje": "Invocación de 'fflush(stdin)' detectada.",
        "explicacion": "Según el estándar ISO C, 'fflush()' solo está definido para streams de salida. Aplicarlo sobre 'stdin' produce comportamiento indefinido.",
        "sugerencia": "Consumí los caracteres restantes del buffer con 'while ((c = getchar()) != '\\n' && c != EOF);'.",
        "ejemplo_incorrecto": "scanf(\"%d\", &x);\nfflush(stdin);",
        "ejemplo_correcto": "int c;\nwhile ((c = getchar()) != '\\n' && c != EOF);",
    },
    "0x300Fh": {
        "codigo": "0x300Fh",
        "alias": "AP008",
        "nombre": "Uso de sizeof(puntero) en reserva dinámica",
        "mensaje": "Se detectó 'sizeof(ptr)' en lugar de 'sizeof(*ptr)' o 'sizeof(tipo)' en malloc/calloc.",
        "explicacion": "'sizeof(ptr)' devuelve el tamaño del puntero (4 u 8 bytes) en lugar del tamaño de la estructura apuntada, provocando reservas insuficientes.",
        "sugerencia": "Escribí 'malloc(sizeof(*ptr) * n)' o 'malloc(sizeof(struct tipo))'.",
        "ejemplo_incorrecto": "nodo_t *n = malloc(sizeof(n));",
        "ejemplo_correcto": "nodo_t *n = malloc(sizeof(*n));",
    },
    "0x100Dh": {
        "codigo": "0x100Dh",
        "alias": "AP009",
        "nombre": "Variable float o double utilizada como contador de bucle",
        "mensaje": "Se detectó una variable de tipo 'float' o 'double' como contador de bucle 'for'.",
        "explicacion": "Los tipos flotantes acumulan errores de redondeo binario IEEE-754 en cada iteración, provocando bucles infinitos o conteos inexactos.",
        "sugerencia": "Utilizá un contador entero (int o size_t) y derivá el valor flotante dentro del cuerpo del bucle.",
        "ejemplo_incorrecto": "for (float x = 0.0f; x < 1.0f; x += 0.1f) { ... }",
        "ejemplo_correcto": "for (int i = 0; i < 10; i++) {\n    float x = i * 0.1f;\n}",
    },
    "0x3001h": {
        "codigo": "0x3001h",
        "alias": "AP010",
        "nombre": "Uso de memoria dinámica sin validar retorno a NULL",
        "mensaje": "Desreferencia o uso directo de retorno de malloc/calloc sin verificar if (ptr == NULL).",
        "explicacion": "Si el sistema agota la memoria, malloc retorna NULL. Desreferenciar sin comprobación causará una caída fatal por SIGSEGV.",
        "sugerencia": "Comprobá siempre 'if (ptr == NULL)' inmediatamente después de la asignación.",
        "ejemplo_incorrecto": "int *p = malloc(10 * sizeof(*p));\np[0] = 42; // Caída si falla malloc",
        "ejemplo_correcto": "int *p = malloc(10 * sizeof(*p));\nif (p == NULL) return -1;\np[0] = 42;",
    },
    "0x3002b": {
        "codigo": "0x3002h",
        "alias": "AP011",
        "nombre": "Puntero colgante sin asignar NULL tras free()",
        "mensaje": "Puntero liberado con free() continúa en uso o no se anula explícitamente.",
        "explicacion": "Dejar la variable con la dirección anterior permite accesos accidentales Use-After-Free o Double-Free.",
        "sugerencia": "Asigná 'ptr = NULL;' inmediatamente después de 'free(ptr);'.",
        "ejemplo_incorrecto": "free(ptr);\n// más instrucciones donde ptr sigue apuntando a memoria liberada",
        "ejemplo_correcto": "free(ptr);\nptr = NULL;",
    },
    "0x2007h": {
        "codigo": "0x2007h",
        "alias": "AP012",
        "nombre": "Variable local declarada pero no utilizada",
        "mensaje": "Se declaró una variable local que no es leída ni referenciada en la función.",
        "explicacion": "Las variables residuales consumen memoria de stack y confunden al lector sobre el estado real de la función.",
        "sugerencia": "Eliminá la variable innecesaria para limpiar el ámbito local.",
        "ejemplo_incorrecto": "int main(void) {\n    int no_usada = 10;\n    return 0;\n}",
        "ejemplo_correcto": "int main(void) {\n    return 0;\n}",
    },
    "0x5004h": {
        "codigo": "0x5004h",
        "alias": "AP013",
        "nombre": "Uso de funciones inseguras de manipulación de cadenas (strcpy/sprintf)",
        "mensaje": "Invocación de función sin control de longitud de destino detectada.",
        "explicacion": "'strcpy' y 'sprintf' no limitan la cantidad de bytes escritos, causando desbordamiento de búfer (Buffer Overflow).",
        "sugerencia": "Migrá a 'snprintf' o copiá controlando explícitamente el tamaño máximo del destino.",
        "ejemplo_incorrecto": "char buf[16];\nsprintf(buf, \"%s: %d\", nombre, valor);",
        "ejemplo_correcto": "char buf[16];\nsnprintf(buf, sizeof(buf), \"%s: %d\", nombre, valor);",
    },
    "0x300Dh": {
        "codigo": "0x300Dh",
        "alias": "AP014",
        "nombre": "Número mágico literal en condición lógica",
        "mensaje": "Uso de literal numérico directo en condición de control o comparación.",
        "explicacion": "Los números mágicos oscurecen el significado del algoritmo e impiden la mantenibilidad del código.",
        "sugerencia": "Declarale un nombre significativo mediante una constante '#define' o 'enum'.",
        "ejemplo_incorrecto": "if (estado == 404) { ... }",
        "ejemplo_correcto": "#define ESTADO_NOT_FOUND 404\nif (estado == ESTADO_NOT_FOUND) { ... }",
    },
    "0x200Bh": {
        "codigo": "0x200Bh",
        "alias": "AP015",
        "nombre": "Función con excesiva cantidad de parámetros (> 5)",
        "mensaje": "Firma de función con más de 5 parámetros de entrada.",
        "explicacion": "Las funciones con muchos parámetros aumentan el acoplamiento y dificultan la invocación correcta en la pila.",
        "sugerencia": "Agrupá los parámetros relacionados en una estructura 'struct params_t'.",
        "ejemplo_incorrecto": "void config(int a, int b, int c, int d, int e, int f);",
        "ejemplo_correcto": "void config(const struct config_t *cfg);",
    },
    "0x100Ah": {
        "codigo": "0x100Ah",
        "alias": "AP016",
        "nombre": "Asignación accidental en condición lógica (if (x = 5))",
        "mensaje": "Asignación simple '=' dentro de la condición de un 'if' o 'while'.",
        "explicacion": "Casi con certeza se intentó escribir una comparación '==' en lugar de una asignación que altera la variable.",
        "sugerencia": "Utilizá '==' para comparar o extraé la asignación antes del condicional.",
        "ejemplo_incorrecto": "if (x = 5) { ... }",
        "ejemplo_correcto": "if (x == 5) { ... }",
    },
    "0x500Ah": {
        "codigo": "0x500Ah",
        "alias": "AP017",
        "nombre": "Macro con argumentos evaluados múltiples veces",
        "mensaje": "Macro de preprocesador evalúa un argumento más de una vez en su reemplazo.",
        "explicacion": "Si el cliente invoca la macro pasando una expresión con efecto colateral (ej. MAX(x++, y)), el argumento se evaluará repetidas veces.",
        "sugerencia": "Reemplazá la macro por una función inline o protegé las evaluaciones.",
        "ejemplo_incorrecto": "#define MAX(a, b) ((a) > (b) ? (a) : (b))",
        "ejemplo_correcto": "static inline int max(int a, int b) { return a > b ? a : b; }",
    },
    "0x2009h": {
        "codigo": "0x2009h",
        "alias": "AP018",
        "nombre": "Llamada recursiva sin caso base explícito",
        "mensaje": "Función recursiva que se invoca a sí misma sin condicional visible de parada.",
        "explicacion": "Toda función recursiva debe validar primero su caso base antes de invocarse nuevamente, previniendo un Stack Overflow.",
        "sugerencia": "Agregá la condición de corte (caso base) al inicio de la función.",
        "ejemplo_incorrecto": "void cuenta(int n) {\n    cuenta(n - 1);\n}",
        "ejemplo_correcto": "void cuenta(int n) {\n    if (n <= 0) return;\n    cuenta(n - 1);\n}",
    },
    "0x5008h": {
        "codigo": "0x5008h",
        "alias": "AP019",
        "nombre": "Invocación de la función prohibida gets()",
        "mensaje": "Llamada a 'gets()' detectada. Esta función fue removida de C11 por ser inherentemente insegura.",
        "explicacion": "'gets()' no recibe el tamaño del búfer destino y lee hasta encontrar un salto de línea, permitiendo desbordes triviales.",
        "sugerencia": "Reemplazala por 'fgets(buffer, sizeof(buffer), stdin)'.",
        "ejemplo_incorrecto": "char buf[100];\ngets(buf);",
        "ejemplo_correcto": "char buf[100];\nfgets(buf, sizeof(buf), stdin);",
    },
    "0x5004b": {
        "codigo": "0x5004h",
        "alias": "AP020",
        "nombre": "Comparación directa de cadenas con == o !=",
        "mensaje": "Se detectó comparación de cadena o puntero contra un literal con '==' o '!='.",
        "explicacion": "El operador '==' compara las direcciones de memoria de los punteros, no el contenido alfabético de las cadenas.",
        "sugerencia": "Utilizá 'strcmp(str, \"...\") == 0' para comparar el contenido textual.",
        "ejemplo_incorrecto": "if (str == \"hola\") { ... }",
        "ejemplo_correcto": "if (strcmp(str, \"hola\") == 0) { ... }",
    },
    "0x100Ch": {
        "codigo": "0x100Ch",
        "alias": "AP021",
        "nombre": "Caso de switch sin break (Fallthrough no intencional)",
        "mensaje": "Bloque 'case' sin sentencia 'break' previa al siguiente caso.",
        "explicacion": "Omitir el 'break' provoca que la ejecución caiga directamente al caso siguiente (fallthrough), usualmente un error no deseado.",
        "sugerencia": "Agregá 'break;' al final del caso o documentá explícitamente '// fallthrough'.",
        "ejemplo_incorrecto": "switch (op) {\ncase 1:\n    hacer_1();\ncase 2:\n    hacer_2();\n    break;\n}",
        "ejemplo_correcto": "switch (op) {\ncase 1:\n    hacer_1();\n    break;\ncase 2:\n    hacer_2();\n    break;\n}",
    },
    "0x0003b": {
        "codigo": "0x0003h",
        "alias": "AP022",
        "nombre": "Declaración de variable mezclada tras sentencias ejecutables",
        "mensaje": "Declaración de variable posterior a sentencias ejecutables dentro del mismo bloque.",
        "explicacion": "En C90 y estilo tradicional de cátedra, las variables deben declararse al inicio del bloque para claridad de dependencias.",
        "sugerencia": "Agrupá las declaraciones al comienzo del bloque de la función.",
        "ejemplo_incorrecto": "int a = 1;\na = a + 5;\nint b = 2; // Declaración retrasada",
        "ejemplo_correcto": "int a = 1;\nint b = 2;\na = a + 5;",
    },
    "0x100Eh": {
        "codigo": "0x100Eh",
        "alias": "AP023",
        "nombre": "Expresión booleana tautológica o contradictoria",
        "mensaje": "Condición lógica que siempre evalúa a verdadero o a falso (ej: x && !x o x || true).",
        "explicacion": "Las expresiones tautológicas representan lógica redundante o errores graves de razonamiento en la condición.",
        "sugerencia": "Simplificá la expresión lógica eliminando términos redundantes o contradictorios.",
        "ejemplo_incorrecto": "if (x && !x) { ... }",
        "ejemplo_correcto": "if (x) { ... }",
    },
}

ALIAS_MAP: Dict[str, str] = {
    "AP001": "0x300Ah",
    "AP002": "0x4002h",
    "AP003": "0x3002h",
    "AP004": "0x3008h",
    "AP005": "0x1005h",
    "AP006": "0x1001h",
    "AP007": "0x4006h",
    "AP008": "0x300Fh",
    "AP009": "0x100Dh",
    "AP010": "0x3001h",
    "AP011": "0x3002b",
    "AP012": "0x2007h",
    "AP013": "0x5004h",
    "AP014": "0x300Dh",
    "AP015": "0x200Bh",
    "AP016": "0x100Ah",
    "AP017": "0x500Ah",
    "AP018": "0x2009h",
    "AP019": "0x5008h",
    "AP020": "0x5004b",
    "AP021": "0x100Ch",
    "AP022": "0x0003b",
    "AP023": "0x100Eh",
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


def _make_antipatron(cod_key: str, archivo: Path, linea: int, columna: int, linea_cod: str, detalle_msg: Optional[str] = None) -> AntipatronDetectado:
    info = CATALOGO_ANTIPATRONES[cod_key]
    alias_val = info.get("alias", "")
    return AntipatronDetectado(
        codigo=RuleCode(info["codigo"], alias_val),
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
    source_bytes = contenido.encode("utf-8")
    parser = get_c_parser()
    tree = parser.parse(source_bytes)

    antipatrones: List[AntipatronDetectado] = []

    # Auditoría complementaria de macros de preprocesador (AP017)
    re_macro_multi = re.compile(r"^[ \t]*#\s*define\s+([a-zA-Z_]\w*)\s*\(([^)]+)\)\s*(.+)$", re.MULTILINE)
    for m in re_macro_multi.finditer(contenido):
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

    def _traverse(node: Node) -> None:
        idx = node.start_point.row + 1
        col = node.start_point.column + 1
        linea_cod = lineas[node.start_point.row] if node.start_point.row < len(lineas) else ""

        # AP001 (0x300Ah): Casteo redundante de malloc/calloc
        if node.type == "cast_expression":
            val_node = node.child_by_field_name("value")
            if val_node and val_node.type == "call_expression":
                fn_node = val_node.child_by_field_name("function")
                if fn_node and _find_identifier(fn_node) in ("malloc", "calloc"):
                    antipatrones.append(_make_antipatron("0x300Ah", archivo, idx, col, linea_cod))

        # AP002 (0x4002h): while(!feof())
        elif node.type == "while_statement":
            cond_node = node.child_by_field_name("condition")
            if cond_node:
                raw_cond = cond_node.text.decode("utf-8", errors="replace")
                if "feof" in raw_cond and "!" in raw_cond:
                    antipatrones.append(_make_antipatron("0x4002h", archivo, idx, col, linea_cod))

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

        # AP004 (0x3008h) & AP005 (0x1005h) & AP016 (0x100Ah) & AP014 (0x300Dh) & AP023 (0x100Eh)
        elif node.type == "if_statement":
            cond_node = node.child_by_field_name("condition")
            body_node = node.child_by_field_name("consequence")
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

                # AP016: if (x = 5) - asignación en condicional
                for child in cond_node.children:
                    if child.type == "assignment_expression":
                        antipatrones.append(_make_antipatron(
                            "0x100Ah",
                            archivo,
                            idx,
                            col,
                            linea_cod,
                            f"Asignación accidental en condición lógica '{child.text.decode("utf-8", errors="replace")}'.",
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
                                    f"Asignación accidental en condición lógica '{sub.text.decode("utf-8", errors="replace")}'.",
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

        # AP009 (0x100Dh): Contador float en for
        elif node.type == "for_statement":
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

        # AP020 (0x5004h): str == "hola"
        elif node.type == "binary_expression":
            op_node = node.child_by_field_name("operator")
            if op_node and op_node.text.decode("utf-8", errors="replace") in ("==", "!="):
                left_n = node.child_by_field_name("left")
                right_n = node.child_by_field_name("right")
                if (left_n and left_n.type == "string_literal") or (right_n and right_n.type == "string_literal"):
                    antipatrones.append(_make_antipatron(
                        "0x5004b",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        f"Comparación de cadenas con operador relacional '{node.text.decode("utf-8", errors="replace")}'.",
                    ))

        # AP007, AP008, AP013, AP019, AP011: llamadas a función
        elif node.type == "call_expression":
            fn_node = node.child_by_field_name("function")
            fn_name = _find_identifier(fn_node) if fn_node else None
            args_node = node.child_by_field_name("arguments")

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
            elif fn_name == "fflush" and args_node:
                raw_args = args_node.text.decode("utf-8", errors="replace")
                if "stdin" in raw_args:
                    antipatrones.append(_make_antipatron("0x4006h", archivo, idx, col, linea_cod))

            # AP008: sizeof(ptr) en malloc/calloc
            elif fn_name in ("malloc", "calloc") and args_node:
                raw_args = args_node.text.decode("utf-8", errors="replace")
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
                            f"Uso de 'sizeof({id_name})' donde '{id_name}' es presumiblemente un puntero.",
                        ))

            # AP011: free(ptr) seguido de uso o sin null
            elif fn_name == "free" and args_node:
                arg_id = _find_identifier(args_node)
                if arg_id:
                    # Inspeccionar si en el mismo bloque se reasigna o si es última sentencia
                    parent = node.parent
                    if parent and parent.type == "expression_statement":
                        grand = parent.parent
                        if grand and grand.type == "compound_statement":
                            siblings = grand.children
                            try:
                                pos = siblings.index(parent)
                                # Si hay sentencias posteriores en el bloque antes del return
                                remaining = [s for s in siblings[pos + 1:] if s.type not in ("}", ";")]
                                if remaining:
                                    next_stmt = remaining[0]
                                    next_text = next_stmt.text.decode("utf-8", errors="replace")
                                    # Si la siguiente no es asignación a NULL y no es return
                                    if next_stmt.type != "return_statement" and f"{arg_id} = NULL" not in next_text and f"{arg_id}=NULL" not in next_text:
                                        # Si el identificador vuelve a ser usado en el resto del bloque
                                        rest_text = "".join(s.text.decode("utf-8", errors="replace") for s in remaining)
                                        if re.search(rf"\b{re.escape(arg_id)}\b", rest_text):
                                            antipatrones.append(_make_antipatron(
                                                "0x3002b",
                                                archivo,
                                                idx,
                                                col,
                                                linea_cod,
                                                f"Uso de puntero '{arg_id}' posterior a su liberación con free() (Dangling Pointer / Use-After-Free).",
                                            ))
                            except ValueError:
                                pass

        # AP015 (0x200Bh) & AP018 (0x2009h) & AP012 (0x2007h): function_definition
        elif node.type == "function_definition":
            decl_node = node.child_by_field_name("declarator")
            fn_name = None
            if decl_node:
                fn_id_node = decl_node.child_by_field_name("declarator")
                fn_name = _find_identifier(fn_id_node or decl_node)

            # AP015: Más de 5 parámetros
            param_list = None
            for ch in (decl_node.children if decl_node else []):
                if ch.type == "parameter_list":
                    param_list = ch
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
                        f"Función '{fn_name or "anónima"}' posee {len(params)} parámetros (máximo recomendado: 5).",
                    ))

            # AP018: Recursión sin caso base explícito
            body_node = node.child_by_field_name("body")
            if fn_name and body_node:
                body_text = body_node.text.decode("utf-8", errors="replace")
                # Llamada recursiva directa
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

                # Contar ocurrencias en el cuerpo
                for v_name, v_row, v_col in declared_vars:
                    # Encontrar apariciones del identificador fuera de la declaración
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
                    # Verificar si la última instrucción de un bloque compuesto contiene break/return
                    has_term = False
                    if last_stmt.type == "compound_statement":
                        sub_stmts = [c for c in last_stmt.children if c.type in ("break_statement", "return_statement")]
                        if sub_stmts:
                            has_term = True
                    if not has_term:
                        case_text = node.text.decode("utf-8", errors="replace")
                        if "fallthrough" not in case_text.lower():
                            antipatrones.append(_make_antipatron("0x100Ch", archivo, idx, col, linea_cod))

        # AP022 (0x0003h): Declaración tras sentencia ejecutable en bloque
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

        for child in node.children:
            _traverse(child)

    _traverse(tree.root_node)
    antipatrones.sort(key=lambda a: (a.linea, a.columna))
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
