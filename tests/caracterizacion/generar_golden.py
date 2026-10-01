"""Genera golden.json: la salida de auditar_archivo sobre los ejemplos del catálogo (N-SPUNK-01).

Se generó antes de partir `auditar_archivo`/`_traverse` en un despachador por tipo de nodo, para que
test_caracterizacion.py verifique que el refactor no cambió ningún hallazgo. Regenerarlo solo cuando
un cambio de comportamiento sea intencional: uv run python tests/caracterizacion/generar_golden.py
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from spunkmeyer.core.catalog import CATALOGO_ANTIPATRONES
from spunkmeyer.core.detector import auditar_archivo

AQUI = Path(__file__).resolve().parent


def ejemplos() -> dict[str, str]:
    """{nombre: código C} con el ejemplo incorrecto y el correcto de cada antipatrón del catálogo."""
    casos: dict[str, str] = {}
    for clave, info in sorted(CATALOGO_ANTIPATRONES.items()):
        for tipo in ("ejemplo_incorrecto", "ejemplo_correcto"):
            codigo = info.get(tipo) or ""
            if codigo.strip():
                casos[f"{clave}:{tipo}"] = codigo
    return casos


def hallazgos(codigo: str) -> list[list]:
    with tempfile.TemporaryDirectory() as tmp:
        fuente = Path(tmp) / "caso.c"
        fuente.write_text(codigo, encoding="utf-8")
        return [[str(a.codigo), a.linea, a.columna, a.mensaje] for a in auditar_archivo(fuente)]


def main() -> None:
    golden = {nombre: hallazgos(codigo) for nombre, codigo in ejemplos().items()}
    (AQUI / "golden.json").write_text(json.dumps(golden, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(golden)} casos, {sum(len(v) for v in golden.values())} hallazgos")


if __name__ == "__main__":
    main()
