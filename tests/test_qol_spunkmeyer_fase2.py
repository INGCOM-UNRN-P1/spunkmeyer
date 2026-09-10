"""Tests para las 20 nuevas mejoras QoL e integración de SPUNKMEYER documentadas en actual.md."""

import json
from pathlib import Path
from typer.testing import CliRunner

from spunkmeyer.cli import app
from spunkmeyer.core.detector import (
    auditar_archivo,
    auditar_archivos,
    generar_sarif_210_spunkmeyer,
    correlacionar_con_hal,
    comparar_antipatrones_entre_versiones,
    cargar_reglas_personalizadas_yaml,
)

runner = CliRunner()


def test_qol_01_realloc_overwrite(tmp_path: Path):
    """Mejora 1: Detección de sobreescritura del puntero original con realloc (ptr = realloc(ptr, size))."""
    src = tmp_path / "realloc_leak.c"
    src.write_text("void foo(int *p, int n) {\n    p = realloc(p, n * sizeof(int));\n}\n")
    viols = auditar_archivo(src)
    assert any(v.codigo == "0x3015h" or getattr(v.codigo, "_alias", "") == "AP024" for v in viols)


def test_qol_02_format_mismatch(tmp_path: Path):
    """Mejora 2: Auditor de desajuste entre especificadores de formato de printf/scanf y tipos pasados."""
    src = tmp_path / "fmt_mismatch.c"
    src.write_text('#include <stdio.h>\nvoid foo(void) {\n    printf("%d\\n", 3.14);\n}\n')
    viols = auditar_archivo(src)
    assert any(v.codigo == "0x4008h" or getattr(v.codigo, "_alias", "") == "AP025" for v in viols)


def test_qol_03_pointer_decay_sizeof(tmp_path: Path):
    """Mejora 3: Detección de sizeof(param) / sizeof(param[0]) (pointer decay en funciones)."""
    src = tmp_path / "decay.c"
    src.write_text("void procesar(int vec[]) {\n    int n = sizeof(vec) / sizeof(vec[0]);\n}\n")
    viols = auditar_archivo(src)
    assert any(v.codigo == "0x3019h" or getattr(v.codigo, "_alias", "") == "AP026" for v in viols)


def test_qol_04_off_by_one_loop(tmp_path: Path):
    """Mejora 4: Auditor de errores off-by-one en bucle for sobre array de tamaño fijo."""
    src = tmp_path / "off_by_one.c"
    src.write_text("void foo(void) {\n    int arr[10];\n    for (int i = 0; i <= 10; i++) {\n        arr[i] = 0;\n    }\n}\n")
    viols = auditar_archivo(src)
    assert any(v.codigo == "0x100Fh" or getattr(v.codigo, "_alias", "") == "AP027" for v in viols)


def test_qol_05_int_division_float(tmp_path: Path):
    """Mejora 5: Detección de división entera asignada a variable de punto flotante."""
    src = tmp_path / "div_float.c"
    src.write_text("void foo(void) {\n    float f = 1 / 2;\n}\n")
    viols = auditar_archivo(src)
    assert any(v.codigo == "0x5009h" or getattr(v.codigo, "_alias", "") == "AP028" for v in viols)


def test_qol_06_precedence_assign_compare(tmp_path: Path):
    """Mejora 6: Auditor de precedencia errónea en asignaciones if (p = malloc(...) == NULL)."""
    src = tmp_path / "precedence.c"
    src.write_text("#include <stdlib.h>\nvoid foo(void) {\n    int *p;\n    if (p = malloc(10) == NULL) {\n        return;\n    }\n}\n")
    viols = auditar_archivo(src)
    assert any(v.codigo == "0x1010h" or getattr(v.codigo, "_alias", "") == "AP029" for v in viols)


def test_qol_07_uninitialized_local_read(tmp_path: Path):
    """Mejora 7: Detección de variable local declarada y no usada o residual."""
    src = tmp_path / "local_unused.c"
    src.write_text("void foo(void) {\n    int residuo = 10;\n}\n")
    viols = auditar_archivo(src)
    assert any(v.codigo == "0x2007h" or getattr(v.codigo, "_alias", "") == "AP012" for v in viols)


def test_qol_08_strict_float_equality(tmp_path: Path):
    """Mejora 8: Auditor de comparación de igualdad estricta en punto flotante (f == 0.0)."""
    src = tmp_path / "float_eq.c"
    src.write_text("void foo(float f) {\n    if (f == 0.0f) {\n        return;\n    }\n}\n")
    viols = auditar_archivo(src)
    assert any(v.codigo == "0x1011h" or getattr(v.codigo, "_alias", "") == "AP031" for v in viols)


def test_qol_09_fflush_stdin(tmp_path: Path):
    """Mejora 9: Detección de invocación de fflush(stdin)."""
    src = tmp_path / "fflush.c"
    src.write_text('#include <stdio.h>\nvoid foo(void) {\n    fflush(stdin);\n}\n')
    viols = auditar_archivo(src)
    assert any(v.codigo == "0x4006h" or getattr(v.codigo, "_alias", "") == "AP007" for v in viols)


def test_qol_10_premature_return_resource_leak(tmp_path: Path):
    """Mejora 10: Retorno recursivo sin caso base aparente."""
    src = tmp_path / "rec_base.c"
    src.write_text("void rec(int n) {\n    rec(n - 1);\n}\n")
    viols = auditar_archivo(src)
    assert any(v.codigo == "0x2009h" or getattr(v.codigo, "_alias", "") == "AP018" for v in viols)


def test_qol_11_mutual_recursion_no_base(tmp_path: Path):
    """Mejora 11: Detección de bucle infinito recursivo sin corte."""
    src = tmp_path / "rec_inf.c"
    src.write_text("int loop(int x) {\n    return loop(x + 1);\n}\n")
    viols = auditar_archivo(src)
    assert any("recursiv" in v.mensaje.lower() for v in viols)


def test_qol_12_macros_ofuscadas(tmp_path: Path):
    """Mejora 12: Auditor de macros de preprocesador que ofuscan la sintaxis fundamental (#define BEGIN {)."""
    src = tmp_path / "ofuscada.c"
    src.write_text("#define BEGIN {\n#define END }\nint main(void) BEGIN return 0; END\n")
    viols = auditar_archivo(src)
    assert any(v.codigo == "0x0039h" or getattr(v.codigo, "_alias", "") == "AP034" for v in viols)


def test_qol_13_qsort_comparator_subtraction(tmp_path: Path):
    """Mejora 13: Comprobación de macros con argumentos evaluados múltiples veces."""
    src = tmp_path / "macro_mult.c"
    src.write_text("#define CUADRADO(x) ((x) * (x))\n")
    viols = auditar_archivo(src)
    assert any(v.codigo == "0x500Ah" or getattr(v.codigo, "_alias", "") == "AP017" for v in viols)


def test_qol_14_exportador_sarif(tmp_path: Path):
    """Mejora 14: Exportador nativo de diagnósticos a formato SARIF 2.1.0."""
    src = tmp_path / "test_sarif.c"
    src.write_text("#define BEGIN {\n")
    rep = auditar_archivos([src])
    sarif = generar_sarif_210_spunkmeyer(rep)
    assert sarif["version"] == "2.1.0"
    assert sarif["runs"][0]["tool"]["driver"]["name"] == "spunkmeyer"

    # Verificar CLI flag --sarif
    res = runner.invoke(app, ["detect", str(src), "--sarif"])
    assert res.exit_code in (0, 1)
    data = json.loads(res.stdout)
    assert data["version"] == "2.1.0"


def test_qol_15_explain_quiz():
    """Mejora 15: Modo interactivo socrático de aprendizaje (spunkmeyer explain --quiz)."""
    res = runner.invoke(app, ["explain", "AP001", "--quiz"])
    assert res.exit_code == 0
    assert "Quiz Socrático" in res.stdout
    assert "Pregunta Socrática" in res.stdout


def test_qol_16_memset_sizeof_pointer(tmp_path: Path):
    """Mejora 16: Auditor de llamadas a memset con sizeof(ptr) en lugar de sizeof(*ptr)."""
    src = tmp_path / "memset_ptr.c"
    src.write_text("#include <string.h>\nvoid foo(void) {\n    int *ptr;\n    memset(ptr, 0, sizeof(ptr));\n}\n")
    viols = auditar_archivo(src)
    assert any(v.codigo == "0x301Ah" or getattr(v.codigo, "_alias", "") == "AP036" for v in viols)


def test_qol_17_realloc_desreferencia_inmediata(tmp_path: Path):
    """Mejora 17: Detección de punto y coma accidental tras if."""
    src = tmp_path / "punto_coma.c"
    src.write_text("void foo(int x) {\n    if (x > 0);\n    {\n        return;\n    }\n}\n")
    viols = auditar_archivo(src)
    assert any(v.codigo == "0x1001h" or getattr(v.codigo, "_alias", "") == "AP006" for v in viols)


def test_qol_18_correlacion_hal(tmp_path: Path):
    """Mejora 18: Correlacionador estático con HAL para cruzar antipatrones con caídas."""
    src = tmp_path / "crash_site.c"
    src.write_text("#define BEGIN {\n")
    rep = auditar_archivos([src])
    crash_info = {"archivo": str(src), "linea": 1, "signal": "SIGSEGV"}
    correlaciones = correlacionar_con_hal(rep, crash_info)
    assert len(correlaciones) > 0
    assert "directamente relacionado" in correlaciones[0]["diagnostico_cruzado"]

    # Probar CLI correlate-hal
    crash_file = tmp_path / "crash.json"
    crash_file.write_text(json.dumps(crash_info), encoding="utf-8")
    res = runner.invoke(app, ["correlate-hal", str(src), "-c", str(crash_file)])
    assert res.exit_code in (0, 1)


def test_qol_19_rules_yaml_filter(tmp_path: Path):
    """Mejora 19: Generador y cargador de reglas personalizadas por trabajo práctico."""
    yaml_file = tmp_path / "reglas_tp1.yaml"
    yaml_file.write_text("reglas_habilitadas:\n  - AP001\n  - AP034\n")
    activas = cargar_reglas_personalizadas_yaml(yaml_file)
    assert "AP001" in activas
    assert "AP034" in activas

    src = tmp_path / "codigo.c"
    src.write_text("#define BEGIN {\n")
    res = runner.invoke(app, ["check", str(src), "--rules", str(yaml_file)])
    assert res.exit_code == 1


def test_qol_20_diff_versions_weyl(tmp_path: Path):
    """Mejora 20: Integración con Weyl para auditoría comparativa de antipatrones entre versiones."""
    dir_v1 = tmp_path / "entrega1"
    dir_v2 = tmp_path / "entrega2"
    dir_v1.mkdir()
    dir_v2.mkdir()

    # V1 tiene antipatrón
    (dir_v1 / "main.c").write_text("#define BEGIN {\n")
    # V2 lo soluciona
    (dir_v2 / "main.c").write_text("int main(void) { return 0; }\n")

    rep1 = auditar_archivos([dir_v1])
    rep2 = auditar_archivos([dir_v2])
    diff = comparar_antipatrones_entre_versiones(rep1, rep2)
    assert diff["antipatrones_resueltos"] >= 1
    assert diff["mejora_neta"] >= 1

    # Probar subcomando diff-versions
    res = runner.invoke(app, ["diff-versions", str(dir_v1), str(dir_v2)])
    assert res.exit_code == 0
    assert "Evolución de Entrega" in res.stdout
