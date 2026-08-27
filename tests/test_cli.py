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
    assert data["ok"] is False
    assert any(a["codigo"] == "AP003" for a in data["antipatrones"])
