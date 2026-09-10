"""Tests exhaustivos para las 20 mejoras QoL de SPUNKMEYER documentadas en actual.md."""

from pathlib import Path
from typer.testing import CliRunner

from spunkmeyer.cli import app
from spunkmeyer.core.detector import auditar_archivo, auditar_archivos
from spunkmeyer.ripley_plugin import SpunkmeyerPlugin

runner = CliRunner()


def test_qol_01_contador_float_for(tmp_path: Path):
    """Mejora 1: Detección de uso de variables float como contadores de bucle."""
    src = tmp_path / "float_for.c"
    src.write_text("void foo(void) {\n    for (float x = 0.0f; x < 10.0f; x += 0.1f) {}\n}\n")
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP009" or "0x100Dh" in str(a.codigo) for a in aps)


def test_qol_02_malloc_sin_null_check(tmp_path: Path):
    """Mejora 2: Auditor de descarte o uso directo de malloc/realloc sin validar NULL."""
    src = tmp_path / "no_check_malloc.c"
    src.write_text("void foo(void) {\n    int *p = (int*)malloc(10 * sizeof(int));\n    p[0] = 42;\n}\n")
    aps = auditar_archivo(src)
    assert len(aps) >= 1


def test_qol_03_while_feof(tmp_path: Path):
    """Mejora 3: Detección de while (!feof(f)) en lectura de archivos."""
    src = tmp_path / "feof.c"
    src.write_text("void leer(void *f) {\n    while (!feof(f)) {}\n}\n")
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP002" or "0x4002h" in str(a.codigo) for a in aps)


def test_qol_04_dangling_pointer_after_free(tmp_path: Path):
    """Mejora 4: Auditor de punteros colgantes (Use-After-Free) tras invocar free()."""
    src = tmp_path / "use_after_free.c"
    src.write_text("void foo(int *ptr) {\n    free(ptr);\n    int x = *ptr;\n    (void)x;\n}\n")
    aps = auditar_archivo(src)
    assert any("0x3002" in str(a.codigo) or a.codigo == "AP011" for a in aps)


def test_qol_05_check_innecesario_free(tmp_path: Path):
    """Mejora 5: Detección de liberaciones redundantes de punteros if (p != NULL) free(p)."""
    src = tmp_path / "free_null.c"
    src.write_text("void foo(int *ptr) {\n    if (ptr != NULL) {\n        free(ptr);\n    }\n}\n")
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP004" or "0x3008h" in str(a.codigo) for a in aps)


def test_qol_06_return_local_stack(tmp_path: Path):
    """Mejora 6: Auditor de retorno de punteros a variables locales de la pila."""
    src = tmp_path / "ret_local.c"
    src.write_text("int* foo(void) {\n    int val = 10;\n    return &val;\n}\n")
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP003" or "0x3002h" in str(a.codigo) for a in aps)


def test_qol_07_variable_local_no_usada(tmp_path: Path):
    """Mejora 7: Detección de variables no utilizadas que consumen memoria en la pila."""
    src = tmp_path / "unused_var.c"
    src.write_text("int foo(void) {\n    int acumulador_olvidado = 100;\n    return 0;\n}\n")
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP012" or "0x2007h" in str(a.codigo) for a in aps)


def test_qol_08_strcpy_sprintf_inseguros(tmp_path: Path):
    """Mejora 8: Auditor de strcpy y sprintf inseguros sin límite de buffer."""
    src = tmp_path / "unsafe_str.c"
    src.write_text("void foo(char *dest, const char *src) {\n    strcpy(dest, src);\n    sprintf(dest, \"%s\", src);\n}\n")
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP013" or "0x5004h" in str(a.codigo) for a in aps)


def test_qol_09_magic_number_en_condicion(tmp_path: Path):
    """Mejora 9: Detección de uso de constantes mágicas numéricas en condiciones lógicas."""
    src = tmp_path / "magic_cond.c"
    src.write_text("void foo(int status) {\n    if (status == 404) {}\n}\n")
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP014" or "0x300Dh" in str(a.codigo) for a in aps)


def test_qol_10_mas_de_cinco_parametros(tmp_path: Path):
    """Mejora 10: Auditor de funciones con excesiva cantidad de parámetros (> 5 argumentos)."""
    src = tmp_path / "muchos_params.c"
    src.write_text("void foo(int a, int b, int c, int d, int e, int f) {}\n")
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP015" or "0x200Bh" in str(a.codigo) for a in aps)


def test_qol_11_asignacion_accidental_en_if(tmp_path: Path):
    """Mejora 11: Detección de asignaciones accidentales dentro de condiciones if (x = 5)."""
    src = tmp_path / "asgn_if.c"
    src.write_text("void foo(int x) {\n    if (x = 5) {}\n}\n")
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP016" or "0x100Ah" in str(a.codigo) for a in aps)


def test_qol_12_macro_argumentos_multiples_evaluaciones(tmp_path: Path):
    """Mejora 12: Auditor de macros con argumentos evaluados múltiples veces."""
    src = tmp_path / "macro_dup.c"
    src.write_text("#define MAX(a, b) ((a) > (b) ? (a) : (b))\nint main(void) { return 0; }\n")
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP017" or "0x500Ah" in str(a.codigo) for a in aps)


def test_qol_13_recursion_sin_caso_base(tmp_path: Path):
    """Mejora 13: Detección de llamadas recursivas sin caso base explícito."""
    src = tmp_path / "recursion_infinita.c"
    src.write_text("void cuenta_regresiva(int n) {\n    cuenta_regresiva(n - 1);\n}\n")
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP018" or "0x2009h" in str(a.codigo) for a in aps)


def test_qol_14_gets_prohibido(tmp_path: Path):
    """Mejora 14: Auditor de uso de gets() (función prohibida y removida en C11)."""
    src = tmp_path / "gets_bad.c"
    src.write_text("void foo(char *buf) {\n    gets(buf);\n}\n")
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP019" or "0x5008h" in str(a.codigo) for a in aps)


def test_qol_15_comparacion_cadenas_con_igual(tmp_path: Path):
    """Mejora 15: Detección de comparaciones directas de cadenas con == o !=."""
    src = tmp_path / "cmp_str.c"
    src.write_text("void foo(char *s) {\n    if (s == \"hola\") {}\n}\n")
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP020" or "0x5004h" in str(a.codigo) for a in aps)


def test_qol_16_switch_case_sin_break(tmp_path: Path):
    """Mejora 16: Auditor de falta de break en casos de switch (fallthrough)."""
    src = tmp_path / "switch_fall.c"
    src.write_text("void foo(int x) {\n    switch (x) {\n    case 1:\n        x = 10;\n    case 2:\n        x = 20;\n        break;\n    }\n}\n")
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP021" or "0x100Ch" in str(a.codigo) for a in aps)


def test_qol_17_declaracion_tras_sentencia_ejecutable(tmp_path: Path):
    """Mejora 17: Detección de declaraciones de variables en medio del bloque en C90/C99."""
    src = tmp_path / "decl_mezclada.c"
    src.write_text("void foo(void) {\n    int a = 1;\n    a = a + 2;\n    int b = 3;\n    (void)b;\n}\n")
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP022" or "0x0003h" in str(a.codigo) for a in aps)


def test_qol_18_tautologia_booleana(tmp_path: Path):
    """Mejora 18: Auditor de expresiones booleanas tautológicas (x && !x, x || !x)."""
    src = tmp_path / "tauto.c"
    src.write_text("void foo(int x) {\n    if (x && !x) {}\n}\n")
    aps = auditar_archivo(src)
    assert any(a.codigo == "AP023" or "0x100Eh" in str(a.codigo) for a in aps)


def test_qol_19_comando_explain_con_ejemplos(tmp_path: Path):
    """Mejora 19: Generador de informes pedagógicos con ejemplos antes/después (spunkmeyer explain)."""
    res = runner.invoke(app, ["explain", "AP001"])
    assert res.exit_code == 0
    assert "Casteo redundante" in res.output
    assert "Código Incorrecto" in res.output
    assert "Código Correcto" in res.output


def test_qol_20_integracion_ripley_y_doctor(tmp_path: Path):
    """Mejora 20: Integración con Ripley y subcomando doctor."""
    res_doc = runner.invoke(app, ["doctor"])
    assert res_doc.exit_code == 0
    assert "Tree-Sitter C Grammar" in res_doc.output

    # Ripley plugin
    plugin = SpunkmeyerPlugin()
    assert plugin.is_available()
    res_exec = plugin.execute(tmp_path, {})
    assert "ok" in res_exec
    assert "total_antipatrones" in res_exec
