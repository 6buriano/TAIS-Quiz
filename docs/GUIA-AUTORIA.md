# Guía de autoría del banco de preguntas

Este documento explica **cómo escribir preguntas** para `content/bank/`. Está pensado
para que cualquier integrante del equipo (o colaborador del repositorio) pueda sumar
preguntas sin romper la aplicación ni bajar la calidad del examen.

Antes de escribir, la fuente de verdad son los PDF del repositorio. El texto extraído
de cada PDF está en `content/corpus/*.json`: un archivo por documento, con una entrada
por página (`{"n": 12, "texto": "..."}`) para ubicar el concepto y citar la página
correcta. Si agregás o actualizás PDF, regeneralo con:

```bash
python scripts/extract_corpus.py          # requiere pypdf o PyMuPDF
```

---

## 1. Estructura del banco

```
content/bank/
├── mc/            → preguntas de múltiple opción (archivos *.json)
│   ├── arquitectura-1.json
│   ├── rest-1.json
│   └── ...
└── short/         → preguntas de desarrollo corto (archivos *.json)
    ├── arquitectura.json
    └── ...
```

- Cada archivo contiene **una lista JSON** de preguntas (también se acepta
  `{"preguntas": [...]}`).
- Se pueden tener **varios archivos por tema**: el motor los mezcla todos.
- Los `id` deben ser **únicos en todo el banco** y no repetirse entre archivos.
- El texto de la pregunta (`pregunta`) debe ser **único en todo el banco** (se
  comparan sin acentos ni mayúsculas).

Convención de `id`: `<tema>-<subtema>-<nnn>`, por ejemplo `rest-cache-007`,
`nosql-cap-012`, `arq-estilos-003`.

## 2. Temas válidos

| Clave del tema  | Nombre                                         | PDFs fuente |
|-----------------|------------------------------------------------|-------------|
| `arquitectura`  | Arquitectura, tácticas y estilos               | `01-01-tais-Introduccion al Curso.pdf` (7 págs.), `01-02-tais-Tacticas de Ing Soft.pdf` (33), `01-03-tais-Estilos.pdf` (78) |
| `contenedores`  | Contenerización y CI/CD                        | `02-01-tais-Contenerizacion-02-01.pdf` (30), `02-02-tais-CI-CD-02-02.pdf` (28) |
| `nosql`         | Persistencia no relacional                     | `03-01-tais-PersistenciaNoRelacional-03-01.pdf` (24), `03-02-tais-PersistenciaNoRelacional-03-02.pdf` (43), `03-03-tais-PersistenciaNoRelacional-03-03.pdf` (17) |
| `cache`         | Caché, bases en memoria y Redis                | `04-01-CacheDatos-BD-Memoria-04-01.pdf` (39), `04-02-Redis-04-02.pdf` (28) |
| `asincronia`    | Programación asincrónica                       | `05-01-ProgAsincronica-05-01.pdf` (16), `05-02-ProgAsincronica-2-05-02.pdf` (30) |
| `rest`          | APIs REST                                      | `06-01-APIs REST-06-01.pdf` (47) |

Prácticos (para inspirarse en el estilo de consigna y en escenarios):
`Practicos/01-00 - Practico 1 - Tacticas de Ing Software.pdf`,
`Practicos/02-00-Practico 02 - Contenerización.pdf`,
`Practicos/03-00- Practico 03 -Persistencia de Datos No-Relacional.pdf`,
`Practicos/04-00 -Practico 04  Cache de Datos _ Bases de Datos en Memoria.pdf`,
`Practicos/05-00-Pracitco 05 Programación Asincrónica.pdf`,
`Practicos/06-00-Practico 06 APIs Rest.pdf`.
Laboratorios: `Laboratorios/Parte 3 - Laboratorio (1).pdf`, `Parte 4 - Laboratorio.pdf`,
`Parte 5 - Laboratorio.pdf`.

## 3. Pregunta de múltiple opción (esquema exacto)

```json
{
  "id": "rest-cache-007",
  "tema": "rest",
  "subtema": "cache",
  "dificultad": "media",
  "pregunta": "Una API devuelve el mismo catálogo de productos a miles de clientes y tarda 800 ms en responder. ¿Qué restricción de REST permite que intermediarios guarden esa respuesta y reduzcan la latencia?",
  "opciones": [
    { "texto": "Cacheable", "correcta": true },
    { "texto": "Stateless", "correcta": false, "porque_no": "Stateless elimina el estado de sesión en el servidor, pero no habilita el almacenamiento de respuestas por parte de intermediarios." },
    { "texto": "Layered System", "correcta": false, "porque_no": "La organización en capas permite interponer intermediarios, pero lo que habilita reutilizar una respuesta es que sea declarada cacheable." },
    { "texto": "Uniform Interface", "correcta": false, "porque_no": "La interfaz uniforme estandariza la forma de interactuar con los recursos; no define el almacenamiento de respuestas." }
  ],
  "explicacion": "La restricción 'Cacheable' indica que las respuestas deben declararse como cacheables o no. Si una respuesta es cacheable, un intermediario (proxy, CDN, caché del cliente) puede reutilizarla y evitar ir al origen, reduciendo latencia y carga.",
  "fuente": { "archivo": "06-01-APIs REST-06-01.pdf", "pagina": 4 },
  "tags": ["rest", "cache", "http"]
}
```

Reglas:

- **4 opciones** (mínimo 3: solo si es natural). Exactamente **una** `correcta: true`.
- **Todos los distractores** llevan `porque_no` (2–3 líneas explicando por qué es
  incorrecto). La opción correcta no lo necesita.
- `explicacion`: 2–4 frases que justifican la respuesta y anclan el concepto.
- `dificultad`: `facil` (definición/reconocimiento), `media` (comparación o
  aplicación), `dificil` (escenario con trade-offs, diagnóstico o cálculo).
- `fuente`: **nombre exacto** de un PDF del repositorio + **número de página
  real** (1..N según la tabla). Verificar la página antes de cargarla.
- `tags`: 1–4 etiquetas cortas en minúsculas (`cap`, `sharding`, `redis`, `docker`).
- **Prohibido**: "todas/ninguna de las anteriores", "siempre", "nunca", opciones
  absurdas o cómicas, opciones que se contradicen entre sí, o distractores que son
  parcialmente correctos sin matiz. Todas las opciones deben tener longitud similar
  y ser gramaticalmente coherentes con el enunciado.
- No usar "¿Cuál de las siguientes...?" más de dos veces seguidas en el mismo
  archivo: variar la forma (escenario, "¿qué táctica...", "un equipo propone...").
- Datos numéricos (timeouts, tamaños, tasas de acierto) solo si el PDF los menciona.

### Buenas preguntas vs. malas preguntas

| ❌ Mala | ✅ Buena |
|---|---|
| "¿Qué es Docker?" (trivia literal, se responde de memoria) | "El equipo necesita que el entorno de desarrollo sea idéntico al de producción y arrancar 20 servicios en una notebook. ¿Qué aporta principalmente la contenerización?" |
| "Redis es una base de datos. Verdadero o falso." | "Un sistema necesita leer un contador de visitas millones de veces por minuto y tolera perder los últimos segundos. ¿Por qué conviene Redis y no PostgreSQL?" |
| Distractores: "Docker", "Kubernetes", "Microsoft Word" | Distractores plausibles del mismo dominio, cada uno con su `porque_no` |

Distribución de dificultad por archivo: ~40 % `facil`, ~40 % `media`, ~20 % `dificil`.

Tipos de consigna recomendados (rotar): definición aplicada, comparación entre dos
tecnologías, elección de herramienta para un escenario, detección del error en un
diseño, consecuencia de una decisión ("¿qué problema introduce...?"), lectura de una
situación del estilo de los prácticos.

## 4. Pregunta de desarrollo corto (esquema exacto)

```json
{
  "id": "rest-stateless-002",
  "tema": "rest",
  "subtema": "stateless",
  "dificultad": "media",
  "pregunta": "Explicá por qué una API stateless escala horizontalmente con más facilidad y qué costo introduce esa decisión.",
  "criterios": [
    { "id": "c1", "descripcion": "Define stateless: el servidor no guarda estado de sesión entre requests", "peso": 0.35, "claves": ["no guarda estado", "no mantiene estado de sesion", "cada request contiene toda la informacion", "sin estado de sesion"] },
    { "id": "c2", "descripcion": "Relaciona con escalado horizontal: cualquier instancia puede atender cualquier request", "peso": 0.35, "claves": ["cualquier instancia", "cualquier servidor puede atender", "no requiere afinidad de sesion", "sticky session", "agregar instancias"] },
    { "id": "c3", "descripcion": "Menciona un costo o trade-off (token/estado en el cliente, más datos por request, invalidación)", "peso": 0.3, "claves": ["token", "jwt", "estado en el cliente", "mas datos en cada request", "invalidar sesion", "crece el payload"] }
  ],
  "respuesta_modelo": "Una API es stateless cuando cada request contiene toda la información necesaria y el servidor no conserva contexto de sesión. Por eso cualquier instancia puede atender cualquier request: no hace falta afinidad de sesión ni replicar estado, y el balanceador puede agregar o quitar instancias libremente. El costo es que el estado se traslada al cliente (por ejemplo, un token firmado) o a un almacén compartido, cada request lleva más datos y hay que resolver la invalidación y la revocación de credenciales.",
  "fuente": { "archivo": "06-01-APIs REST-06-01.pdf", "pagina": 7 },
  "tiempo_sugerido_min": 5,
  "tags": ["rest", "escalabilidad"]
}
```

Reglas:

- **3 a 5 criterios** observables; los `peso` deben **sumar 1.0** (±0.02).
- `claves`: 1–8 formas alternativas en que un alumno podría expresar el criterio
  (sinónimos, variantes sin acento, frases de 2–5 palabras). Son la base de la
  corrección automática cuando no hay un modelo de lenguaje disponible: escribir
  claves realistas, no la definición completa.
- `respuesta_modelo`: 4–8 frases, la respuesta que sacaría nota máxima. Debe servir
  de referencia al alumno y al corrector con IA.
- La consigna debe pedir **explicación/justificación**, no una lista de nombres:
  mejor "explicá por qué" o "compará y justificá" que "nombrá las tácticas".
- `tiempo_sugerido_min`: 3 a 8 minutos.
- Cada pregunta debe poder responderse en **5–10 líneas**.

## 5. Control de calidad (obligatorio antes de entregar)

```bash
python scripts/validate_bank.py content/bank/mc/mi-archivo.json
python scripts/validate_bank.py --estricto-paginas
```

El validador comprueba: esquema, ids únicos, opciones duplicadas, una sola correcta,
`porque_no` en distractores, pesos que suman 1, PDFs existentes y páginas dentro de
rango (con `--estricto-paginas`). Corregir **todos** los errores; las advertencias
también conviene resolverlas.

Checklist final:

- [ ] Cada pregunta se responde con el material del curso, no con conocimiento general.
- [ ] La respuesta correcta es **inequívocamente** correcta y una sola.
- [ ] Los distractores son plausibles y cada uno tiene su `porque_no`.
- [ ] La `fuente` apunta al PDF y página donde está el concepto.
- [ ] No hay preguntas repetidas ni casi repetidas (mismo concepto con otras palabras).
- [ ] El español es neutro/rioplatense, sin errores de tipeo, sin "Todas las anteriores".
- [ ] `python scripts/validate_bank.py` termina sin errores.
