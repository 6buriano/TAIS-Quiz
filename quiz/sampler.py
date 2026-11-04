"""Generación aleatoria de exámenes.

Cada examen se arma muestreando preguntas del banco, priorizando las que se
usaron menos veces (así no se repiten siempre las mismas) y mezclando el orden
de las opciones. Con ``seed`` fija el examen es reproducible; sin seed usa
entropía del sistema, por lo que cada intento es distinto.
"""

from __future__ import annotations

import random
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import bank, util
from .bank import Banco, PreguntaDesarrollo, PreguntaMC

MC_POR_DEFECTO: Dict[str, int] = {
    "arquitectura": 5,
    "contenedores": 5,
    "nosql": 5,
    "cache": 5,
    "asincronia": 5,
    "rest": 5,
}


# ---------------------------------------------------------------------------
# Especificación del examen
# ---------------------------------------------------------------------------


@dataclass
class Especificacion:
    nombre: str = "Examen TAIS"
    descripcion: str = ""
    mc_por_tema: Dict[str, int] = field(default_factory=lambda: dict(MC_POR_DEFECTO))
    desarrollo_total: int = 5
    desarrollo_max_por_tema: int = 1
    mezclar_opciones: bool = True
    pesos: Dict[str, float] = field(default_factory=lambda: {"multiple": 0.6, "desarrollo": 0.4})
    tiempo_limite_min: int = 100

    # -- construcción ------------------------------------------------------
    @classmethod
    def desde_dict(cls, datos: Dict[str, Any]) -> "Especificacion":
        if not isinstance(datos, dict):
            raise ValueError("La especificación debe ser un objeto JSON")
        mc = datos.get("mc_por_tema") or dict(MC_POR_DEFECTO)
        if not isinstance(mc, dict):
            raise ValueError("'mc_por_tema' debe ser un objeto {tema: cantidad}")
        limpio: Dict[str, int] = {}
        for tema, cantidad in mc.items():
            if tema not in bank.TEMAS:
                raise ValueError(f"Tema desconocido en la especificación: {tema!r}")
            cantidad = int(cantidad)
            if cantidad < 0:
                raise ValueError(f"Cantidad inválida para {tema}: {cantidad}")
            if cantidad:
                limpio[tema] = cantidad
        pesos = datos.get("pesos") or {"multiple": 0.6, "desarrollo": 0.4}
        pesos = {"multiple": float(pesos.get("multiple", 0.6)), "desarrollo": float(pesos.get("desarrollo", 0.4))}
        suma = pesos["multiple"] + pesos["desarrollo"]
        if suma <= 0:
            raise ValueError("Los pesos del examen deben ser positivos")
        pesos = {k: v / suma for k, v in pesos.items()}
        return cls(
            nombre=str(datos.get("nombre") or "Examen TAIS"),
            descripcion=str(datos.get("descripcion") or ""),
            mc_por_tema=limpio,
            desarrollo_total=max(0, int(datos.get("desarrollo_total", 5))),
            desarrollo_max_por_tema=max(1, int(datos.get("desarrollo_max_por_tema", 1))),
            mezclar_opciones=bool(datos.get("mezclar_opciones", True)),
            pesos=pesos,
            tiempo_limite_min=max(0, int(datos.get("tiempo_limite_min", 100))),
        )

    @classmethod
    def cargar(cls, ruta: Optional[Path] = None) -> "Especificacion":
        ruta = Path(ruta) if ruta else util.SPEC_PATH
        if not ruta.is_file():
            return cls()
        return cls.desde_dict(util.cargar_json(ruta))

    def como_dict(self) -> Dict[str, Any]:
        return {
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "mc_por_tema": dict(self.mc_por_tema),
            "desarrollo_total": self.desarrollo_total,
            "desarrollo_max_por_tema": self.desarrollo_max_por_tema,
            "mezclar_opciones": self.mezclar_opciones,
            "pesos": dict(self.pesos),
            "tiempo_limite_min": self.tiempo_limite_min,
        }

    # -- variantes ---------------------------------------------------------
    def ajustar(
        self,
        *,
        temas: Optional[Sequence[str]] = None,
        mc_por_tema: Optional[Dict[str, int]] = None,
        desarrollo_total: Optional[int] = None,
    ) -> "Especificacion":
        """Devuelve una copia con los ajustes pedidos (sin mutar el original)."""
        nuevo = Especificacion.desde_dict(self.como_dict())
        if temas is not None:
            for tema in temas:
                if tema not in bank.TEMAS:
                    raise ValueError(f"Tema desconocido: {tema!r}")
            nuevo.mc_por_tema = {t: nuevo.mc_por_tema.get(t, 0) for t in temas}
            nuevo.mc_por_tema = {t: c for t, c in nuevo.mc_por_tema.items() if c > 0}
        if mc_por_tema is not None:
            for tema, cantidad in mc_por_tema.items():
                if tema not in bank.TEMAS:
                    raise ValueError(f"Tema desconocido: {tema!r}")
                nuevo.mc_por_tema[tema] = int(cantidad)
            nuevo.mc_por_tema = {t: c for t, c in nuevo.mc_por_tema.items() if c > 0}
        if desarrollo_total is not None:
            nuevo.desarrollo_total = max(0, int(desarrollo_total))
        return nuevo

    @property
    def total_mc(self) -> int:
        return sum(self.mc_por_tema.values())


# ---------------------------------------------------------------------------
# Historial de uso (para rotar preguntas entre intentos)
# ---------------------------------------------------------------------------


class Historial:
    """Cuenta cuántas veces se usó cada pregunta para evitar repeticiones."""

    def __init__(self, ruta: Optional[Path] = None) -> None:
        self.ruta = Path(ruta) if ruta else util.EXAMENES_DIR / "historial.json"
        self.usos: Dict[str, int] = {}
        self.ultima_vez: Dict[str, str] = {}
        self._cargar()

    def _cargar(self) -> None:
        if not self.ruta.is_file():
            return
        try:
            datos = util.cargar_json(self.ruta)
        except Exception:
            return
        if isinstance(datos, dict):
            self.usos = {str(k): int(v) for k, v in (datos.get("usos") or {}).items()}
            self.ultima_vez = {str(k): str(v) for k, v in (datos.get("ultima_vez") or {}).items()}

    def contar(self, id_pregunta: str) -> int:
        return self.usos.get(id_pregunta, 0)

    def registrar(self, ids: Sequence[str]) -> None:
        ahora = util.ahora_iso()
        for id_pregunta in ids:
            self.usos[id_pregunta] = self.usos.get(id_pregunta, 0) + 1
            self.ultima_vez[id_pregunta] = ahora
        try:
            util.guardar_json(self.ruta, {"usos": self.usos, "ultima_vez": self.ultima_vez})
        except OSError:
            # El historial es una comodidad, no un requisito: si no se puede
            # escribir (permisos, disco lleno) el examen sigue funcionando.
            pass


# ---------------------------------------------------------------------------
# Examen
# ---------------------------------------------------------------------------


@dataclass
class Examen:
    id: str
    seed: int
    creado: str
    especificacion: Dict[str, Any]
    mc: List[Dict[str, Any]]          # [{"id": ..., "orden": [indices de opciones]}]
    desarrollo: List[str]             # ids de preguntas de desarrollo

    # -- serialización -----------------------------------------------------
    def como_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "seed": self.seed,
            "creado": self.creado,
            "especificacion": dict(self.especificacion),
            "mc": [dict(x) for x in self.mc],
            "desarrollo": list(self.desarrollo),
            "version": 1,
        }

    @classmethod
    def desde_dict(cls, datos: Dict[str, Any]) -> "Examen":
        return cls(
            id=datos["id"],
            seed=int(datos.get("seed", 0)),
            creado=str(datos.get("creado", "")),
            especificacion=dict(datos.get("especificacion") or {}),
            mc=[{"id": q["id"], "orden": [int(i) for i in q["orden"]]} for q in datos.get("mc", [])],
            desarrollo=[str(x) for x in datos.get("desarrollo", [])],
        )

    def guardar(self) -> Path:
        return util.guardar_json(util.EXAMENES_DIR / f"{self.id}.json", self.como_dict())

    @classmethod
    def cargar(cls, id_examen: str) -> "Examen":
        ruta = util.EXAMENES_DIR / f"{id_examen}.json"
        if not ruta.is_file():
            raise FileNotFoundError(f"No existe el examen {id_examen!r}")
        return cls.desde_dict(util.cargar_json(ruta))

    # -- vistas ------------------------------------------------------------
    def vista_publica(self, banco: Banco, *, incluir_soluciones: bool = False) -> Dict[str, Any]:
        """Examen para el alumno: sin respuestas correctas ni explicaciones."""
        preguntas: List[Dict[str, Any]] = []
        for indice, item in enumerate(self.mc, 1):
            pregunta = banco.obtener_mc(item["id"])
            orden = item["orden"]
            opciones = [
                {"letra": _letra(pos), "texto": pregunta.opciones[orden[pos]].texto}
                for pos in range(len(orden))
            ]
            entrada: Dict[str, Any] = {
                "numero": indice,
                "tipo": "mc",
                "id": pregunta.id,
                "tema": pregunta.tema,
                "subtema": pregunta.subtema,
                "dificultad": pregunta.dificultad,
                "pregunta": pregunta.pregunta,
                "opciones": opciones,
            }
            if incluir_soluciones:
                entrada["correcta"] = _posicion_correcta(pregunta, orden)
                entrada["explicacion"] = pregunta.explicacion
                entrada["referencia"] = pregunta.referencia()
            preguntas.append(entrada)
        for indice, id_pregunta in enumerate(self.desarrollo, 1):
            pregunta = banco.obtener_desarrollo(id_pregunta)
            entrada = {
                "numero": len(self.mc) + indice,
                "tipo": "desarrollo",
                "id": pregunta.id,
                "tema": pregunta.tema,
                "subtema": pregunta.subtema,
                "dificultad": pregunta.dificultad,
                "pregunta": pregunta.pregunta,
                "tiempo_sugerido_min": pregunta.tiempo_sugerido_min,
                "cantidad_criterios": len(pregunta.criterios),
            }
            if incluir_soluciones:
                # En la práctica, la respuesta modelo y la rúbrica se entregan
                # recién al corregir (POST /api/corregir-desarrollo), no con el
                # examen: así el intento sigue teniendo sentido.
                entrada["referencia"] = pregunta.referencia()
            preguntas.append(entrada)
        return {
            "id": self.id,
            "creado": self.creado,
            "especificacion": dict(self.especificacion),
            "preguntas": preguntas,
            "total_mc": len(self.mc),
            "total_desarrollo": len(self.desarrollo),
        }


def _letra(posicion: int) -> str:
    return "ABCDE"[posicion] if 0 <= posicion < 5 else "?"


def _posicion_correcta(pregunta: PreguntaMC, orden: Sequence[int]) -> int:
    return list(orden).index(pregunta.indice_correcto)


# ---------------------------------------------------------------------------
# Muestreo
# ---------------------------------------------------------------------------


def _elegir(pool: Sequence[Any], cantidad: int, rng: random.Random, historial: Optional[Historial]) -> List[Any]:
    """Elige `cantidad` preguntas del pool, priorizando las menos usadas."""
    if cantidad <= 0:
        return []
    if cantidad > len(pool):
        raise ValueError(f"No hay preguntas suficientes: se pidieron {cantidad} y hay {len(pool)}")
    if historial is None:
        return rng.sample(list(pool), cantidad)

    # Ordenar por cantidad de usos y, dentro de cada nivel, al azar.
    ordenadas = sorted(pool, key=lambda p: (historial.contar(getattr(p, "id", "")), rng.random()))
    return ordenadas[:cantidad]


def generar_examen(
    banco: Banco,
    especificacion: Optional[Especificacion] = None,
    *,
    seed: Optional[int] = None,
    historial: Optional[Historial] = None,
) -> Examen:
    """Genera un examen aleatorio respetando la especificación."""
    especificacion = especificacion or Especificacion.cargar()
    semilla = int(seed) if seed is not None else secrets.randbelow(2**31 - 1)
    rng = random.Random(semilla)
    historial = historial if historial is not None else Historial()
    # Con una semilla explícita el examen debe ser reproducible aunque el
    # historial de uso haya cambiado: en ese caso no se rota por uso previo.
    rotar = seed is None
    historial_para_muestra = historial if rotar else None

    # -- múltiple opción ----------------------------------------------------
    mc_items: List[Dict[str, Any]] = []
    for tema, cantidad in especificacion.mc_por_tema.items():
        disponibles = banco.mc_de(tema)
        try:
            elegidas = _elegir(disponibles, cantidad, rng, historial_para_muestra)
        except ValueError as exc:
            raise ValueError(f"Tema {tema}: {exc}") from exc
        for pregunta in elegidas:
            n = len(pregunta.opciones)
            orden = list(range(n))
            if especificacion.mezclar_opciones:
                rng.shuffle(orden)
            mc_items.append({"id": pregunta.id, "orden": orden})

    # -- desarrollo ---------------------------------------------------------
    desarrollo: List[str] = []
    total_desarrollo = especificacion.desarrollo_total
    if total_desarrollo > 0:
        temas = [t for t in especificacion.mc_por_tema if banco.desarrollo_de(t)]
        if not temas:
            temas = banco.temas_disponibles()
        # Si se piden más preguntas que temas hay, se relaja el tope por tema
        # (por ejemplo al practicar un único tema).
        cupo = max(
            especificacion.desarrollo_max_por_tema,
            -(-total_desarrollo // max(1, len(temas))),
        )
        candidatas: List[Tuple[int, float, str, PreguntaDesarrollo]] = []
        for tema in temas:
            for pregunta in banco.desarrollo_de(tema):
                candidatas.append(
                    (historial.contar(pregunta.id) if rotar else 0, rng.random(), tema, pregunta)
                )
        candidatas.sort(key=lambda x: (x[0], x[1]))
        usados_por_tema: Dict[str, int] = {}
        for _usos, _azar, tema, pregunta in candidatas:
            if len(desarrollo) >= total_desarrollo:
                break
            if usados_por_tema.get(tema, 0) >= cupo:
                continue
            desarrollo.append(pregunta.id)
            usados_por_tema[tema] = usados_por_tema.get(tema, 0) + 1
        if len(desarrollo) < total_desarrollo:
            raise ValueError(
                f"No hay suficientes preguntas de desarrollo: se pidieron "
                f"{total_desarrollo} y hay {len(desarrollo)} disponibles"
            )

    examen = Examen(
        id=_nuevo_id(),
        seed=semilla,
        creado=util.ahora_iso(),
        especificacion=especificacion.como_dict(),
        mc=mc_items,
        desarrollo=desarrollo,
    )
    historial.registrar([item["id"] for item in mc_items] + list(desarrollo))
    return examen


def _nuevo_id() -> str:
    marca = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"tais-{marca}-{secrets.token_hex(3)}"


def crear_examen_practica(
    banco: Banco,
    tema: Optional[str] = None,
    cantidad: int = 10,
    *,
    incluir_desarrollo: bool = False,
    seed: Optional[int] = None,
) -> Examen:
    """Examen corto de práctica con soluciones disponibles."""
    if tema:
        if tema not in bank.TEMAS:
            raise ValueError(f"Tema desconocido: {tema!r}")
        temas = [tema]
    else:
        temas = [t for t in bank.TEMAS if banco.mc_de(t)]
    rng = random.Random(seed if seed is not None else secrets.randbelow(2**31 - 1))
    pool: List[Any] = []
    for t in temas:
        pool.extend(banco.mc_de(t))
    if not pool:
        raise ValueError("El banco no tiene preguntas para la práctica")
    elegidas = rng.sample(pool, min(cantidad, len(pool)))
    mc_items = []
    for pregunta in elegidas:
        orden = list(range(len(pregunta.opciones)))
        rng.shuffle(orden)
        mc_items.append({"id": pregunta.id, "orden": orden})
    desarrollo: List[str] = []
    if incluir_desarrollo:
        depool: List[Any] = []
        for t in temas:
            depool.extend(banco.desarrollo_de(t))
        if depool:
            desarrollo = [rng.choice(depool).id]
    especificacion = Especificacion(
        nombre="Práctica",
        mc_por_tema={},
        desarrollo_total=len(desarrollo),
        tiempo_limite_min=0,
    )
    return Examen(
        id=_nuevo_id(),
        seed=int(seed or 0),
        creado=util.ahora_iso(),
        especificacion=especificacion.como_dict(),
        mc=mc_items,
        desarrollo=desarrollo,
    )
