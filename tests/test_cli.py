"""Tests de integración de la CLI de SPUNKMEYER."""

import json
from pathlib import Path
from typer.testing import CliRunner
from spunkmeyer.cli import app

runner = CliRunner()


def test_cli_version():
    res = runner.invoke(app, ["--version"])
    assert res.exit_code == 0
    assert "SPUNKMEYER" in res.stdout


def test_cli_catalog():
    res = runner.invoke(app, ["catalog"])
    assert res.exit_code == 0
    assert "AP001" in res.stdout


def test_cli_detect_json(tmp_path):
    fuente = tmp_path / "code.c"
    fuente.write_text("int* f() { int x = 1; return &x; }\n")

    res = runner.invoke(app, ["detect", str(fuente), "--json"])
    assert res.exit_code == 1
    data = json.loads(res.stdout)
    assert any(a["codigo"] in ("0x3002h", "AP003") or a.get("alias") == "AP003" for a in data["antipatrones"])


def test_cli_report_exit_codes(tmp_path):
    # Sin antipatrones -> exit code 0
    fuente_ok = tmp_path / "ok.c"
    fuente_ok.write_text("int main(void) { return 0; }\n")
    res_ok = runner.invoke(app, ["report", str(fuente_ok)])
    assert res_ok.exit_code == 0
    assert "spunkmeyer" in res_ok.stdout.lower()

    # Con antipatrones -> exit code 1
    fuente_err = tmp_path / "err.c"
    fuente_err.write_text("int* f() { int x = 1; return &x; }\n")
    res_err = runner.invoke(app, ["report", str(fuente_err)])
    assert res_err.exit_code == 1
    assert "antipatrones detectados" in res_err.stdout.lower()

