# 💡 SPUNKMEYER — Detector de Antipatrones Didácticos en C

> 📖 **Manual de Usuario:** Para una guía exhaustiva de comandos, banderas, arquitectura y ejemplos, consultá el [Manual de Uso](MANUAL.md).

SPUNKMEYER es una herramienta pedagógica diseñada para identificar vicios de diseño, malas prácticas didácticas y antipatrones comunes en estudiantes de programación en C (`malloc()` con casteo redundante, `while(!feof())`, retorno de punteros a variables locales en Stack, macros con efectos colaterales, etc.).

---

## 🎯 Alcance

### Qué cubre
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

### Qué no cubre (Límites y Contrato de Frontera)
- **Estilo y formato cátedra:** `gaff` es el propietario canónico del catálogo general 0xXXXXh de estilo. `spunkmeyer` se enfoca exclusivamente en la detección pedagógica profunda de antipatrones mediante AST (`APxxx` y `SP0x...h`).
- **Seguridad profunda y buffer overflows:** Delegado al satélite `kaneda`.
- **Topología completa del grafo de llamadas:** Delegado a `giger` y `sebastian`.
- **Ejecución y sandboxing:** Delegado a `nostromo`.

---

## 📋 Requisitos

### Requisitos de Sistema y Entorno
- Multiplataforma (Linux / macOS / Windows). Python >= 3.10.

### Dependencias Externas y Binarios
- Ninguno obligatorio: motor de análisis sintáctico puro basado en `tree-sitter` y `tree-sitter-c`.

### Integración en el Ecosistema
- Satélite catalogado en `ripley` (`ripley.plugins` → `antipatterns`).
- Exportación directa de secciones de informe Markdown para `dredd`.
- Correlación estática de causas-raíz cruzadas con reportes de caída de `hal`.

---

## 🚀 Comandos CLI

SPUNKMEYER provee 8 comandos especializados:

```bash
# 1. detect (o check): Audita antipatrones en archivos o directorios
spunkmeyer detect src/ main.c
spunkmeyer check src/

# 2. Salida estructurada JSON para herramientas y automatización
spunkmeyer detect src/ --json

# 3. Exportación en estándar OASIS SARIF 2.1.0 (calibrado warning/error)
spunkmeyer detect src/ --sarif

# 4. Filtrar por reglas específicas mediante archivo YAML de cátedra
spunkmeyer detect src/ --rules config/reglas_tp1.yaml

# 5. report: Genera sección de informe Markdown para incrustar en Dredd
spunkmeyer report src/ -o reporte_antipatrones.md

# 6. catalog: Consulta el catálogo canónico (65 antipatrones didácticos)
spunkmeyer catalog
spunkmeyer catalog --json

# 7. explain: Explica en detalle un antipatrón y cómo corregirlo
spunkmeyer explain AP001
spunkmeyer explain 0x300Ah

# 8. doctor: Diagnostica dependencias y estado de la gramática Tree-Sitter C
spunkmeyer doctor

# 9. correlate-hal: Cruza antipatrones estáticos con el JSON de caída de HAL
spunkmeyer correlate-hal src/ --crash-json crash.json

# 10. diff-versions: Compara la evolución de antipatrones entre dos entregas
spunkmeyer diff-versions entrega1/ entrega2/
```

### Opciones Comunes de `detect`
- `--json`: Emite el reporte consolidado en JSON.
- `--sarif`: Emite diagnósticos en OASIS SARIF 2.1.0 con severidad calibrada (`error` para fallos de memoria/seguridad, `warning` para estilo pedagógico).
- `--rules` / `-r <archivo.yaml>`: Aplica filtro declarativo de reglas activas para el TP. Acepta códigos de cátedra (`0x4006h`), legacy (`0x4002h`), alias (`AP002`) o namespace didáctico (`SP0x4006h`).
- `--md` / `-o <archivo.md>`: Genera la sección Markdown estandarizada para Dredd con escapado de tablas.
