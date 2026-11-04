"""Tests de generación aleatoria de exámenes."""

from __future__ import annotations

import tempfile
import unittest
from collections import Counter
from pathlib import Path

from quiz import bank, sampler, util


class SamplerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.banco = bank.cargar_banco()
        cls.spec = sampler.Especificacion.cargar()

    def setUp(self) -> None:
        self._temporal = tempfile.TemporaryDirectory()
        self._dir_original = util.EXAMENES_DIR
        util.EXAMENES_DIR = Path(self._temporal.name)
        self.historial = sampler.Historial()

    def tearDown(self) -> None:
        util.EXAMENES_DIR = self._dir_original
        self._temporal.cleanup()

    def test_examen_completo(self) -> None:
        examen = sampler.generar_examen(self.banco, self.spec, seed=1, historial=self.historial)
        self.assertEqual(len(examen.mc), 30)
        self.assertEqual(len(examen.desarrollo), 5)
        self.assertEqual(len({x["id"] for x in examen.mc}), 30)
        self.assertEqual(len(set(examen.desarrollo)), 5)
        # 5 preguntas de cada tema
        temas = Counter(self.banco.obtener_mc(x["id"]).tema for x in examen.mc)
        for tema, cantidad in self.spec.mc_por_tema.items():
            self.assertEqual(temas[tema], cantidad)
        # 5 temas distintos en desarrollo
        self.assertEqual(len({self.banco.tema_de(i) for i in examen.desarrollo}), 5)

    def test_misma_semilla_mismo_examen(self) -> None:
        a = sampler.generar_examen(self.banco, self.spec, seed=1234, historial=self.historial)
        b = sampler.generar_examen(self.banco, self.spec, seed=1234, historial=self.historial)
        self.assertEqual([x["id"] for x in a.mc], [x["id"] for x in b.mc])
        self.assertEqual(a.desarrollo, b.desarrollo)
        self.assertEqual([x["orden"] for x in a.mc], [x["orden"] for x in b.mc])

    def test_semillas_distintas_generan_examenes_distintos(self) -> None:
        a = sampler.generar_examen(self.banco, self.spec, seed=1, historial=self.historial)
        b = sampler.generar_examen(self.banco, self.spec, seed=2, historial=self.historial)
        self.assertNotEqual([x["id"] for x in a.mc], [x["id"] for x in b.mc])

    def test_sin_semilla_no_repite_el_orden(self) -> None:
        ids = {tuple(x["id"] for x in sampler.generar_examen(self.banco, self.spec).mc) for _ in range(3)}
        self.assertGreater(len(ids), 1)

    def test_opciones_barajadas_y_completas(self) -> None:
        examen = sampler.generar_examen(self.banco, self.spec, seed=7, historial=self.historial)
        for item in examen.mc:
            pregunta = self.banco.obtener_mc(item["id"])
            self.assertEqual(sorted(item["orden"]), list(range(len(pregunta.opciones))))
            publica = examen.vista_publica(self.banco)
            self.assertTrue(publica["preguntas"])

    def test_vista_publica_no_filtra_respuestas(self) -> None:
        examen = sampler.generar_examen(self.banco, self.spec, seed=3, historial=self.historial)
        publica = examen.vista_publica(self.banco)
        for pregunta in publica["preguntas"]:
            self.assertNotIn("correcta", pregunta)
            self.assertNotIn("explicacion", pregunta)
        con_soluciones = examen.vista_publica(self.banco, incluir_soluciones=True)
        mc = [p for p in con_soluciones["preguntas"] if p["tipo"] == "mc"]
        self.assertTrue(all("correcta" in p for p in mc))

    def test_seed_reproducible_serializado(self) -> None:
        examen = sampler.generar_examen(self.banco, self.spec, seed=99, historial=self.historial)
        examen.guardar()
        recuperado = sampler.Examen.cargar(examen.id)
        self.assertEqual(examen.como_dict(), recuperado.como_dict())
        self.assertEqual(len(recuperado.mc), 30)

    def test_historial_rota_las_preguntas(self) -> None:
        for _ in range(6):
            sampler.generar_examen(self.banco, self.spec, historial=self.historial)
        usos = list(self.historial.usos.values())
        self.assertGreaterEqual(len(usos), 30 * 6)
        self.assertLessEqual(max(usos) - min(usos), 2, "el muestreo debería repartir el uso")

    def test_examen_por_tema(self) -> None:
        spec = self.spec.ajustar(temas=["nosql"], mc_por_tema={"nosql": 12}, desarrollo_total=2)
        examen = sampler.generar_examen(self.banco, spec, seed=5, historial=self.historial)
        self.assertEqual(len(examen.mc), 12)
        self.assertTrue(all(self.banco.obtener_mc(x["id"]).tema == "nosql" for x in examen.mc))
        self.assertEqual(len(examen.desarrollo), 2)
        self.assertTrue(all(self.banco.tema_de(i) == "nosql" for i in examen.desarrollo))

    def test_practica(self) -> None:
        examen = sampler.crear_examen_practica(self.banco, tema="rest", cantidad=8, incluir_desarrollo=True)
        self.assertEqual(len(examen.mc), 8)
        self.assertEqual(len(examen.desarrollo), 1)
        self.assertTrue(all(self.banco.obtener_mc(x["id"]).tema == "rest" for x in examen.mc))

    def test_pedir_mas_preguntas_de_las_que_hay(self) -> None:
        spec = self.spec.ajustar(temas=["rest"], mc_por_tema={"rest": 9999}, desarrollo_total=0)
        with self.assertRaises(ValueError):
            sampler.generar_examen(self.banco, spec, historial=self.historial)

    def test_especificacion_desde_dict(self) -> None:
        spec = sampler.Especificacion.desde_dict(
            {"mc_por_tema": {"rest": 3}, "desarrollo_total": 1, "pesos": {"multiple": 1, "desarrollo": 1}}
        )
        self.assertEqual(spec.mc_por_tema, {"rest": 3})
        self.assertAlmostEqual(spec.pesos["multiple"], 0.5)
        with self.assertRaises(ValueError):
            sampler.Especificacion.desde_dict({"mc_por_tema": {"tema-inexistente": 3}})

    def test_ids_de_examen_unicos(self) -> None:
        ids = {sampler.generar_examen(self.banco, self.spec, historial=self.historial).id for _ in range(5)}
        self.assertEqual(len(ids), 5)


if __name__ == "__main__":
    unittest.main()
