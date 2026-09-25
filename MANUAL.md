# Manual de Uso y Referencia Técnica: spunkmeyer

> **SPUNKMEYER** — Detector de antipatrones de programación y vicios de diseño en código C
> **Versión:** `0.1.0` · **CLI principal:** `spunkmeyer` · **Plugin Ripley:** `antipatterns`

---

## 1. Arquitectura y Propósito Pedagógico

`spunkmeyer` forma parte del ecosistema de herramientas de la cátedra de Programación 1 (UNRN). Su objetivo central es resolver de forma modular, determinista y automatizada las tareas asociadas a su dominio específico dentro del ciclo de desarrollo, evaluación y aprendizaje de software en C.

### Alcance Funcional (Qué cubre)
- Detección estática con Tree-Sitter AST de 65 antipatrones didácticos (catalogados con alias canónicos `AP001`–`AP073` y códigos de taxonomía de cátedra P1 `0xXXXXh` / namespace `SP0xXXXXh`).
- Detección de casteo explícito e innecesario del retorno de `malloc()` o `calloc()` (`0x300Ah`, alias `AP001`).
- Detección de control de lectura con `while(!feof(archivo))` (`0x4006h`, alias `AP002`).
- Detección de retorno de punteros a variables locales de pila / Dangling Stack Pointer (`0x3002h`, alias `AP003`).
- Detección de chequeos innecesarios antes de `free(ptr)` (`0x3008h`, alias `AP004`).
- Detección de punto y coma accidental tras `if`/`while`/`for` (`0x1001h`, alias `AP006`).
- Detección de comparaciones booleanas redundantes (`if (condicion == true)`) (`0x1005h`, alias `AP005`).
- Detección de macros con doble evaluación de argumentos (`0x500Ah`, alias `AP017`).
- Detección de invocación a funciones prohibidas como `gets()` (`0x5008h`, alias `AP019`) o `fflush(stdin)` (`0x400Bh`, alias `AP007`).
- Supresión de falsos positivos en línea mediante directivas `// spunkmeyer:ignore [codigo|alias|all]`.
- Enmascarado léxico que ignora código inactivo bajo `#if 0` y comentarios de bloque o línea.

### Límites de Responsabilidad y Delegación (Qué no cubre)
- **Estilo y formato cátedra:** `gaff` es el propietario canónico del catálogo general 0xXXXXh de estilo. `spunkmeyer` se enfoca exclusivamente en la detección pedagógica profunda de antipatrones mediante AST (`APxxx` y `SP0x...h`).
- **Seguridad profunda y buffer overflows:** Delegado al satélite `kaneda`.
- **Topología completa del grafo de llamadas:** Delegado a `giger` y `sebastian`.
- **Ejecución y sandboxing:** Delegado a `nostromo`.

### Principios de Diseño
- **Enfoque Pedagógico:** Diagnósticos y mensajes en español rioplatense orientados a facilitar la comprensión de errores conceptuales.
- **Salida Estructurada Dual:** Soporte nativo para visualización enriquecida en terminal (Rich) y salida parseable para orquestadores (`--json`).
- **Integración Contractual:** Capacidad de emitir secciones de reporte para `dredd` (`dredd-section`) y actuar como satélite orquestado por `ripley`.
- **Idempotencia y Robustez:** Validación de precondiciones y comandos de autodiagnóstico (`doctor`) para verificación del entorno.

---

## 2. Instalación y Requisitos

### Requisitos del Sistema
- **Python:** `>= 3.10` (recomendado Python 3.11 o 3.12).
- **Gestor de paquetes:** [`uv`](https://github.com/astral-sh/uv) (entorno estándar de cátedra).
- **Toolchain C (si aplica):** GCC / Clang, Make, GDB y bibliotecas estándar de desarrollo.

### Instalación en el Entorno de Usuario
Para instalar la herramienta de forma global y aislada en el sistema mediante `uv tool`:
```bash
uv tool install --editable /home/mrtin/dev/tools/spunkmeyer
```

### Verificación de Instalación
Ejecutá el comando `doctor` para constatar que todas las dependencias y binarios requeridos estén presentes y operativos:
```bash
spunkmeyer doctor
```

---

## 3. Guía Integral de Comandos (CLI)

| Comando | Descripción Breve |
| :--- | :--- |
| [`spunkmeyer detect`](#detect) | Detecta antipatrones y malas prácticas en el código C. |
| [`spunkmeyer report`](#report) | Genera directamente la sección de reporte Markdown de SPUNKMEYER para Dredd. |
| [`spunkmeyer catalog`](#catalog) | Muestra el catálogo completo de antipatrones detectados. |
| [`spunkmeyer doctor`](#doctor) | Verifica dependencias del entorno de análisis de SPUNKMEYER (Tree-Sitter C, Python). |
| [`spunkmeyer explain`](#explain) | Explica detalladamente un antipatrón pedagógico con ejemplos antes y después. |
| [`spunkmeyer check`](#check) | Alias unificado de 'detect' para compatibilidad con el ecosistema (spunkmeyer check). |
| [`spunkmeyer correlate-hal`](#correlatehal) | Cruza los antipatrones estáticos con el informe forense post-mortem de HAL. |
| [`spunkmeyer diff-versions`](#diffversions) | Compara antipatrones entre dos entregas o versiones de código para auditar la evolución pedagógica. |

### `spunkmeyer detect`

Detecta antipatrones y malas prácticas en el código C.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `rutas` | `List[Path]` | Archivos C/H o carpetas a analizar. |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--json` | `bool` | `False` | Salida estructurada en JSON. |
| `--md`, `--output-md`, `-o` | `Optional[Path]` | `None` | Generar sección de reporte en formato Markdown para fusión en Dredd. |
| `--sarif` | `bool` | `False` | Emitir reporte en formato estándar OASIS SARIF 2.1.0. |
| `--rules`, `-r` | `Optional[Path]` | `None` | Ruta a archivo YAML con reglas personalizadas habilitadas para el TP. |

#### Ejemplo de Invocación
```bash
spunkmeyer detect <rutas>
```

### `spunkmeyer report`

Genera directamente la sección de reporte Markdown de SPUNKMEYER para Dredd.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `rutas` | `List[Path]` | Archivos C/H o carpetas a analizar. |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--output`, `-o` | `Optional[Path]` | `None` | Ruta de destino del archivo Markdown. |

#### Ejemplo de Invocación
```bash
spunkmeyer report <rutas>
```

### `spunkmeyer catalog`

Muestra el catálogo completo de antipatrones detectados.

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--json`, `-j` | `bool` | `False` | Emite el catálogo completo en formato JSON versionado con alias canónicos. |

#### Ejemplo de Invocación
```bash
spunkmeyer catalog
```

### `spunkmeyer doctor`

Verifica dependencias del entorno de análisis de SPUNKMEYER (Tree-Sitter C, Python).

#### Ejemplo de Invocación
```bash
spunkmeyer doctor
```

### `spunkmeyer explain`

Explica detalladamente un antipatrón pedagógico con ejemplos antes y después.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `codigo` | `str` | Código de regla o alias de antipatrón (ej: 'AP001', '0x300Ah'). |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--quiz`, `-q` | `bool` | `False` | Modo interactivo socrático: plantea una pregunta formativa sobre el antipatrón. |

#### Ejemplo de Invocación
```bash
spunkmeyer explain <codigo>
```

### `spunkmeyer check`

Alias unificado de 'detect' para compatibilidad con el ecosistema (spunkmeyer check).

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `rutas` | `List[Path]` | Archivos C/H o carpetas a analizar. |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--json` | `bool` | `False` | Salida estructurada en JSON. |
| `--md`, `--output-md`, `-o` | `Optional[Path]` | `None` | Generar sección de reporte en formato Markdown para fusión en Dredd. |
| `--sarif` | `bool` | `False` | Emitir reporte en formato estándar OASIS SARIF 2.1.0. |
| `--rules`, `-r` | `Optional[Path]` | `None` | Ruta a archivo YAML con reglas personalizadas habilitadas para el TP. |

#### Ejemplo de Invocación
```bash
spunkmeyer check <rutas>
```

### `spunkmeyer correlate-hal`

Cruza los antipatrones estáticos con el informe forense post-mortem de HAL.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `rutas` | `List[Path]` | Archivos fuentes C a auditar. |
| `crash_json` | `Path` | Informe de caída forense generado por HAL en formato JSON. |

#### Ejemplo de Invocación
```bash
spunkmeyer correlate-hal <rutas> <crash_json>
```

### `spunkmeyer diff-versions`

Compara antipatrones entre dos entregas o versiones de código para auditar la evolución pedagógica.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `dir_v1` | `Path` | Directorio con la versión inicial o entrega previa. |
| `dir_v2` | `Path` | Directorio con la versión actual o reentrega. |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--json` | `bool` | `False` | Salida estructurada en JSON. |

#### Ejemplo de Invocación
```bash
spunkmeyer diff-versions <dir_v1> <dir_v2>
```

---

## 4. Formatos de Salida e Integración con el Ecosistema

### Modo Interactivo / Terminal (Rich)
Por defecto, la herramienta renderiza paneles, árboles y tablas estilizadas para facilitar la lectura del estudiante y docente en terminales modernas con soporte ANSI.

### Modo Estructurado JSON (`--json`)
Para integración con pipelines de CI/CD, scripts de automatización u orquestadores externos, la opción `--json` emite un documento JSON estricto por la salida estándar (`stdout`), dirigiendo cualquier mensaje de logging a `stderr`:
```bash
spunkmeyer detect --json
```

### Integración con Dredd (`dredd-section`)
Cuando la herramienta genera reportes de evaluación para entregas de alumnos, produce una sección Markdown estandarizada conforme al contrato de integración de Dredd (v1.0.0):
```markdown
<!-- dredd-section: spunkmeyer, tool=spunkmeyer, version=0.1.0, status=ok -->
```
Este encabezado garantiza la agregación determinista de los hallazgos en la rúbrica docente.

### Integración con Ripley
`spunkmeyer` está registrada en el catálogo de plugins satélites de Ripley (`SATELLITE_CATALOG`). Puede invocarse directamente a través del motor de evaluación de Ripley configurando el análisis en `ripley.toml`.

---

## 5. Diagnóstico y Códigos de Salida

### Códigos de Retorno (`exit code`)
| Código | Significado |
| :---: | :--- |
| `0` | Ejecución exitosa sin hallazgos críticos ni errores de sintaxis. |
| `1` | Hallazgos pedagógicos detectados, infracción de reglas o advertencias activas. |
| `2` | Error de sintaxis en argumentos CLI o archivo fuente no encontrado. |
| `>2` | Error no recuperable del sistema, fallo de memoria o excepción interna. |

### Diagnóstico del Entorno (`doctor`)
Ante comportamientos inesperados, verificá el estado operativo con:
```bash
spunkmeyer doctor
```
Comprueba la presencia de las dependencias requeridas y la integridad de los componentes del paquete.