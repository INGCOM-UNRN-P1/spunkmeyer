"""Tests unitarios exhaustivos para las mejoras QoL Fase 4 de SPUNKMEYER (AP049 a AP063)."""

from pathlib import Path
import pytest
from typer.testing import CliRunner

from spunkmeyer.cli import app
from spunkmeyer.core.detector import auditar_archivo, CATALOGO_ANTIPATRONES


runner = CliRunner()


def test_ap049_to_ap063_registered_in_catalog():
    for code, alias in [
        ("0x400Ah", "AP049"),
        ("0x101Ah", "AP050"),
        ("0x2013h", "AP051"),
        ("0x101Bh", "AP052"),
        ("0x3021h", "AP053"),
        ("0x500Bh", "AP054"),
        ("0x3022h", "AP055"),
        ("0x3023h", "AP056"),
        ("0x3024h", "AP057"),
        ("0x3025h", "AP058"),
        ("0x400Bh", "AP059"),
        ("0x3026h", "AP060"),
        ("0x3027h", "AP061"),
        ("0x101Ch", "AP062"),
        ("0x3028h", "AP063"),
    ]:
        assert code in CATALOGO_ANTIPATRONES
        assert alias in CATALOGO_ANTIPATRONES
        assert f"SP{code}" in CATALOGO_ANTIPATRONES


def test_ap049_scanf_unbounded_string(tmp_path: Path):
    src = tmp_path / "scanf_test.c"
    src.write_text("""
    #include <stdio.h>
    void test(void) {
        char buf[20];
        scanf("%s", buf);
    }
    """)
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP049" or a.codigo == "0x400Ah" for a in aps)


def test_ap050_strcmp_direct_boolean(tmp_path: Path):
    src = tmp_path / "strcmp_test.c"
    src.write_text("""
    #include <string.h>
    void test(const char *s) {
        if (strcmp(s, "admin")) {
            // error
        }
    }
    """)
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP050" or a.codigo == "0x101Ah" for a in aps)


def test_ap051_strtol_discarded_return(tmp_path: Path):
    src = tmp_path / "strtol_test.c"
    src.write_text("""
    #include <stdlib.h>
    void test(const char *s) {
        strtol(s, NULL, 10);
    }
    """)
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP051" or a.codigo == "0x2013h" for a in aps)


def test_ap052_signed_unsigned_comparison(tmp_path: Path):
    src = tmp_path / "signed_unsigned.c"
    src.write_text("""
    #include <stddef.h>
    void test(void) {
        int i = -1;
        size_t n = 10;
        if (i < n) {
            // comparison
        }
    }
    """)
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP052" or a.codigo == "0x101Bh" for a in aps)


def test_ap053_free_stack_or_local(tmp_path: Path):
    src = tmp_path / "free_stack.c"
    src.write_text("""
    #include <stdlib.h>
    void test(void) {
        int x = 42;
        free(&x);
    }
    """)
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP053" or a.codigo == "0x3021h" for a in aps)


def test_ap054_redefinition_standard_function(tmp_path: Path):
    src = tmp_path / "redef_abs.c"
    src.write_text("""
    int abs(int x) {
        return x < 0 ? -x : x;
    }
    """)
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP054" or a.codigo == "0x500Bh" for a in aps)


def test_ap055_local_array_to_out_param(tmp_path: Path):
    src = tmp_path / "out_param.c"
    src.write_text("""
    void test(int **res) {
        int arr[5];
        *res = arr;
    }
    """)
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP055" or a.codigo == "0x3022h" for a in aps)


def test_ap056_null_check_after_dereference(tmp_path: Path):
    src = tmp_path / "null_after.c"
    src.write_text("""
    #include <stddef.h>
    void test(int *p) {
        *p = 10;
        if (p != NULL) {
            // late check
        }
    }
    """)
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP056" or a.codigo == "0x3023h" for a in aps)


def test_ap057_loop_malloc_no_cleanup(tmp_path: Path):
    src = tmp_path / "loop_malloc.c"
    src.write_text("""
    #include <stdlib.h>
    void test(int **mat, int n) {
        for (int i = 0; i < n; i++) {
            mat[i] = malloc(10 * sizeof(int));
        }
    }
    """)
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP057" or a.codigo == "0x3024h" for a in aps)


def test_ap058_modify_malloc_base_pointer(tmp_path: Path):
    src = tmp_path / "mod_malloc.c"
    src.write_text("""
    #include <stdlib.h>
    void test(void) {
        char *p = malloc(100);
        p++;
    }
    """)
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP058" or a.codigo == "0x3025h" for a in aps)


def test_ap059_fopen_missing_null_check(tmp_path: Path):
    src = tmp_path / "fopen_check.c"
    src.write_text("""
    #include <stdio.h>
    void test(void) {
        FILE *f = fopen("test.txt", "r");
        fgetc(f);
    }
    """)
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP059" or a.codigo == "0x400Bh" for a in aps)


def test_ap060_conditional_uninit_ptr_deref(tmp_path: Path):
    src = tmp_path / "uninit_ptr.c"
    src.write_text("""
    void test(int cond) {
        int *p;
        if (cond) {
            *p = 10;
        }
    }
    """)
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP060" or a.codigo == "0x3026h" for a in aps)


def test_ap061_flexible_array_struct_malloc_size(tmp_path: Path):
    src = tmp_path / "flex_struct.c"
    src.write_text("""
    #include <stdlib.h>
    struct buf {
        int len;
        char data[];
    };
    void test(void) {
        struct buf *b = malloc(sizeof(struct buf) + 10);
    }
    """)
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP061" or a.codigo == "0x3027h" for a in aps)


def test_ap062_infinite_loop_exit_only(tmp_path: Path):
    src = tmp_path / "infinite_exit.c"
    src.write_text("""
    #include <stdlib.h>
    void test(int cond) {
        while (1) {
            if (cond) {
                exit(0);
            }
        }
    }
    """)
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP062" or a.codigo == "0x101Ch" for a in aps)


def test_ap063_malloc_cast_missing_stdlib(tmp_path: Path):
    src = tmp_path / "cast_nostdlib.c"
    src.write_text("""
    void test(void) {
        int *p = (int *)malloc(sizeof(int));
    }
    """)
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP063" or a.codigo == "0x3028h" for a in aps)
