"""Caracterización de auditar_archivo sobre los ejemplos del catálogo (N-SPUNK-01).

golden.json se generó antes de partir `auditar_archivo` en un despachador por tipo de nodo: si este
test falla, el refactor cambió algún hallazgo. Ver tests/caracterizacion/generar_golden.py.
"""

import importlib.util
import json
from pathlib import Path

import pytest

DIRECTORIO = Path(__file__).parent / "caracterizacion"
_spec = importlib.util.spec_from_file_location("generar_golden", DIRECTORIO / "generar_golden.py")
_generador = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_generador)
ejemplos, hallazgos = _generador.ejemplos, _generador.hallazgos

GOLDEN = json.loads((DIRECTORIO / "golden.json").read_text(encoding="utf-8"))


def test_el_golden_cubre_todo_el_catalogo():
    assert set(GOLDEN) == set(ejemplos())


@pytest.mark.parametrize("nombre", sorted(GOLDEN))
def test_mismos_hallazgos_que_antes_del_refactor(nombre):
    assert hallazgos(ejemplos()[nombre]) == GOLDEN[nombre]
