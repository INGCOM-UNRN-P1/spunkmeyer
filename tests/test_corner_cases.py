from pathlib import Path
import json
import typer
from typer.testing import CliRunner
from spunkmeyer.cli import app
from spunkmeyer.core.detector import auditar_archivo, auditar_archivos
from spunkmeyer.core.exporters import generar_sarif_210_spunkmeyer

runner = CliRunner()


def test_if_0_dead_code_ignored(tmp_path: Path):
    """SPUNK-D0302 / SPUNK-D0702: Código bajo #if 0 no debe ser analizado ni disparar falsos positivos."""
    src = tmp_path / "dead_if0.c"
    src.write_text("""
    #include <stdio.h>
    #include <stdlib.h>
    int main(void) {
    #if 0
        int *p = (int *)malloc(sizeof(int));
        FILE *f = fopen("data.bin", "rb");
        while (!feof(f)) {
            fgetc(f);
        }
    #endif
        return 0;
    }
    """)
    res = auditar_archivo(src)
    assert len(res) == 0, f"Se esperaban 0 antipatrones en código bajo #if 0, pero se encontraron: {[a.codigo for a in res]}"


def test_if_0_else_active_branch_analyzed(tmp_path: Path):
    """SPUNK-D0302: Rama #else activa tras #if 0 sí debe ser analizada."""
    src = tmp_path / "if0_else.c"
    src.write_text("""
    #include <stdio.h>
    #include <stdlib.h>
    int main(void) {
    #if 0
        int x = 1;
    #else
        int *p = (int *)malloc(sizeof(int));
    #endif
        return 0;
    }
    """)
    res = auditar_archivo(src)
    codigos = [str(a.codigo) for a in res]
    assert "0x300Ah" in codigos, "El casteo redundante en la rama activa #else debió ser detectado"


def test_macro_in_block_and_line_comments_ignored(tmp_path: Path):
    """SPUNK-D0303 / SPUNK-D0702: Macros #define dentro de comentarios no deben disparar falsos positivos."""
    src = tmp_path / "comments_macro.c"
    src.write_text("""
    #include <stdio.h>
    /*
    #define MAX(a, b) ((a) + (b) + (a))
    #define BEGIN {
    #define END }
    */
    // #define DUP(x) ((x) * (x))
    int main(void) {
        return 0;
    }
    """)
    res = auditar_archivo(src)
    assert len(res) == 0, f"Macros comentadas no deben reportarse: {[a.codigo for a in res]}"


def test_sarif_severity_levels(tmp_path: Path):
    """SPUNK-D0602: SARIF 2.1.0 debe asignar 'error' a fallos críticos y 'warning' a estilo."""
    src = tmp_path / "critical_vs_warning.c"
    src.write_text("""
    #include <stdio.h>
    #include <stdlib.h>
    int main(void) {
        // Crítico (0x4006h while(!feof)): error
        FILE *f = fopen("test.txt", "r");
        while (!feof(f)) {
            fgetc(f);
        }
        // Estilo didáctico (0x300Ah casteo malloc): warning
        int *ptr = (int *)malloc(sizeof(int));
        return 0;
    }
    """)
    rep = auditar_archivos([src])
    sarif = generar_sarif_210_spunkmeyer(rep)
    results = sarif["runs"][0]["results"]
    levels_by_rule = {r["ruleId"]: r["level"] for r in results}

    assert "0x4006h" in levels_by_rule
    assert levels_by_rule["0x4006h"] == "error"
    assert "0x300Ah" in levels_by_rule
    assert levels_by_rule["0x300Ah"] == "warning"


def test_rules_filter_with_legacy_and_alias_codes(tmp_path: Path):
    """SPUNK-D0501: --rules debe soportar códigos nuevos, antiguos, alias didácticos y advertir si no existen."""
    src = tmp_path / "test_rules.c"
    src.write_text("""
    #include <stdio.h>
    #include <stdlib.h>
    int main(void) {
        FILE *f = fopen("test.txt", "r");
        while (!feof(f)) { fgetc(f); }
        int *ptr = (int *)malloc(sizeof(int));
        return 0;
    }
    """)
    # YAML usando el código anterior de while(!feof): 0x4002h y una regla inexistente
    rules_yaml = tmp_path / "rules.yaml"
    rules_yaml.write_text("""
    reglas:
      - 0x4002h
      - REGLA_INEXISTENTE_XYZ
    """)

    res = runner.invoke(app, ["detect", str(src), "--rules", str(rules_yaml), "--json"])
    assert res.exit_code == 1
    data = json.loads(res.stdout)
    antipatrones = data["antipatrones"]
    # Debe haber quedado solo el while(!feof) (cuyo código actual es 0x4006h)
    assert len(antipatrones) == 1
    assert antipatrones[0]["codigo"] == "0x4006h"
