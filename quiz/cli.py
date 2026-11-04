"""Interfaz de línea de comandos.

Ejemplos:

    python -m quiz servir                    # abre la interfaz web
    python -m quiz examen                    # examen completo interactivo
    python -m quiz examen --temas nosql      # examen de un solo tema
    python -m quiz generar --seed 42         # genera un examen imprimible
    python -m quiz estudiar --tema rest      # práctica con corrección inmediata
    python -m quiz estadisticas              # cobertura del banco
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from . import bank, export, grader, sampler, util
from .bank import Banco, BancoInvalido


# ---------------------------------------------------------------------------
# Utilidades de consola
# ---------------------------------------------------------------------------


def _cargar_banco() -> Banco:
    try:
        return bank.cargar_banco()
    except BancoInvalido as exc:
        print(util.C.rojo("El banco de preguntas tiene problemas:"))
        for error in exc.errores:
            print("  - " + error)
        print()
        print("Corregí los archivos de content/bank/ y volvé a intentar.")
        print("Podés validar con: python scripts/validate_bank.py")
        raise SystemExit(2)


def _codigo_error(mensaje: str) -> int:
    print(util.C.rojo("Error: " + mensaje))
    return 1


def _spec(args: argparse.Namespace) -> sampler.Especificacion:
    spec = sampler.Especificacion.cargar()
    temas = getattr(args, "temas", None)
    if temas:
        desconocidos = [t for t in temas if t not in bank.TEMAS]
        if desconocidos:
            raise SystemExit(_codigo_error("temas desconocidos: " + ", ".join(desconocidos)))
        spec = spec.ajustar(temas=temas)
    if getattr(args, "mc", None) is not None:
        spec = _redistribuir_mc(spec, args.mc)
    if getattr(args, "desarrollo", None) is not None:
        spec = spec.ajustar(desarrollo_total=args.desarrollo)
    if getattr(args, "sin_mezclar", False):
        spec.mezclar_opciones = False
    return spec


def _redistribuir_mc(spec: sampler.Especificacion, total: int) -> sampler.Especificacion:
    temas = list(spec.mc_por_tema) or list(bank.TEMAS)
    total = max(0, int(total))
    base, resto = divmod(total, len(temas))
    nuevo = {tema: base + (1 if i < resto else 0) for i, tema in enumerate(temas)}
    return spec.ajustar(mc_por_tema=nuevo)


def _cronometro(inicio: float) -> str:
    segundos = int(time.time() - inicio)
    return f"{segundos // 60:02d}:{segundos % 60:02d}"


def _encabezado(texto: str, ancho: int = 76) -> None:
    print()
    print(util.C.cian("=" * ancho))
    print(util.C.negrita(texto))
    print(util.C.cian("=" * ancho))


def _chip(tema: str, dificultad: str) -> str:
    return util.C.tenue(f"[{bank.TEMAS.get(tema, tema)} · {dificultad}]")


def _mostrar_mc(pregunta, orden: Sequence[int], numero: int, total: int) -> None:
    print()
    referencia = f"Pregunta {numero}" + (f"/{total}" if total else "")
    print(util.C.tenue(referencia + "  ") + _chip(pregunta.tema, pregunta.dificultad))
    print(util.C.negrita(pregunta.pregunta))
    print()
    for pos, original in enumerate(orden):
        print(f"  {util.C.amarillo('ABCDE'[pos])}) {pregunta.opciones[original].texto}")


def _mostrar_desarrollo(pregunta, numero: int, total: int) -> None:
    referencia = f"Pregunta {numero}" + (f"/{total}" if total else "")
    print()
    print(
        util.C.tenue(f"{referencia} (desarrollo, {pregunta.tiempo_sugerido_min} min)  ")
        + _chip(pregunta.tema, pregunta.dificultad)
    )
    print(util.C.negrita(pregunta.pregunta))
    print()


def _marcar_opcion(item: Dict[str, Any], letra: str) -> str:
    elegida = item.get("elegida")
    if elegida is not None and export.letra(elegida) == letra:
        return util.C.rojo("[XX]")
    return util.C.tenue("[--]")


def _imprimir_resumen(resultado: Dict[str, Any]) -> None:
    r = resultado["resumen"]
    aciertos = f"{r['mc_aciertos']}/{r['mc_total']}"
    desarrollo = f"{r['desarrollo_puntaje']}/{r['desarrollo_total']}"
    nota = f"{r['nota_100']}/100 ({r['nota_10']}/10)"

    _encabezado("Resultado")
    print(f"  Múltiple opción : {util.C.negrita(aciertos)} ({r['mc_porcentaje']}%)")
    print(f"  Desarrollo      : {util.C.negrita(desarrollo)} ({r['desarrollo_porcentaje']}%)")
    print()
    print(f"  {util.barra(r['nota_100'] / 100, 30)}  {util.C.negrita(nota)} - {r['nivel']}")
    print(util.C.tenue("  Corrección de desarrollo: " + str(r["modo_correccion"])))

    por_tema = r.get("por_tema") or {}
    if por_tema:
        print()
        print(util.C.tenue("  Por tema:"))
        for tema, fila in por_tema.items():
            nombre = bank.TEMAS.get(tema, tema)
            print(
                f"    {nombre:<44}{fila['porcentaje']:>5}%   "
                f"{util.barra(fila['porcentaje'] / 100, 12)}"
            )


def _revisar_mc(item: Dict[str, Any], numero: int) -> None:
    print()
    nombre = bank.TEMAS.get(item["tema"], item["tema"])
    print(util.C.tenue(f"{numero}. ") + util.C.negrita(item["pregunta"]) + "  " + util.C.tenue(f"[{nombre}]"))
    for opcion in item["opciones"]:
        if opcion["es_correcta"]:
            marca = util.C.verde("[OK]")
        else:
            marca = _marcar_opcion(item, opcion["letra"])
        print(f"   {marca} {opcion['letra']}) {opcion['texto']}")
    print("   " + util.C.tenue("Por qué: ") + item["explicacion"])
    for opcion in item["opciones"]:
        if not opcion["es_correcta"] and opcion.get("porque_no"):
            print("   " + util.C.tenue(f"{opcion['letra']}) no: {opcion['porque_no']}"))
    print("   " + util.C.tenue("Fuente: " + item.get("referencia", "")))


def _revisar_desarrollo(item: Dict[str, Any], numero: int) -> None:
    correccion = item["correccion"]
    nombre = bank.TEMAS.get(item["tema"], item["tema"])
    print()
    print(util.C.tenue(f"{numero}. ") + util.C.negrita(item["pregunta"]) + "  " + util.C.tenue(f"[{nombre}]"))
    puntaje = f"{correccion['puntaje'] * 100:.0f}%"
    color = util.C.verde if correccion["puntaje"] >= 0.6 else util.C.amarillo
    print("   Puntaje: " + color(puntaje) + f" ({correccion['modo']})")
    print("   " + correccion["comentario"])
    for criterio in correccion["criterios"]:
        marca = util.C.verde("[SI]") if criterio["cumplido"] else util.C.tenue("[NO]")
        print(f"   {marca} ({criterio['peso']:.2f}) {criterio['descripcion']} - {criterio['detalle']}")
    print()
    print("   " + util.C.tenue("Respuesta modelo:"))
    for linea in item["respuesta_modelo"].splitlines():
        print("     " + linea)
    print("   " + util.C.tenue("Fuente: " + item.get("referencia", "")))


def _confirmar(pregunta: str, defecto: bool = False) -> bool:
    sufijo = " [S/n]: " if defecto else " [s/N]: "
    try:
        respuesta = input(pregunta + sufijo).strip().lower()
    except EOFError:
        return defecto
    if not respuesta:
        return defecto
    return respuesta in {"s", "si", "sí", "y", "yes"}


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------


def cmd_servir(args: argparse.Namespace) -> int:
    from . import web

    return web.servir(host=args.host, puerto=args.puerto, abrir_navegador=not args.sin_navegador)


def cmd_generar(args: argparse.Namespace) -> int:
    banco = _cargar_banco()
    spec = _spec(args)
    try:
        examen = sampler.generar_examen(banco, spec, seed=args.seed)
    except ValueError as exc:
        return _codigo_error(str(exc))

    if args.formato == "json":
        # JSON con el estado del examen (ids y orden de opciones): sirve para
        # corregirlo después con `python -m quiz corregir`.
        datos = examen.como_dict()
        texto = json.dumps(datos, ensure_ascii=False, indent=2)
        destino = Path(args.salida) if args.salida else None
        if destino:
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(texto + "\n", encoding="utf-8", newline="\n")
            print(util.C.verde(f"Examen guardado en {destino}"))
        else:
            print(texto)
        if args.soluciones:
            print(util.C.tenue("Nota: el JSON no incluye soluciones; usá --formato md --soluciones para verlas."))
        print(util.C.tenue(
            "Para corregirlo en lote: python -m quiz corregir --examen <archivo> --respuestas respuestas.json"
        ))
        return 0

    texto = export.examen_a_markdown(examen, banco, incluir_soluciones=args.soluciones)
    destino = Path(args.salida) if args.salida else util.EXAMENES_DIR / f"{examen.id}.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8", newline="\n")
    print(util.C.verde(f"Examen generado: {destino}"))
    detalle = f"  {len(examen.mc)} múltiple opción + {len(examen.desarrollo)} desarrollo · seed {examen.seed}"
    print(util.C.tenue(detalle))
    return 0


def _pedir_indice(pregunta: str, cantidad: int) -> Optional[int]:
    """Lee A/B/C/D o 1-4. Devuelve None si se salta."""
    while True:
        try:
            entrada = input(pregunta).strip().lower()
        except EOFError:
            return None
        if entrada in {"s", "saltar", ""}:
            return None
        if entrada in {"a", "b", "c", "d", "e"}:
            indice = "abcde".index(entrada)
        elif entrada.isdigit():
            indice = int(entrada) - 1
        else:
            print(util.C.amarillo("  Ingresá A, B, C, D, E o 1-5."))
            continue
        if not 0 <= indice < cantidad:
            print(util.C.amarillo("  Opción fuera de rango."))
            continue
        return indice


def cmd_examen(args: argparse.Namespace) -> int:
    banco = _cargar_banco()
    spec = _spec(args)
    try:
        examen = sampler.generar_examen(banco, spec, seed=args.seed)
    except ValueError as exc:
        return _codigo_error(str(exc))

    print()
    print(util.C.magenta("TAIS Quiz - examen"))
    detalle = (
        f"{len(examen.mc)} múltiple opción + {len(examen.desarrollo)} desarrollo · "
        f"tiempo sugerido {spec.tiempo_limite_min} min · seed {examen.seed}"
    )
    print(util.C.tenue(detalle))
    print(util.C.tenue("Respondé con A/B/C/D (o 1-4). 's' = saltar, 'q' = abandonar."))

    respuestas_mc: Dict[str, int] = {}
    respuestas_dev: Dict[str, str] = {}
    inicio = time.time()

    try:
        for numero, item in enumerate(examen.mc, 1):
            pregunta = banco.obtener_mc(item["id"])
            orden = item["orden"]
            _mostrar_mc(pregunta, orden, numero, len(examen.mc))
            indice = _pedir_indice("\n  Respuesta: ", len(orden))
            if indice is not None:
                respuestas_mc[pregunta.id] = indice

        for posicion, id_pregunta in enumerate(examen.desarrollo, 1):
            pregunta = banco.obtener_desarrollo(id_pregunta)
            total = len(examen.mc) + len(examen.desarrollo)
            _mostrar_desarrollo(pregunta, len(examen.mc) + posicion, total)
            texto = util.leer_respuesta_multilinea("  Tu respuesta")
            if texto:
                respuestas_dev[pregunta.id] = texto
    except KeyboardInterrupt:
        print()
        print(util.C.amarillo("Interrumpido. No se corrigió el examen."))
        return 1

    print()
    print(util.C.tenue("Tiempo utilizado: " + _cronometro(inicio)))
    print(util.C.tenue("Corrigiendo..."))
    resultado = grader.corregir_examen(banco, examen, {"mc": respuestas_mc, "desarrollo": respuestas_dev})

    _imprimir_resumen(resultado)

    revisar_todo = args.revisar_todo
    if not revisar_todo and sys.stdin.isatty():
        revisar_todo = _confirmar("¿Querés ver también las preguntas correctas?", defecto=False)

    _encabezado("Revisión")
    numero = 0
    for item in resultado["mc"]:
        numero += 1
        if item["es_correcta"] and not revisar_todo:
            continue
        _revisar_mc(item, numero)
    for item in resultado["desarrollo"]:
        numero += 1
        _revisar_desarrollo(item, numero)

    ruta = export.guardar_boleta(resultado, banco)
    print()
    print(util.C.verde(f"Boleta guardada en {ruta}"))
    return 0


def cmd_estudiar(args: argparse.Namespace) -> int:
    banco = _cargar_banco()
    tema = args.tema
    if tema and tema not in bank.TEMAS:
        return _codigo_error("tema desconocido: " + tema)
    pool_mc = banco.mc_de(tema) if tema else banco.mc
    pool_dev = banco.desarrollo_de(tema) if tema else banco.desarrollo
    if args.solo_desarrollo and not pool_dev:
        return _codigo_error("no hay preguntas de desarrollo para practicar")
    if not args.solo_desarrollo and not pool_mc:
        return _codigo_error("no hay preguntas de múltiple opción para practicar")

    print()
    print(util.C.magenta("TAIS Quiz - modo estudio"))
    print(util.C.tenue("Corrección inmediata. 'q' para salir."))

    practicadas = 0
    aciertos = 0
    limite = args.cantidad
    try:
        while limite == 0 or practicadas < limite:
            quiere_desarrollo = bool(pool_dev) and (
                args.solo_desarrollo or (args.incluir_desarrollo and practicadas % 4 == 3)
            )
            if quiere_desarrollo:
                pregunta = random.choice(pool_dev)
                _mostrar_desarrollo(pregunta, practicadas + 1, limite)
                texto = util.leer_respuesta_multilinea("  Tu respuesta")
                if not texto:
                    continue
                correccion = grader.corregir_una_desarrollo(banco, pregunta.id, texto)
                practicadas += 1
                c = correccion["correccion"]
                puntaje = f"{c['puntaje'] * 100:.0f}%"
                print()
                print(f"  Puntaje: {puntaje} ({c['modo']}) - {c['comentario']}")
                for criterio in c["criterios"]:
                    marca = util.C.verde("[SI]") if criterio["cumplido"] else util.C.tenue("[NO]")
                    print(f"  {marca} ({criterio['peso']:.2f}) {criterio['descripcion']}")
                print(util.C.tenue("  Respuesta modelo:"))
                for linea in correccion["respuesta_modelo"].splitlines():
                    print("    " + linea)
                print(util.C.tenue("  Fuente: " + correccion["referencia"]))
                try:
                    if input("\n  Enter para seguir (q = salir): ").strip().lower() in {"q", "salir"}:
                        break
                except EOFError:
                    break
                continue

            pregunta = random.choice(pool_mc)
            orden = list(range(len(pregunta.opciones)))
            random.shuffle(orden)
            _mostrar_mc(pregunta, orden, practicadas + 1, limite)
            indice = _pedir_indice("\n  Respuesta (q = salir): ", len(orden))
            if indice is None:
                try:
                    if input("  ¿Salir? [s/N]: ").strip().lower() in {"s", "si", "sí"}:
                        break
                except EOFError:
                    break
                continue
            correcta = orden.index(pregunta.indice_correcto)
            practicadas += 1
            if indice == correcta:
                aciertos += 1
                print(util.C.verde("  Correcta."))
            else:
                print(util.C.rojo(f"  Incorrecta. La correcta era {export.letra(correcta)}."))
            print("  " + pregunta.explicacion)
            for pos, original in enumerate(orden):
                opcion = pregunta.opciones[original]
                if not opcion.correcta and opcion.porque_no:
                    print(util.C.tenue(f"  {export.letra(pos)}) no: {opcion.porque_no}"))
            print(util.C.tenue("  Fuente: " + pregunta.referencia()))
            if limite == 0:
                try:
                    if input("\n  Enter para seguir (q = salir): ").strip().lower() in {"q", "salir"}:
                        break
                except EOFError:
                    break
    except KeyboardInterrupt:
        print()

    if practicadas:
        print()
        resumen = f"Practicaste {practicadas} preguntas."
        if aciertos:
            resumen += f" Aciertos en múltiple opción: {aciertos}."
        print(util.C.tenue(resumen))
    return 0


def cmd_corregir(args: argparse.Namespace) -> int:
    banco = _cargar_banco()
    try:
        ruta_examen = Path(args.examen)
        if ruta_examen.is_file():
            examen = sampler.Examen.desde_dict(util.cargar_json(ruta_examen))
        else:
            examen = sampler.Examen.cargar(args.examen)
    except (FileNotFoundError, KeyError) as exc:
        return _codigo_error(f"no se encontró el examen: {exc}")

    try:
        respuestas = util.cargar_json(Path(args.respuestas))
    except (OSError, json.JSONDecodeError) as exc:
        return _codigo_error(f"no se pudo leer el archivo de respuestas: {exc}")

    resultado = grader.corregir_examen(banco, examen, respuestas)
    _imprimir_resumen(resultado)
    _encabezado("Revisión")
    for numero, item in enumerate(resultado["mc"], 1):
        _revisar_mc(item, numero)
    for numero, item in enumerate(resultado["desarrollo"], len(resultado["mc"]) + 1):
        _revisar_desarrollo(item, numero)
    ruta = export.guardar_boleta(resultado, banco)
    print()
    print(util.C.verde(f"Boleta guardada en {ruta}"))
    return 0


def cmd_estadisticas(args: argparse.Namespace) -> int:
    banco = _cargar_banco()
    stats = banco.estadisticas()
    _encabezado("Cobertura del banco")
    print(f"  Archivos: {len(stats['archivos'])}")
    print(f"  Múltiple opción: {stats['total_mc']}  |  Desarrollo: {stats['total_desarrollo']}")
    print()
    print(f"  {'Tema':<44}{'MC':>5}{'Dev':>6}{'facil':>7}{'media':>7}{'dificil':>9}")
    print("  " + "-" * 76)
    for tema, fila in stats["por_tema"].items():
        print(
            f"  {bank.TEMAS[tema]:<44}{fila['mc']:>5}{fila['desarrollo']:>6}"
            f"{fila['facil']:>7}{fila['media']:>7}{fila['dificil']:>9}"
        )
    spec = sampler.Especificacion.cargar()
    print()
    faltantes = {
        tema: cantidad
        for tema, cantidad in spec.mc_por_tema.items()
        if stats["por_tema"].get(tema, {}).get("mc", 0) < cantidad
    }
    if faltantes:
        detalle = ", ".join(f"{t} ({c})" for t, c in faltantes.items())
        print(util.C.amarillo("  Aviso: no hay preguntas suficientes para el examen completo en: " + detalle))
    else:
        # Cuántos exámenes completos se pueden armar sin repetir ninguna pregunta.
        cupo = min(stats["por_tema"][t]["mc"] // c for t, c in spec.mc_por_tema.items())
        print(util.C.verde(f"  El banco alcanza para {cupo} exámenes completos sin repetir preguntas."))
    return 0


def cmd_validar(args: argparse.Namespace) -> int:
    rutas = bank.archivos_banco()
    informe = bank.validar_archivos(rutas, estricto_paginas=args.estricto_paginas)
    for adv in informe["advertencias"]:
        print(util.C.amarillo("AVISO: " + adv))
    for err in informe["errores"]:
        print(util.C.rojo("ERROR: " + err))
    if informe["ok"]:
        print(util.C.verde(f"OK: {informe['total_preguntas']} preguntas válidas en {len(rutas)} archivos."))
        return 0
    print(util.C.rojo(f"{len(informe['errores'])} error(es)."))
    return 1


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="quiz",
        description="Generador de exámenes de TAIS (Taller de Tendencias Aplicadas de Ing. de Software).",
        epilog="Ejemplos: python -m quiz servir | python -m quiz examen --temas nosql --mc 10",
    )
    sub = parser.add_subparsers(dest="comando", metavar="comando")

    p_servir = sub.add_parser("servir", aliases=["serve", "web"], help="levanta la interfaz web")
    p_servir.add_argument("--host", default="127.0.0.1", help="interfaz de red (por defecto 127.0.0.1)")
    p_servir.add_argument("--puerto", type=int, default=8765, help="puerto (por defecto 8765)")
    p_servir.add_argument("--sin-navegador", action="store_true", help="no abrir el navegador")
    p_servir.set_defaults(func=cmd_servir)

    p_examen = sub.add_parser("examen", help="examen interactivo en la terminal")
    p_examen.add_argument("--temas", nargs="+", help="temas a incluir (por defecto todos)")
    p_examen.add_argument("--mc", type=int, help="cantidad total de preguntas de múltiple opción")
    p_examen.add_argument("--desarrollo", type=int, help="cantidad de preguntas de desarrollo")
    p_examen.add_argument("--seed", type=int, help="semilla para reproducir el mismo examen")
    p_examen.add_argument("--sin-mezclar", action="store_true", help="no mezclar el orden de las opciones")
    p_examen.add_argument("--revisar-todo", action="store_true", help="revisar también las correctas")
    p_examen.set_defaults(func=cmd_examen)

    p_generar = sub.add_parser("generar", help="genera un examen imprimible (Markdown o JSON)")
    p_generar.add_argument("--temas", nargs="+", help="temas a incluir")
    p_generar.add_argument("--mc", type=int, help="cantidad total de múltiple opción")
    p_generar.add_argument("--desarrollo", type=int, help="cantidad de desarrollo")
    p_generar.add_argument("--seed", type=int, help="semilla")
    p_generar.add_argument("--sin-mezclar", action="store_true", help="no mezclar opciones")
    p_generar.add_argument("--soluciones", action="store_true", help="incluir respuestas y explicaciones")
    p_generar.add_argument("--formato", choices=["md", "json"], default="md")
    p_generar.add_argument("--salida", help="archivo de destino")
    p_generar.set_defaults(func=cmd_generar)

    p_estudiar = sub.add_parser("estudiar", help="práctica con corrección inmediata")
    p_estudiar.add_argument("--tema", help="tema a practicar")
    p_estudiar.add_argument("--cantidad", type=int, default=10, help="cantidad de preguntas (0 = sin límite)")
    p_estudiar.add_argument("--solo-desarrollo", action="store_true", help="practicar solo desarrollo")
    p_estudiar.add_argument("--incluir-desarrollo", action="store_true", help="intercalar preguntas de desarrollo")
    p_estudiar.set_defaults(func=cmd_estudiar)

    p_corregir = sub.add_parser("corregir", help="corrige un examen desde archivos JSON")
    p_corregir.add_argument("--examen", required=True, help="id del examen o ruta al JSON")
    p_corregir.add_argument("--respuestas", required=True, help="JSON con las respuestas")
    p_corregir.set_defaults(func=cmd_corregir)

    p_stats = sub.add_parser("estadisticas", help="cobertura del banco de preguntas")
    p_stats.set_defaults(func=cmd_estadisticas)

    p_validar = sub.add_parser("validar", help="valida el banco de preguntas")
    p_validar.add_argument("--estricto-paginas", action="store_true", help="verificar páginas citadas")
    p_validar.set_defaults(func=cmd_validar)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    util.preparar_consola()
    parser = construir_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return int(args.func(args) or 0)
