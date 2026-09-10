"""Motor de detección de antipatrones y vicios didácticos en SPUNKMEYER usando Tree-Sitter AST."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Set

import tree_sitter_c as tsc
from tree_sitter import Language, Parser, Node

from spunkmeyer.core.models import AntipatronDetectado, ReporteAntipatrones, RuleCode

_C_LANGUAGE: Optional[Language] = None
_PARSER: Optional[Parser] = None


def get_c_parser() -> Parser:
    global _C_LANGUAGE, _PARSER
    if _PARSER is None:
        _C_LANGUAGE = Language(tsc.language())
        _PARSER = Parser(_C_LANGUAGE)
    return _PARSER


CATALOGO_ANTIPATRONES: Dict[str, Dict[str, str]] = {
    "0x300Ah": {
        "codigo": "0x300Ah",
        "alias": "AP001",
        "nombre": "Casteo redundante de malloc()",
        "mensaje": "Castear el retorno de 'malloc()' es innecesario en C y puede enmascarar la falta de #include <stdlib.h>.",
        "explicacion": "En C, 'void*' se promociona automáticamente a cualquier tipo de puntero. Castear '(tipo*)malloc()' proviene de C++ y es una mala práctica en C.",
        "sugerencia": "Escribí 'ptr = malloc(sizeof(*ptr) * n);' directamente.",
        "ejemplo_incorrecto": "int *ptr = (int *)malloc(sizeof(int) * 10);",
        "ejemplo_correcto": "int *ptr = malloc(sizeof(*ptr) * 10);",
    },
    "0x4002h": {
        "codigo": "0x4002h",
        "alias": "AP002",
        "nombre": "Control de lectura con while(!feof())",
        "mensaje": "Usar '!feof(f)' como condición del bucle provoca procesar el último registro dos veces.",
        "explicacion": "'feof()' solo devuelve verdadero DESPUÉS de que una lectura previa intentó leer más allá del fin de archivo y falló.",
        "sugerencia": "Controlá el bucle con el valor de retorno de la función de lectura: 'while (fread(...) == 1)' o 'while (fgets(...) != NULL)'.",
        "ejemplo_incorrecto": "while (!feof(f)) {\n    fread(&elem, sizeof(elem), 1, f);\n    procesar(elem);\n}",
        "ejemplo_correcto": "while (fread(&elem, sizeof(elem), 1, f) == 1) {\n    procesar(elem);\n}",
    },
    "0x3002h": {
        "codigo": "0x3002h",
        "alias": "AP003",
        "nombre": "Retorno de puntero a variable local (Dangling Stack Pointer)",
        "mensaje": "Se detectó el retorno de la dirección de una variable local en la pila.",
        "explicacion": "Al finalizar la función, su stack frame se destruye. El puntero retornado apuntará a memoria inválida o sobrescribible.",
        "sugerencia": "Asigná memoria dinámica con malloc() o pasá el buffer como parámetro por referencia.",
        "ejemplo_incorrecto": "int* fn(void) {\n    int local = 42;\n    return &local;\n}",
        "ejemplo_correcto": "int* fn(void) {\n    int *ptr = malloc(sizeof(*ptr));\n    if (ptr) *ptr = 42;\n    return ptr;\n}",
    },
    "0x3008h": {
        "codigo": "0x3008h",
        "alias": "AP004",
        "nombre": "Chequeo innecesario antes de free()",
        "mensaje": "Comprobar 'if (ptr != NULL)' antes de invocar 'free(ptr)' es redundante.",
        "explicacion": "La especificación del estándar ISO C garantiza que 'free(NULL)' es una operación segura y no realiza ninguna acción.",
        "sugerencia": "Invocá 'free(ptr);' directamente sin envolverlo en un if.",
        "ejemplo_incorrecto": "if (ptr != NULL) {\n    free(ptr);\n}",
        "ejemplo_correcto": "free(ptr);",
    },
    "0x1005h": {
        "codigo": "0x1005h",
        "alias": "AP005",
        "nombre": "Comparación booleana explícita redundante",
        "mensaje": "Comparar explícitamente 'if (cond == 1)' o 'if (cond == true)' es redundante.",
        "explicacion": "En C cualquier valor distinto de 0 evalúa a verdadero en estructuras de control.",
        "sugerencia": "Escribí 'if (cond)' o 'if (!cond)' directamente.",
        "ejemplo_incorrecto": "if (es_valido == true) { ... }",
        "ejemplo_correcto": "if (es_valido) { ... }",
    },
    "0x1001h": {
        "codigo": "0x1001h",
        "alias": "AP006",
        "nombre": "Punto y coma accidental tras condición de control",
        "mensaje": "Punto y coma ';' detectado inmediatamente después de 'if (...)', 'for (...)' o 'while (...)'.",
        "explicacion": "El punto y coma crea una sentencia vacía, haciendo que el bloque que le sigue se ejecute incondicionalmente.",
        "sugerencia": "Eliminá el ';' al final de la condición de control.",
        "ejemplo_incorrecto": "if (x > 0);\n{\n    hacer_algo();\n}",
        "ejemplo_correcto": "if (x > 0)\n{\n    hacer_algo();\n}",
    },
    "0x4006h": {
        "codigo": "0x4006h",
        "alias": "AP007",
        "nombre": "Uso de fflush(stdin) para limpiar buffer",
        "mensaje": "Invocación de 'fflush(stdin)' detectada.",
        "explicacion": "Según el estándar ISO C, 'fflush()' solo está definido para streams de salida. Aplicarlo sobre 'stdin' produce comportamiento indefinido.",
        "sugerencia": "Consumí los caracteres restantes del buffer con 'while ((c = getchar()) != '\\n' && c != EOF);'.",
        "ejemplo_incorrecto": "scanf(\"%d\", &x);\nfflush(stdin);",
        "ejemplo_correcto": "int c;\nwhile ((c = getchar()) != '\\n' && c != EOF);",
    },
    "0x300Fh": {
        "codigo": "0x300Fh",
        "alias": "AP008",
        "nombre": "Uso de sizeof(puntero) en reserva dinámica",
        "mensaje": "Se detectó 'sizeof(ptr)' en lugar de 'sizeof(*ptr)' o 'sizeof(tipo)' en malloc/calloc.",
        "explicacion": "'sizeof(ptr)' devuelve el tamaño del puntero (4 u 8 bytes) en lugar del tamaño de la estructura apuntada, provocando reservas insuficientes.",
        "sugerencia": "Escribí 'malloc(sizeof(*ptr) * n)' o 'malloc(sizeof(struct tipo))'.",
        "ejemplo_incorrecto": "nodo_t *n = malloc(sizeof(n));",
        "ejemplo_correcto": "nodo_t *n = malloc(sizeof(*n));",
    },
    "0x100Dh": {
        "codigo": "0x100Dh",
        "alias": "AP009",
        "nombre": "Variable float o double utilizada como contador de bucle",
        "mensaje": "Se detectó una variable de tipo 'float' o 'double' como contador de bucle 'for'.",
        "explicacion": "Los tipos flotantes acumulan errores de redondeo binario IEEE-754 en cada iteración, provocando bucles infinitos o conteos inexactos.",
        "sugerencia": "Utilizá un contador entero (int o size_t) y derivá el valor flotante dentro del cuerpo del bucle.",
        "ejemplo_incorrecto": "for (float x = 0.0f; x < 1.0f; x += 0.1f) { ... }",
        "ejemplo_correcto": "for (int i = 0; i < 10; i++) {\n    float x = i * 0.1f;\n}",
    },
    "0x3001h": {
        "codigo": "0x3001h",
        "alias": "AP010",
        "nombre": "Uso de memoria dinámica sin validar retorno a NULL",
        "mensaje": "Desreferencia o uso directo de retorno de malloc/calloc sin verificar if (ptr == NULL).",
        "explicacion": "Si el sistema agota la memoria, malloc retorna NULL. Desreferenciar sin comprobación causará una caída fatal por SIGSEGV.",
        "sugerencia": "Comprobá siempre 'if (ptr == NULL)' inmediatamente después de la asignación.",
        "ejemplo_incorrecto": "int *p = malloc(10 * sizeof(*p));\np[0] = 42; // Caída si falla malloc",
        "ejemplo_correcto": "int *p = malloc(10 * sizeof(*p));\nif (p == NULL) return -1;\np[0] = 42;",
    },
    "0x3002b": {
        "codigo": "0x3002h",
        "alias": "AP011",
        "nombre": "Puntero colgante sin asignar NULL tras free()",
        "mensaje": "Puntero liberado con free() continúa en uso o no se anula explícitamente.",
        "explicacion": "Dejar la variable con la dirección anterior permite accesos accidentales Use-After-Free o Double-Free.",
        "sugerencia": "Asigná 'ptr = NULL;' inmediatamente después de 'free(ptr);'.",
        "ejemplo_incorrecto": "free(ptr);\n// más instrucciones donde ptr sigue apuntando a memoria liberada",
        "ejemplo_correcto": "free(ptr);\nptr = NULL;",
    },
    "0x2007h": {
        "codigo": "0x2007h",
        "alias": "AP012",
        "nombre": "Variable local declarada pero no utilizada",
        "mensaje": "Se declaró una variable local que no es leída ni referenciada en la función.",
        "explicacion": "Las variables residuales consumen memoria de stack y confunden al lector sobre el estado real de la función.",
        "sugerencia": "Eliminá la variable innecesaria para limpiar el ámbito local.",
        "ejemplo_incorrecto": "int main(void) {\n    int no_usada = 10;\n    return 0;\n}",
        "ejemplo_correcto": "int main(void) {\n    return 0;\n}",
    },
    "0x5004h": {
        "codigo": "0x5004h",
        "alias": "AP013",
        "nombre": "Uso de funciones inseguras de manipulación de cadenas (strcpy/sprintf)",
        "mensaje": "Invocación de función sin control de longitud de destino detectada.",
        "explicacion": "'strcpy' y 'sprintf' no limitan la cantidad de bytes escritos, causando desbordamiento de búfer (Buffer Overflow).",
        "sugerencia": "Migrá a 'snprintf' o copiá controlando explícitamente el tamaño máximo del destino.",
        "ejemplo_incorrecto": "char buf[16];\nsprintf(buf, \"%s: %d\", nombre, valor);",
        "ejemplo_correcto": "char buf[16];\nsnprintf(buf, sizeof(buf), \"%s: %d\", nombre, valor);",
    },
    "0x300Dh": {
        "codigo": "0x300Dh",
        "alias": "AP014",
        "nombre": "Número mágico literal en condición lógica",
        "mensaje": "Uso de literal numérico directo en condición de control o comparación.",
        "explicacion": "Los números mágicos oscurecen el significado del algoritmo e impiden la mantenibilidad del código.",
        "sugerencia": "Declarale un nombre significativo mediante una constante '#define' o 'enum'.",
        "ejemplo_incorrecto": "if (estado == 404) { ... }",
        "ejemplo_correcto": "#define ESTADO_NOT_FOUND 404\nif (estado == ESTADO_NOT_FOUND) { ... }",
    },
    "0x200Bh": {
        "codigo": "0x200Bh",
        "alias": "AP015",
        "nombre": "Función con excesiva cantidad de parámetros (> 5)",
        "mensaje": "Firma de función con más de 5 parámetros de entrada.",
        "explicacion": "Las funciones con muchos parámetros aumentan el acoplamiento y dificultan la invocación correcta en la pila.",
        "sugerencia": "Agrupá los parámetros relacionados en una estructura 'struct params_t'.",
        "ejemplo_incorrecto": "void config(int a, int b, int c, int d, int e, int f);",
        "ejemplo_correcto": "void config(const struct config_t *cfg);",
    },
    "0x100Ah": {
        "codigo": "0x100Ah",
        "alias": "AP016",
        "nombre": "Asignación accidental en condición lógica (if (x = 5))",
        "mensaje": "Asignación simple '=' dentro de la condición de un 'if' o 'while'.",
        "explicacion": "Casi con certeza se intentó escribir una comparación '==' en lugar de una asignación que altera la variable.",
        "sugerencia": "Utilizá '==' para comparar o extraé la asignación antes del condicional.",
        "ejemplo_incorrecto": "if (x = 5) { ... }",
        "ejemplo_correcto": "if (x == 5) { ... }",
    },
    "0x500Ah": {
        "codigo": "0x500Ah",
        "alias": "AP017",
        "nombre": "Macro con argumentos evaluados múltiples veces",
        "mensaje": "Macro de preprocesador evalúa un argumento más de una vez en su reemplazo.",
        "explicacion": "Si el cliente invoca la macro pasando una expresión con efecto colateral (ej. MAX(x++, y)), el argumento se evaluará repetidas veces.",
        "sugerencia": "Reemplazá la macro por una función inline o protegé las evaluaciones.",
        "ejemplo_incorrecto": "#define MAX(a, b) ((a) > (b) ? (a) : (b))",
        "ejemplo_correcto": "static inline int max(int a, int b) { return a > b ? a : b; }",
    },
    "0x2009h": {
        "codigo": "0x2009h",
        "alias": "AP018",
        "nombre": "Llamada recursiva sin caso base explícito",
        "mensaje": "Función recursiva que se invoca a sí misma sin condicional visible de parada.",
        "explicacion": "Toda función recursiva debe validar primero su caso base antes de invocarse nuevamente, previniendo un Stack Overflow.",
        "sugerencia": "Agregá la condición de corte (caso base) al inicio de la función.",
        "ejemplo_incorrecto": "void cuenta(int n) {\n    cuenta(n - 1);\n}",
        "ejemplo_correcto": "void cuenta(int n) {\n    if (n <= 0) return;\n    cuenta(n - 1);\n}",
    },
    "0x5008h": {
        "codigo": "0x5008h",
        "alias": "AP019",
        "nombre": "Invocación de la función prohibida gets()",
        "mensaje": "Llamada a 'gets()' detectada. Esta función fue removida de C11 por ser inherentemente insegura.",
        "explicacion": "'gets()' no recibe el tamaño del búfer destino y lee hasta encontrar un salto de línea, permitiendo desbordes triviales.",
        "sugerencia": "Reemplazala por 'fgets(buffer, sizeof(buffer), stdin)'.",
        "ejemplo_incorrecto": "char buf[100];\ngets(buf);",
        "ejemplo_correcto": "char buf[100];\nfgets(buf, sizeof(buf), stdin);",
    },
    "0x5004b": {
        "codigo": "0x5004h",
        "alias": "AP020",
        "nombre": "Comparación directa de cadenas con == o !=",
        "mensaje": "Se detectó comparación de cadena o puntero contra un literal con '==' o '!='.",
        "explicacion": "El operador '==' compara las direcciones de memoria de los punteros, no el contenido alfabético de las cadenas.",
        "sugerencia": "Utilizá 'strcmp(str, \"...\") == 0' para comparar el contenido textual.",
        "ejemplo_incorrecto": "if (str == \"hola\") { ... }",
        "ejemplo_correcto": "if (strcmp(str, \"hola\") == 0) { ... }",
    },
    "0x100Ch": {
        "codigo": "0x100Ch",
        "alias": "AP021",
        "nombre": "Caso de switch sin break (Fallthrough no intencional)",
        "mensaje": "Bloque 'case' sin sentencia 'break' previa al siguiente caso.",
        "explicacion": "Omitir el 'break' provoca que la ejecución caiga directamente al caso siguiente (fallthrough), usualmente un error no deseado.",
        "sugerencia": "Agregá 'break;' al final del caso o documentá explícitamente '// fallthrough'.",
        "ejemplo_incorrecto": "switch (op) {\ncase 1:\n    hacer_1();\ncase 2:\n    hacer_2();\n    break;\n}",
        "ejemplo_correcto": "switch (op) {\ncase 1:\n    hacer_1();\n    break;\ncase 2:\n    hacer_2();\n    break;\n}",
    },
    "0x0003b": {
        "codigo": "0x0003h",
        "alias": "AP022",
        "nombre": "Declaración de variable mezclada tras sentencias ejecutables",
        "mensaje": "Declaración de variable posterior a sentencias ejecutables dentro del mismo bloque.",
        "explicacion": "En C90 y estilo tradicional de cátedra, las variables deben declararse al inicio del bloque para claridad de dependencias.",
        "sugerencia": "Agrupá las declaraciones al comienzo del bloque de la función.",
        "ejemplo_incorrecto": "int a = 1;\na = a + 5;\nint b = 2; // Declaración retrasada",
        "ejemplo_correcto": "int a = 1;\nint b = 2;\na = a + 5;",
    },
    "0x100Eh": {
        "codigo": "0x100Eh",
        "alias": "AP023",
        "nombre": "Expresión booleana tautológica o contradictoria",
        "mensaje": "Condición lógica que siempre evalúa a verdadero o a falso (ej: x && !x o x || true).",
        "explicacion": "Las expresiones tautológicas representan lógica redundante o errores graves de razonamiento en la condición.",
        "sugerencia": "Simplificá la expresión lógica eliminando términos redundantes o contradictorios.",
        "ejemplo_incorrecto": "if (x && !x) { ... }",
        "ejemplo_correcto": "if (x) { ... }",
    },
    "0x3015h": {
        "codigo": "0x3015h",
        "alias": "AP024",
        "nombre": "Sobreescritura directa de puntero en realloc",
        "mensaje": "Sobreescritura directa 'ptr = realloc(ptr, ...)'. Si realloc falla retorna NULL y la dirección previa se pierde, provocando fuga de memoria.",
        "explicacion": "Al asignar el retorno de realloc sobre la misma variable, si la reasignación falla se pierde la única referencia a la memoria previamente reservada.",
        "sugerencia": "Utilizá una variable temporal: 'void *tmp = realloc(ptr, n); if (tmp) ptr = tmp;'.",
        "ejemplo_incorrecto": "ptr = realloc(ptr, nuevo_tam);",
        "ejemplo_correcto": "void *tmp = realloc(ptr, nuevo_tam);\nif (tmp != NULL) ptr = tmp;",
    },
    "0x4008h": {
        "codigo": "0x4008h",
        "alias": "AP025",
        "nombre": "Desajuste de especificadores de formato en printf/scanf",
        "mensaje": "Desajuste entre el especificador de formato y el tipo de dato del argumento.",
        "explicacion": "Pasar argumentos que no corresponden con la máscara de formato produce comportamiento indefinido o corrupción de la pila.",
        "sugerencia": "Asegurate de usar '%d' para int, '%f'/'%lf' para float/double y '%s' para char*.",
        "ejemplo_incorrecto": "double d = 3.14;\nprintf(\"%d\\n\", d);",
        "ejemplo_correcto": "double d = 3.14;\nprintf(\"%f\\n\", d);",
    },
    "0x3019h": {
        "codigo": "0x3019h",
        "alias": "AP026",
        "nombre": "Pointer decay en sizeof de arreglo parámetro",
        "mensaje": "Uso de 'sizeof(arr) / sizeof(arr[0])' sobre un arreglo recibido como parámetro de función.",
        "explicacion": "En C los arreglos decaen a punteros simples al pasarse como argumentos, por lo que sizeof(arr) siempre devuelve el tamaño de un puntero (4 u 8 bytes).",
        "sugerencia": "Pasá la cantidad de elementos explícitamente como un parámetro adicional 'size_t n'.",
        "ejemplo_incorrecto": "void foo(int vec[]) {\n    size_t n = sizeof(vec) / sizeof(vec[0]);\n}",
        "ejemplo_correcto": "void foo(const int *vec, size_t n) {\n    // usar n recibido por parámetro\n}",
    },
    "0x100Fh": {
        "codigo": "0x100Fh",
        "alias": "AP027",
        "nombre": "Posible error off-by-one en condición de parada de bucle",
        "mensaje": "Condición de parada '<=' en bucle que itera sobre un arreglo de tamaño fijo.",
        "explicacion": "Un arreglo de tamaño N tiene índices válidos de 0 a N-1. Usar '<= N' intenta acceder al elemento N que cae fuera de rango.",
        "sugerencia": "Utilizá el operador estricto '< N' en la condición de terminación.",
        "ejemplo_incorrecto": "int arr[10];\nfor (int i = 0; i <= 10; i++) arr[i] = 0;",
        "ejemplo_correcto": "int arr[10];\nfor (int i = 0; i < 10; i++) arr[i] = 0;",
    },
    "0x5009h": {
        "codigo": "0x5009h",
        "alias": "AP028",
        "nombre": "División entera silenciosa asignada a flotante",
        "mensaje": "División entre operandos enteros asignada a variable float o double.",
        "explicacion": "La división 'a / b' trunca a la parte entera antes de promover al tipo flotante, perdiendo los decimales inadvertidamente.",
        "sugerencia": "Casteá explícitamente uno de los operandos: '(float)a / b' o usá un literal flotante '1.0 / 2'.",
        "ejemplo_incorrecto": "float tasa = 1 / 2; // resulta en 0.0f",
        "ejemplo_correcto": "float tasa = 1.0f / 2.0f; // resulta en 0.5f",
    },
    "0x1010h": {
        "codigo": "0x1010h",
        "alias": "AP029",
        "nombre": "Precedencia errónea entre asignación y comparación",
        "mensaje": "Asignación sin paréntesis en condición 'if (p = fn() == NULL)'.",
        "explicacion": "El operador de comparación '==' tiene mayor precedencia que '='. La variable 'p' recibirá el resultado booleano (0 o 1) en lugar del retorno de la función.",
        "sugerencia": "Encerrá la asignación entre paréntesis: 'if ((p = fn()) == NULL)'.",
        "ejemplo_incorrecto": "if (p = malloc(10) == NULL) { ... }",
        "ejemplo_correcto": "if ((p = malloc(10)) == NULL) { ... }",
    },
    "0x0004b": {
        "codigo": "0x0004b",
        "alias": "AP030",
        "nombre": "Lectura de variable local no inicializada",
        "mensaje": "Variable local utilizada en una expresión antes de haber sido inicializada o asignada.",
        "explicacion": "Las variables locales en la pila no se inicializan a cero automáticamente y contienen basura previa de memoria.",
        "sugerencia": "Inicializá la variable al declararla (ej. 'int contador = 0;').",
        "ejemplo_incorrecto": "int acumulador;\nacumulador += valor;",
        "ejemplo_correcto": "int acumulador = 0;\nacumulador += valor;",
    },
    "0x1011h": {
        "codigo": "0x1011h",
        "alias": "AP031",
        "nombre": "Comparación de igualdad estricta en punto flotante",
        "mensaje": "Comparación con '==' o '!=' sobre variables float o double.",
        "explicacion": "Por la representación IEEE-754 de precisión finita, los números flotantes rara vez coinciden de forma exacta.",
        "sugerencia": "Compará con una tolerancia épsilon: 'fabs(a - b) < 0.00001'.",
        "ejemplo_incorrecto": "if (f == 0.0f) { ... }",
        "ejemplo_correcto": "if (fabs(f) < 1e-6) { ... }",
    },
    "0x4009h": {
        "codigo": "0x4009h",
        "alias": "AP032",
        "nombre": "Retorno prematuro con fuga de recursos de archivo",
        "mensaje": "Sentencia 'return' que sale de la función sin cerrar el archivo abierto con fopen().",
        "explicacion": "Abandonar la función sin invocar fclose() deja el descriptor de archivo abierto consumiendo recursos del sistema operativo.",
        "sugerencia": "Asegurate de llamar a 'fclose(f);' antes de cada rama de salida o return.",
        "ejemplo_incorrecto": "FILE *f = fopen(\"data.txt\", \"r\");\nif (!f) return -1;\nif (error) return -2; // Fuga: f no se cierra\nfclose(f);",
        "ejemplo_correcto": "if (error) { fclose(f); return -2; }",
    },
    "0x2011h": {
        "codigo": "0x2011h",
        "alias": "AP033",
        "nombre": "Recursión mutua o cíclica sin caso base",
        "mensaje": "Funciones que se llaman recursivamente de forma cruzada sin condición de corte evidente.",
        "explicacion": "La recursión mutua sin caso base explícito causa agotamiento de la pila (Stack Overflow) rápidamente.",
        "sugerencia": "Establecé una condición de parada clara al inicio de cada función del ciclo.",
        "ejemplo_incorrecto": "void fa(int n) { fb(n); }\nvoid fb(int n) { fa(n); }",
        "ejemplo_correcto": "void fa(int n) { if (n <= 0) return; fb(n - 1); }",
    },
    "0x0039h": {
        "codigo": "0x0039h",
        "alias": "AP034",
        "nombre": "Macro que ofusca sintaxis fundamental de C",
        "mensaje": "Macro #define que reemplaza palabras clave nativas o llaves de bloque (ej. BEGIN, END, AND).",
        "explicacion": "Ofuscar la sintaxis de C con macros personalizadas dificulta la lectura universal y perjudica el aprendizaje idiomático.",
        "sugerencia": "Usá la sintaxis estándar de C sin envolver llaves ni operadores en macros.",
        "ejemplo_incorrecto": "#define BEGIN {\n#define END }",
        "ejemplo_correcto": "// Usar bloques estándar { }",
    },
    "0x2012h": {
        "codigo": "0x2012h",
        "alias": "AP035",
        "nombre": "Comparador de qsort con resta directa sujeta a overflow",
        "mensaje": "Función de comparación para qsort/bsearch que resta enteros directamente 'return *a - *b;'.",
        "explicacion": "Si los números tienen signos opuestos y valores extremos (ej. INT_MAX y INT_MIN), la resta produce integer overflow y altera el orden.",
        "sugerencia": "Utilizá comparaciones explícitas: 'if (*a > *b) return 1; if (*a < *b) return -1; return 0;'.",
        "ejemplo_incorrecto": "int cmp(const void *a, const void *b) {\n    return *(int*)a - *(int*)b;\n}",
        "ejemplo_correcto": "int cmp(const void *a, const void *b) {\n    int va = *(int*)a, vb = *(int*)b;\n    return (va > vb) - (va < vb);\n}",
    },
    "0x301Ah": {
        "codigo": "0x301Ah",
        "alias": "AP036",
        "nombre": "Tamaño insuficiente en memset con sizeof(ptr)",
        "mensaje": "Llamada a memset usando sizeof(ptr) donde ptr es un puntero a bloque dinámico.",
        "explicacion": "Usar sizeof(ptr) solo limpia el tamaño del puntero (4 u 8 bytes) dejando el resto de la estructura o buffer sin inicializar.",
        "sugerencia": "Usá 'sizeof(*ptr)' o el tamaño real del búfer.",
        "ejemplo_incorrecto": "struct nodo_t *n = malloc(sizeof(*n));\nmemset(n, 0, sizeof(n));",
        "ejemplo_correcto": "memset(n, 0, sizeof(*n));",
    },
    "0x301Bh": {
        "codigo": "0x301Bh",
        "alias": "AP037",
        "nombre": "Desreferencia inmediata tras realloc",
        "mensaje": "Acceso a la memoria apuntada por el retorno de realloc() sin verificar si retornó NULL.",
        "explicacion": "Si el sistema no puede reubicar o expandir el bloque, realloc devuelve NULL y el acceso inmediato causará SIGSEGV.",
        "sugerencia": "Validá siempre 'if (ptr == NULL)' antes de usar el puntero reubicado.",
        "ejemplo_incorrecto": "ptr = realloc(ptr, nuevo_tam);\nptr[0] = 42; // Riesgo de segfault",
        "ejemplo_correcto": "void *tmp = realloc(ptr, nuevo_tam);\nif (!tmp) return NULL;\nptr = tmp;\nptr[0] = 42;",
    },
    "0x301Ch": {
        "codigo": "0x301Ch",
        "alias": "AP038",
        "nombre": "Casteo redundante en invocación de free()",
        "mensaje": "Castear el puntero en la llamada a 'free()' (ej. free((void*)p) o free((char*)p)) es innecesario en C.",
        "explicacion": "'free()' recibe 'void*', por lo que cualquier tipo de puntero se convierte implícitamente sin necesidad de cast.",
        "sugerencia": "Invocá 'free(p);' directamente sin casteo de tipo.",
        "ejemplo_incorrecto": "free((void *)ptr);",
        "ejemplo_correcto": "free(ptr);",
    },
    "0x1014h": {
        "codigo": "0x1014h",
        "alias": "AP039",
        "nombre": "Invocación a strlen() en condición de parada de bucle for",
        "mensaje": "Llamada a 'strlen()' dentro de la condición del bucle for reevalúa la longitud en cada iteración.",
        "explicacion": "Llamar a strlen() repetidamente en el bucle degrada la complejidad computacional a O(n^2).",
        "sugerencia": "Guardá la longitud en una variable previa: 'size_t len = strlen(s); for (size_t i = 0; i < len; i++)'.",
        "ejemplo_incorrecto": "for (size_t i = 0; i < strlen(s); i++) { ... }",
        "ejemplo_correcto": "size_t len = strlen(s);\nfor (size_t i = 0; i < len; i++) { ... }",
    },
    "0x1015h": {
        "codigo": "0x1015h",
        "alias": "AP040",
        "nombre": "Modificación de variable de control dentro del cuerpo del for",
        "mensaje": "La variable de control de la iteración 'for' se modifica dentro del cuerpo del bucle.",
        "explicacion": "Alterar la variable de control dentro del cuerpo oculta el paso del bucle y dificulta el razonamiento estructurado.",
        "sugerencia": "Si la lógica de avance no es regular o depende de condiciones dinámicas, utilizá un bucle 'while'.",
        "ejemplo_incorrecto": "for (int i = 0; i < n; i++) {\n    if (cond) i += 2;\n}",
        "ejemplo_correcto": "int i = 0;\nwhile (i < n) {\n    if (cond) i += 2;\n    else i++;\n}",
    },
    "0x301Dh": {
        "codigo": "0x301Dh",
        "alias": "AP041",
        "nombre": "Comparación sintáctica errónea de puntero con carácter nulo '\\0'",
        "mensaje": "Se comparó el puntero de cadena directamente contra '\\0' (ej. 'str == '\\0'') en lugar de desreferenciar.",
        "explicacion": "'str == '\\0'' compara la dirección del puntero con 0 (equivalente a str == NULL). Para verificar el carácter terminador debe usarse '*str == '\\0''.",
        "sugerencia": "Desreferenciá el puntero: '*str == '\\0'' o 'str[0] == '\\0''.",
        "ejemplo_incorrecto": "if (str == '\\0') { ... }",
        "ejemplo_correcto": "if (*str == '\\0') { ... }",
    },
    "0x301Eh": {
        "codigo": "0x301Eh",
        "alias": "AP042",
        "nombre": "Reserva de buffer con malloc(strlen(s)) sin espacio para byte nulo",
        "mensaje": "Reserva de memoria con 'malloc(strlen(s))' omite el byte adicional para el terminador '\\0'.",
        "explicacion": "strlen() cuenta solo los caracteres visibles. Copiar la cadena en un bloque de strlen(s) bytes provoca un buffer overflow de un byte (off-by-one).",
        "sugerencia": "Sumá 1 byte al tamaño asignado: 'malloc(strlen(s) + 1)'.",
        "ejemplo_incorrecto": "char *dup = malloc(strlen(s));",
        "ejemplo_correcto": "char *dup = malloc(strlen(s) + 1);",
    },
    "0x1016h": {
        "codigo": "0x1016h",
        "alias": "AP043",
        "nombre": "Uso de operador bit a bit (&, |) en condición lógica en lugar de booleano (&&, ||)",
        "mensaje": "Uso de operador a nivel de bits '&' o '|' en condición de control en lugar de operador lógico.",
        "explicacion": "Los operadores bit a bit no realizan evaluación en cortocircuito y pueden provocar desreferencias nulas o efectos colaterales no deseados.",
        "sugerencia": "Utilizá los operadores lógicos '&&' o '||' con evaluación cortocircuitada.",
        "ejemplo_incorrecto": "if (a > 0 & b > 0) { ... }",
        "ejemplo_correcto": "if (a > 0 && b > 0) { ... }",
    },
    "0x1017h": {
        "codigo": "0x1017h",
        "alias": "AP044",
        "nombre": "Ramas idénticas duplicadas en bifurcación if-else",
        "mensaje": "Las ramas 'then' y 'else' del condicional contienen exactamente el mismo bloque de código.",
        "explicacion": "Tener bloques idénticos en ambas ramas invalida el propósito de la bifurcación condicional o denota un error tipográfico en una de las ramas.",
        "sugerencia": "Eliminá la estructura condicional si el comportamiento es uniforme o corregí la rama divergente.",
        "ejemplo_incorrecto": "if (x > 0) { total += x; } else { total += x; }",
        "ejemplo_correcto": "total += x;",
    },
    "0x1018h": {
        "codigo": "0x1018h",
        "alias": "AP045",
        "nombre": "Ambigüedad sintáctica por omisión de llaves en condicional anidado (Dangling Else)",
        "mensaje": "Sentencia 'if' anidada sin llaves delimitadoras con cláusula 'else' ambigua.",
        "explicacion": "El compilador asocia siempre 'else' con el 'if' más próximo, lo cual difiere frecuentemente de la intención del programador cuando se omiten las llaves.",
        "sugerencia": "Encapsulá siempre los bloques de cada nivel condicional con llaves '{ }'.",
        "ejemplo_incorrecto": "if (a) if (b) foo(); else bar();",
        "ejemplo_correcto": "if (a) {\n    if (b) {\n        foo();\n    }\n} else {\n    bar();\n}",
    },
    "0x301Fh": {
        "codigo": "0x301Fh",
        "alias": "AP046",
        "nombre": "Asignación de retorno de malloc() a variable no puntero",
        "mensaje": "La dirección de memoria retornada por 'malloc()' se asignó a una variable de tipo entero nativo.",
        "explicacion": "Los punteros en arquitecturas modernas tienen 64 bits de ancho. Asignarlos a un entero nativo trunca la dirección y corrompe el puntero.",
        "sugerencia": "Declará la variable como puntero ('tipo *ptr = malloc(...)').",
        "ejemplo_incorrecto": "int addr = malloc(sizeof(int));",
        "ejemplo_correcto": "int *ptr = malloc(sizeof(int));",
    },
    "0x3020h": {
        "codigo": "0x3020h",
        "alias": "AP047",
        "nombre": "Casteo forzado entre punteros de tipos incompatibles (Violación de Strict Aliasing)",
        "mensaje": "Casteo directo entre punteros a tipos incompatibles (ej. float* a int* o struct dispar).",
        "explicacion": "Desreferenciar punteros a tipos incompatibles viola la regla de strict aliasing del estándar ISO C y causa comportamientos indefinidos al optimizar.",
        "sugerencia": "Utilizá 'memcpy()' o un tipo agregador 'union' para puntear bits (type punning) conforme al estándar.",
        "ejemplo_incorrecto": "float f = 1.0f;\nint *pi = (int *)&f;",
        "ejemplo_correcto": "float f = 1.0f;\nint i;\nmemcpy(&i, &f, sizeof(i));",
    },
    "0x1019h": {
        "codigo": "0x1019h",
        "alias": "AP048",
        "nombre": "Uso de salto goto hacia atrás vulnerando programación estructurada",
        "mensaje": "Salto 'goto' hacia atrás hacia una etiqueta anterior simulando un lazo desestructurado.",
        "explicacion": "Los saltos hacia atrás quiebran los axiomas de Dijkstra de la programación estructurada y generan código espagueti.",
        "sugerencia": "Reemplazá el salto hacia atrás por una estructura de repetición canónica ('while', 'for').",
        "ejemplo_incorrecto": "repetir:\n    // ...\n    goto repetir;",
        "ejemplo_correcto": "while (cond) {\n    // ...\n}",
    },
}

ALIAS_MAP: Dict[str, str] = {
    "AP001": "0x300Ah",
    "AP002": "0x4002h",
    "AP003": "0x3002h",
    "AP004": "0x3008h",
    "AP005": "0x1005h",
    "AP006": "0x1001h",
    "AP007": "0x4006h",
    "AP008": "0x300Fh",
    "AP009": "0x100Dh",
    "AP010": "0x3001h",
    "AP011": "0x3002b",
    "AP012": "0x2007h",
    "AP013": "0x5004h",
    "AP014": "0x300Dh",
    "AP015": "0x200Bh",
    "AP016": "0x100Ah",
    "AP017": "0x500Ah",
    "AP018": "0x2009h",
    "AP019": "0x5008h",
    "AP020": "0x5004b",
    "AP021": "0x100Ch",
    "AP022": "0x0003b",
    "AP023": "0x100Eh",
    "AP024": "0x3015h",
    "AP025": "0x4008h",
    "AP026": "0x3019h",
    "AP027": "0x100Fh",
    "AP028": "0x5009h",
    "AP029": "0x1010h",
    "AP030": "0x0004b",
    "AP031": "0x1011h",
    "AP032": "0x4009h",
    "AP033": "0x2011h",
    "AP034": "0x0039h",
    "AP035": "0x2012h",
    "AP036": "0x301Ah",
    "AP037": "0x301Bh",
    "AP038": "0x301Ch",
    "AP039": "0x1014h",
    "AP040": "0x1015h",
    "AP041": "0x301Dh",
    "AP042": "0x301Eh",
    "AP043": "0x1016h",
    "AP044": "0x1017h",
    "AP045": "0x1018h",
    "AP046": "0x301Fh",
    "AP047": "0x3020h",
    "AP048": "0x1019h",
}

for k, v in ALIAS_MAP.items():
    if v in CATALOGO_ANTIPATRONES:
        CATALOGO_ANTIPATRONES[k] = CATALOGO_ANTIPATRONES[v]

# Codificación canónica SP0x... para explicación exhaustiva
for k, v in list(CATALOGO_ANTIPATRONES.items()):
    if k.startswith("0x"):
        sp_k = f"SP{k}"
        v["sp_codigo"] = sp_k
        ALIAS_MAP[sp_k] = k
        CATALOGO_ANTIPATRONES[sp_k] = v


def _find_identifier(node: Node) -> Optional[str]:
    if node.type in ("identifier", "type_identifier", "field_identifier"):
        return node.text.decode("utf-8", errors="replace")
    for child in node.children:
        res = _find_identifier(child)
        if res:
            return res
    return None


def _make_antipatron(cod_key: str, archivo: Path, linea: int, columna: int, linea_cod: str, detalle_msg: Optional[str] = None) -> AntipatronDetectado:
    info = CATALOGO_ANTIPATRONES[cod_key]
    alias_val = info.get("alias", "")
    sp_val = info.get("sp_codigo", f"SP{info['codigo']}" if info.get("codigo", "").startswith("0x") else "")
    return AntipatronDetectado(
        codigo=RuleCode(info["codigo"], alias_val, sp_val),
        nombre=info["nombre"],
        archivo=archivo,
        linea=linea,
        columna=columna,
        mensaje=detalle_msg or info["mensaje"],
        explicacion=info["explicacion"],
        sugerencia=info["sugerencia"],
        codigo_linea=linea_cod,
        ejemplo_incorrecto=info.get("ejemplo_incorrecto", ""),
        ejemplo_correcto=info.get("ejemplo_correcto", ""),
    )



def auditar_archivo(archivo: Path) -> List[AntipatronDetectado]:
    """Analiza un archivo C y detecta los 20+ antipatrones didácticos usando Tree-Sitter AST."""
    archivo = Path(archivo)
    if not archivo.is_file():
        return []

    try:
        contenido = archivo.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    lineas = contenido.splitlines()
    source_bytes = contenido.encode("utf-8")
    parser = get_c_parser()
    tree = parser.parse(source_bytes)

    antipatrones: List[AntipatronDetectado] = []

    # Auditoría complementaria de macros que ofuscan sintaxis (AP034)
    re_macro_ofuscada = re.compile(r"^[ \t]*#\s*define\s+([a-zA-Z_]\w*)[ \t]+([^\n\r]+)", re.MULTILINE)
    for m in re_macro_ofuscada.finditer(contenido):
        m_name = m.group(1)
        m_body = m.group(2).strip()
        if m_name in ("BEGIN", "END", "AND", "OR", "THEN") or m_body in ("{", "}", "&&", "||"):
            line_no = contenido[:m.start()].count("\n") + 1
            antipatrones.append(_make_antipatron(
                "0x0039h",
                archivo,
                line_no,
                1,
                lineas[line_no - 1] if line_no <= len(lineas) else "",
                f"Macro '{m_name}' enmascara sintaxis nativa de C.",
            ))

    # Auditoría complementaria de macros de preprocesador (AP017)
    re_macro_multi = re.compile(r"^[ \t]*#\s*define\s+([a-zA-Z_]\w*)\s*\(([^)]+)\)\s*(.+)$", re.MULTILINE)
    for m in re_macro_multi.finditer(contenido):
        m_name = m.group(1)
        params = [p.strip() for p in m.group(2).split(",") if p.strip()]
        body = m.group(3)
        for p in params:
            # Buscar ocurrencias del parámetro en el cuerpo
            occ = len(re.findall(rf"\b{re.escape(p)}\b", body))
            if occ >= 2:
                line_no = contenido[:m.start()].count("\n") + 1
                antipatrones.append(_make_antipatron(
                    "0x500Ah",
                    archivo,
                    line_no,
                    1,
                    lineas[line_no - 1] if line_no <= len(lineas) else "",
                    f"Macro '{m_name}' evalúa el parámetro '{p}' {occ} veces en su cuerpo.",
                ))
                break

    # Recolección previa de etiquetas para detección de backward goto (AP048)
    etiquetas_lineas: Dict[str, int] = {}
    def _collect_labels(n: Node) -> None:
        if n.type == "labeled_statement":
            lbl_n = n.child_by_field_name("label") or next((c for c in n.children if c.type == "statement_identifier"), None)
            if lbl_n:
                etiquetas_lineas[lbl_n.text.decode("utf-8", "replace")] = n.start_point.row + 1
        for ch in n.children:
            _collect_labels(ch)

    _collect_labels(tree.root_node)

    # Recolección previa de tipos para detección de strict aliasing (AP047) y no-punteros (AP046)
    var_types: Dict[str, str] = {}
    def _collect_var_types(n: Node) -> None:
        if n.type == "declaration":
            t_n = n.child_by_field_name("type")
            t_text = t_n.text.decode("utf-8", "replace") if t_n else ""
            for ch in n.children:
                if ch.type == "init_declarator":
                    d_c = ch.child_by_field_name("declarator")
                    if d_c:
                        is_ptr = d_c.type == "pointer_declarator"
                        v_id = _find_identifier(d_c)
                        if v_id:
                            var_types[v_id] = f"{t_text}*" if is_ptr else t_text
                elif ch.type == "identifier":
                    var_types[ch.text.decode("utf-8", "replace")] = t_text
        for ch in n.children:
            _collect_var_types(ch)

    _collect_var_types(tree.root_node)

    def _traverse(node: Node) -> None:
        idx = node.start_point.row + 1
        col = node.start_point.column + 1
        linea_cod = lineas[node.start_point.row] if node.start_point.row < len(lineas) else ""

        # AP001 (0x300Ah) & AP047 (0x3020h): Casteos
        if node.type == "cast_expression":
            val_node = node.child_by_field_name("value")
            if val_node and val_node.type == "call_expression":
                fn_node = val_node.child_by_field_name("function")
                if fn_node and _find_identifier(fn_node) in ("malloc", "calloc"):
                    antipatrones.append(_make_antipatron("0x300Ah", archivo, idx, col, linea_cod))

            # AP047 (0x3020h): Violación de Strict Aliasing (ej. (int *)&float_var)
            type_n = node.child_by_field_name("type")
            if type_n and val_node and val_node.type == "pointer_expression":
                cast_type_txt = type_n.text.decode("utf-8", errors="replace").replace(" ", "").replace("*", "")
                val_id = _find_identifier(val_node)
                if val_id and val_id in var_types:
                    orig_type = var_types[val_id].replace(" ", "").replace("*", "")
                    incompatibles = {
                        ("int", "float"), ("float", "int"),
                        ("int", "double"), ("double", "int"),
                        ("long", "float"), ("float", "long"),
                        ("long", "double"), ("double", "long"),
                    }
                    t_desc = type_n.text.decode("utf-8", errors="replace")
                    if (cast_type_txt, orig_type) in incompatibles:
                        antipatrones.append(_make_antipatron(
                            "0x3020h",
                            archivo,
                            idx,
                            col,
                            linea_cod,
                            f"Casteo forzado entre punteros incompatibles '({t_desc})&{val_id}' (violación de strict aliasing).",
                        ))

        # AP048 (0x1019h): Salto goto hacia atrás (desestructurado)
        elif node.type == "goto_statement":
            lbl_n = node.child_by_field_name("label") or next((c for c in node.children if c.type == "statement_identifier"), None)
            if lbl_n:
                lbl_name = lbl_n.text.decode("utf-8", errors="replace")
                if lbl_name in etiquetas_lineas and etiquetas_lineas[lbl_name] <= idx:
                    antipatrones.append(_make_antipatron(
                        "0x1019h",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        f"Salto 'goto {lbl_name}' hacia atrás en la línea {etiquetas_lineas[lbl_name]} simulando un lazo desestructurado.",
                    ))

        # AP002 (0x4002h) & AP006 (0x1001h) & AP043 (0x1016h): while statements
        elif node.type == "while_statement":
            cond_node = node.child_by_field_name("condition")
            body_node = node.child_by_field_name("body")
            if body_node and body_node.type == "expression_statement" and body_node.text.decode("utf-8").strip() == ";":
                antipatrones.append(_make_antipatron(
                    "0x1001h",
                    archivo,
                    idx,
                    col,
                    linea_cod,
                    "Punto y coma accidental tras la condición del while (cuerpo vacío).",
                ))
            if cond_node:
                raw_cond = cond_node.text.decode("utf-8", errors="replace")
                if "feof" in raw_cond and "!" in raw_cond:
                    antipatrones.append(_make_antipatron("0x4002h", archivo, idx, col, linea_cod))

                # AP043: Operador bit a bit & o | en condición lógica
                def _has_bitwise_while(n: Node) -> bool:
                    if n.type == "binary_expression":
                        op = next((c.text.decode("utf-8") for c in n.children if c.type in ("&", "|")), None)
                        if op:
                            curr = n.parent
                            in_cmp = False
                            while curr and curr != cond_node.parent:
                                if curr.type == "binary_expression":
                                    c_op = next((c.text.decode("utf-8") for c in curr.children if c.type in ("==", "!=", "<", ">", "<=", ">=")), None)
                                    if c_op:
                                        in_cmp = True
                                        break
                                curr = curr.parent
                            if not in_cmp:
                                return True
                    for ch in n.children:
                        if _has_bitwise_while(ch):
                            return True
                    return False

                if _has_bitwise_while(cond_node):
                    antipatrones.append(_make_antipatron(
                        "0x1016h",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        "Uso de operador a nivel de bits ('&' o '|') en condición lógica en lugar de operador booleano.",
                    ))

        # AP003 (0x3002h): Retorno de puntero a variable local
        elif node.type == "return_statement":
            raw_ret = node.text.decode("utf-8", errors="replace")
            if "&" in raw_ret:
                m = re.search(r"&\s*([a-zA-Z_][a-zA-Z0-9_]*)", raw_ret)
                var_name = m.group(1) if m else "var"
                antipatrones.append(_make_antipatron(
                    "0x3002h",
                    archivo,
                    idx,
                    col,
                    linea_cod,
                    f"Retorno de dirección de variable local '&{var_name}'.",
                ))

        # AP004, AP005, AP016, AP014, AP023, AP006, AP043, AP044, AP045: if statements
        elif node.type == "if_statement":
            cond_node = node.child_by_field_name("condition")
            body_node = node.child_by_field_name("consequence")
            alt_node = node.child_by_field_name("alternative")

            # AP006: Punto y coma accidental tras condición
            if body_node and body_node.type == "expression_statement" and body_node.text.decode("utf-8").strip() == ";":
                antipatrones.append(_make_antipatron(
                    "0x1001h",
                    archivo,
                    idx,
                    col,
                    linea_cod,
                    "Punto y coma accidental tras la condición del if (cuerpo vacío).",
                ))

            # AP044 (0x1017h): Ramas then y else idénticas
            if body_node and alt_node:
                else_stmt = next((c for c in alt_node.children if c.type != "else"), None)
                if else_stmt and body_node.text.decode("utf-8").strip() == else_stmt.text.decode("utf-8").strip():
                    antipatrones.append(_make_antipatron(
                        "0x1017h",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        "Las ramas 'then' y 'else' de la estructura condicional son idénticas.",
                    ))

            # AP045 (0x1018h): Dangling else por omitir llaves en if anidado
            if body_node and body_node.type == "if_statement":
                inner_has_else = body_node.child_by_field_name("alternative") is not None
                outer_has_else = alt_node is not None
                if inner_has_else or outer_has_else:
                    antipatrones.append(_make_antipatron(
                        "0x1018h",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        "Sentencia 'if' anidada sin llaves delimitadoras con cláusula 'else' ambigua (dangling else).",
                    ))

            if cond_node and body_node:
                cond_text = cond_node.text.decode("utf-8", errors="replace")
                body_text = body_node.text.decode("utf-8", errors="replace")

                # AP004: if (ptr != NULL) free(ptr);
                if ("!= NULL" in cond_text or "!= 0" in cond_text) and "free(" in body_text:
                    antipatrones.append(_make_antipatron("0x3008h", archivo, idx, col, linea_cod))

            if cond_node:
                cond_text = cond_node.text.decode("utf-8", errors="replace")
                # AP005: if (cond == true) o if (cond == 1)
                if "== true" in cond_text or "== 1" in cond_text or "== TRUE" in cond_text:
                    antipatrones.append(_make_antipatron("0x1005h", archivo, idx, col, linea_cod))

                # AP043: Operador bit a bit & o | en condición lógica
                def _has_bitwise_if(n: Node) -> bool:
                    if n.type == "binary_expression":
                        op = next((c.text.decode("utf-8") for c in n.children if c.type in ("&", "|")), None)
                        if op:
                            curr = n.parent
                            in_cmp = False
                            while curr and curr != cond_node.parent:
                                if curr.type == "binary_expression":
                                    c_op = next((c.text.decode("utf-8") for c in curr.children if c.type in ("==", "!=", "<", ">", "<=", ">=")), None)
                                    if c_op:
                                        in_cmp = True
                                        break
                                curr = curr.parent
                            if not in_cmp:
                                return True
                    for ch in n.children:
                        if _has_bitwise_if(ch):
                            return True
                    return False

                if _has_bitwise_if(cond_node):
                    antipatrones.append(_make_antipatron(
                        "0x1016h",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        "Uso de operador a nivel de bits ('&' o '|') en condición lógica en lugar de operador booleano.",
                    ))

                # AP016: if (x = 5) - asignación en condicional
                for child in cond_node.children:
                    if child.type == "assignment_expression":
                        antipatrones.append(_make_antipatron(
                            "0x100Ah",
                            archivo,
                            idx,
                            col,
                            linea_cod,
                            f"Asignación accidental en condición lógica '{child.text.decode("utf-8", errors="replace")}'.",
                        ))
                    elif child.type == "parenthesized_expression":
                        for sub in child.children:
                            if sub.type == "assignment_expression":
                                antipatrones.append(_make_antipatron(
                                    "0x100Ah",
                                    archivo,
                                    idx,
                                    col,
                                    linea_cod,
                                    f"Asignación accidental en condición lógica '{sub.text.decode("utf-8", errors="replace")}'.",
                                ))

                # AP014: Número mágico en condición
                for child in cond_node.children:
                    if child.type == "binary_expression":
                        for operand in child.children:
                            if operand.type == "number_literal":
                                num_str = operand.text.decode("utf-8", errors="replace")
                                if num_str not in ("0", "1", "2", "-1", "0.0", "1.0"):
                                    antipatrones.append(_make_antipatron(
                                        "0x300Dh",
                                        archivo,
                                        idx,
                                        col,
                                        linea_cod,
                                        f"Número mágico '{num_str}' utilizado directamente en condición lógica.",
                                    ))

                # AP023: Expresión tautológica (x && !x, x || !x, x || true)
                if re.search(r"\b([a-zA-Z_]\w*)\s*&&\s*!\s*\1\b|\b([a-zA-Z_]\w*)\s*\|\|\s*!\s*\2\b|\|\|\s*true\b|&&\s*false\b", cond_text, re.IGNORECASE):
                    antipatrones.append(_make_antipatron("0x100Eh", archivo, idx, col, linea_cod))

        # AP009 (0x100Dh) & AP027 (0x100Fh) & AP006 (0x1001h) & AP039 (0x1014h) & AP040 (0x1015h): for statements
        elif node.type == "for_statement":
            body_node = node.child_by_field_name("body")
            # AP006: Punto y coma accidental tras for (cuerpo vacío)
            if body_node and body_node.type == "expression_statement" and body_node.text.decode("utf-8").strip() == ";":
                antipatrones.append(_make_antipatron(
                    "0x1001h",
                    archivo,
                    idx,
                    col,
                    linea_cod,
                    "Punto y coma accidental tras la condición del for (cuerpo vacío).",
                ))

            # AP039: Invocación a strlen() en condición de parada
            cond_node = node.child_by_field_name("condition")
            if cond_node and re.search(r"\bstrlen\s*\(", cond_node.text.decode("utf-8", errors="replace")):
                antipatrones.append(_make_antipatron(
                    "0x1014h",
                    archivo,
                    idx,
                    col,
                    linea_cod,
                    "Invocación a 'strlen()' dentro de la condición de parada del bucle for (complejidad O(n^2)).",
                ))

            # AP040: Modificación de variable de control dentro del cuerpo
            ctrl_var = None
            init_node = node.child_by_field_name("initializer")
            if init_node:
                init_text = init_node.text.decode("utf-8", errors="replace")
                if re.match(r"^\s*(?:float|double)\b", init_text):
                    antipatrones.append(_make_antipatron(
                        "0x100Dh",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        f"Contador de bucle de tipo coma flotante '{init_text}'.",
                    ))
                for c in init_node.children:
                    if c.type == "init_declarator":
                        d_id = c.child_by_field_name("declarator")
                        ctrl_var = _find_identifier(d_id or c)
                        break
                    elif c.type == "assignment_expression":
                        l_id = c.child_by_field_name("left")
                        ctrl_var = _find_identifier(l_id or c)
                        break

            if not ctrl_var:
                upd_node = node.child_by_field_name("update")
                if upd_node:
                    ctrl_var = _find_identifier(upd_node)

            if ctrl_var and body_node:
                def _check_ctrl_mod(n: Node) -> bool:
                    if n.type in ("for_statement", "function_definition"):
                        return False
                    if n.type == "assignment_expression":
                        l_id = n.child_by_field_name("left")
                        if l_id and _find_identifier(l_id) == ctrl_var:
                            return True
                    elif n.type == "update_expression":
                        if _find_identifier(n) == ctrl_var:
                            return True
                    for ch in n.children:
                        if _check_ctrl_mod(ch):
                            return True
                    return False

                if _check_ctrl_mod(body_node):
                    antipatrones.append(_make_antipatron(
                        "0x1015h",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        f"Variable de control '{ctrl_var}' modificada dentro del cuerpo del bucle for.",
                    ))

            # AP027: off-by-one en bucle for
            for_text = node.text.decode("utf-8", errors="replace")
            m_off = re.search(r"<=\s*(\d+)", for_text)
            if m_off:
                limit_num = m_off.group(1)
                curr = node.parent
                while curr and curr.type != "function_definition":
                    curr = curr.parent
                if curr:
                    f_text = curr.text.decode("utf-8", errors="replace")
                    if f"[{limit_num}]" in f_text:
                        antipatrones.append(_make_antipatron(
                            "0x100Fh",
                            archivo,
                            idx,
                            col,
                            linea_cod,
                            f"Posible error off-by-one: condición de parada '<= {limit_num}' excede los límites del arreglo.",
                        ))

        # AP020 (0x5004h) & AP031 (0x1011h) & AP026 (0x3019h): binary expressions
        elif node.type == "binary_expression":
            bin_text = node.text.decode("utf-8", errors="replace")
            bin_op = next((c.text.decode("utf-8") for c in node.children if c.type in ("==", "!=")), "")
            if bin_op:
                left_n = node.child_by_field_name("left")
                right_n = node.child_by_field_name("right")
                if (left_n and left_n.type == "string_literal") or (right_n and right_n.type == "string_literal"):
                    antipatrones.append(_make_antipatron(
                        "0x5004b",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        f"Comparación de cadenas con operador relacional '{bin_text}'.",
                    ))
                # AP031: igualdad estricta con float
                if re.search(r"\b\d+\.\d+f?\b", bin_text):
                    antipatrones.append(_make_antipatron(
                        "0x1011h",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        "Comparación de igualdad estricta ('==') sobre tipo de coma flotante.",
                    ))

                # AP041 (0x301Dh): Comparación sintáctica de puntero con carácter nulo '\0'
                def _is_null_char(n: Optional[Node]) -> bool:
                    if not n or n.type != "char_literal":
                        return False
                    txt = n.text.decode("utf-8", "replace").strip("'")
                    return txt in ("\\0", "")

                if _is_null_char(left_n) and right_n and right_n.type == "identifier":
                    antipatrones.append(_make_antipatron(
                        "0x301Dh",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        f"Comparación sintáctica errónea de puntero '{right_n.text.decode('utf-8', 'replace')}' con '\\0' en lugar de desreferenciar.",
                    ))
                elif _is_null_char(right_n) and left_n and left_n.type == "identifier":
                    antipatrones.append(_make_antipatron(
                        "0x301Dh",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        f"Comparación sintáctica errónea de puntero '{left_n.text.decode('utf-8', 'replace')}' con '\\0' en lugar de desreferenciar.",
                    ))

            # AP026: pointer decay sizeof
            if "/" in bin_text and "sizeof" in bin_text:
                m_decay = re.search(r"sizeof\s*\(\s*([a-zA-Z_]\w*)\s*\)\s*/\s*sizeof", bin_text)
                if m_decay:
                    p_name = m_decay.group(1)
                    curr = node.parent
                    while curr and curr.type != "function_definition":
                        curr = curr.parent
                    if curr:
                        decl_node = curr.child_by_field_name("declarator")
                        if decl_node and p_name in decl_node.text.decode("utf-8"):
                            antipatrones.append(_make_antipatron(
                                "0x3019h",
                                archivo,
                                idx,
                                col,
                                linea_cod,
                                f"Pointer decay al usar sizeof sobre el parámetro '{p_name}'.",
                            ))

        # AP007, AP008, AP013, AP019, AP025, AP036: llamadas a función
        elif node.type == "call_expression":
            fn_node = node.child_by_field_name("function")
            fn_name = _find_identifier(fn_node) if fn_node else None
            args_node = next((c for c in node.children if c.type == "argument_list"), None)
            raw_args = args_node.text.decode("utf-8", errors="replace") if args_node else ""

            # AP019: gets()
            if fn_name == "gets":
                antipatrones.append(_make_antipatron(
                    "0x5008h",
                    archivo,
                    idx,
                    col,
                    linea_cod,
                    "Invocación de la función prohibida 'gets()'.",
                ))

            # AP025: printf / sprintf formato mismatch
            if fn_name in ("printf", "sprintf"):
                if re.search(r'"[^"]*%d[^"]*"\s*,\s*\d+\.\d+', raw_args) or re.search(r'"[^"]*%s[^"]*"\s*,\s*\d+\b', raw_args):
                    antipatrones.append(_make_antipatron(
                        "0x4008h",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        "Desajuste entre el especificador de formato y el tipo de dato del argumento.",
                    ))

            # AP013: strcpy, strcat, sprintf
            elif fn_name in ("strcpy", "strcat", "sprintf"):
                antipatrones.append(_make_antipatron(
                    "0x5004h",
                    archivo,
                    idx,
                    col,
                    linea_cod,
                    f"Uso de función insegura '{fn_name}()' sin limitación de longitud.",
                ))

            # AP007: fflush(stdin)
            elif fn_name == "fflush" and "stdin" in raw_args:
                antipatrones.append(_make_antipatron("0x4006h", archivo, idx, col, linea_cod))

            # AP036: memset(ptr, 0, sizeof(ptr))
            elif fn_name == "memset":
                m_ms = re.search(r"\(\s*([a-zA-Z_]\w*)\s*,\s*[^,]+,\s*sizeof\s*\(\s*([a-zA-Z_]\w*)\s*\)", raw_args)
                if m_ms and m_ms.group(1) == m_ms.group(2):
                    antipatrones.append(_make_antipatron(
                        "0x301Ah",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        f"Tamaño insuficiente en memset: 'sizeof({m_ms.group(1)})' limpia solo el puntero.",
                    ))

            # AP008 & AP042 (0x301Eh): malloc/calloc
            elif fn_name in ("malloc", "calloc") and args_node:
                # AP042: malloc(strlen(s)) sin espacio para byte nulo '\0'
                if re.search(r"\bstrlen\s*\(", raw_args) and not re.search(r"\+\s*(?:1|sizeof\s*\(\s*char\s*\))", raw_args):
                    antipatrones.append(_make_antipatron(
                        "0x301Eh",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        "Reserva de memoria con 'malloc(strlen(...))' sin espacio para el byte terminador '\\0'.",
                    ))

                m_sz = re.search(r"sizeof\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)", raw_args)
                if m_sz:
                    id_name = m_sz.group(1)
                    tipos_base = {"int", "char", "float", "double", "long", "short", "size_t", "void", "uint8_t", "int32_t", "uint32_t", "int64_t", "uint64_t"}
                    if not (id_name.endswith("_t") or id_name.startswith("t_") or id_name in tipos_base):
                        antipatrones.append(_make_antipatron(
                            "0x300Fh",
                            archivo,
                            idx,
                            col,
                            linea_cod,
                            f"Uso de 'sizeof({id_name})' donde probablemente se requería 'sizeof(*{id_name})'.",
                        ))

            # AP011 & AP038 (0x301Ch): free(ptr)
            elif fn_name == "free" and args_node:
                # AP038: Casteo redundante en llamada a free()
                for arg_c in args_node.children:
                    if arg_c.type == "cast_expression":
                        antipatrones.append(_make_antipatron(
                            "0x301Ch",
                            archivo,
                            idx,
                            col,
                            linea_cod,
                            "Casteo redundante de puntero en invocación a 'free()'.",
                        ))
                        break

                arg_id = _find_identifier(args_node)
                if arg_id:
                    curr = node.parent
                    while curr and curr.type not in ("compound_statement", "function_definition"):
                        curr = curr.parent
                    if curr and curr.type == "compound_statement":
                        comp_text = curr.text.decode("utf-8", errors="replace")
                        pos_free = comp_text.find(f"free({arg_id})")
                        if pos_free != -1:
                            sub_after = comp_text[pos_free:]
                            if not re.search(rf"\b{re.escape(arg_id)}\s*=\s*NULL\b", sub_after):
                                if not re.search(r"return\b", sub_after[:80]):
                                    antipatrones.append(_make_antipatron(
                                        "0x3002b",
                                        archivo,
                                        idx,
                                        col,
                                        linea_cod,
                                        f"Puntero '{arg_id}' liberado con free() pero no anulado con NULL posteriormente.",
                                    ))

        # AP010 (0x3001h) & AP015 (0x200Bh) & AP018 (0x2009h)
        elif node.type == "function_definition":
            decl_node = node.child_by_field_name("declarator")
            body_node = node.child_by_field_name("body")
            fn_name = _find_identifier(decl_node) if decl_node else None

            # AP015: más de 5 parámetros
            if decl_node:
                param_list = None
                for c in decl_node.children:
                    if c.type == "parameter_list":
                        param_list = c
                        break
                if param_list:
                    params = [c for c in param_list.children if c.type == "parameter_declaration"]
                    if len(params) > 5:
                        antipatrones.append(_make_antipatron(
                            "0x200Bh",
                            archivo,
                            idx,
                            col,
                            linea_cod,
                            f"Función '{fn_name}' declara {len(params)} parámetros (máximo recomendado: 5).",
                        ))

            # AP018: recursión sin caso base
            if fn_name and body_node:
                body_text = body_node.text.decode("utf-8", errors="replace")
                if re.search(rf"\b{re.escape(fn_name)}\s*\(", body_text):
                    has_if = any(c.type == "if_statement" for c in body_node.children)
                    if not has_if and "if" not in body_text and "?" not in body_text:
                        antipatrones.append(_make_antipatron(
                            "0x2009h",
                            archivo,
                            idx,
                            col,
                            linea_cod,
                            f"Función recursiva '{fn_name}' sin condicional aparente para caso base (riesgo de recursión infinita).",
                        ))

            # AP012: Variable local declarada pero no utilizada
            if body_node and body_node.type == "compound_statement":
                declared_vars = []
                for stmt in body_node.children:
                    if stmt.type == "declaration":
                        for decl_child in stmt.children:
                            if decl_child.type == "init_declarator":
                                id_node = decl_child.child_by_field_name("declarator")
                                v_name = _find_identifier(id_node or decl_child)
                                if v_name:
                                    declared_vars.append((v_name, stmt.start_point.row + 1, stmt.start_point.column + 1))
                            elif decl_child.type == "identifier":
                                v_name = decl_child.text.decode("utf-8", errors="replace")
                                declared_vars.append((v_name, stmt.start_point.row + 1, stmt.start_point.column + 1))

                for v_name, v_row, v_col in declared_vars:
                    occ = len(re.findall(rf"\b{re.escape(v_name)}\b", body_text))
                    if occ <= 1:
                        antipatrones.append(_make_antipatron(
                            "0x2007h",
                            archivo,
                            v_row,
                            v_col,
                            lineas[v_row - 1] if v_row <= len(lineas) else "",
                            f"Variable local '{v_name}' declarada pero no utilizada en el cuerpo de la función.",
                        ))

        # AP021 (0x100Ch): switch case sin break
        elif node.type == "case_statement":
            statements = [c for c in node.children if c.type in ("expression_statement", "compound_statement", "return_statement", "break_statement", "goto_statement")]
            if statements:
                last_stmt = statements[-1]
                if last_stmt.type not in ("break_statement", "return_statement", "goto_statement"):
                    has_term = False
                    if last_stmt.type == "compound_statement":
                        sub_stmts = [c for c in last_stmt.children if c.type in ("break_statement", "return_statement")]
                        if sub_stmts:
                            has_term = True
                    if not has_term:
                        case_text = node.text.decode("utf-8", errors="replace")
                        if "fallthrough" not in case_text.lower():
                            antipatrones.append(_make_antipatron("0x100Ch", archivo, idx, col, linea_cod))

        # AP022 (0x0003h): Declaración tras sentencia ejecutable en bloque
        elif node.type == "compound_statement":
            saw_exec = False
            for child in node.children:
                if child.type in ("expression_statement", "if_statement", "while_statement", "for_statement", "switch_statement"):
                    saw_exec = True
                elif child.type == "declaration" and saw_exec:
                    antipatrones.append(_make_antipatron(
                        "0x0003b",
                        archivo,
                        child.start_point.row + 1,
                        child.start_point.column + 1,
                        lineas[child.start_point.row] if child.start_point.row < len(lineas) else "",
                    ))
                    break

        # AP024 (0x3015h): ptr = realloc(ptr, size)
        elif node.type == "assignment_expression":
            left_node = node.child_by_field_name("left")
            right_node = node.child_by_field_name("right")
            if left_node and right_node:
                l_name = _find_identifier(left_node)
                # AP029 (0x1010h): if (ptr = malloc(...) == NULL)
                if right_node.type == "binary_expression":
                    bin_op = next((c.text.decode("utf-8") for c in right_node.children if c.type in ("==", "!=")), "")
                    if bin_op:
                        r_left = right_node.child_by_field_name("left")
                        if r_left and r_left.type == "call_expression":
                            antipatrones.append(_make_antipatron(
                                "0x1010h",
                                archivo,
                                idx,
                                col,
                                linea_cod,
                                "Precedencia de operadores errónea: '==' evalúa antes que '='.",
                            ))

                if right_node.type == "call_expression":
                    fn_node = right_node.child_by_field_name("function")
                    args_node = next((c for c in right_node.children if c.type == "argument_list"), None)
                    fn_name_a = _find_identifier(fn_node) if fn_node else None
                    if fn_name_a == "realloc" and args_node:
                        arg_children = [c for c in args_node.children if c.type not in ("(", ")", ",")]
                        if arg_children:
                            first_arg_name = _find_identifier(arg_children[0])
                            if l_name and first_arg_name and l_name == first_arg_name:
                                antipatrones.append(_make_antipatron(
                                    "0x3015h",
                                    archivo,
                                    idx,
                                    col,
                                    linea_cod,
                                    f"Sobreescritura directa de puntero '{l_name}' en llamada a realloc.",
                                ))
                    elif fn_name_a in ("malloc", "calloc") and l_name:
                        if var_types.get(l_name) in ("int", "long", "short", "unsigned int", "unsigned long", "int32_t", "uint32_t"):
                            antipatrones.append(_make_antipatron(
                                "0x301Fh",
                                archivo,
                                idx,
                                col,
                                linea_cod,
                                f"Asignación de retorno de '{fn_name_a}()' a variable no puntero '{l_name}'.",
                            ))

        # AP028 (0x5009h) & AP046 (0x301Fh): Declaraciones e inicializaciones
        elif node.type in ("init_declarator", "declaration"):
            raw_text = node.text.decode("utf-8", errors="replace")
            # AP046: Asignación de retorno de malloc/calloc a variable no puntero en declaración
            if node.type == "declaration":
                type_n = node.child_by_field_name("type")
                type_txt = type_n.text.decode("utf-8", errors="replace") if type_n else ""
                if type_txt in ("int", "long", "short", "unsigned int", "unsigned long", "int32_t", "uint32_t"):
                    for init_c in node.children:
                        if init_c.type == "init_declarator":
                            decl_c = init_c.child_by_field_name("declarator")
                            val_c = init_c.child_by_field_name("value")
                            if decl_c and decl_c.type == "identifier" and val_c and val_c.type == "call_expression":
                                fn_c = val_c.child_by_field_name("function")
                                fn_name_c = _find_identifier(fn_c) if fn_c else None
                                if fn_name_c in ("malloc", "calloc"):
                                    antipatrones.append(_make_antipatron(
                                        "0x301Fh",
                                        archivo,
                                        idx,
                                        col,
                                        linea_cod,
                                        f"Asignación de retorno de '{fn_name_c}()' a variable no puntero '{decl_c.text.decode('utf-8', errors='replace')}'.",
                                    ))

            if re.search(r"\b(?:float|double)\b", raw_text) and "=" in raw_text:
                m_div = re.search(r"=\s*([0-9]+)\s*/\s*([0-9]+)", raw_text)
                if m_div:
                    antipatrones.append(_make_antipatron(
                        "0x5009h",
                        archivo,
                        idx,
                        col,
                        linea_cod,
                        f"División entera '{m_div.group(1)} / {m_div.group(2)}' asignada a variable flotante.",
                    ))

        for child in node.children:
            _traverse(child)

    _traverse(tree.root_node)
    antipatrones.sort(key=lambda a: (a.linea, a.columna))
    return antipatrones


def auditar_archivos(rutas: List[Path]) -> ReporteAntipatrones:
    """Audita una lista de archivos o directorios."""
    archivos_objetivo: Set[Path] = set()
    for r in rutas:
        p = Path(r)
        if p.is_file() and p.suffix.lower() in (".c", ".h"):
            archivos_objetivo.add(p)
        elif p.is_dir():
            for sub in p.rglob("*"):
                if sub.is_file() and sub.suffix.lower() in (".c", ".h"):
                    archivos_objetivo.add(sub)

    todos: List[AntipatronDetectado] = []
    for arch in sorted(archivos_objetivo):
        todos.extend(auditar_archivo(arch))

    return ReporteAntipatrones(
        total_archivos=len(archivos_objetivo),
        antipatrones=todos,
    )


def generar_sarif_210_spunkmeyer(reporte: ReporteAntipatrones) -> Dict[str, Any]:
    """Genera informe en formato estándar OASIS SARIF 2.1.0."""
    from spunkmeyer import __version__
    sarif_rules = []
    reglas_vistas = set()
    results = []

    for ap in reporte.antipatrones:
        c_str = str(ap.codigo)
        if c_str not in reglas_vistas:
            reglas_vistas.add(c_str)
            sarif_rules.append({
                "id": c_str,
                "name": ap.nombre,
                "shortDescription": {"text": ap.nombre},
                "fullDescription": {"text": ap.explicacion},
                "defaultConfiguration": {"level": "warning"},
            })

        results.append({
            "ruleId": c_str,
            "level": "warning",
            "message": {"text": f"{ap.mensaje} Sugerencia: {ap.sugerencia}"},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": str(ap.archivo)},
                        "region": {"startLine": max(1, ap.linea), "startColumn": max(1, ap.columna)},
                    }
                }
            ],
        })

    return {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "spunkmeyer",
                        "version": __version__,
                        "informationUri": "https://github.com/unsam/spunkmeyer",
                        "rules": sarif_rules,
                    }
                },
                "results": results,
            }
        ],
    }


def correlacionar_con_hal(reporte: ReporteAntipatrones, crash_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Cruza los antipatrones detectados con la información de un core dump o caída reportada por HAL."""
    correlaciones = []
    crash_file = crash_data.get("archivo", "")
    crash_line = crash_data.get("linea", 0)

    for ap in reporte.antipatrones:
        coincide_archivo = not crash_file or Path(crash_file).name == ap.archivo.name
        distancia_lineas = abs(ap.linea - crash_line) if crash_line > 0 else 0
        if coincide_archivo and distancia_lineas <= 5:
            correlaciones.append({
                "antipatron": ap.to_dict(),
                "crash": crash_data,
                "diagnostico_cruzado": f"El antipatrón '{ap.nombre}' en línea {ap.linea} está directamente relacionado con la caída en línea {crash_line}.",
            })
    return correlaciones


def comparar_antipatrones_entre_versiones(v1: ReporteAntipatrones, v2: ReporteAntipatrones) -> Dict[str, Any]:
    """Compara los antipatrones entre dos entregas o versiones para medir la evolución del estudiante (Weyil integration)."""
    set_v1 = {(str(a.codigo), a.archivo.name, a.linea) for a in v1.antipatrones}
    set_v2 = {(str(a.codigo), a.archivo.name, a.linea) for a in v2.antipatrones}

    resueltos = len(set_v1 - set_v2)
    nuevos = len(set_v2 - set_v1)
    persistentes = len(set_v1 & set_v2)

    return {
        "total_version_anterior": len(v1.antipatrones),
        "total_version_actual": len(v2.antipatrones),
        "antipatrones_resueltos": resueltos,
        "antipatrones_nuevos": nuevos,
        "antipatrones_persistentes": persistentes,
        "mejora_neta": resueltos - nuevos,
    }


def cargar_reglas_personalizadas_yaml(ruta_yaml: Path) -> Set[str]:
    """Carga reglas personalizadas habilitadas desde un archivo YAML de cátedra."""
    import re
    if not ruta_yaml.is_file():
        return set()
    txt = ruta_yaml.read_text(encoding="utf-8")
    reglas = set(re.findall(r"-\s*([A-Za-z0-9_]+)", txt))
    return reglas
