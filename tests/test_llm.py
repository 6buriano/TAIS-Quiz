"""Tests del cliente de modelos locales y del parser de JSON."""

from __future__ import annotations

import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from quiz import llm


class _MockOllama(BaseHTTPRequestHandler):
    respuesta_chat = {
        "criterios": [{"id": "c1", "cumplido": True, "detalle": "ok"}],
        "puntaje": 0.9,
        "comentario": "bien",
        "faltantes": [],
    }
    fallar = False

    def log_message(self, *args):  # silencio
        pass

    def _json(self, datos, estado=200):
        cuerpo = json.dumps(datos).encode("utf-8")
        self.send_response(estado)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):  # noqa: N802
        if self.path == "/api/tags":
            return self._json({"models": [{"name": "modelo-prueba"}]})
        self._json({"error": "no encontrado"}, 404)

    def do_POST(self):  # noqa: N802
        largo = int(self.headers.get("Content-Length", 0))
        self.rfile.read(largo)
        if self.path != "/api/chat":
            return self._json({"error": "no encontrado"}, 404)
        if self.fallar:
            return self._json({"error": "boom"}, 500)
        self._json({"message": {"role": "assistant", "content": json.dumps(self.respuesta_chat)}})


class ParserTests(unittest.TestCase):
    def test_json_limpio(self) -> None:
        self.assertEqual(llm.extraer_json('{"a": 1}'), {"a": 1})

    def test_json_con_fences(self) -> None:
        self.assertEqual(llm.extraer_json('```json\n{"a": 2}\n```'), {"a": 2})

    def test_json_con_texto_alrededor(self) -> None:
        self.assertEqual(llm.extraer_json('Claro: {"a": 3} y eso es todo'), {"a": 3})

    def test_json_anidado_y_con_llaves_en_strings(self) -> None:
        crudo = 'respuesta: {"a": {"b": "texto con } llave"}, "c": [1, 2]} fin'
        self.assertEqual(llm.extraer_json(crudo)["a"]["b"], "texto con } llave")

    def test_sin_json(self) -> None:
        with self.assertRaises(llm.ErrorLLM):
            llm.extraer_json("no hay nada")

    def test_respuesta_vacia(self) -> None:
        with self.assertRaises(llm.ErrorLLM):
            llm.extraer_json("")


class ConfigTests(unittest.TestCase):
    def test_desde_entorno(self) -> None:
        previo = {k: os.environ.get(k) for k in ("QUIZ_LLM_PROVEEDOR", "QUIZ_LLM_URL", "QUIZ_LLM_MODELO")}
        try:
            os.environ["QUIZ_LLM_PROVEEDOR"] = "openai"
            os.environ["QUIZ_LLM_URL"] = "http://localhost:1234/v1"
            os.environ["QUIZ_LLM_MODELO"] = "llama3"
            config = llm.ConfigLLM.desde_entorno()
            self.assertEqual(config.proveedor, "openai")
            self.assertEqual(config.url, "http://localhost:1234/v1")
            self.assertEqual(config.modelo, "llama3")
        finally:
            for clave, valor in previo.items():
                if valor is None:
                    os.environ.pop(clave, None)
                else:
                    os.environ[clave] = valor

    def test_normalizar_url(self) -> None:
        self.assertEqual(
            llm._normalizar_url_openai("http://localhost:1234"),
            "http://localhost:1234/v1/chat/completions",
        )
        self.assertEqual(
            llm._normalizar_url_openai("http://localhost:1234/v1/"),
            "http://localhost:1234/v1/chat/completions",
        )
        self.assertEqual(
            llm._normalizar_url_openai("http://servidor/v1/chat/completions"),
            "http://servidor/v1/chat/completions",
        )


class ClienteTests(unittest.TestCase):
    def setUp(self) -> None:
        _MockOllama.fallar = False
        self.servidor = HTTPServer(("127.0.0.1", 0), _MockOllama)
        self.hilo = threading.Thread(target=self.servidor.serve_forever, daemon=True)
        self.hilo.start()
        self.url = f"http://127.0.0.1:{self.servidor.server_address[1]}"
        self.cliente = llm.ClienteLLM(
            llm.ConfigLLM(proveedor="ollama", url=self.url, modelo="modelo-prueba", timeout=10)
        )

    def tearDown(self) -> None:
        self.servidor.shutdown()
        self.servidor.server_close()
        self.hilo.join(timeout=2)

    def test_modelos(self) -> None:
        self.assertIn("modelo-prueba", self.cliente.modelos())

    def test_estado_disponible(self) -> None:
        estado = self.cliente.estado(refrescar=True)
        self.assertTrue(estado["disponible"])
        self.assertEqual(estado["proveedor"], "ollama")
        self.assertEqual(estado["modelo"], "modelo-prueba")

    def test_chat_json(self) -> None:
        datos = self.cliente.chat_json([{"role": "user", "content": "hola"}])
        self.assertEqual(datos["puntaje"], 0.9)

    def test_error_http(self) -> None:
        _MockOllama.fallar = True
        with self.assertRaises(llm.ErrorLLM):
            self.cliente.chat([{"role": "user", "content": "hola"}])

    def test_servidor_inexistente(self) -> None:
        cliente = llm.ClienteLLM(llm.ConfigLLM(proveedor="ollama", url="http://127.0.0.1:1", timeout=1))
        self.assertFalse(cliente.disponible(refrescar=True))
        with self.assertRaises(llm.ErrorLLM):
            cliente.chat([{"role": "user", "content": "hola"}])


if __name__ == "__main__":
    unittest.main()
