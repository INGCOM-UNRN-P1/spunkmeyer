"""Test para verificar el cargador YAML de reglas personalizadas (SPUNK-D0103, SPUNK-D0304)."""

from pathlib import Path
from spunkmeyer.core.detector import cargar_reglas_personalizadas_yaml


def test_yaml_safe_load_con_claves_especificas(tmp_path: Path):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text(
        """
        reglas_habilitadas:
          - 0x300Ah
          - AP002
        otros:
          - etiqueta_cosa
          - 42
        """,
        encoding="utf-8",
    )
    reglas = cargar_reglas_personalizadas_yaml(yaml_file)
    assert "0x300Ah" in reglas
    assert "AP002" in reglas
    assert "etiqueta_cosa" not in reglas
    assert "42" not in reglas


def test_yaml_lista_directa(tmp_path: Path):
    yaml_file = tmp_path / "lista.yaml"
    yaml_file.write_text(
        """
        - 0x4006h
        - 0x5008h
        """,
        encoding="utf-8",
    )
    reglas = cargar_reglas_personalizadas_yaml(yaml_file)
    assert "0x4006h" in reglas
    assert "0x5008h" in reglas
