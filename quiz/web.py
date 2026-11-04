"""Servidor web local (biblioteca estándar, sin dependencias).

Levanta la interfaz en http://127.0.0.1:8765 y expone una API JSON mínima.
"""

from __future__ import annotations

import json
import mimetypes
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse

from . import __version__, bank, export, grader, sampler, util
from .bank import Banco, BancoInvalido

LIMITE_CUERPO = 2 * 1024 * 1024  # 2 MB
MIME_EXTRA = {
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".md": "text/markdown; charset=utf-8",
}


class Estado:
    """Estado compartido del servidor."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.banco: Banco = bank.cargar_banco()
        self.especificacion = sampler.Especificacion.cargar()
        self.historial = sampler.Historial()
        self.corrector = grader.CorrectorAuto()
        self.examenes: Dict[str, sampler.Examen] = {}

    # -- exámenes ----------------------------------------------------------
    def guardar_examen(self, examen: sampler.Examen) -> None:
        with self.lock:
            self.examenes[examen.id] = examen
        try:
            examen.guardar()
        except OSError:
            pass

    def obtener_examen(self, id_examen: str) -> sampler.Examen:
        with self.lock:
            if id_examen in self.examenes:
                return self.examenes[id_examen]
        examen = sampler.Examen.cargar(id_examen)
        with self.lock:
            self.examenes[id_examen] = examen
        return examen

    # -- resultados --------------------------------------------------------
    def guardar_resultado(self, resultado: Dict[str, Any]) -> None:
        try:
            util.guardar_json(
                util.EXAMENES_DIR / f"{resultado['examen_id']}-resultado.json", resultado
            )
        except OSError:
            pass

    def obtener_resultado(self, id_examen: str) -> Optional[Dict[str, Any]]:
        ruta = util.EXAMENES_DIR / f"{id_examen}-resultado.json"
        if not ruta.is_file():
            return None
        try:
            return util.cargar_json(ruta)
        except (OSError, json.JSONDecodeError):
            return None

    def historial_resultados(self, limite: int = 40) -> List[Dict[str, Any]]:
        salida: List[Dict[str, Any]] = []
        if not util.EXAMENES_DIR.is_dir():
            return salida
        archivos = sorted(
            util.EXAMENES_DIR.glob("*-resultado.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:limite]
        for ruta in archivos:
            try:
                datos = util.cargar_json(ruta)
            except (OSError, json.JSONDecodeError):
                continue
            resumen = datos.get("resumen") or {}
            salida.append(
                {
                    "examen_id": datos.get("examen_id"),
                    "creado": datos.get("creado"),
                    "nota_100": resumen.get("nota_100"),
                    "nivel": resumen.get("nivel"),
                    "mc_aciertos": resumen.get("mc_aciertos"),
                    "mc_total": resumen.get("mc_total"),
                    "desarrollo_porcentaje": resumen.get("desarrollo_porcentaje"),
                    "nombre": (datos.get("especificacion") or {}).get("nombre", "Examen"),
                }
            )
        return salida

    # -- estado ------------------------------------------------------------
    def estado(self, *, refrescar_llm: bool = False) -> Dict[str, Any]:
        info = self.corrector.estado()
        if refrescar_llm:
            info = self.corrector.llm.estado(refrescar=True)
        return {
            "version": __version__,
            "especificacion": self.especificacion.como_dict(),
            "temas": [{"clave": t, "nombre": n} for t, n in bank.TEMAS.items()],
            "banco": self.banco.estadisticas(),
            "corrector": info,
        }


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def _int(valor: Any, defecto: int = 0) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return defecto


def _construir_especificacion(estado: Estado, cuerpo: Dict[str, Any]) -> sampler.Especificacion:
    spec = estado.especificacion.ajustar()
    temas = cuerpo.get("temas")
    if isinstance(temas, list) and temas:
        spec = spec.ajustar(temas=[str(t) for t in temas if t in bank.TEMAS])
    if isinstance(cuerpo.get("mc_por_tema"), dict) and cuerpo["mc_por_tema"]:
        spec = spec.ajustar(mc_por_tema={str(k): _int(v) for k, v in cuerpo["mc_por_tema"].items()})
    elif cuerpo.get("mc") is not None:
        total = _int(cuerpo.get("mc"), spec.total_mc)
        temas_actuales = list(spec.mc_por_tema) or list(bank.TEMAS)
        base, resto = divmod(max(0, total), len(temas_actuales))
        spec = spec.ajustar(
            mc_por_tema={
                tema: base + (1 if i < resto else 0) for i, tema in enumerate(temas_actuales)
            }
        )
    if cuerpo.get("desarrollo") is not None:
        spec = spec.ajustar(desarrollo_total=_int(cuerpo.get("desarrollo"), spec.desarrollo_total))
    if cuerpo.get("sin_mezclar"):
        spec.mezclar_opciones = False
    if cuerpo.get("tiempo_limite_min") is not None:
        spec.tiempo_limite_min = max(0, _int(cuerpo.get("tiempo_limite_min"), spec.tiempo_limite_min))
    return spec


class Manejador(BaseHTTPRequestHandler):
    server_version = f"TAISQuiz/{__version__}"
    estado: Estado  # se asigna al crear el servidor

    # -- utilidades --------------------------------------------------------
    def log_message(self, formato: str, *args: Any) -> None:  # silencio en consola
        pass

    def _json(self, datos: Any, estado: int = 200) -> None:
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(estado)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _error(self, mensaje: str, estado: int = 400) -> None:
        self._json({"error": mensaje}, estado)

    def _leer_json(self) -> Dict[str, Any]:
        largo = _int(self.headers.get("Content-Length"), 0)
        if largo <= 0:
            return {}
        if largo > LIMITE_CUERPO:
            raise ValueError("El cuerpo de la petición es demasiado grande")
        crudo = self.rfile.read(largo)
        try:
            datos = json.loads(crudo.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"JSON inválido: {exc}") from exc
        if not isinstance(datos, dict):
            raise ValueError("Se esperaba un objeto JSON")
        return datos

    def _archivo(self, ruta: Path, tipo: Optional[str] = None) -> None:
        if not ruta.is_file():
            self._error("Archivo no encontrado", 404)
            return
        datos = ruta.read_bytes()
        tipo = tipo or MIME_EXTRA.get(ruta.suffix.lower()) or mimetypes.guess_type(ruta.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(datos)

    # -- GET ---------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        ruta = urlparse(self.path).path
        try:
            if ruta in {"/", "/index.html"}:
                return self._archivo(util.WEB_DIR / "index.html")
            if ruta.startswith("/static/"):
                return self._estatico(ruta[len("/static/") :])
            if ruta == "/api/estado":
                return self._json(self.estado.estado())
            if ruta == "/api/historial":
                return self._json({"examenes": self.estado.historial_resultados()})
            if ruta.startswith("/api/examen/") and ruta.endswith("/boleta"):
                id_examen = ruta[len("/api/examen/") : -len("/boleta")]
                return self._boleta(id_examen)
            if ruta.startswith("/api/examen/"):
                id_examen = ruta[len("/api/examen/") :]
                examen = self.estado.obtener_examen(id_examen)
                return self._json(examen.vista_publica(self.estado.banco))
            if ruta.startswith("/api/resultado/"):
                id_examen = ruta[len("/api/resultado/") :]
                resultado = self.estado.obtener_resultado(id_examen)
                if not resultado:
                    return self._error("Resultado no encontrado", 404)
                return self._json(resultado)
            if ruta == "/api/banco":
                return self._json(self.estado.banco.estadisticas())
            if ruta == "/favicon.ico":
                return self._error("no encontrado", 404)
            return self._error("Ruta no encontrada", 404)
        except FileNotFoundError:
            self._error("Examen no encontrado", 404)
        except Exception as exc:  # pragma: no cover - defensivo
            traceback.print_exc()
            self._error(f"Error interno: {exc}", 500)

    def _estatico(self, nombre: str) -> None:
        base = util.WEB_DIR.resolve()
        destino = (base / unquote(nombre)).resolve()
        if base != destino and base not in destino.parents:
            return self._error("Ruta inválida", 403)
        if destino.is_dir():
            return self._error("Ruta inválida", 403)
        self._archivo(destino)

    # -- POST --------------------------------------------------------------
    def do_POST(self) -> None:  # noqa: N802
        ruta = urlparse(self.path).path
        try:
            cuerpo = self._leer_json()
            if ruta == "/api/examen":
                return self._crear_examen(cuerpo)
            if ruta == "/api/corregir":
                return self._corregir(cuerpo)
            if ruta == "/api/corregir-desarrollo":
                return self._corregir_desarrollo(cuerpo)
            return self._error("Ruta no encontrada", 404)
        except ValueError as exc:
            return self._error(str(exc), 400)
        except FileNotFoundError:
            self._error("Examen no encontrado", 404)
        except Exception as exc:  # pragma: no cover - defensivo
            traceback.print_exc()
            self._error(f"Error interno: {exc}", 500)

    def _crear_examen(self, cuerpo: Dict[str, Any]) -> None:
        modo = str(cuerpo.get("modo") or "examen")
        if modo == "practica":
            tema = cuerpo.get("tema") or None
            if tema is not None and tema not in bank.TEMAS:
                raise ValueError(f"Tema desconocido: {tema}")
            cantidad = max(1, min(60, _int(cuerpo.get("cantidad"), 10)))
            examen = sampler.crear_examen_practica(
                self.estado.banco,
                tema=tema,
                cantidad=cantidad,
                incluir_desarrollo=bool(cuerpo.get("incluir_desarrollo")),
                seed=cuerpo.get("seed"),
            )
            self.estado.guardar_examen(examen)
            datos = examen.vista_publica(self.estado.banco, incluir_soluciones=True)
            datos["modo"] = "practica"
            return self._json(datos)

        especificacion = _construir_especificacion(self.estado, cuerpo)
        seed = cuerpo.get("seed")
        examen = sampler.generar_examen(
            self.estado.banco,
            especificacion,
            seed=int(seed) if seed not in (None, "") else None,
            historial=self.estado.historial,
        )
        self.estado.guardar_examen(examen)
        self._json(examen.vista_publica(self.estado.banco))

    def _corregir(self, cuerpo: Dict[str, Any]) -> None:
        id_examen = str(cuerpo.get("examen_id") or "")
        if not id_examen:
            raise ValueError("Falta 'examen_id'")
        examen = self.estado.obtener_examen(id_examen)
        respuestas = {
            "mc": cuerpo.get("mc") or {},
            "desarrollo": cuerpo.get("desarrollo") or {},
        }
        usar_llm = cuerpo.get("usar_llm")
        corrector = self.estado.corrector
        if usar_llm is False and corrector.preferencia != "heuristica":
            corrector = grader.CorrectorAuto(preferencia="heuristica")
        resultado = grader.corregir_examen(self.estado.banco, examen, respuestas, corrector=corrector)
        resultado["nombre"] = (examen.especificacion or {}).get("nombre", "Examen")
        self.estado.guardar_resultado(resultado)
        self._json(resultado)

    def _corregir_desarrollo(self, cuerpo: Dict[str, Any]) -> None:
        id_pregunta = str(cuerpo.get("pregunta_id") or "")
        if not id_pregunta:
            raise ValueError("Falta 'pregunta_id'")
        respuesta = str(cuerpo.get("respuesta") or "")
        corrector = self.estado.corrector
        if cuerpo.get("usar_llm") is False and corrector.preferencia != "heuristica":
            corrector = grader.CorrectorAuto(preferencia="heuristica")
        self._json(grader.corregir_una_desarrollo(self.estado.banco, id_pregunta, respuesta, corrector=corrector))

    def _boleta(self, id_examen: str) -> None:
        resultado = self.estado.obtener_resultado(id_examen)
        if not resultado:
            raise FileNotFoundError(id_examen)
        texto = export.resultado_a_markdown(resultado, self.estado.banco)
        ruta = util.EXAMENES_DIR / f"boleta-{id_examen}.md"
        try:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_text(texto, encoding="utf-8", newline="\n")
        except OSError:
            pass
        cuerpo = texto.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/markdown; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="boleta-{id_examen}.md"')
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------


def crear_servidor(host: str = "127.0.0.1", puerto: int = 8765, estado: Optional[Estado] = None) -> ThreadingHTTPServer:
    estado = estado or Estado()
    manejador = type("ManejadorConEstado", (Manejador,), {"estado": estado})
    servidor = ThreadingHTTPServer((host, puerto), manejador)
    servidor.daemon_threads = True
    return servidor


def servir(host: str = "127.0.0.1", puerto: int = 8765, abrir_navegador: bool = True) -> int:
    util.preparar_consola()
    try:
        estado = Estado()
    except BancoInvalido as exc:
        print("El banco de preguntas tiene problemas y el servidor no puede arrancar:")
        for error in exc.errores[:10]:
            print("  - " + error)
        print("\nValidá con: python scripts/validate_bank.py")
        return 2

    try:
        servidor = crear_servidor(host, puerto, estado)
    except OSError as exc:
        print(f"No se pudo abrir el puerto {puerto}: {exc}")
        print(f"Probá con otro puerto: python -m quiz servir --puerto {puerto + 1}")
        return 1

    url = f"http://{host if host != '0.0.0.0' else '127.0.0.1'}:{puerto}"
    info = estado.corrector.estado()
    print()
    print("  TAIS Quiz - generador de exámenes")
    print(f"  Interfaz:  {url}")
    print(f"  Banco:     {estado.banco.estadisticas()['total_mc']} múltiple opción, "
          f"{estado.banco.estadisticas()['total_desarrollo']} desarrollo")
    if info.get("disponible"):
        print(f"  IA local:  {info.get('proveedor')} · {info.get('modelo')}")
    else:
        print("  IA local:  no disponible (se corrige con criterios y palabras clave)")
    print("  Ctrl+C para detener.")
    print()
    sys.stdout.flush()

    if abrir_navegador:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        servidor.server_close()
    return 0
