# 💡 SPUNKMEYER — Detector de Antipatrones Didácticos en C

SPUNKMEYER es una herramienta pedagógica diseñada para identificar vicios de diseño y antipatrones comunes en estudiantes de C (`malloc()` con casting innecesario, `while(!feof())`, retorno de punteros a variables locales en Stack, etc.).

## Uso Rápido

```bash
# 1. Detectar antipatrones en archivos o carpetas
spunkmeyer detect src/ main.c

# 2. Salida estructurada JSON
spunkmeyer detect src/ --json

# 3. Ver catálogo completo de antipatrones
spunkmeyer catalog
```
