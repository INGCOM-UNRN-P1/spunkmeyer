---
title: "Manual de Referencia: spunkmeyer"
subtitle: "Spunkmeyer — Detector de Antipatrones de Programación y Vicios Didácticos en C"
author: "Cátedra de Algoritmos y Programación"
date: "2026-08-31"
---

(manual-spunkmeyer)=
# Spunkmeyer — Detector de Antipatrones de Programación y Vicios Didácticos en C

````{abstract}
**Rol en el ecosistema:** Detección estática de antipatrones típicos de estudiantes: casteo innecesario de `malloc()`, lazos `while (!feof(f))`, comparaciones redundantes `if (cond == true)`, y punteros a variables locales devueltos desde el stack.
````

---

(manual-spunkmeyer-proposito)=
## 1. Propósito y Filosofía Pedagógica

La herramienta **`spunkmeyer`** forma parte del ecosistema oficial de software de la cátedra. Su diseño sigue principios pedagógicos rigurosos:

1. **Evidencia Técnica Directa**: Todo diagnóstico se fundamenta en la norma ISO C (C11/C23), en el modelo de memoria del sistema o en convenciones arquitectónicas formales.
2. **Acción Correctiva Concreta**: Cada advertencia incluye la prescripción técnica inmediata para resolver el defecto sin recurrir a conjeturas.
3. **Autonomía del Estudiante**: Facilita la autoevaluación local antes de la entrega final del trabajo práctico.
4. **Objetividad Docente**: Estandariza la corrección automática eliminando discrepancias subjetivas en la evaluación.

---

(manual-spunkmeyer-instalacion)=
## 2. Instalación y Diagnóstico del Entorno

````{important}
Asegurate de contar con el compilador GCC/Clang y las librerías del sistema instaladas antes de ejecutar `spunkmeyer`.
````

Para comprobar el estado de salud de tu entorno de trabajo y las dependencias auxiliares:

````{code-block} bash
# Comprobación de dependencias del sistema
spunkmeyer doctor
````

Si se detecta la falta de alguna utilidad (como `gdb`, `valgrind`, `clang-format` o `typst`), el comando indicará el paquete exacto a instalar según tu distribución GNU/Linux o entorno MSYS2.

---

(manual-spunkmeyer-comandos)=
## 3. Referencia Completa de Comandos CLI

A continuación se detallan los subcomandos principales disponibles en `spunkmeyer`:

| Sintaxis del Comando | Descripción y Efecto |
| :--- | :--- |
| `spunkmeyer detect src/ include/` | Escanea el código fuente en busca de antipatrones educativos. |
| `spunkmeyer explain <codigo_antipatron>` | Explica por qué una construcción es considerada un antipatrón y cómo corregirla. |
| `spunkmeyer list` | Lista todos los antipatrones catalogados por Spunkmeyer. |
| `spunkmeyer fix src/` | Aplica correcciones automáticas sobre antipatrones seguros. |

````{tip}
Podés agregar el flag `--json` a la mayoría de los comandos para exportar resultados en formato estructurado o `--md` para generar reportes Markdown para el informe de entrega.
````

---

(manual-spunkmeyer-tutorial)=
## 4. Tutorial Paso a Paso con Ejemplos Reales

### Caso de Estudio

Considerá el siguiente fragmento de código representativo:

````{code-block} c
:linenos:
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>

void antipatrones_comunes(FILE *f) {
    // 1. Casteo de malloc innecesario en C
    int *v = (int*) malloc(sizeof(int) * 10);
    
    // 2. Comparación booleana redundante
    bool flag = true;
    if (flag == true) { /* ... */ }
    
    // 3. while(!feof) lee el último dato duplicado
    int x;
    while (!feof(f)) {
        fscanf(f, "%d", &x);
    }
}
````

### Ejecución de la Herramienta

Ejecutá el análisis desde tu terminal:

````{code-block} bash
spunkmeyer detect src/ include/
````

### Salida Obtenida en Consola

````{code-block} text
⚠️ SPUNKMEYER DETECTÓ 3 ANTIPATRONES:
┌──────────────┬─────────────┬────────────────────────────────────────────────────────┐
│ Ubicación    │ Antipatrón  │ Corrección Pedagógica Recomendada                      │
├──────────────┼─────────────┼────────────────────────────────────────────────────────┤
│ app.c:6:14   │ MALLOC_CAST │ No castees el retorno de malloc() en C: 'int *v = mal…'│
│ app.c:10:9   │ BOOL_CMP    │ Simplificá 'if (flag == true)' por 'if (flag)'         │
│ app.c:14:5   │ WHILE_FEOF  │ 'while (!feof(f))' es erróneo. Validá el retorno de …  │
└──────────────┴─────────────┴────────────────────────────────────────────────────────┘
````

````{note}
Prestá atención a la explicación pedagógica generada: la herramienta no solo señala la línea del problema, sino que explica la causa raíz y el impacto en memoria o arquitectura.
````

---

(manual-spunkmeyer-ejercicios)=
## 5. Ejercicios Prácticos y Desafíos

Practicá el uso avanzado de **`spunkmeyer`** resolviendo los siguientes ejercicios:

````{exercise} Desafío 1: Limpieza de Antipatrones en Código de Alumno
Escanear una entrega y eliminar todos los vicios de programación.

**Instrucción de ejecución:**
```bash
spunkmeyer detect src/
```
````

````{solution} Desafío 1
```bash
spunkmeyer detect src/
# Verificá que la operación concluya exitosamente con código de salida 0.
```
````

````{exercise} Desafío 2: Consulta de Explicación de `while (!feof)`
Leer el fundamento técnico de por qué `feof` no se activa antes de intentar leer.

**Instrucción de ejecución:**
```bash
spunkmeyer explain WHILE_FEOF
```
````

````{solution} Desafío 2
```bash
spunkmeyer explain WHILE_FEOF
# Revisá el archivo generado o el informe en terminal para confirmar la resolución del problema.
```
````

````{exercise} Desafío 3: Auto-Corrección de Comparaciones Booleanas
Corregir automáticamente expresiones redundantes con `--fix`.

**Instrucción de ejecución:**
```bash
spunkmeyer fix src/ --dry-run
```
````

````{solution} Desafío 3
```bash
spunkmeyer fix src/ --dry-run
# Comprobá que la salida confirme la ausencia de advertencias o errores pendientes.
```
````

---

(manual-spunkmeyer-makefile)=
## 6. Integración en el Flujo de Trabajo y Makefile

Para incorporar `spunkmeyer` de forma automática a tu flujo de desarrollo, agregá la siguiente regla en el `Makefile` de tu proyecto:

````{code-block} makefile
check-spunkmeyer:
	@echo "=== Ejecutando verificación con spunkmeyer ==="
	spunkmeyer check src/ include/

.PHONY: check-spunkmeyer
````

Ejecutá `make check-spunkmeyer` antes de cada commit para asegurar que tu código conserve el estado de aprobación.
