"""Tests del banco de preguntas y del validador."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from quiz import bank, util


class BancoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.banco = bank.cargar_banco()

    def test_hay_preguntas_suficientes(self) -> None:
        self.assertGreaterEqual(len(self.banco.mc), 150)
        self.assertGreaterEqual(len(self.banco.desarrollo), 25)

    def test_todos_los_temas_tienen_cobertura(self) -> None:
        for tema in bank.TEMAS:
            with self.subTest(tema=tema):
                self.assertGreaterEqual(len(self.banco.mc_de(tema)), 20)
                self.assertGreaterEqual(len(self.banco.desarrollo_de(tema)), 3)

    def test_ids_unicos(self) -> None:
        ids = [q.id for q in self.banco.mc] + [q.id for q in self.banco.desarrollo]
        self.assertEqual(len(ids), len(set(ids)))

    def test_una_sola_respuesta_correcta(self) -> None:
        for pregunta in self.banco.mc:
            with self.subTest(pregunta=pregunta.id):
                correctas = [op for op in pregunta.opciones if op.correcta]
                self.assertEqual(len(correctas), 1)
                self.assertGreaterEqual(len(pregunta.opciones), 3)
                for opcion in pregunta.opciones:
                    self.assertTrue(opcion.texto.strip())
                    if not opcion.correcta:
                        self.assertGreaterEqual(len(opcion.porque_no), 10, pregunta.id)

    def test_pesos_de_criterios_suman_uno(self) -> None:
        for pregunta in self.banco.desarrollo:
            with self.subTest(pregunta=pregunta.id):
                total = sum(criterio.peso for criterio in pregunta.criterios)
                self.assertAlmostEqual(total, 1.0, places=2)
                self.assertGreaterEqual(len(pregunta.criterios), 3)

    def test_fuentes_apuntan_a_pdfs_del_repositorio(self) -> None:
        disponibles = util.nombres_pdf()
        for pregunta in list(self.banco.mc) + list(self.banco.desarrollo):
            with self.subTest(pregunta=pregunta.id):
                self.assertIn(pregunta.fuente.get("archivo"), disponibles)
                self.assertGreaterEqual(int(pregunta.fuente.get("pagina", 0)), 1)

    def test_paginas_dentro_del_rango_de_los_pdfs(self) -> None:
        rutas = bank.archivos_banco()
        informe = bank.validar_archivos(rutas, estricto_paginas=True)
        self.assertTrue(informe["ok"], "\n".join(informe["errores"]))

    def test_estadisticas(self) -> None:
        stats = self.banco.estadisticas()
        self.assertEqual(stats["total_mc"], len(self.banco.mc))
        self.assertEqual(stats["total_desarrollo"], len(self.banco.desarrollo))
        self.assertEqual(set(stats["por_tema"]), set(bank.TEMAS))

    def test_dict_roundtrip(self) -> None:
        pregunta = self.banco.mc[0]
        copia = bank.PreguntaMC(
            id=pregunta.id,
            tema=pregunta.tema,
            subtema=pregunta.subtema,
            dificultad=pregunta.dificultad,
            pregunta=pregunta.pregunta,
            opciones=pregunta.opciones,
            explicacion=pregunta.explicacion,
            fuente=pregunta.fuente,
            tags=pregunta.tags,
        )
        self.assertEqual(copia.como_dict(), pregunta.como_dict())


class ValidadorTests(unittest.TestCase):
    def _validar(self, preguntas, *, desarrollo: bool = False) -> dict:
        with tempfile.TemporaryDirectory() as temporal:
            carpeta = Path(temporal) / ("short" if desarrollo else "mc")
            carpeta.mkdir(parents=True)
            ruta = carpeta / "prueba.json"
            ruta.write_text(json.dumps(preguntas, ensure_ascii=False), encoding="utf-8")
            return bank.validar_archivos([ruta])

    def _mc_valida(self) -> dict:
        return {
            "id": "prueba-001",
            "tema": "rest",
            "subtema": "cache",
            "dificultad": "media",
            "pregunta": "¿Qué restricción de REST permite reutilizar respuestas en intermediarios?",
            "opciones": [
                {"texto": "Cacheable", "correcta": True},
                {"texto": "Stateless", "correcta": False, "porque_no": "No conserva estado de sesión, pero no habilita guardar respuestas."},
                {"texto": "Layered System", "correcta": False, "porque_no": "Organiza en capas pero no define almacenamiento de respuestas."},
                {"texto": "Uniform Interface", "correcta": False, "porque_no": "Estandariza la interacción pero no el caché."},
            ],
            "explicacion": "Cacheable indica que la respuesta puede guardarse y reutilizarse, reduciendo latencia y carga del origen.",
            "fuente": {"archivo": "06-01-APIs REST-06-01.pdf", "pagina": 4},
            "tags": ["rest"],
        }

    def test_pregunta_valida(self) -> None:
        informe = self._validar([self._mc_valida()])
        self.assertTrue(informe["ok"], informe["errores"])

    def test_detecta_dos_correctas(self) -> None:
        datos = self._mc_valida()
        datos["opciones"][1]["correcta"] = True
        datos["opciones"][1]["porque_no"] = "justificación de relleno suficientemente larga"
        informe = self._validar([datos])
        self.assertFalse(informe["ok"])
        self.assertTrue(any("exactamente una" in e for e in informe["errores"]))

    def test_detecta_opcion_de_relleno(self) -> None:
        datos = self._mc_valida()
        datos["opciones"][2]["texto"] = "Todas las anteriores"
        informe = self._validar([datos])
        self.assertFalse(informe["ok"])

    def test_detecta_falta_de_porque_no(self) -> None:
        datos = self._mc_valida()
        datos["opciones"][1]["porque_no"] = ""
        informe = self._validar([datos])
        self.assertFalse(informe["ok"])

    def test_detecta_archivo_inexistente(self) -> None:
        datos = self._mc_valida()
        datos["fuente"]["archivo"] = "no-existe.pdf"
        informe = self._validar([datos])
        self.assertFalse(informe["ok"])

    def test_detecta_id_duplicado(self) -> None:
        datos = self._mc_valida()
        informe = self._validar([datos, dict(datos)])
        self.assertFalse(informe["ok"])
        self.assertTrue(any("duplicado" in e for e in informe["errores"]))

    def test_detecta_pesos_que_no_suman_uno(self) -> None:
        datos = {
            "id": "prueba-dev-001",
            "tema": "rest",
            "subtema": "stateless",
            "dificultad": "media",
            "pregunta": "Explicá por qué una API stateless escala mejor y qué costo introduce esa decisión.",
            "criterios": [
                {"id": "c1", "descripcion": "Define stateless correctamente", "peso": 0.2, "claves": ["no guarda estado"]},
                {"id": "c2", "descripcion": "Relaciona con escalado horizontal", "peso": 0.2, "claves": ["cualquier instancia"]},
                {"id": "c3", "descripcion": "Menciona un costo", "peso": 0.2, "claves": ["token"]},
            ],
            "respuesta_modelo": "Una API stateless no guarda estado de sesión en el servidor; cada request lleva todo lo necesario. "
                                "Por eso cualquier instancia puede atender cualquier request y se puede escalar horizontalmente. "
                                "El costo es trasladar el estado al cliente o a un almacén compartido y resolver la invalidación.",
            "fuente": {"archivo": "06-01-APIs REST-06-01.pdf", "pagina": 7},
            "tiempo_sugerido_min": 5,
        }
        informe = self._validar([datos], desarrollo=True)
        self.assertFalse(informe["ok"])
        self.assertTrue(any("sumar 1.0" in e for e in informe["errores"]))

    def test_detecta_pagina_fuera_de_rango(self) -> None:
        datos = self._mc_valida()
        datos["fuente"]["pagina"] = 999
        informe = self._validar([datos])
        self.assertTrue(informe["ok"])  # sin --estricto-paginas no se verifica
        with tempfile.TemporaryDirectory() as temporal:
            carpeta = Path(temporal) / "mc"
            carpeta.mkdir()
            ruta = carpeta / "prueba.json"
            ruta.write_text(json.dumps([datos], ensure_ascii=False), encoding="utf-8")
            informe = bank.validar_archivos([ruta], estricto_paginas=True)
            self.assertFalse(informe["ok"])


if __name__ == "__main__":
    unittest.main()
