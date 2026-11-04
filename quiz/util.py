"""Utilidades comunes: rutas, normalización de texto, JSON y consola.

Este módulo no tiene dependencias externas: todo funciona con la biblioteca
estándar de Python 3.9+.
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

# ---------------------------------------------------------------------------
# Rutas del proyecto
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content"
BANK_DIR = CONTENT_DIR / "bank"
MC_DIR = BANK_DIR / "mc"
SHORT_DIR = BANK_DIR / "short"
CORPUS_DIR = CONTENT_DIR / "corpus"
WEB_DIR = ROOT / "web"
EXAMENES_DIR = ROOT / "examenes"
SPEC_PATH = CONTENT_DIR / "exam_spec.json"

#: Archivos PDF que son fuente del material (se resuelven en tiempo de ejecución).
CARPETAS_PDF = ("", "Practicos", "Laboratorios")

#: Palabras vacías del español que se ignoran al comparar respuestas.
STOPWORDS = frozenset(
    """
    a al algo algun alguna algunas alguno algunos ante antes aquello aquellos
    aqui asi aun aunque cada como con contra cual cuales cuando de del demas
    desde donde dos el ella ellas ello ellos en entre era eran es esa esas ese
    eso esos esta estaba estan estas este esto estos estoy fue fueron ha haber
    habia han hasta hay la las le les lo los mas me misma mismo mucho muy nada
    ni no nos nosotros o os otro otra otros para pero poco por porque que quien
    se sea sean segun ser si sido sin sobre son su sus tambien tan tanto te
    tener tiene tienen todo todos tras tu tus un una unas uno unos usted ustedes
    vosotros y ya yo
    """
    .split()
)


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------


def sin_acentos(texto: str) -> str:
    """Devuelve el texto sin acentos (útil para comparar respuestas)."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def normalizar(texto: str) -> str:
    """Normaliza para comparar: minúsculas, sin acentos, sin signos."""
    texto = sin_acentos(texto).lower()
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def tokenizar(texto: str, *, quitar_vacias: bool = True) -> List[str]:
    """Parte un texto en tokens normalizados."""
    tokens = [t for t in normalizar(texto).split(" ") if t]
    if quitar_vacias:
        tokens = [t for t in tokens if t not in STOPWORDS]
    return tokens


def recortar(texto: str, largo: int = 90) -> str:
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto if len(texto) <= largo else texto[: largo - 1].rstrip() + "…"


def slug(texto: str) -> str:
    """Convierte un texto en un identificador ASCII simple."""
    return re.sub(r"[^a-z0-9]+", "-", sin_acentos(texto).lower()).strip("-")


def ahora_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def cargar_json(ruta: Path) -> Any:
    with Path(ruta).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def guardar_json(ruta: Path, datos: Any) -> Path:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(datos, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    tmp.replace(ruta)
    return ruta


# ---------------------------------------------------------------------------
# Configuración por variables de entorno (.env opcional, sin dependencias)
# ---------------------------------------------------------------------------


def cargar_dotenv(ruta: Optional[Path] = None) -> None:
    """Carga pares CLAVE=valor de un archivo .env si existe.

    No sobreescribe variables ya definidas en el entorno.
    """
    ruta = Path(ruta) if ruta else ROOT / ".env"
    if not ruta.is_file():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        clave = clave.strip()
        valor = valor.strip().strip('"').strip("'")
        if clave:
            os.environ.setdefault(clave, valor)


def config(clave: str, defecto: str = "") -> str:
    return os.environ.get(clave, defecto)


def config_bool(clave: str, defecto: bool = False) -> bool:
    valor = os.environ.get(clave)
    if valor is None:
        return defecto
    return valor.strip().lower() in {"1", "si", "sí", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Consola
# ---------------------------------------------------------------------------


def preparar_consola() -> None:
    """Fuerza UTF-8 en la salida (Windows usa cp1252 por defecto)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigurar = getattr(stream, "reconfigure", None)
        if callable(reconfigurar):
            try:
                reconfigurar(encoding="utf-8", errors="replace")
            except Exception:
                pass


def color_habilitado(stream: Any = None) -> bool:
    stream = stream or sys.stdout
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return bool(getattr(stream, "isatty", lambda: False)())


class _Colores:
    def __init__(self, activo: bool) -> None:
        self.activo = activo

    def _envolver(self, codigo: str, texto: str) -> str:
        return f"\033[{codigo}m{texto}\033[0m" if self.activo else texto

    def negrita(self, t: str) -> str:
        return self._envolver("1", t)

    def tenue(self, t: str) -> str:
        return self._envolver("2", t)

    def rojo(self, t: str) -> str:
        return self._envolver("31", t)

    def verde(self, t: str) -> str:
        return self._envolver("32", t)

    def amarillo(self, t: str) -> str:
        return self._envolver("33", t)

    def azul(self, t: str) -> str:
        return self._envolver("34", t)

    def magenta(self, t: str) -> str:
        return self._envolver("35", t)

    def cian(self, t: str) -> str:
        return self._envolver("36", t)


C = _Colores(color_habilitado())


def imprimir(texto: str = "") -> None:
    print(texto)


def barra(valor: float, ancho: int = 24) -> str:
    """Barra de progreso en texto ASCII, valor entre 0 y 1."""
    valor = max(0.0, min(1.0, valor))
    llenos = int(round(valor * ancho))
    return "=" * llenos + "." * (ancho - llenos)


def porcentaje(valor: float) -> str:
    return f"{valor * 100:.0f}%"


def leer_respuesta_multilinea(mensaje: str = "Tu respuesta") -> str:
    """Lee un texto multilínea terminado con una línea vacía."""
    imprimir(C.tenue(f"{mensaje} (terminá con una línea vacía):"))
    lineas: List[str] = []
    while True:
        try:
            linea = input()
        except EOFError:
            break
        if linea.strip() == "":
            if lineas:
                break
            continue
        lineas.append(linea)
    return "\n".join(lineas).strip()


def pedir_opcion(prompt: str, validas: Iterable[str]) -> str:
    validas = {v.lower() for v in validas}
    while True:
        try:
            valor = input(prompt).strip().lower()
        except EOFError:
            return ""
        if valor in validas:
            return valor
        imprimir(C.amarillo(f"Opción inválida. Válidas: {', '.join(sorted(validas))}"))


def paginas_pdf(nombre: str) -> Optional[int]:
    """Cantidad de páginas de un PDF fuente (si hay librería disponible)."""
    for carpeta in CARPETAS_PDF:
        ruta = (ROOT / carpeta / nombre) if carpeta else (ROOT / nombre)
        if ruta.is_file():
            return _contar_paginas(ruta)
    return None


_CACHE_PAGINAS: Dict[str, Optional[int]] = {}


def _contar_paginas(ruta: Path) -> Optional[int]:
    clave = str(ruta)
    if clave in _CACHE_PAGINAS:
        return _CACHE_PAGINAS[clave]
    total: Optional[int] = None
    try:  # PyMuPDF es el más rápido
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            import fitz  # type: ignore

        with fitz.open(ruta) as doc:
            total = doc.page_count
    except Exception:
        try:
            from pypdf import PdfReader  # type: ignore

            total = len(PdfReader(str(ruta)).pages)
        except Exception:
            total = None
    _CACHE_PAGINAS[clave] = total
    return total


def ruta_pdf(nombre: str) -> Optional[Path]:
    for carpeta in CARPETAS_PDF:
        ruta = (ROOT / carpeta / nombre) if carpeta else (ROOT / nombre)
        if ruta.is_file():
            return ruta
    return None


def nombres_pdf() -> List[str]:
    nombres = []
    for carpeta in CARPETAS_PDF:
        base = ROOT / carpeta if carpeta else ROOT
        if not base.is_dir():
            continue
        for p in sorted(base.glob("*.pdf")):
            nombres.append(p.name)
    return nombres


def es_texto(texto: Any, minimo: int = 1) -> bool:
    return isinstance(texto, str) and len(texto.strip()) >= minimo
