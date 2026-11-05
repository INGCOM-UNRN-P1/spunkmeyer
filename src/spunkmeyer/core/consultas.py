"""Antipatrones que son un patrón sintáctico puro, como consultas de tree-sitter.

Cada `ReglaConsulta` es una consulta con una captura `@hallazgo` (dónde se informa) y, si hace falta,
un mensaje que nombra otras capturas. Las reglas que dependen de lo que pasó antes en el archivo (los
tipos de las variables, un `fopen` sin comprobar, un puntero ya desreferenciado) no son expresables
así y siguen en `reglas_nodos.py`.

Se mudaría a `yutani.ts_queries` con la ola R1, igual que el motor de kaneda.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Dict, List, Optional, Tuple

from tree_sitter import Node, Query, QueryCursor

from spunkmeyer.core.nodos import lenguaje_c

CUERPO_VACIO = '(expression_statement . ";" .)'
RELACIONALES = '["<" ">" "<=" ">="]'
FUNCION_MALLOC = '(identifier) @funcion (#any-of? @funcion "malloc" "calloc")'


@dataclass(frozen=True)
class ReglaConsulta:
    codigo: str
    consulta: str
    # Plantilla con las capturas ({hallazgo}, {funcion}…); None usa el mensaje del catálogo.
    mensaje: Optional[str] = None
    # Condición sobre el archivo, que una consulta no puede ver.
    aplica: Optional[Callable[[object], bool]] = None


REGLAS: Tuple[ReglaConsulta, ...] = (
    # AP001: casteo del retorno de malloc
    ReglaConsulta("0x300Ah", f"(cast_expression value: (call_expression function: {FUNCION_MALLOC})) @hallazgo"),
    ReglaConsulta("0x3028h", f"(cast_expression value: (call_expression function: {FUNCION_MALLOC})) @hallazgo",
                  "Casteo explícito de 'malloc()' en archivo sin inclusión obligatoria de '<stdlib.h>'.",
                  lambda ctx: not ctx.has_stdlib),  # type: ignore[attr-defined]
    # AP006: punto y coma accidental tras la condición
    ReglaConsulta("0x1001h", f"(while_statement body: {CUERPO_VACIO}) @hallazgo",
                  "Punto y coma accidental tras la condición del while (cuerpo vacío)."),
    ReglaConsulta("0x1001h", f"(if_statement consequence: {CUERPO_VACIO}) @hallazgo",
                  "Punto y coma accidental tras la condición del if (cuerpo vacío)."),
    ReglaConsulta("0x1001h", f"(for_statement body: {CUERPO_VACIO}) @hallazgo",
                  "Punto y coma accidental tras la condición del for (cuerpo vacío)."),
    # AP045: dangling else
    ReglaConsulta("0x1018h", """[(if_statement consequence: (if_statement alternative: (_))) @hallazgo
                                 (if_statement consequence: (if_statement) alternative: (_)) @hallazgo]""",
                  "Sentencia 'if' anidada sin llaves delimitadoras con cláusula 'else' ambigua (dangling else)."),
    # AP016: asignación en la condición de un if
    ReglaConsulta("0x100Ah", """(if_statement condition: (parenthesized_expression
                                 [(assignment_expression) @asignacion
                                  (parenthesized_expression (assignment_expression) @asignacion)])) @hallazgo""",
                  "Asignación accidental en condición lógica '{asignacion}'."),
    # AP081: `a < b < c` se evalúa como `(a < b) < c`
    ReglaConsulta("0x101Dh", f"""(binary_expression left: (binary_expression operator: {RELACIONALES}) @izquierdo
                                                    operator: {RELACIONALES}) @hallazgo""",
                  "Comparaciones encadenadas en '{hallazgo}': se evalúa como '({izquierdo}) ...'."),
    # AP020: comparar cadenas con == o !=
    ReglaConsulta("0x5004b", """[(binary_expression left: (string_literal) operator: ["==" "!="]) @hallazgo
                                 (binary_expression operator: ["==" "!="] right: (string_literal)) @hallazgo]""",
                  "Comparación de cadenas con operador relacional '{hallazgo}'."),
    # AP029: `p = malloc(n) == NULL`
    ReglaConsulta("0x1010h", """(assignment_expression right: (binary_expression left: (call_expression)
                                                                                 operator: ["==" "!="])) @hallazgo""",
                  "Precedencia de operadores errónea: '==' evalúa antes que '='."),
    # AP019, AP013: funciones inseguras
    ReglaConsulta("0x5008h", '(call_expression function: (identifier) @funcion (#eq? @funcion "gets")) @hallazgo',
                  "Invocación de la función prohibida 'gets()'."),
    ReglaConsulta("0x5004h", """(call_expression function: (identifier) @funcion
                                 (#any-of? @funcion "strcpy" "strcat")) @hallazgo""",
                  "Uso de función insegura '{funcion}()' sin limitación de longitud."),
    # AP007: fflush(stdin)
    ReglaConsulta("0x4006h", """(call_expression function: (identifier) @funcion (#eq? @funcion "fflush")
                                 arguments: (argument_list (identifier) @flujo (#eq? @flujo "stdin"))) @hallazgo"""),
    # AP038: casteo en la llamada a free
    ReglaConsulta("0x301Ch", """(call_expression function: (identifier) @funcion (#eq? @funcion "free")
                                 arguments: (argument_list (cast_expression))) @hallazgo""",
                  "Casteo redundante de puntero en invocación a 'free()'."),
    # AP051: descartar lo que devuelve una conversión numérica
    ReglaConsulta("0x2013h", """(expression_statement (call_expression function: (identifier) @funcion
                                 (#any-of? @funcion "strtol" "strtoul" "strtod"))) @hallazgo""",
                  "Descarte del valor retornado por '{funcion}()' sin verificación de errores."),
    # AP054: redefinir una función estándar
    ReglaConsulta("0x500Bh", """(function_definition declarator: [
                                   (function_declarator declarator: (identifier) @funcion)
                                   (pointer_declarator declarator: (function_declarator declarator: (identifier) @funcion))]
                                 (#any-of? @funcion "abs" "min" "max" "index" "labs" "puts" "abort")) @hallazgo""",
                  "Redefinición de identificador de función estándar '{funcion}'."),
)


@lru_cache(maxsize=None)
def _compilada(consulta: str) -> Query:
    return Query(lenguaje_c(), consulta)


def _textos(capturas: Dict[str, List[Node]]) -> Dict[str, str]:
    return {nombre: (nodos[0].text or b"").decode("utf-8", errors="replace") for nombre, nodos in capturas.items()}


def aplicar_consultas(raiz: Node, ctx) -> None:
    """Anota en `ctx` lo que encuentra cada regla. Una consulta no recorre el árbol desde Python."""
    for regla in REGLAS:
        if regla.aplica is not None and not regla.aplica(ctx):
            continue
        for _, capturas in QueryCursor(_compilada(regla.consulta)).matches(raiz):
            nodo = capturas["hallazgo"][0]
            fila = nodo.start_point.row
            ctx.anotar(regla.codigo, fila + 1, nodo.start_point.column + 1,
                       ctx.lineas[fila] if fila < len(ctx.lineas) else "",
                       regla.mensaje.format(**_textos(capturas)) if regla.mensaje else None)
