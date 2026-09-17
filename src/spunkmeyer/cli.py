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
    lines = ["<!-- dredd-section: spunkmeyer v1.0.0 -->\n## Detección de Antipatrones Didácticos (Spunkmeyer)\n"]
    lines.append(f"- **Archivos analizados:** {reporte.total_archivos}")
    lines.append(f"- **Antipatrones detectados:** {len(reporte.antipatrones)}")
    lines.append("")
    if reporte.ok:
        lines.append("> [!TIP]\n> **Buenas Prácticas:** No se detectaron vicios ni antipatrones comunes de programación en C.\n")
    else:
        lines.append("| Archivo | Línea | Código | Antipatrón | Explicación | Sugerencia |")
        lines.append("| :--- | :---: | :---: | :--- | :--- | :--- |")
        for ap in reporte.antipatrones:
            arch_name = ap.archivo.name.replace("|", "\\|")
            cod = str(ap.codigo).replace("|", "\\|")
            nom = str(ap.nombre).replace("|", "\\|")
            exp = str(ap.explicacion).replace("|", "\\|")
            sug = str(ap.sugerencia).replace("|", "\\|")
            lines.append(f"| `{arch_name}` | {ap.linea} | `{cod}` | **{nom}** | {exp} | {sug} |")
        lines.append("")
    return "\n".join(lines)


@app.command("detect")
def detect_cmd(
    rutas: List[Path] = typer.Argument(..., help="Archivos C/H o carpetas a analizar."),
    json_output: bool = typer.Option(False, "--json", help="Salida estructurada en JSON."),
    output_md: Optional[Path] = typer.Option(None, "--md", "--output-md", "-o", help="Generar sección de reporte en formato Markdown para fusión en Dredd."),
    sarif: bool = typer.Option(False, "--sarif", help="Emitir reporte en formato estándar OASIS SARIF 2.1.0."),
    rules: Optional[Path] = typer.Option(None, "--rules", "-r", help="Ruta a archivo YAML con reglas personalizadas habilitadas para el TP."),
) -> None:
    """Detecta antipatrones y malas prácticas en el código C."""
    reporte = auditar_archivos(rutas)

    if rules and rules.is_file():
        from spunkmeyer.core.detector import cargar_reglas_personalizadas_yaml
        reglas_activas = cargar_reglas_personalizadas_yaml(rules)
        if reglas_activas:
            reporte.antipatrones = [ap for ap in reporte.antipatrones if str(ap.codigo) in reglas_activas or getattr(ap.codigo, "_alias", "") in reglas_activas]

    if sarif:
        from spunkmeyer.core.detector import generar_sarif_210_spunkmeyer
        sarif_payload = generar_sarif_210_spunkmeyer(reporte)
        print(json.dumps(sarif_payload, indent=2, ensure_ascii=False))
        raise typer.Exit(code=0 if reporte.ok else 1)

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

    if not reporte.ok:
        raise typer.Exit(code=1)


@app.command("catalog")
def catalog_cmd(
    json_output: bool = typer.Option(False, "--json", "-j", help="Emite el catálogo completo en formato JSON versionado con alias canónicos."),
) -> None:
    """Muestra el catálogo completo de antipatrones detectados."""
    entradas = [
        (cod, info) for cod, info in sorted(CATALOGO_ANTIPATRONES.items())
        if cod.startswith("0x")
    ]
    if json_output:
        payload = {
            "schema_version": "1.0.0",
            "herramienta": "spunkmeyer",
            "namespace_prefijo": "SP",
            "total_antipatrones": len(entradas),
            "patrones": [
                {
                    "codigo": cod,
                    "alias": info.get("alias", ""),
                    "sp_codigo": info.get("sp_codigo", f"SP{cod}"),
                    "nombre": info.get("nombre", ""),
                    "explicacion": info.get("explicacion", ""),
                    "sugerencia": info.get("sugerencia", ""),
                    "ejemplo_incorrecto": info.get("ejemplo_incorrecto", ""),
                    "ejemplo_correcto": info.get("ejemplo_correcto", ""),
                }
                for cod, info in entradas
            ],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    tabla = Table(title=f"Catálogo de Antipatrones SPUNKMEYER ({len(entradas)} patrones)")
    tabla.add_column("Código", justify="center", style="bold cyan")
    tabla.add_column("Alias", justify="center", style="bold yellow")
    tabla.add_column("Nombre", style="bold")
    tabla.add_column("Explicación")
    tabla.add_column("Sugerencia", style="green")

    for cod, info in entradas:
        alias_str = f"{info.get('alias', '')} / {info.get('sp_codigo', '')}".strip(" /")
        tabla.add_row(cod, alias_str, info["nombre"], info["explicacion"], info["sugerencia"])

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
    quiz: bool = typer.Option(False, "--quiz", "-q", help="Modo interactivo socrático: plantea una pregunta formativa sobre el antipatrón."),
) -> None:
    """Explica detalladamente un antipatrón pedagógico con ejemplos antes y después."""
    info = CATALOGO_ANTIPATRONES.get(codigo)
    if not info:
        err_console.print(f"[red]Error:[/red] El código o alias '{codigo}' no existe en el catálogo de antipatrones.")
        raise typer.Exit(code=2)

    if quiz:
        console.print(Panel(
            f"[bold cyan]Pregunta Socrática sobre {info['nombre']}:[/bold cyan]\n\n"
            f"¿Por qué el siguiente fragmento es riesgoso o no idiomático?\n\n"
            f"[yellow]{info.get('ejemplo_incorrecto', '// N/A')}[/yellow]\n\n"
            f"[bold]Opciones:[/bold]\n"
            f" 1) {info['explicacion']}\n"
            f" 2) Es código C válido pero no compila con ningún flag.\n"
            f" 3) Solo afecta a sistemas embebidos de 16 bits.\n\n"
            f"[dim]Pista:[/dim] La respuesta correcta es la (1). Refactorización recomendada:\n"
            f"[green]{info.get('ejemplo_correcto', '// N/A')}[/green]",
            title=f"🧠 Quiz Socrático: {info.get('codigo', codigo)}",
            border_style="magenta",
        ))
        raise typer.Exit(code=0)

    cuerpo = (
        f"[bold]{info['nombre']}[/bold]\n\n"
        f"[bold cyan]🔍 Explicación didáctica:[/bold cyan]\n{info['explicacion']}\n\n"
        f"[bold green]💡 Sugerencia de refactorización:[/bold green]\n{info['sugerencia']}\n\n"
        f"[bold red]✗ Código Incorrecto (Antipatrón):[/bold red]\n```c\n{info.get('ejemplo_incorrecto', '// N/A')}\n```\n\n"
        f"[bold green]✓ Código Correcto (Idiomático):[/bold green]\n```c\n{info.get('ejemplo_correcto', '// N/A')}\n```"
    )
    console.print(Panel(cuerpo, title=f"📘 Antipatrón {info.get('codigo', codigo)} ({info.get('alias', '')})", border_style="cyan"))




@app.command("check")
def check_cmd(
    rutas: List[Path] = typer.Argument(..., help="Archivos C/H o carpetas a analizar."),
    json_output: bool = typer.Option(False, "--json", help="Salida estructurada en JSON."),
    output_md: Optional[Path] = typer.Option(None, "--md", "--output-md", "-o", help="Generar sección de reporte en formato Markdown para fusión en Dredd."),
    sarif: bool = typer.Option(False, "--sarif", help="Emitir reporte en formato estándar OASIS SARIF 2.1.0."),
    rules: Optional[Path] = typer.Option(None, "--rules", "-r", help="Ruta a archivo YAML con reglas personalizadas habilitadas para el TP."),
) -> None:
    """Alias unificado de 'detect' para compatibilidad con el ecosistema (spunkmeyer check)."""
    detect_cmd(rutas=rutas, json_output=json_output, output_md=output_md, sarif=sarif, rules=rules)


@app.command("correlate-hal")
def correlate_hal_cmd(
    rutas: List[Path] = typer.Argument(..., help="Archivos fuentes C a auditar."),
    crash_json: Path = typer.Option(..., "--crash-json", "-c", help="Informe de caída forense generado por HAL en formato JSON."),
) -> None:
    """Cruza los antipatrones estáticos con el informe forense post-mortem de HAL."""
    from spunkmeyer.core.detector import correlacionar_con_hal
    if not crash_json.is_file():
        err_console.print(f"[red]Error:[/red] No se encontró el archivo de crash '{crash_json}'.")
        raise typer.Exit(code=1)

    try:
        crash_data = json.loads(crash_json.read_text(encoding="utf-8"))
    except Exception as ex:
        err_console.print(f"[red]Error leyendo JSON de crash:[/red] {ex}")
        raise typer.Exit(code=1)

    reporte = auditar_archivos(rutas)
    correlaciones = correlacionar_con_hal(reporte, crash_data)

    if not correlaciones:
        console.print("[green]✓ No se hallaron antipatrones directamente correlacionados con la línea del crash.[/green]")
        raise typer.Exit(code=0)

    console.print(f"\n[bold red]⚠️ Se encontraron {len(correlaciones)} correlaciones causa-raíz con HAL:[/bold red]\n")
    for item in correlaciones:
        ap = item["antipatron"]
        console.print(f" • [yellow]{ap['nombre']}[/yellow] ({ap['codigo']}) en [cyan]{ap['archivo']}:{ap['linea']}[/cyan]")
        console.print(f"   [dim]{item['diagnostico_cruzado']}[/dim]\n")


@app.command("diff-versions")
def diff_versions_cmd(
    dir_v1: Path = typer.Argument(..., help="Directorio con la versión inicial o entrega previa."),
    dir_v2: Path = typer.Argument(..., help="Directorio con la versión actual o reentrega."),
    json_output: bool = typer.Option(False, "--json", help="Salida estructurada en JSON."),
) -> None:
    """Compara antipatrones entre dos entregas para auditar la mejora pedagógica (Integración Weyl)."""
    from spunkmeyer.core.detector import comparar_antipatrones_entre_versiones
    rep1 = auditar_archivos([dir_v1])
    rep2 = auditar_archivos([dir_v2])

    res = comparar_antipatrones_entre_versiones(rep1, rep2)
    if json_output:
        print(json.dumps(res, indent=2, ensure_ascii=False))
        raise typer.Exit(code=0)

    console.print(Panel(
        f"📊 [bold]Comparación de Calidad entre Entregas[/bold]\n\n"
        f" • Antipatrones versión anterior: {res['total_version_anterior']}\n"
        f" • Antipatrones versión actual: {res['total_version_actual']}\n"
        f" • [green]✓ Antipatrones corregidos:[/green] {res['antipatrones_resueltos']}\n"
        f" • [red]✗ Nuevos antipatrones introducidos:[/red] {res['antipatrones_nuevos']}\n"
        f" • [yellow]⚖ Antipatrones persistentes:[/yellow] {res['antipatrones_persistentes']}\n"
        f" • [bold cyan]Mejora neta de código:[/bold cyan] {res['mejora_neta']} problemas erradicados",
        title="SPUNKMEYER ⟷ WEYL Evolución de Entrega",
        border_style="green" if res['mejora_neta'] >= 0 else "red",
    ))


def main() -> None:
    app()


if __name__ == "__main__":
    main()

