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


def generar_seccion_markdown(reporte) -> str:
    """Genera sección de antipatrones didácticos para Dredd."""
    lines = ["## Detección de Antipatrones Didácticos (Spunkmeyer)\n"]
    lines.append(f"- **Archivos analizados:** {reporte.total_archivos}")
    lines.append(f"- **Antipatrones detectados:** {len(reporte.antipatrones)}")
    lines.append("")
    if reporte.ok:
        lines.append("> [!TIP]\n> **Buenas Prácticas:** No se detectaron vicios ni antipatrones comunes de programación en C.\n")
    else:
        lines.append("| Archivo | Línea | Código | Antipatrón | Explicación | Sugerencia |")
        lines.append("| :--- | :---: | :---: | :--- | :--- | :--- |")
        for ap in reporte.antipatrones:
            lines.append(f"| `{ap.archivo.name}` | {ap.linea} | `{ap.codigo}` | **{ap.nombre}** | {ap.explicacion} | {ap.sugerencia} |")
        lines.append("")
    return "\n".join(lines)


@app.command("detect")
def detect_cmd(
    rutas: List[Path] = typer.Argument(..., help="Archivos C/H o carpetas a analizar."),
    json_output: bool = typer.Option(False, "--json", help="Salida estructurada en JSON."),
    output_md: Optional[Path] = typer.Option(None, "--md", "--output-md", "-o", help="Generar sección de reporte en formato Markdown para fusión en Dredd."),
) -> None:
    """Detecta antipatrones y malas prácticas en el código C."""
    reporte = auditar_archivos(rutas)

    if output_md:
        md_text = generar_seccion_markdown(reporte)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(md_text, encoding="utf-8")
        console.print(f"[green]✓ Sección Markdown generada en:[/green] [cyan]{output_md}[/cyan]")
        raise typer.Exit(code=0 if reporte.ok else 1)

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


@app.command("report")
def report_cmd(
    rutas: List[Path] = typer.Argument(..., help="Archivos C/H o carpetas a analizar."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Ruta de destino del archivo Markdown."),
) -> None:
    """Genera directamente la sección de reporte Markdown de SPUNKMEYER para Dredd."""
    reporte = auditar_archivos(rutas)
    md_content = generar_seccion_markdown(reporte)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md_content, encoding="utf-8")
        console.print(f"[green]✓ Reporte Markdown generado en:[/green] [cyan]{output}[/cyan]")
    else:
        print(md_content)


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


@app.command("doctor")
def doctor_cmd() -> None:
    """Verifica dependencias del entorno de análisis de SPUNKMEYER (Tree-Sitter C, Python)."""
    tabla = Table(title="🏥 Diagnóstico del Entorno SPUNKMEYER (doctor)", border_style="cyan")
    tabla.add_column("Componente", style="bold white")
    tabla.add_column("Estado", justify="center")
    tabla.add_column("Detalle")

    import tree_sitter_c as tsc
    from spunkmeyer.core.detector import get_c_parser
    try:
        p = get_c_parser()
        tabla.add_row("Tree-Sitter C Grammar", "[bold green]✓ Operativo[/bold green]", "Gramática C AST cargada exitosamente")
    except Exception as e:
        tabla.add_row("Tree-Sitter C Grammar", "[bold red]✗ Error[/bold red]", str(e))

    console.print(tabla)


@app.command("explain")
def explain_cmd(
    codigo: str = typer.Argument(..., help="Código de regla o alias de antipatrón (ej: 'AP001', '0x300Ah')."),
) -> None:
    """Explica detalladamente un antipatrón pedagógico con ejemplos antes y después."""
    info = CATALOGO_ANTIPATRONES.get(codigo)
    if not info:
        err_console.print(f"[red]Error:[/red] El código o alias '{codigo}' no existe en el catálogo de antipatrones.")
        raise typer.Exit(code=2)

    cuerpo = (
        f"[bold]{info['nombre']}[/bold]\n\n"
        f"[bold cyan]🔍 Explicación didáctica:[/bold cyan]\n{info['explicacion']}\n\n"
        f"[bold green]💡 Sugerencia de refactorización:[/bold green]\n{info['sugerencia']}\n\n"
        f"[bold red]✗ Código Incorrecto (Antipatrón):[/bold red]\n```c\n{info.get('ejemplo_incorrecto', '// N/A')}\n```\n\n"
        f"[bold green]✓ Código Correcto (Idiomático):[/bold green]\n```c\n{info.get('ejemplo_correcto', '// N/A')}\n```"
    )
    console.print(Panel(cuerpo, title=f"📘 Antipatrón {info.get('codigo', codigo)} ({info.get('alias', '')})", border_style="cyan"))


def main() -> None:
    app()


if __name__ == "__main__":
    main()

