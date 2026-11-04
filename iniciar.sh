#!/usr/bin/env bash
# Levanta la interfaz de TAIS Quiz en el navegador.
set -e
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
  exec python3 -m quiz servir "$@"
fi
exec python -m quiz servir "$@"
