# Cómo funciona

Notas técnicas para quien quiera entender, auditar o extender la herramienta.

## 1. Banco de preguntas

El banco son archivos JSON versionados en `content/bank/`:

- `mc/*.json`: preguntas de múltiple opción.
- `short/*.json`: preguntas de desarrollo corto.

Cada archivo es una lista de preguntas. `quiz/bank.py` los carga, valida el esquema y construye
objetos inmutables (`PreguntaMC`, `PreguntaDesarrollo`). La validación es la misma que corre
`scripts/validate_bank.py`, por lo que un banco inválido **no** deja arrancar la aplicación: falla
con la lista de errores y un mensaje para corregirlos.

Reglas que se verifican automáticamente:

- `id` único en todo el banco y con formato de slug.
- Múltiple opción: 3 a 5 opciones, exactamente una `correcta: true`, cada distractor con
  `porque_no` (por qué está mal), explicación de 40 a 1500 caracteres, sin «todas/ninguna de las
  anteriores», sin opciones repetidas.
- Desarrollo: 3 a 5 criterios, pesos que suman 1.0, 1 a 8 palabras clave por criterio, respuesta
  modelo y tiempo sugerido.
- Fuente: el PDF tiene que existir en el repositorio y la página estar dentro del rango real
  (esto último se comprueba con `--estricto-paginas`, que necesita `pypdf` o `PyMuPDF`).
- Enunciados normalizados únicos: no se permiten dos preguntas con el mismo texto, aunque cambien
  acentos o mayúsculas.

El corpus (`content/corpus/*.json`) guarda el texto de cada PDF por página. Se usa para auditar
citas y buscar conceptos; se regenera con `scripts/extract_corpus.py`.

## 2. Generación del examen

`quiz/sampler.py` implementa tres ideas:

1. **Composición fija por especificación.** `content/exam_spec.json` define cuántas preguntas de
   cada tema (5 × 6 = 30), cuántas de desarrollo (5, una por tema como máximo), los pesos (60/40) y
   el tiempo sugerido. Se puede variar por CLI (`--mc`, `--temas`, `--desarrollo`) o por API.
2. **Muestreo con rotación.** Para cada tema se ordenan las preguntas por cantidad de usos previos
   (`examenes/historial.json`) y, dentro de cada nivel de uso, por azar; se toman las primeras.
   Así el banco rota y no se repiten siempre las mismas.
3. **Reproducibilidad.** Con `seed` explícita se ignora el historial de uso y se usa solo el
   generador pseudoaleatorio: el mismo número produce siempre el mismo examen (preguntas y orden
   de opciones), lo que sirve para compartir un intento o para depurar.

El orden de las opciones se baraja con el mismo generador y se guarda como una permutación
(`orden`) en el JSON del examen, para que la corrección sepa qué posición eligió el alumno.

## 3. Corrección

### Múltiple opción

Exacta: se compara la posición elegida (en la vista con opciones mezcladas) con la posición que
ocupa la opción correcta. Sin modelo, sin ambigüedad.

### Desarrollo: criterios + palabras clave

`CorrectorHeuristico` procesa el texto del alumno:

- Normaliza (minúsculas, sin acentos, sin puntuación) y tokeniza ignorando palabras vacías.
- Para cada criterio busca si alguna de sus `claves` aparece en la respuesta. Una clave de una
  palabra coincide por token exacto, prefijo (`shard` / `sharding`) o similitud alta; las de dos
  palabras exigen ambos términos; las más largas aceptan el 70 % de los términos o la frase exacta.
- Puntaje = suma de pesos de los criterios cubiertos, con topes por extensión (menos de 6
  palabras: máximo 0.35; menos de 14: máximo 0.8).
- Devuelve detalle por criterio (cumplido / no cumplido, con la evidencia detectada), faltantes y
  comentario. También calcula una similitud global contra la respuesta modelo, solo como dato
  orientativo.

Ventaja: explica exactamente por qué puso lo que puso. Límite: no entiende paráfrasis muy
alejadas de las claves; por eso existe el modo con LLM.

### Desarrollo con LLM local

`CorrectorLLM` arma un prompt con la consigna, los criterios ponderados, la respuesta modelo y la
respuesta del alumno (delimitada). El modelo devuelve un JSON con el estado de cada criterio, un
puntaje y un comentario. El cliente (`quiz/llm.py`) soporta:

- **Ollama**: `POST /api/chat` con `format: "json"`.
- **Cualquier servidor compatible con OpenAI** (LM Studio, llama.cpp, vLLM…): `POST /v1/chat/completions`
  con `response_format: {"type": "json_object"}`.

El parser tolera bloques ```json, texto alrededor y llaves dentro de cadenas. Si el `puntaje`
informado contradice el detalle de los criterios (diferencia mayor a 0.2), se usa la suma de pesos,
que es la fuente auditable. Si hay error de red o timeout, se cae a la corrección heurística y la
boleta muestra el aviso.

Como la respuesta del alumno es texto libre, el prompt la trata como **datos**: el sistema indica
explícitamente que ignore instrucciones embebidas en ella.

## 4. Persistencia

| Archivo | Contenido |
|---|---|
| `examenes/<id>.json` | Examen generado: ids, permutación de opciones, seed, especificación |
| `examenes/<id>-resultado.json` | Corrección completa, con explicaciones y devoluciones |
| `examenes/boleta-<id>.md` | Boleta en Markdown para descargar o imprimir |
| `examenes/historial.json` | Veces que se usó cada pregunta (para la rotación) |

Todo se guarda localmente; nada sale de la máquina.

## 5. Interfaz y API

`quiz/web.py` es un servidor `ThreadingHTTPServer` de la biblioteca estándar:

- Sirve `web/` (HTML, CSS y JS sin frameworks ni CDN) y una API JSON.
- Valida rutas estáticas para que no se pueda salir del directorio `web/`.
- Mantiene los exámenes en memoria y los persiste en disco; si se reinicia, los recupera.
- El estado del modelo local se cachea 30 segundos para no consultar en cada request.

La API está documentada en la tabla del [`README`](../README.md#api-local).

## 6. Decisiones de diseño

- **Sin dependencias en tiempo de ejecución**: portabilidad real; el único requisito es Python.
- **Banco versionado en vez de generación en vivo**: el examen es estable, auditable y funciona
  offline. Un LLM puede redactar preguntas, pero sin curaduría humana la calidad y las citas se
  degradan.
- **Corrección explicable por defecto**: si el alumno no entiende por qué perdió puntos, la
  corrección no sirve para estudiar. Por eso cada criterio muestra su estado y la fuente.
- **Fuentes obligatorias**: cada pregunta cita el PDF y la página; el validador lo exige.
