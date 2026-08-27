"""Motor de detección de antipatrones y vicios didácticos en SPUNKMEYER."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Set

from spunkmeyer.core.models import AntipatronDetectado, ReporteAntipatrones

CATALOGO_ANTIPATRONES: Dict[str, Dict[str, str]] = {
    "AP001": {
        "nombre": "Casteo redundante de malloc()",
        "mensaje": "Castear el retorno de 'malloc()' es innecesario en C y puede enmascarar la falta de #include <stdlib.h>.",
        "explicacion": "En C, 'void*' se promociona automáticamente a cualquier tipo de puntero. Castear '(tipo*)malloc()' proviene de C++ y es una mala práctica en C.",
        "sugerencia": "Escribí 'ptr = malloc(sizeof(*ptr) * n);' directamente.",
    },
    "AP002": {
        "nombre": "Control de lectura con while(!feof())",
        "mensaje": "Usar '!feof(f)' como condición del bucle provoca procesar el último registro dos veces.",
        "explicacion": "'feof()' solo devuelve verdadero DESPUÉS de que una lectura previa intentó leer más allá del fin de archivo y falló.",
        "sugerencia": "Controlá el bucle con el valor de retorno de la función de lectura: 'while (fread(...) == 1)' o 'while (fgets(...) != NULL)'.",
    },
    "AP003": {
        "nombre": "Retorno de puntero a variable local (Dangling Pointer)",
        "mensaje": "Se detectó el retorno de la dirección de una variable local en la pila.",
        "explicacion": "Al finalizar la función, su frame de pila se destruye. El puntero retornado apuntará a memoria inválida/basura.",
        "sugerencia": "Asigná memoria dinámica con malloc() o pasá el búfer como parámetro por referencia.",
    },
    "AP004": {
        "nombre": "Chequeo innecesario antes de free()",
        "mensaje": "Comprobar 'if (ptr != NULL)' antes de invocar 'free(ptr)' es redundante.",
        "explicacion": "La especificación del estándar C garantiza que 'free(NULL)' no realiza ninguna acción y es 100% seguro.",
        "sugerencia": "Invocá 'free(ptr);' directamente sin envolverlo en un if.",
    },
    "AP005": {
        "nombre": "Comparación booleana explícita redundante",
        "mensaje": "Comparar explícitamente 'if (cond == 1)' o 'if (cond == true)' es redundante.",
        "explicacion": "En C cualquier valor distinto de 0 evalúa a verdadero en estructuras de control.",
        "sugerencia": "Escribí 'if (cond)' o 'if (!cond)' directamente.",
    },
    "AP006": {
        "nombre": "Punto y coma accidental tras condición de control",
        "mensaje": "Punto y coma ';' detectado inmediatamente después de 'if (...)', 'for (...)' o 'while (...)'.",
        "explicacion": "El punto y coma crea una sentencia vacía, haciendo que el bloque que le sigue se ejecute incondicionalmente.",
        "sugerencia": "Eliminá el ';' al final de la condición de control.",
    },
}


def _eliminar_comentarios(texto: str) -> str:
    def replacer(match):
        s = match.group(0)
        if s.startswith("/"):
            return "".join("\n" if c == "\n" else " " for c in s)
        return s

    pattern = re.compile(r'//.*?$|/\*.*?\*/', re.DOTALL | re.MULTILINE)
    return re.sub(pattern, replacer, texto)


def auditar_archivo(archivo: Path) -> List[AntipatronDetectado]:
    """Analiza un archivo C y detecta antipatrones didácticos."""
    archivo = Path(archivo)
    if not archivo.is_file():
        return []

    try:
        contenido = archivo.read_text(encoding="utf-8")
    except Exception:
        return []

    lineas = contenido.splitlines()
    codigo_sin_comentarios = _eliminar_comentarios(contenido)
    lineas_limpias = codigo_sin_comentarios.splitlines()

    antipatrones: List[AntipatronDetectado] = []

    # Regexes
    re_cast_malloc = re.compile(r"\(\s*[a-zA-Z0-9_]+\s*\*\s*\)\s*malloc\s*\(")
    re_feof_loop = re.compile(r"while\s*\(\s*!feof\s*\([^)]+\)\s*\)")
    re_ret_stack = re.compile(r"return\s+&([a-zA-Z0-9_]+)\s*;")
    re_free_null = re.compile(r"if\s*\(\s*([a-zA-Z0-9_]+)\s*!=\s*NULL\s*\)\s*free\s*\(\s*\1\s*\);?")
    re_bool_cmp = re.compile(r"if\s*\([^)]*==\s*(?:true|1)\s*\)")
    re_semi_if = re.compile(r"^\s*(?:if|while|for)\s*\([^)]+\)\s*;(?!\s*$)")

    for idx, l in enumerate(lineas_limpias, 1):
        # AP001
        if m := re_cast_malloc.search(l):
            info = CATALOGO_ANTIPATRONES["AP001"]
            antipatrones.append(AntipatronDetectado(
                codigo="AP001",
                nombre=info["nombre"],
                archivo=archivo,
                linea=idx,
                columna=m.start() + 1,
                mensaje=info["mensaje"],
                explicacion=info["explicacion"],
                sugerencia=info["sugerencia"],
                codigo_linea=lineas[idx - 1],
            ))

        # AP002
        if m := re_feof_loop.search(l):
            info = CATALOGO_ANTIPATRONES["AP002"]
            antipatrones.append(AntipatronDetectado(
                codigo="AP002",
                nombre=info["nombre"],
                archivo=archivo,
                linea=idx,
                columna=m.start() + 1,
                mensaje=info["mensaje"],
                explicacion=info["explicacion"],
                sugerencia=info["sugerencia"],
                codigo_linea=lineas[idx - 1],
            ))

        # AP003
        if m := re_ret_stack.search(l):
            info = CATALOGO_ANTIPATRONES["AP003"]
            antipatrones.append(AntipatronDetectado(
                codigo="AP003",
                nombre=info["nombre"],
                archivo=archivo,
                linea=idx,
                columna=m.start() + 1,
                mensaje=f"Retorno de dirección de variable local '&{m.group(1)}'.",
                explicacion=info["explicacion"],
                sugerencia=info["sugerencia"],
                codigo_linea=lineas[idx - 1],
            ))

        # AP004
        if m := re_free_null.search(l):
            info = CATALOGO_ANTIPATRONES["AP004"]
            antipatrones.append(AntipatronDetectado(
                codigo="AP004",
                nombre=info["nombre"],
                archivo=archivo,
                linea=idx,
                columna=m.start() + 1,
                mensaje=info["mensaje"],
                explicacion=info["explicacion"],
                sugerencia=info["sugerencia"],
                codigo_linea=lineas[idx - 1],
            ))

        # AP005
        if m := re_bool_cmp.search(l):
            info = CATALOGO_ANTIPATRONES["AP005"]
            antipatrones.append(AntipatronDetectado(
                codigo="AP005",
                nombre=info["nombre"],
                archivo=archivo,
                linea=idx,
                columna=m.start() + 1,
                mensaje=info["mensaje"],
                explicacion=info["explicacion"],
                sugerencia=info["sugerencia"],
                codigo_linea=lineas[idx - 1],
            ))

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
