"""Tests unitarios para el detector de antipatrones en SPUNKMEYER."""

from pathlib import Path
import pytest
from spunkmeyer.core.detector import auditar_archivo, auditar_archivos


def test_detectar_malloc_cast_y_while_feof(tmp_path):
    fuente = tmp_path / "antipatron.c"
    fuente.write_text("""
    #include <stdio.h>
    #include <stdlib.h>

    int main(void) {
        int* p = (int*)malloc(sizeof(int) * 10);
        FILE* f = fopen("datos.txt", "r");
        while (!feof(f)) {
            // leer
        }
        return 0;
    }
    """)

    aps = auditar_archivo(fuente)
    codigos = [a.codigo for a in aps]
    assert "AP001" in codigos
    assert "AP002" in codigos


def test_detectar_return_stack_address(tmp_path):
    fuente = tmp_path / "dangling.c"
    fuente.write_text("""
    int* obtener_puntero(void) {
        int local = 42;
        return &local;
    }
    """)

    aps = auditar_archivo(fuente)
    assert any(a.codigo == "AP003" for a in aps)


def test_codigo_limpio_sin_antipatrones(tmp_path):
    fuente = tmp_path / "limpio.c"
    fuente.write_text("""
    #include <stdio.h>
    #include <stdlib.h>

    int main(void) {
        int* p = malloc(sizeof(*p) * 10);
        if (p == NULL) return 1;
        free(p);
        return 0;
    }
    """)

    rep = auditar_archivos([fuente])
    assert rep.ok is True
    assert len(rep.antipatrones) == 0
