"""Catálogo canónico de antipatrones didácticos para SPUNKMEYER."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import yaml

CATALOGO_ANTIPATRONES_BASE: Dict[str, Dict[str, str]] = {
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
    "0x400Ah": {
        "codigo": "0x400Ah",
        "alias": "AP049",
        "nombre": "Lectura de cadenas con scanf() sin límite de ancho en buffer fijo",
        "mensaje": "Uso de especificador '%s' en scanf()/fscanf() sin limitador de ancho sobre buffer estático.",
        "explicacion": "'%s' lee hasta encontrar un espacio en blanco sin verificar el tamaño del buffer destino, permitiendo desbordamientos de buffer (buffer overflow).",
        "sugerencia": "Especificá el ancho máximo restando el byte nulo terminador (ej. '%9s' para un buffer de 10 bytes) o utilizá fgets().",
        "ejemplo_incorrecto": "char buf[10];\nscanf(\"%s\", buf);",
        "ejemplo_correcto": "char buf[10];\nscanf(\"%9s\", buf);",
    },
    "0x101Ah": {
        "codigo": "0x101Ah",
        "alias": "AP050",
        "nombre": "Comparación lógica invertida con strcmp() en condicional",
        "mensaje": "Uso de 'strcmp()' como condición booleana directa sin comparación explícita contra 0.",
        "explicacion": "'strcmp()' retorna 0 cuando ambas cadenas son idénticas. Evaluar 'if (strcmp(a, b))' ejecuta la rama cuando son DIFERENTES.",
        "sugerencia": "Escribí explícitamente 'if (strcmp(a, b) == 0)' para verificar igualdad o '!= 0' para desigualdad.",
        "ejemplo_incorrecto": "if (strcmp(nombre, \"admin\")) {\n    dar_acceso();\n}",
        "ejemplo_correcto": "if (strcmp(nombre, \"admin\") == 0) {\n    dar_acceso();\n}",
    },
    "0x2013h": {
        "codigo": "0x2013h",
        "alias": "AP051",
        "nombre": "Descarte del valor retornado por funciones de conversión numérica",
        "mensaje": "Invocación a 'strtol()', 'strtoul()' o 'strtod()' descartando el valor de retorno o sin verificar errores.",
        "explicacion": "Las funciones de la familia 'strtoX' requieren verificar 'endptr' y 'errno' (ERANGE) para detectar si la conversión fue exitosa.",
        "sugerencia": "Almacená el resultado y verificá 'errno == 0 && *endptr == '\\0''.",
        "ejemplo_incorrecto": "strtol(cadena, NULL, 10);",
        "ejemplo_correcto": "char *endptr;\nerrno = 0;\nlong val = strtol(cadena, &endptr, 10);\nif (errno != 0 || *endptr != '\\0') { /* error */ }",
    },
    "0x101Bh": {
        "codigo": "0x101Bh",
        "alias": "AP052",
        "nombre": "Comparación entre tipos enteros con y sin signo en condición",
        "mensaje": "Comparación relacional directa entre variable con signo ('int') y sin signo ('size_t' o 'unsigned').",
        "explicacion": "En C, si un operando es con signo y el otro es sin signo del mismo o mayor rango, el valor con signo se convierte implícitamente a sin signo. Si 'i' es negativo (-1), se convierte a un número enorme mayor que cualquier límite positivo.",
        "sugerencia": "Utilizá tipos consistentes (ambos 'size_t' o casteá de forma controlada tras verificar que i >= 0).",
        "ejemplo_incorrecto": "int i = -1;\nsize_t n = 10;\nif (i < n) { ... }",
        "ejemplo_correcto": "size_t i = 0;\nsize_t n = 10;\nif (i < n) { ... }",
    },
    "0x3021h": {
        "codigo": "0x3021h",
        "alias": "AP053",
        "nombre": "Invocación a free() sobre memoria estática o variables automáticas de pila",
        "mensaje": "Llamada a 'free()' sobre la dirección de una variable local de stack o arreglo estático.",
        "explicacion": "'free()' solo es válido sobre punteros retornados previamente por 'malloc()', 'calloc()' o 'realloc()'. Intentar liberar memoria del stack corrompe el heap y causa SIGSEGV o abort.",
        "sugerencia": "Eliminá la llamada a 'free()' sobre variables automáticas de stack.",
        "ejemplo_incorrecto": "int x = 42;\nfree(&x);",
        "ejemplo_correcto": "int *p = malloc(sizeof(int));\n*p = 42;\nfree(p);",
    },
    "0x500Bh": {
        "codigo": "0x500Bh",
        "alias": "AP054",
        "nombre": "Redefinición de identificadores de funciones estándar de la biblioteca C",
        "mensaje": "Declaración o definición de función propia con nombre reservado de biblioteca estándar ('abs', 'min', 'max', 'index').",
        "explicacion": "Redefinir identificadores estándar causa colisiones de enlace con la libc o comportamientos indefinidos por interferencia con macros del sistema.",
        "sugerencia": "Elegí un identificador con prefijo institucional o descriptivo de tu módulo (ej. 'calcular_abs', 'mi_min').",
        "ejemplo_incorrecto": "int abs(int x) {\n    return x < 0 ? -x : x;\n}",
        "ejemplo_correcto": "int valor_absoluto(int x) {\n    return x < 0 ? -x : x;\n}",
    },
    "0x3022h": {
        "codigo": "0x3022h",
        "alias": "AP055",
        "nombre": "Asignación de punteros a arreglos locales en parámetros de salida",
        "mensaje": "Asignación de la dirección de un arreglo local de la pila a un puntero pasado por referencia ('*salida = local_arr').",
        "explicacion": "El arreglo local reside en el marco de pila de la función actual. Al retornar, la memoria queda invalidada y el puntero almacenado en el llamador queda colgante.",
        "sugerencia": "Copiá el contenido con 'memcpy()' o asigná memoria dinámica en el heap.",
        "ejemplo_incorrecto": "void obtener(int **res) {\n    int arr[5] = {0};\n    *res = arr;\n}",
        "ejemplo_correcto": "void obtener(int *dest, size_t n) {\n    for (size_t i = 0; i < n; i++) dest[i] = 0;\n}",
    },
    "0x3023h": {
        "codigo": "0x3023h",
        "alias": "AP056",
        "nombre": "Comprobación de puntero nulo posterior a su desreferencia",
        "mensaje": "Verificación 'if (ptr != NULL)' posterior a una desreferencia previa del mismo puntero.",
        "explicacion": "Si el puntero hubiera sido NULL, el programa ya habría caído por Segmentation Fault en la línea de desreferencia anterior. La verificación tardía indica aserciones invertidas.",
        "sugerencia": "Ubicá la comprobación 'if (ptr == NULL)' antes de cualquier acceso a sus datos.",
        "ejemplo_incorrecto": "*ptr = 10;\nif (ptr != NULL) {\n    // ...\n}",
        "ejemplo_correcto": "if (ptr != NULL) {\n    *ptr = 10;\n}",
    },
    "0x3024h": {
        "codigo": "0x3024h",
        "alias": "AP057",
        "nombre": "Asignación múltiple a malloc en bucle sin liberación ante fallos parciales",
        "mensaje": "Reserva de filas de matriz con 'malloc()' dentro de un bucle sin control ni liberación de las filas previamente asignadas si una falla.",
        "explicacion": "Si la asignación de la fila k falla y la función retorna NULL inmediatamente, las filas 0 a k-1 quedan como fugas de memoria irrecuperables (memory leak).",
        "sugerencia": "En caso de fallo en una fila, liberá todas las filas asignadas previamente antes de retornar.",
        "ejemplo_incorrecto": "for (int i = 0; i < n; i++) {\n    mat[i] = malloc(m * sizeof(int));\n}",
        "ejemplo_correcto": "for (int i = 0; i < n; i++) {\n    mat[i] = malloc(m * sizeof(int));\n    if (!mat[i]) { /* liberar mat[0..i-1] y retornar NULL */ }\n}",
    },
    "0x3025h": {
        "codigo": "0x3025h",
        "alias": "AP058",
        "nombre": "Modificación directa del puntero base asignado por malloc()",
        "mensaje": "Aritmética de punteros directa ('ptr++' o 'ptr += n') sobre la variable puntero que retuvo el retorno de 'malloc()'.",
        "explicacion": "Modificar el puntero original hace que se pierda la dirección de inicio del bloque asignado, impidiendo luego pasar la dirección correcta a 'free()' y generando fallas de liberación.",
        "sugerencia": "Utilizá un puntero auxiliar iterador ('tipo *iter = ptr; iter++;') o indexación por corchetes ('ptr[i]').",
        "ejemplo_incorrecto": "char *p = malloc(100);\nwhile (*p) p++;\nfree(p);",
        "ejemplo_correcto": "char *p = malloc(100);\nchar *iter = p;\nwhile (*iter) iter++;\nfree(p);",
    },
    "0x400Bh": {
        "codigo": "0x400Bh",
        "alias": "AP059",
        "nombre": "Omisión de verificación de retorno NULL en fopen()",
        "mensaje": "Uso inmediato del descriptor devuelto por 'fopen()' sin comprobar previamente si es NULL.",
        "explicacion": "Si el archivo no existe o no tiene permisos de lectura/escritura, 'fopen()' retorna NULL. Desreferenciarlo en 'fread', 'fgets' o 'fgetc' causa caída inmediata por SIGSEGV.",
        "sugerencia": "Verificá siempre 'if (f == NULL)' inmediatamente después de invocar 'fopen()'.",
        "ejemplo_incorrecto": "FILE *f = fopen(\"datos.txt\", \"r\");\nfread(&elem, sizeof(elem), 1, f);",
        "ejemplo_correcto": "FILE *f = fopen(\"datos.txt\", \"r\");\nif (f == NULL) return -1;\nfread(&elem, sizeof(elem), 1, f);",
    },
    "0x3026h": {
        "codigo": "0x3026h",
        "alias": "AP060",
        "nombre": "Desreferencia condicional de puntero local sin inicializar",
        "mensaje": "Puntero local declarado sin inicialización que es desreferenciado en una rama condicional.",
        "explicacion": "Los punteros locales no inicializados contienen valores residuales de la pila (wild pointers). Desreferenciarlos conduce a comportamiento indefinido o corrupción de memoria.",
        "sugerencia": "Inicializá siempre los punteros a NULL al momento de declararlos ('tipo *ptr = NULL;').",
        "ejemplo_incorrecto": "int *p;\nif (cond) *p = 10;",
        "ejemplo_correcto": "int *p = NULL;\nif (cond) {\n    p = malloc(sizeof(int));\n    if (p) *p = 10;\n}",
    },
    "0x3027h": {
        "codigo": "0x3027h",
        "alias": "AP061",
        "nombre": "Cálculo erróneo de tamaño para struct dinámico con miembro flexible",
        "mensaje": "Reserva dinámica para estructura con miembro flexible sumando 'n' directamente en lugar de 'n * sizeof(elemento)'.",
        "explicacion": "Si el elemento del arreglo flexible tiene un tamaño mayor a 1 byte (ej. int, puntero), 'sizeof(struct T) + n' asigna menos memoria de la necesaria, causando desbordamiento de heap.",
        "sugerencia": "Calculá el tamaño exacto: 'sizeof(struct T) + n * sizeof(elemento)'.",
        "ejemplo_incorrecto": "malloc(sizeof(struct vector) + 10);",
        "ejemplo_correcto": "malloc(sizeof(struct vector) + 10 * sizeof(int));",
    },
    "0x101Ch": {
        "codigo": "0x101Ch",
        "alias": "AP062",
        "nombre": "Bucle infinito con salida condicionada exclusivamente por exit()",
        "mensaje": "Bucle 'while(1)' o 'for(;;)' cuya única condición de terminación es la invocación a 'exit()'.",
        "explicacion": "Terminar la ejecución del proceso mediante 'exit()' dentro de un bucle omite la ejecución del código de limpieza, la liberación de memoria y la preservación de invariantes estructurados.",
        "sugerencia": "Utilizá 'break' o una variable de control booleana para salir limpiamente del bucle y retornar por el flujo natural.",
        "ejemplo_incorrecto": "while (1) {\n    if (fin) exit(0);\n}",
        "ejemplo_correcto": "while (1) {\n    if (fin) break;\n}",
    },
    "0x3028h": {
        "codigo": "0x3028h",
        "alias": "AP063",
        "nombre": "Casteo de retorno de malloc() con omisión de include stdlib.h",
        "mensaje": "Uso de casteo explícito en 'malloc()' en un archivo que no incluye '<stdlib.h>'.",
        "explicacion": "En C90/C99 sin '<stdlib.h>', el compilador asume que 'malloc()' retorna 'int'. El casteo explícito oculta la advertencia del compilador y en arquitecturas de 64 bits trunca la dirección de memoria a 32 bits.",
        "sugerencia": "Incluí obligatoriamente '#include <stdlib.h>' y retirá el casteo redundante.",
        "ejemplo_incorrecto": "int *p = (int *)malloc(sizeof(int)); // Sin #include <stdlib.h>",
        "ejemplo_correcto": "#include <stdlib.h>\nint *p = malloc(sizeof(*p));",
    },
    "0x3029h": {
        "codigo": "0x3029h",
        "alias": "AP070",
        "nombre": "Desreferencia directa tras retorno de realloc sin asignación temporal",
        "mensaje": "Desreferencia directa inmediata sobre el resultado de 'realloc()' sin validación previa de NULL.",
        "explicacion": "Si realloc falla y retorna NULL, cualquier acceso o desreferencia directa causa caída catastrófica (SIGSEGV) y pérdida del puntero original.",
        "sugerencia": "Asigná el retorno de 'realloc' a un puntero temporal auxiliar y comprobá 'if (!temp)' antes de desreferenciar.",
        "ejemplo_incorrecto": "*((int *)realloc(p, n)) = 42;",
        "ejemplo_correcto": "int *temp = realloc(p, n);\nif (!temp) { /* manejar error */ }\n*temp = 42;",
    },
    "0x302Ah": {
        "codigo": "0x302Ah",
        "alias": "AP073",
        "nombre": "Casteo forzado de tipos numéricos o literales enteros a punteros",
        "mensaje": "Casteo explícito de constante numérica o dirección absoluta a tipo puntero.",
        "explicacion": "En arquitecturas modernas con memoria virtual, acceder a direcciones fijas arbitrarias sin mapeo causa violación de segmento inmediata y anula la portabilidad.",
        "sugerencia": "Obtené punteros mediante asignadores dinámicos ('malloc') o el operador de dirección ('&') sobre objetos válidos.",
        "ejemplo_incorrecto": "int *p = (int *)0x1000;",
        "ejemplo_correcto": "int *p = malloc(sizeof(int));",
    },
}


MAPA_ANTIPATRONES: Dict[str, str] = {'AP-0x0003b': '0x7001h', 'AP-0x0004b': '0x7001h', 'AP-0x0039h': '0x500Dh', 'AP-0x1001h': '0x1001h', 'AP-0x1005h': '0x1005h', 'AP-0x100Ah': '0x1009h', 'AP-0x100Ch': '0x1008h', 'AP-0x100Dh': '0x1018h', 'AP-0x100Eh': '0x1013h', 'AP-0x100Fh': '0x100Dh', 'AP-0x1010h': '0x1012h', 'AP-0x1011h': '0x301Fh', 'AP-0x1014h': '0x100Dh', 'AP-0x1015h': '0x1003h', 'AP-0x1016h': '0x1013h', 'AP-0x1017h': '0x2015h', 'AP-0x1018h': '0x1001h', 'AP-0x1019h': '0x1006h', 'AP-0x101Ah': '0x1005h', 'AP-0x101Bh': '0x1005h', 'AP-0x101Ch': '0x1002h', 'AP-0x2007h': '0x2006h', 'AP-0x2009h': '0x2017h', 'AP-0x200Bh': '0x200Ah', 'AP-0x2011h': '0x2017h', 'AP-0x2012h': '0x2018h', 'AP-0x2013h': '0x7003h', 'AP-0x3001h': '0x3001h', 'AP-0x3002b': '0x3002h', 'AP-0x3002h': '0x3002h', 'AP-0x3008h': '0x3008h', 'AP-0x300Ah': '0x300Ah', 'AP-0x300Dh': '0x300Dh', 'AP-0x300Fh': '0x3013h', 'AP-0x3015h': '0x3015h', 'AP-0x3019h': '0x300Bh', 'AP-0x301Ah': '0x3016h', 'AP-0x301Bh': '0x3001h', 'AP-0x301Ch': '0x300Ah', 'AP-0x301Dh': '0x3008h', 'AP-0x301Eh': '0x300Bh', 'AP-0x301Fh': '0x3001h', 'AP-0x3020h': '0x300Ah', 'AP-0x3021h': '0x3002h', 'AP-0x3022h': '0x3002h', 'AP-0x3023h': '0x3001h', 'AP-0x3024h': '0x3001h', 'AP-0x3025h': '0x3002h', 'AP-0x3026h': '0x3001h', 'AP-0x3027h': '0x300Bh', 'AP-0x3028h': '0x300Ah', 'AP-0x3029h': '0x3001h', 'AP-0x302Ah': '0x300Ah', 'AP-0x4002h': '0x4006h', 'AP-0x4006h': '0x400Bh', 'AP-0x4008b': '0x400Ch', 'AP-0x4008h': '0x400Ch', 'AP-0x4009h': '0x4004h', 'AP-0x400Ah': '0x5006h', 'AP-0x400Bh': '0x4001h', 'AP-0x5004b': '0x5004h', 'AP-0x5004c': '0x5004h', 'AP-0x5004h': '0x5004h', 'AP-0x5008h': '0x5008h', 'AP-0x5009h': '0x5009h', 'AP-0x500Ah': '0x500Ah', 'AP-0x500Bh': '0x500Dh', 'AP-0x5014h': '0x5015h', 'AP-0x5016h': '0x5015h'}


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
    "AP049": "0x400Ah",
    "AP050": "0x101Ah",
    "AP051": "0x2013h",
    "AP052": "0x101Bh",
    "AP053": "0x3021h",
    "AP054": "0x500Bh",
    "AP055": "0x3022h",
    "AP056": "0x3023h",
    "AP057": "0x3024h",
    "AP058": "0x3025h",
    "AP059": "0x400Bh",
    "AP060": "0x3026h",
    "AP061": "0x3027h",
    "AP062": "0x101Ch",
    "AP063": "0x3028h",
    "AP070": "0x3029h",
    "AP073": "0x302Ah",
}



class CatalogDict(dict):
    """Diccionario canónico de 65 antipatrones didácticos con resolución de alias y namespaces alternativos."""

    def __init__(self, canonical_items: Dict[str, Dict[str, Any]], alias_index: Dict[str, str]):
        super().__init__(canonical_items)
        self._alias_index = alias_index

    def __getitem__(self, key: str) -> Dict[str, Any]:
        if super().__contains__(key):
            return super().__getitem__(key)
        target = self._alias_index.get(str(key).lower())
        if target and super().__contains__(target):
            return super().__getitem__(target)
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: object) -> bool:
        if super().__contains__(key):
            return True
        if isinstance(key, str):
            return str(key).lower() in self._alias_index
        return False


def _build_catalog() -> CatalogDict:
    canonical: Dict[str, Dict[str, Any]] = {}
    alias_index: Dict[str, str] = {}

    for _k, _info in CATALOGO_ANTIPATRONES_BASE.items():
        info_copy = dict(_info)
        _ap_key = f"AP-{_k}"
        _cod_nuevo = MAPA_ANTIPATRONES.get(_ap_key, MAPA_ANTIPATRONES.get(_k, _k))
        info_copy["codigo_anterior"] = _k
        info_copy["codigo"] = _cod_nuevo
        info_copy["alias_ap"] = _ap_key

        sp_nuevo = f"SP{_cod_nuevo}" if _cod_nuevo.startswith("0x") else ""
        info_copy["sp_codigo"] = sp_nuevo

        canonical[_k] = info_copy

        alias_index[_k.lower()] = _k
        if _cod_nuevo.lower() not in alias_index:
            alias_index[_cod_nuevo.lower()] = _k
        alias_index[_ap_key.lower()] = _k
        alias = info_copy.get("alias")
        if alias:
            alias_index[alias.lower()] = _k
        if sp_nuevo and sp_nuevo.lower() not in alias_index:
            alias_index[sp_nuevo.lower()] = _k
        if _k.startswith("0x"):
            sp_k = f"sp{_k.lower()}"
            if sp_k not in alias_index:
                alias_index[sp_k] = _k

    for k, v in ALIAS_MAP.items():
        if v in canonical:
            alias_index[k.lower()] = v

    return CatalogDict(canonical, alias_index)


CATALOGO_ANTIPATRONES: CatalogDict = _build_catalog()


def obtener_antipatron(clave: str) -> Optional[Dict[str, Any]]:
    """Obtiene la información didáctica de un antipatrón por cualquier código, alias o namespace."""
    return CATALOGO_ANTIPATRONES.get(clave)


def cargar_reglas_personalizadas_yaml(ruta_yaml: Path) -> Set[str]:
    """Carga reglas personalizadas habilitadas desde un archivo YAML de cátedra."""
    import yaml

    if not ruta_yaml.is_file():
        return set()

    try:
        data = yaml.safe_load(ruta_yaml.read_text(encoding="utf-8"))
    except Exception:
        return set()

    if not data:
        return set()

    reglas: Set[str] = set()

    def _extraer(items: Any) -> None:
        if isinstance(items, list):
            for it in items:
                if isinstance(it, str):
                    reglas.add(it.strip())
        elif isinstance(items, str):
            for part in items.replace(",", " ").split():
                if part:
                    reglas.add(part.strip())

    if isinstance(data, list):
        _extraer(data)
    elif isinstance(data, dict):
        claves_reglas = ("reglas", "rules", "reglas_habilitadas", "enabled_rules", "antipatrones", "patterns")
        encontrado = False
        for k in claves_reglas:
            if k in data:
                _extraer(data[k])
                encontrado = True
        if not encontrado:
            for k, val in data.items():
                if isinstance(val, (list, str)):
                    _extraer(val)

    return reglas
