import pytest
from pathlib import Path
from spunkmeyer.core.detector import auditar_archivo, CATALOGO_ANTIPATRONES


def test_ignore_inline_directive(tmp_path):
    c_code = """
#include <stdio.h>
#include <stdlib.h>

void f(void) {
    int *p = malloc(10); // spunkmeyer:ignore 0x3001h
    *p = 5;
}
"""
    arch = tmp_path / "test_ign.c"
    arch.write_text(c_code, encoding="utf-8")
    res = auditar_archivo(arch)
    codigos = [str(a.codigo) for a in res]
    assert "0x3001h" not in codigos


def test_ap073_cast_const_to_pointer(tmp_path):
    c_code = """
void f(void) {
    int *ptr = (int *)0x1000;
}
"""
    arch = tmp_path / "test_ap073.c"
    arch.write_text(c_code, encoding="utf-8")
    res = auditar_archivo(arch)
    codigos = [str(a.codigo) for a in res]
    assert "0x300Ah" in codigos or "0x302Ah" in [a.codigo for a in res]


def test_ap070_direct_realloc_deref(tmp_path):
    c_code = """
#include <stdlib.h>
void f(void *p) {
    *((int *)realloc(p, 20)) = 10;
}
"""
    arch = tmp_path / "test_ap070.c"
    arch.write_text(c_code, encoding="utf-8")
    res = auditar_archivo(arch)
    codigos = [str(a.codigo) for a in res]
    assert "0x3001h" in codigos or "0x3029h" in [a.codigo for a in res]


def test_catalogo_myst_generado():
    cat_dir = Path("/home/mrtin/dev/tools/spunkmeyer/catalogo")
    assert cat_dir.is_dir()
    docs = list(cat_dir.glob("*.md"))
    assert len(docs) >= 60
    # Chequear un archivo específico
    ej = docs[0].read_text(encoding="utf-8")
    assert "## Diagnóstico" in ej
    assert "## Justificación Pedagógica" in ej
    assert "## Sugerencia de Corrección" in ej
