"""Tests unitarios exhaustivos para las mejoras QoL Fase 3 de SPUNKMEYER."""

import json
from pathlib import Path
import pytest
from typer.testing import CliRunner

from spunkmeyer.cli import app
from spunkmeyer.core.detector import auditar_archivo, auditar_archivos, CATALOGO_ANTIPATRONES
from spunkmeyer.core.models import RuleCode

runner = CliRunner()


def test_rulecode_properties_and_equality():
    rc = RuleCode("0x301Ch", "AP038", "SP0x301Ch")
    assert rc == "0x301Ch"
    assert rc == "ap038"
    assert rc == "sp0x301ch"
    assert rc.alias == "AP038"
    assert rc.sp_codigo == "SP0x301Ch"


def test_sp_canonical_codes_in_catalog_and_explain():
    assert "SP0x300Ah" in CATALOGO_ANTIPATRONES
    assert "SP0x1001h" in CATALOGO_ANTIPATRONES
    assert "SP0x301Ch" in CATALOGO_ANTIPATRONES

    res = runner.invoke(app, ["explain", "SP0x301Ch"])
    assert res.exit_code == 0
    assert "free" in res.stdout


def test_ap038_free_void_cast(tmp_path: Path):
    src = tmp_path / "free_cast.c"
    src.write_text("""
    #include <stdlib.h>
    void test(int *p) {
        free((void*)p);
    }
    """)
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP038" or a.codigo == "0x301Ch" or a.codigo == "SP0x301Ch" for a in aps)


def test_ap039_strlen_in_for_condition(tmp_path: Path):
    src = tmp_path / "for_strlen.c"
    src.write_text("""
    #include <string.h>
    void test(const char *s) {
        for (int i = 0; i < strlen(s); i++) {
            // body
        }
    }
    """)
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP039" or a.codigo == "0x1014h" for a in aps)


def test_ap040_for_control_var_modified(tmp_path: Path):
    src = tmp_path / "for_mod.c"
    src.write_text("""
    void test(int n) {
        for (int i = 0; i < n; i++) {
            if (n > 5) {
                i += 2;
            }
        }
    }
    """)
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP040" or a.codigo == "0x1015h" for a in aps)


def test_ap041_pointer_compared_to_null_char(tmp_path: Path):
    src = tmp_path / "ptr_null_char.c"
    src.write_text("""
    void test(char *s) {
        if (s == '\\0') {
            return;
        }
    }
    """)
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP041" or a.codigo == "0x301Dh" for a in aps)


def test_ap042_malloc_strlen_without_null_byte(tmp_path: Path):
    src = tmp_path / "malloc_strlen.c"
    src.write_text("""
    #include <stdlib.h>
    #include <string.h>
    void test(const char *str) {
        char *dup = malloc(strlen(str));
    }
    """)
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP042" or a.codigo == "0x301Eh" for a in aps)


def test_ap006_spurious_semicolon_loops(tmp_path: Path):
    src = tmp_path / "spurious_loops.c"
    src.write_text("""
    void test(int x) {
        while (x > 0);
        for (int i = 0; i < 10; i++);
    }
    """)
    aps = auditar_archivo(src)
    semi_aps = [a for a in aps if a.codigo == "AP006" or a.codigo == "0x1001h"]
    assert len(semi_aps) >= 2


def test_ap043_bitwise_operator_in_condition(tmp_path: Path):
    src = tmp_path / "bitwise_cond.c"
    src.write_text("""
    void test(int a, int b) {
        if (a > 0 & b > 0) {
            return;
        }
        while (a > 0 | b > 0) {
            a--;
        }
    }
    """)
    aps = auditar_archivo(src)
    bw_aps = [a for a in aps if a.codigo == "AP043" or a.codigo == "0x1016h"]
    assert len(bw_aps) >= 2


def test_ap044_identical_if_else_branches(tmp_path: Path):
    src = tmp_path / "identical_branches.c"
    src.write_text("""
    void test(int x) {
        int y = 0;
        if (x > 0) {
            y = 1;
        } else {
            y = 1;
        }
    }
    """)
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP044" or a.codigo == "0x1017h" for a in aps)


def test_ap045_dangling_else(tmp_path: Path):
    src = tmp_path / "dangling_else.c"
    src.write_text("""
    void test(int a, int b) {
        if (a > 0)
            if (b > 0)
                a = 1;
            else
                a = 2;
    }
    """)
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP045" or a.codigo == "0x1018h" for a in aps)


def test_ap046_non_pointer_malloc(tmp_path: Path):
    src = tmp_path / "non_ptr_malloc.c"
    src.write_text("""
    #include <stdlib.h>
    void test(void) {
        int x = malloc(16);
    }
    """)
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP046" or a.codigo == "0x301Fh" for a in aps)


def test_ap047_strict_aliasing_cast(tmp_path: Path):
    src = tmp_path / "strict_aliasing.c"
    src.write_text("""
    void test(void) {
        float f = 3.14f;
        int *pi = (int *)&f;
    }
    """)
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP047" or a.codigo == "0x3020h" for a in aps)


def test_ap048_backward_goto(tmp_path: Path):
    src = tmp_path / "backward_goto.c"
    src.write_text("""
    void test(int x) {
    inicio:
        x--;
        if (x > 0) goto inicio;
    }
    """)
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP048" or a.codigo == "0x1019h" for a in aps)
