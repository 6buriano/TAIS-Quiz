# Imagen mínima: la aplicación usa solo la biblioteca estándar de Python.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY . .

RUN mkdir -p /app/examenes

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/estado', timeout=3)"

# --sin-navegador: dentro del contenedor no hay uno disponible.
CMD ["python", "-m", "quiz", "servir", "--host", "0.0.0.0", "--puerto", "8765", "--sin-navegador"]
