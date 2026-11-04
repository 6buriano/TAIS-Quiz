"""Modelo y validación del banco de preguntas.

El banco vive en ``content/bank/mc/*.json`` (múltiple opción) y
``content/bank/short/*.json`` (desarrollo corto). Cada archivo contiene una
lista de preguntas (o un objeto ``{"preguntas": [...]}``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import util

#: Temas del curso. La clave se usa en todo el código y en los archivos del banco.
TEMAS: Dict[str, str] = {
    "arquitectura": "Arquitectura, tácticas y estilos",
    "contenedores": "Contenerización y CI/CD",
    "nosql": "Persistencia no relacional",
    "cache": "Caché, bases en memoria y Redis",
    "asincronia": "Programación asincrónica",
    "rest": "APIs REST",
}

DIFICULTADES = ("facil", "media", "dificil")

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,60}$")

#: Expresiones que delatan opciones de relleno ("todas las anteriores", etc.).
PATRONES_PROHIBIDOS = (
    r"\btodas las anteriores\b",
    r"\bninguna de las anteriores\b",
    r"\bambas( son correctas)?\b",
    r"\bninguna\b.*\bcorrecta\b",
    r"\btodas\b.*\bcorrectas\b",
)


class BancoInvalido(Exception):
    """Se lanza cuando el banco no cumple el esquema."""

    def __init__(self, errores: Sequence[str]) -> None:
        self.errores = list(errores)
        super().__init__("\n".join(self.errores))


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Opcion:
    texto: str
    correcta: bool
    porque_no: str = ""


@dataclass(frozen=True)
class PreguntaMC:
    id: str
    tema: str
    subtema: str
    dificultad: str
    pregunta: str
    opciones: Tuple[Opcion, ...]
    explicacion: str
    fuente: Dict[str, Any]
    tags: Tuple[str, ...] = ()

    @property
    def indice_correcto(self) -> int:
        for i, op in enumerate(self.opciones):
            if op.correcta:
                return i
        raise ValueError(f"{self.id}: sin opción correcta")

    def referencia(self) -> str:
        archivo = self.fuente.get("archivo", "")
        pagina = self.fuente.get("pagina")
        return f"{archivo} (pág. {pagina})" if pagina else str(archivo)

    def como_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tema": self.tema,
            "subtema": self.subtema,
            "dificultad": self.dificultad,
            "pregunta": self.pregunta,
            "opciones": [
                {"texto": o.texto, "correcta": o.correcta, "porque_no": o.porque_no}
                for o in self.opciones
            ],
            "explicacion": self.explicacion,
            "fuente": dict(self.fuente),
            "tags": list(self.tags),
        }


@dataclass(frozen=True)
class Criterio:
    id: str
    descripcion: str
    peso: float
    claves: Tuple[str, ...]


@dataclass(frozen=True)
class PreguntaDesarrollo:
    id: str
    tema: str
    subtema: str
    dificultad: str
    pregunta: str
    criterios: Tuple[Criterio, ...]
    respuesta_modelo: str
    fuente: Dict[str, Any]
    tiempo_sugerido_min: int = 5
    tags: Tuple[str, ...] = ()

    def referencia(self) -> str:
        archivo = self.fuente.get("archivo", "")
        pagina = self.fuente.get("pagina")
        return f"{archivo} (pág. {pagina})" if pagina else str(archivo)

    def como_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tema": self.tema,
            "subtema": self.subtema,
            "dificultad": self.dificultad,
            "pregunta": self.pregunta,
            "criterios": [
                {"id": c.id, "descripcion": c.descripcion, "peso": c.peso, "claves": list(c.claves)}
                for c in self.criterios
            ],
            "respuesta_modelo": self.respuesta_modelo,
            "fuente": dict(self.fuente),
            "tiempo_sugerido_min": self.tiempo_sugerido_min,
            "tags": list(self.tags),
        }


@dataclass
class Banco:
    mc: List[PreguntaMC] = field(default_factory=list)
    desarrollo: List[PreguntaDesarrollo] = field(default_factory=list)
    archivos: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._mc_idx = {q.id: q for q in self.mc}
        self._dev_idx = {q.id: q for q in self.desarrollo}

    # -- consultas ---------------------------------------------------------
    def mc_de(self, tema: str) -> List[PreguntaMC]:
        return [q for q in self.mc if q.tema == tema]

    def desarrollo_de(self, tema: str) -> List[PreguntaDesarrollo]:
        return [q for q in self.desarrollo if q.tema == tema]

    def obtener_mc(self, id_pregunta: str) -> PreguntaMC:
        return self._mc_idx[id_pregunta]

    def obtener_desarrollo(self, id_pregunta: str) -> PreguntaDesarrollo:
        return self._dev_idx[id_pregunta]

    def tema_de(self, id_pregunta: str) -> str:
        if id_pregunta in self._mc_idx:
            return self._mc_idx[id_pregunta].tema
        return self._dev_idx[id_pregunta].tema

    def temas_disponibles(self) -> List[str]:
        return [t for t in TEMAS if self.mc_de(t)]

    def estadisticas(self) -> Dict[str, Any]:
        por_tema: Dict[str, Dict[str, int]] = {}
        for tema in TEMAS:
            mc = self.mc_de(tema)
            dev = self.desarrollo_de(tema)
            por_tema[tema] = {
                "mc": len(mc),
                "desarrollo": len(dev),
                "facil": sum(1 for q in mc if q.dificultad == "facil"),
                "media": sum(1 for q in mc if q.dificultad == "media"),
                "dificil": sum(1 for q in mc if q.dificultad == "dificil"),
            }
        return {
            "total_mc": len(self.mc),
            "total_desarrollo": len(self.desarrollo),
            "por_tema": por_tema,
            "archivos": list(self.archivos),
        }


# ---------------------------------------------------------------------------
# Validación
# ---------------------------------------------------------------------------


def _texto(valor: Any) -> bool:
    return isinstance(valor, str) and valor.strip() != ""


def validar_mc(datos: Any, *, ruta: str = "") -> Tuple[List[str], List[str]]:
    """Valida una pregunta de múltiple opción. Devuelve (errores, advertencias)."""
    errores: List[str] = []
    advertencias: List[str] = []
    prefijo = f"{ruta}: " if ruta else ""

    if not isinstance(datos, dict):
        return [f"{prefijo}la pregunta debe ser un objeto JSON"], advertencias

    qid = datos.get("id")
    if not isinstance(qid, str) or not ID_RE.match(qid):
        errores.append(f"{prefijo}id inválido ({qid!r}): usar minúsculas, números y guiones")
        qid = qid if isinstance(qid, str) else "?"
    prefijo = f"{ruta} [{qid}]: " if ruta else f"[{qid}] "

    tema = datos.get("tema")
    if tema not in TEMAS:
        errores.append(f"{prefijo}tema inválido ({tema!r}); válidos: {', '.join(TEMAS)}")

    if not _texto(datos.get("subtema")):
        errores.append(f"{prefijo}falta 'subtema'")
    if datos.get("dificultad") not in DIFICULTADES:
        errores.append(f"{prefijo}dificultad inválida; usar {DIFICULTADES}")

    pregunta = datos.get("pregunta")
    if not _texto(pregunta) or not 15 <= len(pregunta.strip()) <= 700:
        errores.append(f"{prefijo}'pregunta' debe ser un texto de 15 a 700 caracteres")

    opciones = datos.get("opciones")
    if not isinstance(opciones, list) or not 3 <= len(opciones) <= 5:
        errores.append(f"{prefijo}'opciones' debe ser una lista de 3 a 5 opciones")
        opciones = []
    correctas = 0
    textos: List[str] = []
    for i, op in enumerate(opciones, 1):
        if not isinstance(op, dict):
            errores.append(f"{prefijo}opción {i} debe ser un objeto")
            continue
        texto = op.get("texto")
        if not _texto(texto) or len(texto.strip()) > 300:
            errores.append(f"{prefijo}opción {i}: 'texto' vacío o demasiado largo")
        else:
            textos.append(util.normalizar(texto))
        correcta = op.get("correcta")
        if not isinstance(correcta, bool):
            errores.append(f"{prefijo}opción {i}: 'correcta' debe ser true/false")
        elif correcta:
            correctas += 1
        else:
            porque = op.get("porque_no")
            if not _texto(porque) or len(porque.strip()) < 10:
                errores.append(
                    f"{prefijo}opción {i}: los distractores necesitan 'porque_no' (por qué es incorrecta)"
                )
        if correcta and _texto(op.get("porque_no")):
            advertencias.append(f"{prefijo}opción {i}: la correcta no necesita 'porque_no'")
        for patron in PATRONES_PROHIBIDOS:
            if _texto(texto) and re.search(patron, util.normalizar(texto)):
                errores.append(f"{prefijo}opción {i}: evitar opciones de relleno ('todas/ninguna de las anteriores')")
                break
    if opciones and correctas != 1:
        errores.append(f"{prefijo}debe haber exactamente una opción correcta (hay {correctas})")
    if len(set(textos)) != len(textos):
        errores.append(f"{prefijo}hay opciones repetidas")

    explicacion = datos.get("explicacion")
    if not _texto(explicacion) or not 40 <= len(explicacion.strip()) <= 1500:
        errores.append(f"{prefijo}'explicacion' debe tener entre 40 y 1500 caracteres")

    errores.extend(_validar_fuente(datos.get("fuente"), prefijo))
    errores.extend(_validar_tags(datos.get("tags"), prefijo))
    return errores, advertencias


def validar_desarrollo(datos: Any, *, ruta: str = "") -> Tuple[List[str], List[str]]:
    """Valida una pregunta de desarrollo corto. Devuelve (errores, advertencias)."""
    errores: List[str] = []
    advertencias: List[str] = []
    prefijo = f"{ruta}: " if ruta else ""

    if not isinstance(datos, dict):
        return [f"{prefijo}la pregunta debe ser un objeto JSON"], advertencias

    qid = datos.get("id")
    if not isinstance(qid, str) or not ID_RE.match(qid):
        errores.append(f"{prefijo}id inválido ({qid!r})")
        qid = qid if isinstance(qid, str) else "?"
    prefijo = f"{ruta} [{qid}]: " if ruta else f"[{qid}] "

    if datos.get("tema") not in TEMAS:
        errores.append(f"{prefijo}tema inválido ({datos.get('tema')!r})")
    if not _texto(datos.get("subtema")):
        errores.append(f"{prefijo}falta 'subtema'")
    if datos.get("dificultad") not in DIFICULTADES:
        errores.append(f"{prefijo}dificultad inválida; usar {DIFICULTADES}")

    pregunta = datos.get("pregunta")
    if not _texto(pregunta) or not 20 <= len(pregunta.strip()) <= 800:
        errores.append(f"{prefijo}'pregunta' debe ser un texto de 20 a 800 caracteres")

    criterios = datos.get("criterios")
    if not isinstance(criterios, list) or not 3 <= len(criterios) <= 5:
        errores.append(f"{prefijo}'criterios' debe tener entre 3 y 5 elementos")
        criterios = []
    suma = 0.0
    ids: List[str] = []
    for i, crit in enumerate(criterios, 1):
        if not isinstance(crit, dict):
            errores.append(f"{prefijo}criterio {i} debe ser un objeto")
            continue
        cid = crit.get("id")
        if not _texto(cid):
            errores.append(f"{prefijo}criterio {i}: falta 'id'")
        else:
            if cid in ids:
                errores.append(f"{prefijo}criterio {i}: id duplicado ({cid})")
            ids.append(cid)
        if not _texto(crit.get("descripcion")) or len(crit["descripcion"].strip()) < 8:
            errores.append(f"{prefijo}criterio {i}: falta 'descripcion'")
        peso = crit.get("peso")
        if not isinstance(peso, (int, float)) or isinstance(peso, bool) or not 0 < float(peso) <= 1:
            errores.append(f"{prefijo}criterio {i}: 'peso' debe ser un número entre 0 y 1")
        else:
            suma += float(peso)
        claves = crit.get("claves")
        if not isinstance(claves, list) or not 1 <= len(claves) <= 8:
            errores.append(f"{prefijo}criterio {i}: 'claves' debe ser una lista de 1 a 8 frases")
        else:
            for clave in claves:
                if not _texto(clave) or len(clave.strip()) > 120 or len(clave.strip()) < 3:
                    errores.append(f"{prefijo}criterio {i}: clave inválida ({clave!r})")
    if criterios and abs(suma - 1.0) > 0.02:
        errores.append(f"{prefijo}los pesos de los criterios deben sumar 1.0 (suman {suma:.2f})")

    modelo = datos.get("respuesta_modelo")
    if not _texto(modelo) or not 120 <= len(modelo.strip()) <= 3000:
        errores.append(f"{prefijo}'respuesta_modelo' debe tener entre 120 y 3000 caracteres")

    tiempo = datos.get("tiempo_sugerido_min", 5)
    if not isinstance(tiempo, int) or not 2 <= tiempo <= 20:
        errores.append(f"{prefijo}'tiempo_sugerido_min' debe ser un entero entre 2 y 20")

    errores.extend(_validar_fuente(datos.get("fuente"), prefijo))
    errores.extend(_validar_tags(datos.get("tags"), prefijo))
    return errores, advertencias


def _validar_fuente(fuente: Any, prefijo: str) -> List[str]:
    errores: List[str] = []
    if not isinstance(fuente, dict):
        return [f"{prefijo}falta 'fuente' (objeto con 'archivo' y 'pagina')"]
    archivo = fuente.get("archivo")
    if not _texto(archivo):
        errores.append(f"{prefijo}'fuente.archivo' es obligatorio")
    else:
        disponibles = util.nombres_pdf()
        if disponibles and archivo not in disponibles:
            errores.append(
                f"{prefijo}'fuente.archivo' no es un PDF del repositorio: {archivo!r}"
            )
    pagina = fuente.get("pagina")
    if not isinstance(pagina, int) or isinstance(pagina, bool) or pagina < 1:
        errores.append(f"{prefijo}'fuente.pagina' debe ser un entero >= 1")
    return errores


def _validar_tags(tags: Any, prefijo: str) -> List[str]:
    if tags is None:
        return []
    if not isinstance(tags, list) or not all(_texto(t) for t in tags):
        return [f"{prefijo}'tags' debe ser una lista de textos"]
    return []


def validar_fuente_paginas(preguntas: Sequence[Dict[str, Any]], prefijo: str = "") -> List[str]:
    """Comprueba que las páginas citadas existan en el PDF (si hay lector)."""
    errores: List[str] = []
    for datos in preguntas:
        if not isinstance(datos, dict):
            continue
        fuente = datos.get("fuente")
        if not isinstance(fuente, dict):
            continue
        archivo, pagina = fuente.get("archivo"), fuente.get("pagina")
        if not _texto(archivo) or not isinstance(pagina, int):
            continue
        total = util.paginas_pdf(archivo)
        if total is not None and not 1 <= pagina <= total:
            errores.append(
                f"{prefijo}[{datos.get('id', '?')}]: página {pagina} fuera de rango "
                f"({archivo} tiene {total} páginas)"
            )
    return errores


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------


def _leer_archivo(ruta: Path) -> List[Any]:
    datos = util.cargar_json(ruta)
    if isinstance(datos, dict):
        datos = datos.get("preguntas", [])
    if not isinstance(datos, list):
        raise BancoInvalido([f"{ruta.name}: el archivo debe contener una lista de preguntas"])
    return datos


def _construir_mc(datos: Dict[str, Any]) -> PreguntaMC:
    return PreguntaMC(
        id=datos["id"],
        tema=datos["tema"],
        subtema=datos["subtema"],
        dificultad=datos["dificultad"],
        pregunta=datos["pregunta"].strip(),
        opciones=tuple(
            Opcion(
                texto=op["texto"].strip(),
                correcta=bool(op["correcta"]),
                porque_no=(op.get("porque_no") or "").strip(),
            )
            for op in datos["opciones"]
        ),
        explicacion=datos["explicacion"].strip(),
        fuente=dict(datos["fuente"]),
        tags=tuple(datos.get("tags") or ()),
    )


def _construir_desarrollo(datos: Dict[str, Any]) -> PreguntaDesarrollo:
    return PreguntaDesarrollo(
        id=datos["id"],
        tema=datos["tema"],
        subtema=datos["subtema"],
        dificultad=datos["dificultad"],
        pregunta=datos["pregunta"].strip(),
        criterios=tuple(
            Criterio(
                id=c["id"],
                descripcion=c["descripcion"].strip(),
                peso=float(c["peso"]),
                claves=tuple(k.strip() for k in c["claves"]),
            )
            for c in datos["criterios"]
        ),
        respuesta_modelo=datos["respuesta_modelo"].strip(),
        fuente=dict(datos["fuente"]),
        tiempo_sugerido_min=int(datos.get("tiempo_sugerido_min", 5)),
        tags=tuple(datos.get("tags") or ()),
    )


def validar_archivos(rutas: Iterable[Path], *, estricto_paginas: bool = False) -> Dict[str, Any]:
    """Valida archivos de banco y detecta duplicados entre ellos."""
    errores: List[str] = []
    advertencias: List[str] = []
    ids: Dict[str, str] = {}
    stems: Dict[str, str] = {}
    total = 0

    for ruta in rutas:
        try:
            preguntas = _leer_archivo(ruta)
        except Exception as exc:  # JSON roto
            errores.append(f"{ruta.name}: no se pudo leer ({exc})")
            continue
        es_desarrollo = ruta.parent.name == "short" or "desarrollo" in ruta.name
        validador = validar_desarrollo if es_desarrollo else validar_mc
        for datos in preguntas:
            total += 1
            errs, warns = validador(datos, ruta=ruta.name)
            errores.extend(errs)
            advertencias.extend(warns)
            if isinstance(datos, dict):
                qid = datos.get("id")
                if isinstance(qid, str):
                    if qid in ids:
                        errores.append(f"{ruta.name}: id duplicado {qid} (también en {ids[qid]})")
                    else:
                        ids[qid] = ruta.name
                stem = util.normalizar(str(datos.get("pregunta", "")))
                if stem:
                    if stem in stems:
                        errores.append(
                            f"{ruta.name} [{datos.get('id', '?')}]: pregunta duplicada "
                            f"de {stems[stem]}"
                        )
                    else:
                        stems[stem] = f"{ruta.name} [{datos.get('id', '?')}]"
        if estricto_paginas:
            errores.extend(validar_fuente_paginas(preguntas, prefijo=ruta.name))

    return {
        "archivos": [str(r) for r in rutas],
        "total_preguntas": total,
        "errores": errores,
        "advertencias": advertencias,
        "ok": not errores,
    }


def archivos_banco() -> List[Path]:
    rutas: List[Path] = []
    for carpeta in (util.MC_DIR, util.SHORT_DIR):
        if carpeta.is_dir():
            rutas.extend(sorted(carpeta.glob("*.json")))
    return rutas


def cargar_banco(
    rutas: Optional[Sequence[Path]] = None, *, validar: bool = True
) -> Banco:
    """Carga el banco completo desde content/bank."""
    rutas = list(rutas) if rutas is not None else archivos_banco()
    if not rutas:
        raise BancoInvalido(["no se encontraron archivos de preguntas en content/bank"])

    if validar:
        informe = validar_archivos(rutas)
        if not informe["ok"]:
            raise BancoInvalido(informe["errores"])

    mc: List[PreguntaMC] = []
    desarrollo: List[PreguntaDesarrollo] = []
    for ruta in rutas:
        preguntas = _leer_archivo(ruta)
        if ruta.parent.name == "short" or "desarrollo" in ruta.name:
            desarrollo.extend(_construir_desarrollo(d) for d in preguntas)
        else:
            mc.extend(_construir_mc(d) for d in preguntas)
    return Banco(mc=mc, desarrollo=desarrollo, archivos=[r.name for r in rutas])
