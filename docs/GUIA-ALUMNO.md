# Guía rápida para practicar

Todo corre en tu computadora. No hace falta crear cuentas, ni subir nada a internet.

---

## 1. Qué necesitás

| Requisito | Detalle |
|---|---|
| **Python 3.9 o superior** | Es lo único obligatorio. En Windows, instalalo desde [python.org](https://www.python.org/downloads/) marcando **“Add python.exe to PATH”**. |
| **El repositorio** | `git clone <url>` o descargar el ZIP y descomprimirlo. |
| **Un navegador** | Chrome, Edge, Firefox o Safari. |
| **Ollama (opcional)** | Solo si querés corrección de desarrollo con un modelo local. Sin esto, la app funciona igual. |

Comprobá Python antes de empezar:

```bash
python --version        # Windows también: py -3 --version
```

Si no aparece la versión, instalá Python y volvé a abrir la terminal.

---

## 2. Paso a paso (interfaz web)

1. **Abrí una terminal en la carpeta del repositorio.**
   En Windows: clic derecho sobre la carpeta → “Abrir en Terminal”. En macOS/Linux: `cd` hasta la carpeta.
2. **Arrancá el quiz:**

   ```bash
   python -m quiz servir
   ```

   En Windows también podés hacer **doble clic en `iniciar.cmd`**; usa el lanzador `py` si está disponible.
   En macOS/Linux: `bash iniciar.sh` (o `./iniciar.sh`).
3. **Se abre el navegador solo** en <http://127.0.0.1:8765>. Si no se abre, entrá a esa dirección a mano.
4. **Elegí el modo** y tocá **“Comenzar intento”**:
   - **Examen completo:** 30 de múltiple opción + 5 de desarrollo, 100 minutos sugeridos, 60/40.
   - **Práctica rápida:** 5 a 20 preguntas con la respuesta y la explicación al instante.
   - **Por tema:** elegís un tema, cuántas de múltiple opción y cuántas de desarrollo.
5. **Respondé:**
   - Múltiple opción: clic en la opción o teclas `A`–`D` (también `1`–`4`).
   - Desarrollo: escribí en el cuadro; abajo ves el contador de palabras. Se guarda solo.
   - Navegá con **Anterior / Siguiente**, las flechas del teclado o el mapa de números.
6. **“Finalizar”** (o “Finalizar y corregir” en la última pregunta) → corrección.
7. **Mirá el resultado:** nota sobre 100 y sobre 10, desglose **por tema**, y cada pregunta con:
   - tu elección y la correcta, `por qué` falla cada distractor y la **fuente** (PDF y página);
   - en desarrollo, qué criterios cubriste, cuáles faltaron, la devolución y la **respuesta modelo**.
8. **“Descargar boleta (.md)”** guarda el intento en `examenes/`. En **Historial** podés volver a abrir cualquier intento anterior.

> Si cerrás el navegador a mitad de un intento, al volver aparece un aviso para **retomarlo** con las respuestas guardadas (dura 24 horas).

---

## 3. Si querés IA local para corregir el desarrollo (opcional)

La corrección por criterios y palabras clave **ya funciona sin instalar nada**. Si querés una
devolución más fina:

```bash
# 1. Instalar Ollama desde https://ollama.com
# 2. Bajar un modelo (una sola vez, requiere internet)
ollama pull qwen2.5:7b-instruct

# 3. Reiniciar el quiz y recargar la página
python -m quiz servir
```

Arriba a la derecha tiene que decir **“IA local: qwen2.5:7b-instruct”**. Si dice “apagada”, la app
sigue corrigiendo por criterios: no se rompe nada. Con 8 GB de RAM andá por `qwen2.5:3b-instruct`;
con 16 GB, `qwen2.5:7b-instruct` o `llama3.1:8b`.

Para usar LM Studio o llama.cpp, copiá `.env.example` como `.env` y completá `QUIZ_LLM_PROVEEDOR=openai`
y `QUIZ_LLM_URL`. El interruptor **“Usar el modelo local…”** de la pantalla de inicio permite
corregir sin IA aunque esté disponible.

---

## 4. Sin interfaz (terminal)

```bash
python -m quiz examen                 # examen completo interactivo
python -m quiz examen --temas nosql   # un solo tema
python -m quiz estudiar --tema rest --cantidad 10   # práctica con corrección inmediata
python -m quiz generar --seed 7       # examen imprimible en examenes/ (Markdown)
python -m quiz estadisticas           # cuántas preguntas hay por tema
```

`--seed 42` genera siempre el mismo examen (sirve para comparar entre compañeros).

---

## 5. Problemas comunes

| Síntoma | Solución |
|---|---|
| `python` no se reconoce | Probá `py -3 -m quiz servir` (Windows) o `python3 -m quiz servir`. Reinstalá Python marcando “Add to PATH”. |
| El puerto está ocupado | `python -m quiz servir --puerto 8766` y abrí esa dirección. |
| “IA local: apagada” | Normal si Ollama no está corriendo o el modelo tiene otro nombre. La corrección por criterios sigue andando. |
| No veo mi intento anterior | Quedan en `examenes/` (JSON y Markdown) y en la pestaña **Historial**. |
| Acentos raros en la consola de Windows | `chcp 65001` o usá Windows Terminal. La web no tiene ese problema. |
| Quiero borrar todo y empezar de cero | Borrá el contenido de `examenes/`; las preguntas están en `content/bank/`. |

---

## 6. Cómo aprovecharlo

1. Hacé **un examen completo** cronometrado, sin mirar el material.
2. En resultados, ordená los temas por porcentaje: los que quedaron abajo son la prioridad.
3. Usá **“Por tema”** en esos temas y leé siempre la explicación, el `por qué` de los distractores
   y la fuente antes de pasar a la siguiente.
4. Para desarrollo, compará tu respuesta con la **respuesta modelo** y fijate qué criterios no
   aparecieron: eso es exactamente lo que el docente espera leer.
5. Repetí a los dos o tres días: el banco rota las preguntas, así que no vas a ver lo mismo.

La corrección automática es una ayuda para estudiar; la referencia final es siempre el material de
la cátedra. El detalle técnico del proyecto está en el [`README`](../README.md) y en
[`COMO-FUNCIONA`](COMO-FUNCIONA.md).
