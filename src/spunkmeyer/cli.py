"""CLI de SPUNKMEYER — Detector pedagógico de antipatrones en C."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from spunkmeyer import __version__
from spunkmeyer.core.detector import CATALOGO_ANTIPATRONES, auditar_archivos

console = Console()
err_console = Console(stderr=True)

app = typer.Typer(
    name="spunkmeyer",
    help="💡 SPUNKMEYER — Detector de antipatrones de programación y vicios didácticos en código C.",
    add_completion=True,
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"[bold cyan]SPUNKMEYER[/bold cyan] versión [bold]{__version__}[/bold]")
        raise typer.Exit(code=0)


@app.callback()
def main_callback(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Muestra la versión de SPUNKMEYER.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    pass


@app.command("detect")
def detect_cmd(
    rutas: List[Path] = typer.Argument(..., help="Archivos C/H o carpetas a analizar."),
    json_output: bool = typer.Option(False, "--json", help="Salida estructurada en JSON."),
) -> None:
    """Detecta antipatrones y malas prácticas en el código C."""
    reporte = auditar_archivos(rutas)

    if json_output:
        print(json.dumps(reporte.to_dict(), indent=2, ensure_ascii=False))
        raise typer.Exit(code=0 if reporte.ok else 1)

    if reporte.ok:
        console.print(Panel(
            f"[bold green]✓ No se encontraron antipatrones en los {reporte.total_archivos} archivos analizados.[/bold green]",
            title="SPUNKMEYER OK",
            border_style="green",
        ))
        raise typer.Exit(code=0)

    console.print(f"\n[bold yellow]⚠️ Se detectaron {len(reporte.antipatrones)} antipatrones didácticos:[/bold yellow]\n")

    tabla = Table(title="Antipatrones de Programación Detectados")
    tabla.add_column("Ubicación", style="cyan")
    tabla.add_column("Código", justify="center", style="bold yellow")
    tabla.add_column("Antipatrón", style="bold")
    tabla.add_column("Explicación")
    tabla.add_column("Sugerencia", style="dim")

    for ap in reporte.antipatrones:
        tabla.add_row(
            f"{ap.archivo.name}:{ap.linea}",
            ap.codigo,
            ap.nombre,
            ap.explicacion,
            ap.sugerencia,
        )

    console.print(tabla)
    raise typer.Exit(code=1)


@app.command("catalog")
def catalog_cmd() -> None:
    """Muestra el catálogo completo de antipatrones detectados."""
    tabla = Table(title=f"Catálogo de Antipatrones SPUNKMEYER ({len(CATALOGO_ANTIPATRONES)} patrones)")
    tabla.add_column("Código", justify="center", style="bold cyan")
    tabla.add_column("Nombre", style="bold")
    tabla.add_column("Explicación")
    tabla.add_column("Sugerencia", style="green")

    for cod, info in sorted(CATALOGO_ANTIPATRONES.items()):
        tabla.add_row(cod, info["nombre"], info["explicacion"], info["sugerencia"])

    console.print(tabla)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
