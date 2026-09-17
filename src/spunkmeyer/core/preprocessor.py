"""Preprocesamiento léxico y enmascarado de comentarios y código inactivo en C."""

from __future__ import annotations

import re


def enmascarar_comentarios(texto: str) -> str:
    """Reemplaza comentarios de C (// y /* */) por espacios preservando saltos de línea y longitud."""
    res = list(texto)
    i = 0
    n = len(texto)
    in_str = False
    in_chr = False

    while i < n:
        c = texto[i]
        if not in_str and not in_chr:
            if c == '"':
                in_str = True
                i += 1
                continue
            elif c == "'":
                in_chr = True
                i += 1
                continue
            elif c == "/" and i + 1 < n and texto[i + 1] == "/":
                while i < n and texto[i] not in ("\n", "\r"):
                    res[i] = " "
                    i += 1
                continue
            elif c == "/" and i + 1 < n and texto[i + 1] == "*":
                res[i] = " "
                res[i + 1] = " "
                i += 2
                while i < n:
                    if texto[i] == "*" and i + 1 < n and texto[i + 1] == "/":
                        res[i] = " "
                        res[i + 1] = " "
                        i += 2
                        break
                    if texto[i] not in ("\n", "\r"):
                        res[i] = " "
                    i += 1
                continue
        elif in_str:
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            elif c == '"':
                in_str = False
        elif in_chr:
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            elif c == "'":
                in_chr = False
        i += 1

    return "".join(res)


def enmascarar_codigo_inactivo(texto: str) -> str:
    """Enmascara bloques inactivos de preprocesador como #if 0 ... #endif preservando saltos de línea."""
    lineas = texto.splitlines(keepends=True)
    res = []
    # Elemento del stack: (padre_activo, rama_tomada, esta_rama_activa, es_bloque_if0)
    stack = []

    for l in lineas:
        strip_l = l.strip()
        m_if0 = re.match(r"^#\s*if\s+0\b", strip_l)
        m_if = re.match(r"^#\s*(?:if|ifdef|ifndef)\b", strip_l)
        m_elif = re.match(r"^#\s*elif\b", strip_l)
        m_else = re.match(r"^#\s*else\b", strip_l)
        m_endif = re.match(r"^#\s*endif\b", strip_l)

        if m_if0:
            padre_activo = stack[-1][2] if stack else True
            stack.append((padre_activo, False, False, True))
            res.append("".join(" " if c not in ("\n", "\r") else c for c in l))
            continue
        elif m_if:
            padre_activo = stack[-1][2] if stack else True
            stack.append((padre_activo, True, padre_activo, False))
            res.append(l)
            continue
        elif m_elif:
            if stack:
                padre_activo, rama_tomada, _, es_if0 = stack[-1]
                m_elif0 = re.match(r"^#\s*elif\s+0\b", strip_l)
                if m_elif0 or rama_tomada or not padre_activo:
                    stack[-1] = (padre_activo, rama_tomada, False, es_if0)
                    res.append("".join(" " if c not in ("\n", "\r") else c for c in l))
                else:
                    stack[-1] = (padre_activo, True, True, es_if0)
                    if es_if0:
                        res.append("".join(" " if c not in ("\n", "\r") else c for c in l))
                    else:
                        res.append(l)
            else:
                res.append(l)
            continue
        elif m_else:
            if stack:
                padre_activo, rama_tomada, _, es_if0 = stack[-1]
                if not rama_tomada and padre_activo:
                    stack[-1] = (padre_activo, True, True, es_if0)
                else:
                    stack[-1] = (padre_activo, rama_tomada, False, es_if0)
                if es_if0 or not padre_activo:
                    res.append("".join(" " if c not in ("\n", "\r") else c for c in l))
                else:
                    res.append(l)
            else:
                res.append(l)
            continue
        elif m_endif:
            if stack:
                padre_activo, rama_tomada, esta_rama, es_if0 = stack.pop()
                if es_if0 or not esta_rama or not padre_activo:
                    res.append("".join(" " if c not in ("\n", "\r") else c for c in l))
                    continue
            res.append(l)
            continue

        esta_activo = stack[-1][2] if stack else True
        if not esta_activo:
            res.append("".join(" " if c not in ("\n", "\r") else c for c in l))
        else:
            res.append(l)

    return "".join(res)
