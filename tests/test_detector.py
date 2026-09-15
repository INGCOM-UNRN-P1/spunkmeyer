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


def test_detectar_fflush_stdin_y_sizeof_ptr(tmp_path):
    fuente = tmp_path / "bad_io.c"
    fuente.write_text("""
    #include <stdio.h>
    #include <stdlib.h>

    int main(void) {
        int *p = malloc(sizeof(p) * 10);
        fflush(stdin);
        return 0;
    }
    """)
    aps = auditar_archivo(fuente)
    codigos = [str(a.codigo) for a in aps]
    assert any("0x400Bh" in c or "0x4006h" in c or "AP007" in c for c in codigos)
    assert any("0x3013h" in c or "0x300Fh" in c or "AP008" in c for c in codigos)


def test_spunk_d0301_corpus_real_sin_segfault():
    """Verifica que auditar archivos complejos reales del corpus no arroje SIGSEGV."""
    corpus_file = Path(__file__).resolve().parents[2] / "librerias" / "bitmaps" / "bitmap" / "libreria.c"
    if corpus_file.is_file():
        aps = auditar_archivo(corpus_file)
        assert isinstance(aps, list)
        assert len(aps) > 0


def test_correlacionar_con_hal_schema(tmp_path):
    from spunkmeyer.core.detector import correlacionar_con_hal
    from spunkmeyer.core.models import ReporteAntipatrones, AntipatronDetectado

    ap = AntipatronDetectado(
        archivo=tmp_path / "crashy.c",
        linea=10,
        columna=5,
        codigo="0x300Ah",
        nombre="Casteo redundante de malloc()",
        mensaje="msg",
        explicacion="exp",
        sugerencia="sug"
    )
    reporte = ReporteAntipatrones(total_archivos=1, antipatrones=[ap])

    # HAL emite archivo_falla y linea_falla (más archivo/linea por compat)
    crash_hal = {
        "schema_version": "1.0.0",
        "es_crash": True,
        "archivo_falla": "crashy.c",
        "linea_falla": 12,
        "tipo_senal": "SIGSEGV"
    }
    corrs = correlacionar_con_hal(reporte, crash_hal)
    assert len(corrs) == 1
    assert "crashy.c" in corrs[0]["antipatron"]["archivo"]

    # Inocente en otro archivo no debe correlacionar
    crash_otro = {
        "schema_version": "1.0.0",
        "archivo_falla": "otro.c",
        "linea_falla": 10
    }
    assert len(correlacionar_con_hal(reporte, crash_otro)) == 0



