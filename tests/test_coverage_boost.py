"""Tests adicionales para maximizar la cobertura en SPUNKMEYER."""

import json
from pathlib import Path
from typer.testing import CliRunner
import spunkmeyer.cli
from spunkmeyer.cli import app
from spunkmeyer.core.detector import auditar_archivos, auditar_archivo
from spunkmeyer.ripley_plugin import SpunkmeyerPlugin

runner = CliRunner()


def test_plugin_execution(tmp_path):
    p = SpunkmeyerPlugin()
    assert p.is_available() is True

    f = tmp_path / "code.c"
    f.write_text("int main() { if (1 == true) {} return 0; }\n")
    res = p.execute(tmp_path, {})
    assert res["ok"] is False
    assert len(res["observaciones"]) >= 1


def test_cli_detect_rich_and_clean(tmp_path):
    # Bad rich output
    f_bad = tmp_path / "bad.c"
    f_bad.write_text("int main() { int *p = NULL; if (p != NULL) free(p); return 0; }\n")
    res_b = runner.invoke(app, ["detect", str(f_bad)])
    assert res_b.exit_code == 1
    assert "Antipatrones de Programación" in res_b.stdout

    # Clean rich output
    f_ok = tmp_path / "ok.c"
    f_ok.write_text("int main() { return 0; }\n")
    res_ok = runner.invoke(app, ["detect", str(f_ok)])
    assert res_ok.exit_code == 0
    assert "SPUNKMEYER OK" in res_ok.stdout


def test_detector_rules_all(tmp_path):
    f = tmp_path / "rules.c"
    f.write_text("""
    #include <stdlib.h>
    int main(void) {
        int *p = (int*)malloc(10);
        if (p != NULL) free(p);
        if (1 == 1) {}
        return 0;
    }
    """)
    rep = auditar_archivos([f])
    codigos = [a.codigo for a in rep.antipatrones]
    assert "AP001" in codigos
    assert "AP004" in codigos


def test_cli_main_block(monkeypatch):
    monkeypatch.setattr("sys.argv", ["spunkmeyer", "--version"])
    try:
        spunkmeyer.cli.main()
    except SystemExit as e:
        assert e.code == 0
