#!/usr/bin/env python3
"""Extrae el texto de los PDF del curso a ``content/corpus/``.

El corpus permite citar la fuente de cada pregunta y buscar en el material
sin abrir los PDF. No es necesario para usar el quiz (el banco ya está armado);
solo se corre cuando se agregan o actualizan PDF.

Uso:
    python scripts/extract_corpus.py            # extrae todos los PDF
    python scripts/extract_corpus.py --fuerza   # sobrescribe los existentes
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from quiz import util  # noqa: E402


def _paginas_con_fitz(ruta: Path):
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        import fitz  # type: ignore

    with fitz.open(ruta) as documento:
        return [pagina.get_text("text") for pagina in documento]


def _paginas_con_pypdf(ruta: Path):
    from pypdf import PdfReader  # type: ignore

    return [pagina.extract_text() or "" for pagina in PdfReader(str(ruta)).pages]


def extraer(ruta: Path) -> dict:
    try:
        paginas = _paginas_con_fitz(ruta)
    except ImportError:
        try:
            paginas = _paginas_con_pypdf(ruta)
        except ImportError as exc:
            raise SystemExit(
                "Para regenerar el corpus hace falta PyMuPDF o pypdf.\n"
                "  pip install pymupdf    (recomendado)\n"
                "  pip install pypdf      (alternativa)\n"
                f"Detalle: {exc}"
            )
    return {
        "archivo": ruta.name,
        "carpeta": "" if ruta.parent == RAIZ else ruta.parent.name,
        "paginas": [
            {"n": numero, "texto": texto.replace("\r\n", "\n").strip()}
            for numero, texto in enumerate(paginas, 1)
        ],
    }


def nombre_salida(ruta: Path) -> str:
    base = util.slug(ruta.stem) or "documento"
    if ruta.parent != RAIZ:
        base = f"{util.slug(ruta.parent.name)}-{base}"
    return base + ".json"


def main(argv=None) -> int:
    util.preparar_consola()
    parser = argparse.ArgumentParser(description="Extrae el texto de los PDF a content/corpus/.")
    parser.add_argument("--fuerza", action="store_true", help="sobrescribir archivos existentes")
    args = parser.parse_args(argv)

    rutas = []
    for carpeta in util.CARPETAS_PDF:
        base = RAIZ / carpeta if carpeta else RAIZ
        if base.is_dir():
            rutas.extend(sorted(base.glob("*.pdf")))
    if not rutas:
        print("No se encontraron PDF en el repositorio.")
        return 1

    util.CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    indice = []
    for ruta in rutas:
        destino = util.CORPUS_DIR / nombre_salida(ruta)
        if destino.exists() and not args.fuerza:
            print(util.C.tenue(f"  = {destino} (ya existe)"))
        else:
            datos = extraer(ruta)
            destino.write_text(
                json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
            )
            print(util.C.verde(f"  + {destino} ({len(datos['paginas'])} páginas)"))
        indice.append(
            {
                "archivo": ruta.name,
                "carpeta": "" if ruta.parent == RAIZ else ruta.parent.name,
                "corpus": destino.name,
                "paginas": len(json.loads(destino.read_text(encoding="utf-8"))["paginas"]),
            }
        )

    (util.CORPUS_DIR / "indice.json").write_text(
        json.dumps({"documentos": indice}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(util.C.verde(f"\nListo: {len(indice)} documentos en {util.CORPUS_DIR}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
