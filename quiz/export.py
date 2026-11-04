"""Exportación a Markdown: examen para imprimir y boleta de corrección."""

from __future__ import annotations

from typing import Any, Dict, List

from . import bank, util
from .bank import Banco
from .sampler import Examen

DIFICULTAD = {"facil": "fácil", "media": "media", "dificil": "difícil"}


def _titulo(examen: Examen) -> str:
    nombre = (examen.especificacion or {}).get("nombre") or "Examen TAIS"
    return f"{nombre} — {examen.id}"


def examen_a_markdown(examen: Examen, banco: Banco, *, incluir_soluciones: bool = False) -> str:
    """Genera el examen en Markdown (sin respuestas, salvo que se pidan)."""
    lineas: List[str] = []
    lineas.append(f"# {_titulo(examen)}")
    lineas.append("")
    lineas.append(f"- **Creado:** {examen.creado}")
    lineas.append(f"- **Múltiple opción:** {len(examen.mc)} preguntas")
    lineas.append(f"- **Desarrollo:** {len(examen.desarrollo)} preguntas")
    tiempo = (examen.especificacion or {}).get("tiempo_limite_min")
    if tiempo:
        lineas.append(f"- **Tiempo sugerido:** {tiempo} minutos")
    lineas.append("")
    lineas.append("---")
    lineas.append("")

    if examen.mc:
        lineas.append("## Parte A — Múltiple opción")
        lineas.append("")
        for numero, item in enumerate(examen.mc, 1):
            pregunta = banco.obtener_mc(item["id"])
            lineas.append(f"**{numero}.** {pregunta.pregunta}")
            lineas.append("")
            for pos, original in enumerate(item["orden"]):
                opcion = pregunta.opciones[original]
                lineas.append(f"- **{letra(pos)}.** {opcion.texto}")
            lineas.append("")
            if incluir_soluciones:
                correcta = item["orden"].index(pregunta.indice_correcto)
                lineas.append(f"> ✅ Respuesta: **{letra(correcta)}**. {pregunta.explicacion}")
                lineas.append(">")
                lineas.append(f"> Fuente: {pregunta.referencia()}")
                lineas.append("")

    if examen.desarrollo:
        lineas.append("## Parte B — Desarrollo corto")
        lineas.append("")
        for indice, id_pregunta in enumerate(examen.desarrollo, 1):
            pregunta = banco.obtener_desarrollo(id_pregunta)
            lineas.append(f"**{len(examen.mc) + indice}.** {pregunta.pregunta}")
            lineas.append("")
            lineas.append(f"*Tiempo sugerido: {pregunta.tiempo_sugerido_min} minutos.*")
            lineas.append("")
            if incluir_soluciones:
                lineas.append("**Respuesta modelo:**")
                lineas.append("")
                lineas.append(pregunta.respuesta_modelo)
                lineas.append("")
                lineas.append("**Criterios de evaluación:**")
                for criterio in pregunta.criterios:
                    lineas.append(f"- ({criterio.peso:.2f}) {criterio.descripcion}")
                lineas.append("")
                lineas.append(f"> Fuente: {pregunta.referencia()}")
                lineas.append("")

    if not incluir_soluciones:
        lineas.append("---")
        lineas.append("")
        lineas.append("### Hoja de respuestas")
        lineas.append("")
        if examen.mc:
            lineas.append("| Pregunta | A | B | C | D |")
            lineas.append("|---|---|---|---|---|")
            for numero in range(1, len(examen.mc) + 1):
                lineas.append(f"| {numero} | ☐ | ☐ | ☐ | ☐ |")
            lineas.append("")

    lineas.append("")
    lineas.append(f"*Generado por TAIS Quiz — {util.ahora_iso()}*")
    lineas.append("")
    return "\n".join(lineas)


def resultado_a_markdown(resultado: Dict[str, Any], banco: Banco) -> str:
    """Genera la boleta de corrección en Markdown."""
    resumen = resultado.get("resumen") or {}
    lineas: List[str] = []
    lineas.append(f"# Boleta de corrección — {resultado.get('examen_id', '')}")
    lineas.append("")
    lineas.append(f"**Corregido:** {util.ahora_iso()}")
    lineas.append(f"**Modo de corrección de desarrollo:** {resumen.get('modo_correccion', 'heuristica')}")
    lineas.append("")
    lineas.append("## Resultado")
    lineas.append("")
    lineas.append("| Componente | Resultado |")
    lineas.append("|---|---|")
    lineas.append(f"| Múltiple opción | {resumen.get('mc_aciertos', 0)}/{resumen.get('mc_total', 0)} ({resumen.get('mc_porcentaje', 0)} %) |")
    lineas.append(
        f"| Desarrollo | {resumen.get('desarrollo_puntaje', 0)}/{resumen.get('desarrollo_total', 0)} "
        f"({resumen.get('desarrollo_porcentaje', 0)} %) |"
    )
    lineas.append(f"| **Nota** | **{resumen.get('nota_100', 0)}/100 ({resumen.get('nota_10', 0)}/10) — {resumen.get('nivel', '')}** |")
    lineas.append("")

    por_tema = resumen.get("por_tema") or {}
    if por_tema:
        lineas.append("### Por tema")
        lineas.append("")
        lineas.append("| Tema | Resultado |")
        lineas.append("|---|---|")
        for tema, fila in por_tema.items():
            lineas.append(f"| {fila.get('nombre') or bank.TEMAS.get(tema, tema)} | {fila.get('porcentaje', 0)} % |")
        lineas.append("")

    if resultado.get("mc"):
        lineas.append("## Parte A — Múltiple opción")
        lineas.append("")
        for numero, item in enumerate(resultado["mc"], 1):
            marca = "✅" if item["es_correcta"] else ("⬜" if item.get("elegida") is None else "❌")
            lineas.append(f"### {numero}. {item['pregunta']}")
            lineas.append("")
            lineas.append(f"{marca} **Resultado:** {'correcta' if item['es_correcta'] else 'incorrecta'}"
                          + (f" · respondiste {letra(item['elegida'])}" if item.get("elegida") is not None else " · sin responder"))
            lineas.append("")
            for opcion in item["opciones"]:
                prefijo = "**[correcta]**" if opcion["es_correcta"] else ""
                lineas.append(f"- **{opcion['letra']}.** {opcion['texto']} {prefijo}".rstrip())
                if not opcion["es_correcta"] and opcion.get("porque_no"):
                    lineas.append(f"  - {opcion['porque_no']}")
            lineas.append("")
            lineas.append(f"> {item['explicacion']}")
            lineas.append(">")
            lineas.append(f"> Fuente: {item.get('referencia', '')}")
            lineas.append("")

    if resultado.get("desarrollo"):
        lineas.append("## Parte B — Desarrollo corto")
        lineas.append("")
        for numero, item in enumerate(resultado["desarrollo"], 1):
            correccion = item["correccion"]
            lineas.append(f"### {numero}. {item['pregunta']}")
            lineas.append("")
            lineas.append(f"**Puntaje:** {correccion['puntaje'] * 100:.0f} % · modo: {correccion['modo']}")
            lineas.append("")
            lineas.append("**Tu respuesta:**")
            lineas.append("")
            lineas.append("> " + (item["respuesta"].replace("\n", "\n> ") if item.get("respuesta") else "*(sin responder)*"))
            lineas.append("")
            lineas.append("**Devolución:** " + correccion.get("comentario", ""))
            lineas.append("")
            lineas.append("**Criterios:**")
            for criterio in correccion.get("criterios", []):
                marca = "✅" if criterio.get("cumplido") else "⬜"
                lineas.append(f"- {marca} ({criterio['peso']:.2f}) {criterio['descripcion']} — {criterio.get('detalle', '')}")
            lineas.append("")
            lineas.append("**Respuesta modelo:**")
            lineas.append("")
            lineas.append(item["respuesta_modelo"])
            lineas.append("")
            lineas.append(f"> Fuente: {item.get('referencia', '')}")
            lineas.append("")

    lineas.append("---")
    lineas.append("")
    lineas.append("*Generado por TAIS Quiz. La corrección automática es una ayuda para estudiar: "
                  "siempre conviene contrastar con la respuesta modelo y el material.*")
    lineas.append("")
    return "\n".join(lineas)


def letra(indice: int) -> str:
    return "ABCDE"[indice] if isinstance(indice, int) and 0 <= indice < 5 else "?"


def guardar_boleta(resultado: Dict[str, Any], banco: Banco) -> str:
    """Guarda la boleta en examenes/ y devuelve la ruta."""
    texto = resultado_a_markdown(resultado, banco)
    ruta = util.EXAMENES_DIR / f"boleta-{resultado.get('examen_id', 'examen')}.md"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8", newline="\n")
    return str(ruta)
