"""Tests de corrección (heurística y con modelo simulado)."""

from __future__ import annotations

import unittest

from quiz import bank, grader, sampler, util


class _ClienteFalso:
    """Cliente LLM de mentira para probar el flujo sin red."""

    def __init__(self, respuesta=None, falla=False):
        self.respuesta = respuesta or {}
        self.falla = falla
        self.llamadas = 0

    def disponible(self, refrescar=False):
        return True

    def estado(self):
        return {"disponible": True, "proveedor": "falso", "modelo": "falso", "url": "http://test", "detalle": ""}

    def chat_json(self, mensajes, **kwargs):
        self.llamadas += 1
        if self.falla:
            raise grader.llm.ErrorLLM("falla simulada")
        return self.respuesta


class HeuristicaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.banco = bank.cargar_banco()
        cls.corrector = grader.CorrectorHeuristico()

    def test_respuesta_modelo_saca_puntaje_completo(self) -> None:
        for pregunta in self.banco.desarrollo:
            with self.subTest(pregunta=pregunta.id):
                correccion = self.corrector.corregir(pregunta, pregunta.respuesta_modelo)
                self.assertGreaterEqual(correccion.puntaje, 0.9)

    def test_respuesta_vacia_da_cero(self) -> None:
        pregunta = self.banco.desarrollo[0]
        correccion = self.corrector.corregir(pregunta, "   ")
        self.assertEqual(correccion.puntaje, 0.0)
        self.assertEqual(correccion.modo, "heuristica")
        self.assertTrue(correccion.faltantes)

    def test_respuesta_fuera_de_tema_no_puntua(self) -> None:
        pregunta = self.banco.desarrollo[0]
        correccion = self.corrector.corregir(
            pregunta,
            "La capital de Francia es París y el fútbol se juega con once jugadores por equipo.",
        )
        self.assertLess(correccion.puntaje, 0.4)

    def test_respuesta_copiada_de_las_claves(self) -> None:
        pregunta = self.banco.desarrollo[0]
        texto = " ".join(clave for criterio in pregunta.criterios for clave in criterio.claves)
        correccion = self.corrector.corregir(pregunta, texto)
        self.assertGreaterEqual(correccion.puntaje, 0.5)

    def test_texto_muy_corto_se_penaliza(self) -> None:
        pregunta = self.banco.desarrollo[0]
        clave = pregunta.criterios[0].claves[0]
        corta = self.corrector.corregir(pregunta, clave)
        larga = self.corrector.corregir(
            pregunta,
            f"{clave}. Además, esto se desarrolla con más detalle porque la consigna pide explicar el porqué "
            "y relacionarlo con el resto de los conceptos del tema, incluyendo las consecuencias prácticas.",
        )
        self.assertLessEqual(corta.puntaje, 0.35)
        self.assertGreaterEqual(larga.puntaje, corta.puntaje)

    def test_detecta_sinonimos_con_y_sin_acentos(self) -> None:
        pregunta = self.banco.desarrollo[0]
        texto = " ".join(clave for criterio in pregunta.criterios for clave in criterio.claves)
        sin_acentos = util.sin_acentos(texto)
        a = self.corrector.corregir(pregunta, texto)
        b = self.corrector.corregir(pregunta, sin_acentos)
        self.assertAlmostEqual(a.puntaje, b.puntaje, places=2)


class CorrectorLLMTests(unittest.TestCase):
    def setUp(self) -> None:
        self.banco = bank.cargar_banco()
        self.pregunta = self.banco.desarrollo[0]

    def _respuesta(self) -> dict:
        return {
            "criterios": [
                {"id": c.id, "cumplido": True, "detalle": "cubierto"} for c in self.pregunta.criterios
            ],
            "puntaje": 1.0,
            "comentario": "Muy completa.",
            "faltantes": [],
        }

    def test_usa_el_modelo(self) -> None:
        cliente = _ClienteFalso(self._respuesta())
        corrector = grader.CorrectorLLM(cliente=cliente)
        correccion = corrector.corregir(self.pregunta, "Una respuesta cualquiera con contenido suficiente.")
        self.assertEqual(correccion.modo, "llm")
        self.assertEqual(correccion.puntaje, 1.0)
        self.assertEqual(cliente.llamadas, 1)
        self.assertTrue(all(c["cumplido"] for c in correccion.criterios))

    def test_prioriza_los_criterios_si_el_puntaje_se_contradice(self) -> None:
        datos = self._respuesta()
        datos["puntaje"] = 0.1
        for criterio in datos["criterios"]:
            criterio["cumplido"] = True
        corrector = grader.CorrectorLLM(cliente=_ClienteFalso(datos))
        correccion = corrector.corregir(self.pregunta, "Texto suficientemente largo para evaluar.")
        self.assertGreaterEqual(correccion.puntaje, 0.8)

    def test_cae_a_heuristica_si_el_modelo_falla(self) -> None:
        corrector = grader.CorrectorLLM(cliente=_ClienteFalso(falla=True))
        correccion = corrector.corregir(self.pregunta, self.pregunta.respuesta_modelo)
        self.assertEqual(correccion.modo, "heuristica")
        self.assertIn("falló el modelo", correccion.error)
        self.assertGreaterEqual(correccion.puntaje, 0.9)

    def test_respuesta_vacia_no_llama_al_modelo(self) -> None:
        cliente = _ClienteFalso(self._respuesta())
        corrector = grader.CorrectorLLM(cliente=cliente)
        correccion = corrector.corregir(self.pregunta, "   \n ")
        self.assertEqual(correccion.modo, "heuristica")
        self.assertEqual(correccion.puntaje, 0.0)
        self.assertEqual(cliente.llamadas, 0)


class ExamenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.banco = bank.cargar_banco()
        cls.spec = sampler.Especificacion.cargar()

    def _respuestas_correctas(self, examen: sampler.Examen) -> dict:
        mc = {}
        for item in examen.mc:
            pregunta = self.banco.obtener_mc(item["id"])
            mc[pregunta.id] = item["orden"].index(pregunta.indice_correcto)
        return {"mc": mc, "desarrollo": {}}

    def test_todo_correcto(self) -> None:
        examen = sampler.generar_examen(self.banco, self.spec, seed=11)
        resultado = grader.corregir_examen(self.banco, examen, self._respuestas_correctas(examen))
        self.assertEqual(resultado["resumen"]["mc_aciertos"], 30)
        self.assertEqual(resultado["resumen"]["mc_porcentaje"], 100.0)
        self.assertLessEqual(resultado["resumen"]["nota_100"], 100.0)

    def test_todo_incorrecto(self) -> None:
        examen = sampler.generar_examen(self.banco, self.spec, seed=12)
        mc = {item["id"]: 0 for item in examen.mc}
        # asegurar que la opción 0 sea incorrecta
        for item in examen.mc:
            pregunta = self.banco.obtener_mc(item["id"])
            correcta = item["orden"].index(pregunta.indice_correcto)
            mc[item["id"]] = (correcta + 1) % len(item["orden"])
        resultado = grader.corregir_examen(self.banco, examen, {"mc": mc, "desarrollo": {}})
        self.assertEqual(resultado["resumen"]["mc_aciertos"], 0)
        self.assertEqual(resultado["resumen"]["nota_100"], 0.0)

    def test_sin_responder(self) -> None:
        examen = sampler.generar_examen(self.banco, self.spec, seed=13)
        resultado = grader.corregir_examen(self.banco, examen, {})
        self.assertEqual(resultado["resumen"]["mc_aciertos"], 0)
        self.assertTrue(all(item["elegida"] is None for item in resultado["mc"]))
        self.assertTrue(all(item["respuesta"] == "" for item in resultado["desarrollo"]))

    def test_indice_fuera_de_rango_se_ignora(self) -> None:
        examen = sampler.generar_examen(self.banco, self.spec, seed=14)
        mc = {item["id"]: 99 for item in examen.mc}
        resultado = grader.corregir_examen(self.banco, examen, {"mc": mc})
        self.assertTrue(all(item["elegida"] is None for item in resultado["mc"]))
        self.assertEqual(resultado["resumen"]["mc_aciertos"], 0)

    def test_pesos_y_nota(self) -> None:
        examen = sampler.generar_examen(self.banco, self.spec, seed=15)
        respuestas = self._respuestas_correctas(examen)
        respuestas["desarrollo"] = {
            item: self.banco.obtener_desarrollo(item).respuesta_modelo for item in examen.desarrollo
        }
        resultado = grader.corregir_examen(self.banco, examen, respuestas)
        self.assertGreaterEqual(resultado["resumen"]["desarrollo_porcentaje"], 90.0)
        self.assertGreaterEqual(resultado["resumen"]["nota_100"], 90.0)

    def test_examen_solo_multiple_opcion(self) -> None:
        spec = self.spec.ajustar(temas=["rest"], mc_por_tema={"rest": 5}, desarrollo_total=0)
        examen = sampler.generar_examen(self.banco, spec, seed=16)
        resultado = grader.corregir_examen(self.banco, examen, self._respuestas_correctas(examen))
        self.assertEqual(resultado["resumen"]["nota_100"], 100.0)
        self.assertEqual(resultado["resumen"]["desarrollo_total"], 0)

    def test_detalle_para_revision(self) -> None:
        examen = sampler.generar_examen(self.banco, self.spec, seed=17)
        resultado = grader.corregir_examen(self.banco, examen, {})
        primero = resultado["mc"][0]
        self.assertIn("opciones", primero)
        self.assertTrue(any(opcion["es_correcta"] for opcion in primero["opciones"]))
        self.assertTrue(primero["explicacion"])
        self.assertTrue(primero["referencia"])
        self.assertEqual(len(resultado["desarrollo"]), 5)
        self.assertIn("criterios", resultado["desarrollo"][0]["correccion"])

    def test_usa_corrector_llm_en_el_examen(self) -> None:
        from quiz.bank import Criterio, PreguntaDesarrollo

        pregunta = PreguntaDesarrollo(
            id="dev-test-001",
            tema="rest",
            subtema="x",
            dificultad="media",
            pregunta="Explicá algo.",
            criterios=(Criterio("c1", "criterio uno", 1.0, ("clave",)),),
            respuesta_modelo="modelo",
            fuente={"archivo": "06-01-APIs REST-06-01.pdf", "pagina": 1},
        )
        cliente = _ClienteFalso({
            "criterios": [{"id": "c1", "cumplido": True, "detalle": "ok"}],
            "puntaje": 1.0,
            "comentario": "ok",
        })
        resultado = grader.CorrectorLLM(cliente=cliente).corregir(pregunta, "respuesta")
        self.assertEqual(resultado.modo, "llm")
        self.assertEqual(resultado.puntaje, 1.0)


class CorrectorAutoTests(unittest.TestCase):
    def test_preferencia_heuristica(self) -> None:
        corrector = grader.CorrectorAuto(preferencia="heuristica")
        self.assertEqual(corrector.estado()["modo_efectivo"], "heuristica")

    def test_corrige_una_sola(self) -> None:
        banco = bank.cargar_banco()
        pregunta = banco.desarrollo[0]
        datos = grader.corregir_una_desarrollo(banco, pregunta.id, pregunta.respuesta_modelo)
        self.assertEqual(datos["id"], pregunta.id)
        self.assertIn("correccion", datos)
        self.assertIn("respuesta_modelo", datos)
        self.assertGreaterEqual(datos["correccion"]["puntaje"], 0.9)


if __name__ == "__main__":
    unittest.main()
