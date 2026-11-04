#!/usr/bin/env python3
"""Valida el banco de preguntas contra el esquema del proyecto.

Uso:
    python scripts/validate_bank.py                    # valida todo el banco
    python scripts/validate_bank.py content/bank/mc/rest.json
    python scripts/validate_bank.py --estricto-paginas  # verifica páginas citadas
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from quiz import bank, util  # noqa: E402


def main(argv=None) -> int:
    util.preparar_consola()
    parser = argparse.ArgumentParser(description="Valida el banco de preguntas del quiz.")
    parser.add_argument("rutas", nargs="*", help="archivos JSON a validar (por defecto: todo el banco)")
    parser.add_argument("--estricto-paginas", action="store_true", help="verifica que las páginas citadas existan en el PDF")
    parser.add_argument("--json", action="store_true", help="salida en JSON")
    args = parser.parse_args(argv)

    rutas = [Path(r) for r in args.rutas] if args.rutas else bank.archivos_banco()
    if not rutas:
        print("No se encontraron archivos para validar.")
        return 1

    informe = bank.validar_archivos(rutas, estricto_paginas=args.estricto_paginas)

    if args.json:
        print(json.dumps(informe, ensure_ascii=False, indent=2))
        return 0 if informe["ok"] else 1

    print(util.C.negrita(f"Validando {len(rutas)} archivo(s) - {informe['total_preguntas']} preguntas"))
    for ruta in rutas:
        print(util.C.tenue(f"  - {ruta}"))

    if informe["advertencias"]:
        print()
        print(util.C.amarillo(f"AVISO: {len(informe['advertencias'])} advertencia(s):"))
        for adv in informe["advertencias"]:
            print("  " + util.C.amarillo(adv))

    if informe["errores"]:
        print()
        print(util.C.rojo(f"ERROR: {len(informe['errores'])} problema(s):"))
        for err in informe["errores"]:
            print("  " + util.C.rojo(err))
        return 1

    print()
    print(util.C.verde("OK: banco válido, todas las preguntas cumplen el esquema."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
