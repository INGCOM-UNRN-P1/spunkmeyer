"""Reglas #919, #921, #940; mapa de códigos compartidos con gaff; taxonomía y ejemplos."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from spunkmeyer.cli import app
from spunkmeyer.core.compartidos import CODIGOS_COMPARTIDOS_CON_GAFF, SIN_PAGINA_EN_EL_APUNTE
from spunkmeyer.core.detector import auditar_archivos

runner = CliRunner()

FUENTE = """#include <stdio.h>
#include <stdlib.h>
#include <time.h>

int main(void)
{
    int v[4];
    int nota = 5;
    char c = getchar();
    for (int i = 0; i < 4; i++)
    {
        srand(time(NULL));
        v[i] = rand() % 100;
    }
    while (c != EOF)
    {
        c = getchar();
    }
    if (0 <= nota <= 9)
    {
        printf("%d\\n", v[0]);
    }
    return 0;
}
"""

SIN_ANTIPATRONES = """#include <stdio.h>
int main(void)
{
    int c = getchar();
    int a = 1, b = 2, d = 3;
    srand(7);
    if (a < b && b < d && c != EOF)
    {
        puts("ok");
    }
    return 0;
}
"""


def _codigos(tmp_path: Path, fuente: str) -> dict:
    f = tmp_path / "p.c"
    f.write_text(fuente, encoding="utf-8")
    return {str(a.codigo): a.linea for a in auditar_archivos([f]).antipatrones}


def test_reglas_nuevas(tmp_path):
    codigos = _codigos(tmp_path, FUENTE)
    assert codigos["0x2019h"] == 12 and codigos["0x4010h"] == 15 and codigos["0x101Dh"] == 19


def test_sin_falsos_positivos(tmp_path):
    codigos = _codigos(tmp_path, SIN_ANTIPATRONES)
    assert not {"0x2019h", "0x4010h", "0x101Dh"} & set(codigos)


def test_hallazgos_y_mapa_con_gaff(tmp_path):
    f = tmp_path / "p.c"
    f.write_text(FUENTE, encoding="utf-8")
    res = runner.invoke(app, ["detect", str(f), "--json"])
    datos = json.loads(res.stdout)
    por_id = {h["id"]: h for h in datos["hallazgos"]}
    assert por_id["spunkmeyer:AP078"]["categoria"] == "funciones"
    assert por_id["spunkmeyer:AP078"]["enlace"].endswith("/funciones")
    magico = next(h for h in datos["hallazgos"] if h["codigo"] == "0x300Dh")
    assert magico["tambien_en_gaff"] and magico["enlace"].endswith("/x300dh")

    res = runner.invoke(app, ["detect", str(f), "--json", "--sin-compartidos"])
    assert not any(h["tambien_en_gaff"] for h in json.loads(res.stdout)["hallazgos"])


def test_ejemplos_antes_y_despues(tmp_path):
    f = tmp_path / "p.c"
    f.write_text(FUENTE, encoding="utf-8")
    res = runner.invoke(app, ["detect", str(f), "--ejemplos"])
    assert "Antes:" in res.stdout and "Después:" in res.stdout
    md = tmp_path / "r.md"
    runner.invoke(app, ["detect", str(f), "--md", str(md)])
    assert "antes y después" in md.read_text(encoding="utf-8")


def test_el_mapa_coincide_con_las_reglas_de_gaff():
    pytest.importorskip("gaff")
    import re
    import gaff.rules as reglas

    implementadas = set()
    for archivo in Path(reglas.__file__).parent.glob("*.py"):
        implementadas |= set(re.findall(r'esta_activa\("(0x[0-9A-Fa-f]{4}h)"\)', archivo.read_text(encoding="utf-8")))
    from spunkmeyer.core.catalog import CATALOGO_ANTIPATRONES

    canonicos = {info["codigo"] for _, info in CATALOGO_ANTIPATRONES.items()}
    assert CODIGOS_COMPARTIDOS_CON_GAFF == canonicos & implementadas
    assert not SIN_PAGINA_EN_EL_APUNTE & implementadas
