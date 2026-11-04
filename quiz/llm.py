"""Cliente para modelos de lenguaje locales (opcional).

La aplicación funciona sin esto. Si hay un modelo disponible se usa para
corregir las respuestas de desarrollo con más criterio; si no, se cae
automáticamente a la corrección por criterios y palabras clave.

Proveedores soportados:

* ``ollama``  — http://localhost:11434 (API nativa ``/api/chat``)
* ``openai``  — cualquier servidor compatible con la API de OpenAI
  (LM Studio :1234, llama.cpp :8080, vLLM, text-generation-webui, etc.)

Configuración por variables de entorno (o archivo ``.env`` en la raíz):

============================  ==========================================
``QUIZ_LLM_PROVEEDOR``        ``auto`` (por defecto), ``ollama``, ``openai``, ``ninguno``
``QUIZ_LLM_URL``              URL base del servidor
``QUIZ_LLM_MODELO``           nombre del modelo (ej. ``qwen2.5:7b-instruct``)
``QUIZ_LLM_API_KEY``          opcional, para servidores que la piden
``QUIZ_LLM_TIMEOUT``          segundos de espera para una corrección
============================  ==========================================
"""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from . import util

MODELO_POR_DEFECTO = "qwen2.5:7b-instruct"
URL_OLLAMA = "http://localhost:11434"
URL_OPENAI = "http://localhost:1234/v1"


class ErrorLLM(Exception):
    """Error de comunicación con el modelo."""


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------


@dataclass
class ConfigLLM:
    proveedor: str = "auto"
    url: str = ""
    modelo: str = MODELO_POR_DEFECTO
    api_key: str = ""
    timeout: float = 180.0

    @classmethod
    def desde_entorno(cls) -> "ConfigLLM":
        util.cargar_dotenv()
        proveedor = (util.config("QUIZ_LLM_PROVEEDOR") or util.config("QUIZ_LLM", "auto")).strip().lower()
        if proveedor in {"", "auto", "automatico", "automático"}:
            proveedor = "auto"
        if proveedor in {"none", "no", "ninguno", "off", "deshabilitado"}:
            proveedor = "ninguno"
        if proveedor not in {"auto", "ollama", "openai", "ninguno"}:
            proveedor = "auto"
        try:
            timeout = float(util.config("QUIZ_LLM_TIMEOUT", "180") or 180)
        except ValueError:
            timeout = 180.0
        return cls(
            proveedor=proveedor,
            url=util.config("QUIZ_LLM_URL", "").strip(),
            modelo=util.config("QUIZ_LLM_MODELO", MODELO_POR_DEFECTO).strip() or MODELO_POR_DEFECTO,
            api_key=util.config("QUIZ_LLM_API_KEY", "").strip(),
            timeout=timeout,
        )


# ---------------------------------------------------------------------------
# Utilidades HTTP
# ---------------------------------------------------------------------------


def _peticion(
    url: str,
    *,
    datos: Optional[Dict[str, Any]] = None,
    cabeceras: Optional[Dict[str, str]] = None,
    timeout: float = 10.0,
) -> Any:
    cuerpo = json.dumps(datos).encode("utf-8") if datos is not None else None
    cabeceras = dict(cabeceras or {})
    cabeceras.setdefault("Accept", "application/json")
    if cuerpo is not None:
        cabeceras.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=cuerpo, headers=cabeceras, method="POST" if cuerpo else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            crudo = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detalle = exc.read().decode("utf-8", errors="replace")[:300]
        raise ErrorLLM(f"HTTP {exc.code} en {url}: {detalle}") from exc
    except urllib.error.URLError as exc:
        raise ErrorLLM(f"No se pudo conectar con {url}: {exc.reason}") from exc
    except (socket.timeout, TimeoutError) as exc:
        raise ErrorLLM(f"Tiempo de espera agotado ({timeout:.0f}s) en {url}") from exc
    except OSError as exc:
        raise ErrorLLM(f"Error de red en {url}: {exc}") from exc
    try:
        return json.loads(crudo)
    except json.JSONDecodeError as exc:
        raise ErrorLLM(f"Respuesta no JSON de {url}: {crudo[:200]}") from exc


def _normalizar_url_openai(url: str) -> str:
    url = url.rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1"):
        return url + "/chat/completions"
    return url + "/v1/chat/completions"


def _inferir_proveedor(url: str) -> str:
    if "11434" in url or url.rstrip("/").endswith("/api"):
        return "ollama"
    return "openai"


def extraer_json(texto: str) -> Dict[str, Any]:
    """Extrae el primer objeto JSON de un texto (tolerante a ```json ...```)."""
    if not texto:
        raise ErrorLLM("El modelo devolvió una respuesta vacía")
    limpio = texto.strip()
    if limpio.startswith("```"):
        limpio = limpio.strip("`")
        if limpio.lower().startswith("json"):
            limpio = limpio[4:]
        limpio = limpio.strip()
    try:
        datos = json.loads(limpio)
        if isinstance(datos, dict):
            return datos
    except json.JSONDecodeError:
        pass
    # Buscar el primer objeto balanceado.
    inicio = limpio.find("{")
    if inicio == -1:
        raise ErrorLLM(f"El modelo no devolvió JSON: {texto[:200]!r}")
    profundidad = 0
    en_cadena = False
    escape = False
    for i in range(inicio, len(limpio)):
        c = limpio[i]
        if en_cadena:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                en_cadena = False
            continue
        if c == '"':
            en_cadena = True
        elif c == "{":
            profundidad += 1
        elif c == "}":
            profundidad -= 1
            if profundidad == 0:
                fragmento = limpio[inicio : i + 1]
                try:
                    datos = json.loads(fragmento)
                except json.JSONDecodeError as exc:
                    raise ErrorLLM(f"JSON inválido del modelo: {fragmento[:200]}") from exc
                if isinstance(datos, dict):
                    return datos
                break
    raise ErrorLLM(f"No se encontró un objeto JSON válido en: {texto[:200]!r}")


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------


class ClienteLLM:
    """Cliente mínimo para chatear con un modelo local."""

    def __init__(self, config: Optional[ConfigLLM] = None) -> None:
        self.config = config or ConfigLLM.desde_entorno()
        self._lock = threading.Lock()
        self._estado_cache: Optional[Dict[str, Any]] = None
        self._estado_momento = 0.0

    # -- estado ------------------------------------------------------------
    def _resolver(self) -> Dict[str, str]:
        cfg = self.config
        if cfg.proveedor == "ninguno":
            return {"proveedor": "ninguno", "url": "", "detalle": "deshabilitado por configuración"}
        if cfg.url:
            proveedor = cfg.proveedor if cfg.proveedor in {"ollama", "openai"} else _inferir_proveedor(cfg.url)
            return {"proveedor": proveedor, "url": cfg.url}
        # Sin URL: probar los servidores locales habituales.
        for proveedor, url in (("ollama", URL_OLLAMA), ("openai", URL_OPENAI)):
            if cfg.proveedor not in {"auto", proveedor}:
                continue
            if _responde(url, proveedor, cfg.api_key):
                return {"proveedor": proveedor, "url": url}
        return {"proveedor": "ninguno", "url": "", "detalle": "no se detectó un modelo local"}

    def estado(self, *, refrescar: bool = False) -> Dict[str, Any]:
        with self._lock:
            ahora = time.time()
            if not refrescar and self._estado_cache is not None and ahora - self._estado_momento < 30:
                return self._estado_cache
            resuelto = self._resolver()
            proveedor = resuelto["proveedor"]
            disponible = proveedor in {"ollama", "openai"}
            if disponible:
                url = resuelto["url"]
                if not _responde(url, proveedor, self.config.api_key):
                    return {
                        "disponible": False,
                        "proveedor": proveedor,
                        "url": url,
                        "modelo": self.config.modelo,
                        "detalle": f"el servidor configurado no responde en {url}",
                        "modelos": [],
                    }
                detalle = "modelo local disponible"
                modelos: List[str] = []
                try:
                    modelos = self.modelos()
                except ErrorLLM:
                    pass
                if modelos and self.config.modelo not in modelos:
                    detalle = (
                        f"el servidor responde pero el modelo {self.config.modelo!r} "
                        f"no aparece en la lista ({', '.join(modelos[:5])})"
                    )
                estado = {
                    "disponible": disponible,
                    "proveedor": proveedor,
                    "url": url,
                    "modelo": self.config.modelo,
                    "detalle": detalle,
                    "modelos": modelos,
                }
            else:
                estado = {
                    "disponible": False,
                    "proveedor": "ninguno",
                    "url": "",
                    "modelo": self.config.modelo,
                    "detalle": resuelto.get("detalle", "no disponible"),
                    "modelos": [],
                }
            self._estado_cache = estado
            self._estado_momento = ahora
            return estado

    def disponible(self, *, refrescar: bool = False) -> bool:
        return bool(self.estado(refrescar=refrescar)["disponible"])

    # -- API ---------------------------------------------------------------
    def modelos(self) -> List[str]:
        resuelto = self._resolver()
        proveedor, url = resuelto["proveedor"], resuelto["url"]
        if proveedor == "ollama":
            datos = _peticion(url.rstrip("/") + "/api/tags", timeout=2.5)
            return [m.get("name", "") for m in datos.get("models", []) if m.get("name")]
        if proveedor == "openai":
            base = url.rstrip("/")
            if base.endswith("/chat/completions"):
                base = base[: -len("/chat/completions")]
            if not base.endswith("/v1"):
                base += "/v1"
            datos = _peticion(base + "/models", cabeceras=self._cabeceras(), timeout=2.5)
            return [m.get("id", "") for m in datos.get("data", []) if m.get("id")]
        raise ErrorLLM("No hay proveedor configurado")

    def _cabeceras(self) -> Dict[str, str]:
        if self.config.api_key:
            return {"Authorization": f"Bearer {self.config.api_key}"}
        return {}

    def chat(
        self,
        mensajes: List[Dict[str, str]],
        *,
        json_mode: bool = True,
        temperatura: float = 0.15,
        max_tokens: int = 900,
    ) -> str:
        resuelto = self._resolver()
        proveedor, url = resuelto["proveedor"], resuelto["url"]
        if proveedor == "ollama":
            cuerpo: Dict[str, Any] = {
                "model": self.config.modelo,
                "messages": mensajes,
                "stream": False,
                "options": {"temperature": temperatura, "num_predict": max_tokens},
            }
            if json_mode:
                cuerpo["format"] = "json"
            datos = _peticion(url.rstrip("/") + "/api/chat", datos=cuerpo, timeout=self.config.timeout)
            contenido = (datos.get("message") or {}).get("content")
            if not isinstance(contenido, str):
                raise ErrorLLM("Respuesta inesperada de Ollama (sin 'message.content')")
            return contenido
        if proveedor == "openai":
            cuerpo = {
                "model": self.config.modelo,
                "messages": mensajes,
                "temperature": temperatura,
                "max_tokens": max_tokens,
            }
            if json_mode:
                cuerpo["response_format"] = {"type": "json_object"}
            datos = _peticion(
                _normalizar_url_openai(url),
                datos=cuerpo,
                cabeceras=self._cabeceras(),
                timeout=self.config.timeout,
            )
            try:
                contenido = datos["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise ErrorLLM(f"Respuesta inesperada del servidor: {str(datos)[:200]}") from exc
            if not isinstance(contenido, str):
                raise ErrorLLM("El servidor devolvió contenido vacío")
            return contenido
        raise ErrorLLM("No hay un modelo de lenguaje configurado")

    def chat_json(self, mensajes: List[Dict[str, str]], **kwargs: Any) -> Dict[str, Any]:
        return extraer_json(self.chat(mensajes, json_mode=True, **kwargs))


def _responde(url: str, proveedor: str, api_key: str = "") -> bool:
    """Chequeo rápido y silencioso de disponibilidad."""
    cabeceras = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        if proveedor == "ollama":
            _peticion(url.rstrip("/") + "/api/tags", cabeceras=cabeceras, timeout=1.5)
        else:
            base = url.rstrip("/")
            if not base.endswith("/v1"):
                base += "/v1"
            _peticion(base + "/models", cabeceras=cabeceras, timeout=1.5)
        return True
    except ErrorLLM:
        return False
    except Exception:
        return False


_CLIENTE: Optional[ClienteLLM] = None


def cliente() -> ClienteLLM:
    """Instancia compartida (singleton) del cliente."""
    global _CLIENTE
    if _CLIENTE is None:
        _CLIENTE = ClienteLLM()
    return _CLIENTE
