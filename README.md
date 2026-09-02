# 💡 SPUNKMEYER — Detector de Antipatrones Didácticos en C

SPUNKMEYER es una herramienta pedagógica diseñada para identificar vicios de diseño y antipatrones comunes en estudiantes de C (`malloc()` con casting innecesario, `while(!feof())`, retorno de punteros a variables locales en Stack, etc.).

---

## 🎯 Alcance

### Qué cubre
- Detección estática de antipatrones pedagógicos y vicios didácticos comunes en código C universitario (`0x10XXh`).
- Detección de casteo explícito e innecesario del puntero de retorno de `malloc` o `calloc` (`0x1001h`).
- Detección de lectura de archivos controlada con condición incorrecta `while(!feof(archivo))` (`0x1002h`).
- Detección de comparaciones booleanas redundantes (`if (condicion == true)` o `if (val == 0)` para booleanos).
- Detección de reasignación de punteros sin liberación previa y macros vacías innecesarias.

### Qué no cubre (Límites y Delegación)
- Auditoría de vulnerabilidades críticas de seguridad o buffer overflows (delegado a `kaneda`).
- Control de estilo visual o indentación (delegado a `gaff`).
- Ejecución de código (delegado a `nostromo`).

---

## 📋 Requisitos

### Requisitos de Sistema y Entorno
- Multiplataforma. Python >= 3.10.

### Dependencias Externas y Binarios
- Ninguno obligatorio (análisis estático con Tree-Sitter AST).

### Integración en el Ecosistema
- CLI `spunkmeyer`. Plugin registrado en `ripley.plugins` (`antipatterns`).

---

## Uso Rápido

```bash
# 1. Detectar antipatrones en archivos o carpetas
spunkmeyer detect src/ main.c

# 2. Salida estructurada JSON
spunkmeyer detect src/ --json

# 3. Ver catálogo completo de antipatrones
spunkmeyer catalog
```
