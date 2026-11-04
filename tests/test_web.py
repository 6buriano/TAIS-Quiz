"""Tests de la API HTTP y del servidor web."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from quiz import util, web


class ServidorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporal = tempfile.TemporaryDirectory()
        cls._dir_original = util.EXAMENES_DIR
        util.EXAMENES_DIR = Path(cls._temporal.name)
        cls._env_original = os.environ.get("QUIZ_LLM_PROVEEDOR")
        os.environ["QUIZ_LLM_PROVEEDOR"] = "ninguno"
        cls.estado = web.Estado()
        cls.servidor = web.crear_servidor("127.0.0.1", 0, cls.estado)
        cls.hilo = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        cls.hilo.start()
        cls.base = f"http://127.0.0.1:{cls.servidor.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.servidor.shutdown()
        cls.servidor.server_close()
        cls.hilo.join(timeout=3)
        util.EXAMENES_DIR = cls._dir_original
        if cls._env_original is None:
            os.environ.pop("QUIZ_LLM_PROVEEDOR", None)
        else:
            os.environ["QUIZ_LLM_PROVEEDOR"] = cls._env_original
        cls._temporal.cleanup()

    # -- helpers -----------------------------------------------------------
    def _get(self, ruta: str):
        with urllib.request.urlopen(self.base + ruta, timeout=15) as respuesta:
            return respuesta.status, respuesta.read().decode("utf-8")

    def _get_json(self, ruta: str):
        estado, cuerpo = self._get(ruta)
        return estado, json.loads(cuerpo)

    def _post(self, ruta: str, datos):
        cuerpo = json.dumps(datos).encode("utf-8") if datos is not None else b"{}"
        solicitud = urllib.request.Request(
            self.base + ruta, data=cuerpo, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(solicitud, timeout=60) as respuesta:
                return respuesta.status, json.loads(respuesta.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def _crear_examen(self, **extra):
        _, examen = self._post("/api/examen", {"modo": "examen", "seed": 2024, **extra})
        return examen

    # -- tests -------------------------------------------------------------
    def test_index(self) -> None:
        estado, cuerpo = self._get("/")
        self.assertEqual(estado, 200)
        self.assertIn("TAIS Quiz", cuerpo)

    def test_estaticos(self) -> None:
        for ruta, fragmento in (("/static/app.js", "comenzar"), ("/static/estilos.css", "--acento")):
            with self.subTest(ruta=ruta):
                estado, cuerpo = self._get(ruta)
                self.assertEqual(estado, 200)
                self.assertIn(fragmento, cuerpo)

    def test_ruta_inexistente(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as contexto:
            self._get("/api/no-existe")
        self.assertEqual(contexto.exception.code, 404)

    def test_no_permite_salir_del_directorio_web(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as contexto:
            self._get("/static/%2e%2e/%2e%2e/quiz/cli.py")
        self.assertIn(contexto.exception.code, (403, 404))

    def test_estado(self) -> None:
        estado, datos = self._get_json("/api/estado")
        self.assertEqual(estado, 200)
        self.assertIn("banco", datos)
        self.assertIn("especificacion", datos)
        self.assertGreater(datos["banco"]["total_mc"], 100)
        self.assertEqual(len(datos["temas"]), 6)
        self.assertEqual(datos["corrector"]["modo_efectivo"], "heuristica")

    def test_crear_examen(self) -> None:
        examen = self._crear_examen()
        self.assertEqual(len(examen["preguntas"]), 35)
        self.assertEqual(examen["total_mc"], 30)
        self.assertEqual(examen["total_desarrollo"], 5)
        for pregunta in examen["preguntas"]:
            self.assertNotIn("correcta", pregunta)
            self.assertNotIn("respuesta_modelo", pregunta)
            if pregunta["tipo"] == "mc":
                self.assertEqual(len(pregunta["opciones"]), 4)
                letras = [opcion["letra"] for opcion in pregunta["opciones"]]
                self.assertEqual(letras, list("ABCD"))

    def test_corregir_examen(self) -> None:
        examen = self._crear_examen()
        mc = {p["id"]: 0 for p in examen["preguntas"] if p["tipo"] == "mc"}
        desarrollo = {p["id"]: "Respuesta corta de prueba." for p in examen["preguntas"] if p["tipo"] == "desarrollo"}
        estado, resultado = self._post("/api/corregir", {
            "examen_id": examen["id"], "mc": mc, "desarrollo": desarrollo, "usar_llm": False,
        })
        self.assertEqual(estado, 200)
        self.assertEqual(resultado["examen_id"], examen["id"])
        self.assertEqual(len(resultado["mc"]), 30)
        self.assertEqual(len(resultado["desarrollo"]), 5)
        self.assertIn("nota_100", resultado["resumen"])
        self.assertEqual(resultado["resumen"]["modo_correccion"], "heuristica")
        self.assertTrue(all("criterios" in d["correccion"] for d in resultado["desarrollo"]))
        self.assertTrue((Path(self._temporal.name) / f"{examen['id']}-resultado.json").is_file())

    def test_historial_y_resultado(self) -> None:
        examen = self._crear_examen()
        estado, resultado = self._post("/api/corregir", {"examen_id": examen["id"], "mc": {}, "desarrollo": {}})
        self.assertEqual(estado, 200)
        _, historial = self._get_json("/api/historial")
        self.assertTrue(any(item["examen_id"] == examen["id"] for item in historial["examenes"]))
        _, recuperado = self._get_json(f"/api/resultado/{examen['id']}")
        self.assertEqual(recuperado["resumen"]["nota_100"], resultado["resumen"]["nota_100"])

    def test_boleta_markdown(self) -> None:
        examen = self._crear_examen()
        self._post("/api/corregir", {"examen_id": examen["id"], "mc": {}, "desarrollo": {}})
        estado, cuerpo = self._get(f"/api/examen/{examen['id']}/boleta")
        self.assertEqual(estado, 200)
        self.assertIn("Boleta de corrección", cuerpo)
        self.assertIn("Respuesta modelo", cuerpo)

    def test_practica_con_soluciones(self) -> None:
        estado, examen = self._post("/api/examen", {"modo": "practica", "tema": "rest", "cantidad": 5})
        self.assertEqual(estado, 200)
        self.assertEqual(examen["modo"], "practica")
        self.assertEqual(len(examen["preguntas"]), 5)
        for pregunta in examen["preguntas"]:
            self.assertIn("correcta", pregunta)
            self.assertIn("explicacion", pregunta)
            self.assertTrue(all(p["tema"] == "rest" for p in examen["preguntas"]))

    def test_corregir_desarrollo_suelto(self) -> None:
        estado, examen = self._post("/api/examen", {"modo": "practica", "tema": "nosql", "cantidad": 1, "incluir_desarrollo": True})
        self.assertEqual(estado, 200)
        desarrollo = [p for p in examen["preguntas"] if p["tipo"] == "desarrollo"]
        self.assertEqual(len(desarrollo), 1)
        estado, datos = self._post("/api/corregir-desarrollo", {
            "pregunta_id": desarrollo[0]["id"], "respuesta": "Una respuesta de prueba suficientemente larga.",
        })
        self.assertEqual(estado, 200)
        self.assertIn("correccion", datos)
        self.assertIn("respuesta_modelo", datos)

    def test_json_invalido(self) -> None:
        solicitud = urllib.request.Request(
            self.base + "/api/examen", data=b"{roto", headers={"Content-Type": "application/json"}, method="POST"
        )
        with self.assertRaises(urllib.error.HTTPError) as contexto:
            urllib.request.urlopen(solicitud, timeout=10)
        self.assertEqual(contexto.exception.code, 400)

    def test_examen_inexistente(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as contexto:
            self._get("/api/examen/no-existe")
        self.assertEqual(contexto.exception.code, 404)

    def test_examen_seed_reproducible(self) -> None:
        a = self._crear_examen()
        b = self._crear_examen()
        self.assertEqual([p["id"] for p in a["preguntas"]], [p["id"] for p in b["preguntas"]])

    def test_examen_por_tema(self) -> None:
        estado, examen = self._post("/api/examen", {
            "modo": "examen", "temas": ["cache"], "mc_por_tema": {"cache": 6}, "desarrollo": 1,
        })
        self.assertEqual(estado, 200)
        self.assertEqual(len(examen["preguntas"]), 7)
        self.assertTrue(all(p["tema"] == "cache" for p in examen["preguntas"]))


if __name__ == "__main__":
    unittest.main()
