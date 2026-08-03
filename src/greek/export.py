"""Export de la base a un JSON estatico para la web del mapa.

La app no necesita servidor: son 1.062 lugares y ~9.900 afirmaciones, cabe entero
en un fichero que el navegador carga una vez. Todo lo caro (la derivacion
generacional, el anclaje por autoridad, el join con pasajes) ya esta hecho en
SQLite; aqui solo se serializa.

Lo que se exporta y por que:

- `autoridades`: la escala generacion -> anio de cada cronografo antiguo. Cambiar
  de autoridad re-fecha el mito entero sin reordenarlo, porque las 11 discrepan en
  donde cae el ancla troyana (-1334 Duris … -1135 Eforo), no en la secuencia.
- `lugares`: solo los que el mito toca **y** tienen coordenada. Pleiades trae
  36.851 lugares con coordenada, pero la inmensa mayoria no aparece en ningun
  relato: meterlos ahogaria el mapa.
- `afirmaciones`: cada una con su generacion (la del agente), su cita textual y sus
  flags de incertidumbre. El lugar puede venir del objeto directo o de un rol
  (`en`, `hacia`, `desde`), porque MANTO deja sin objeto el 29 % de las relaciones.
- `contradicciones`: los casos en que dos fuentes situan el mismo hecho en lugares
  distintos, con las dos coordenadas. Es la unica capa que no se puede fingir:
  sale de `contradiccion`, que existe justamente para no aplanar el mito.

Claves cortas a proposito (`l`, `g`, `a`) — con ~9.900 filas la diferencia entre
nombres largos y cortos es de megabytes.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from unidecode import unidecode

from .db import ROOT

DEST = ROOT / "web" / "public" / "data" / "greek.json"
MAX_CITAS = 3
MAX_VARIANTES_BUSQUEDA = 12

#: Plantillas de enlace externo. Las cuatro comprobadas con HTTP 200 antes de
#: generarlas: un enlace roto en la ficha es peor que ningun enlace.
#: MANTO queda fuera a proposito — su id es un object id de Nodegoat y no hay URL
#: publica estable que se pueda verificar.
ENLACES = {
    "pleiades": ("Pleiades", "https://pleiades.stoa.org/places/{}"),
    "topostext": ("ToposText", "https://topostext.org/place/{}"),
    "wikidata": ("Wikidata", "https://www.wikidata.org/wiki/{}"),
}

#: `predicado.categoria` -> etiqueta para los filtros. Las claves ya son
#: castellanas pero abreviadas; esto es lo que se lee en el chip.
CATEGORIAS_ES = {
    "belica": "guerra",
    "muerte": "muerte",
    "genealogica": "genealogía",
    "cultual": "culto",
    "fundacion": "fundación",
    "conyugal": "matrimonio",
    "politica": "gobierno",
    "geografica": "geografía",
    "objeto": "objetos",
    "transformacion": "metamorfosis",
    "nacimiento": "nacimiento",
    "creacion": "creación",
    "oficio": "oficio",
    "profecia": "profecía",
    "competicion": "competición",
    "otra": "otros",
}

PAPELES_ES = {
    "dios": "dioses",
    "heroe": "héroes",
    "gobernante": "gobernantes",
    "monstruo": "monstruos",
    "deificado": "deificados",
    "profeta": "profetas",
    "artesano": "artesanos",
}

ATRIBUCION = [
    "MANTO (Mapping Ancient Narratives, Territories, Objects), Greta Hawes, "
    "R. Scott Smith et al. — CC BY-NC 4.0 — manto-myth.org",
    "Pleiades: A community-built gazetteer and graph of ancient places — "
    "CC BY 3.0 — pleiades.stoa.org",
    "ToposText, Aikaterini Laskaridis Foundation — topostext.org",
    "Digital Marmor Parium, Monica Berti, Universitat Leipzig — CC BY-SA 4.0",
    "Wikidata contributors — CC0",
    "Mapa base © OpenStreetMap contributors — ODbL",
]


def clave_busqueda(*nombres: str | None) -> str:
    """Pajar para el buscador del navegador: todas las variantes, dos veces.

    Se guarda la forma transliterada (`unidecode`) **y** la cruda en minusculas.
    La transliterada hace que teclear `achilleus` encuentre `Ἀχιλλεύς`; la cruda
    permite escribir directamente en griego. Como el pajar incluye ya todas las
    variantes atestiguadas (`Kirke` junto a `Circe`), la busqueda puede ser una
    subcadena simple y no hace falta reimplementar en TypeScript los pliegues
    griego->latin de `normalize.normalizar()`, que es logica delicada y se
    desincronizaria.
    """
    partes = [n for n in nombres if n]
    if not partes:
        return ""
    crudo = " ".join(partes).lower()
    # Deduplicado por palabra: las variantes repiten el nombre principal muchas
    # veces (`circe circe kirke circe circe circe kirke`) y con 1.920 entidades eso
    # eran 1,1 MB de JSON que no aportan ninguna coincidencia nueva.
    vistas: dict[str, None] = {}
    for palabra in f"{unidecode(crudo)} {crudo}".split():
        vistas.setdefault(palabra.strip("()[],.;·"), None)
    return " ".join(p for p in vistas if p)


def _variantes(con: sqlite3.Connection) -> dict[int, list[str]]:
    d: dict[int, list[str]] = defaultdict(list)
    for f in con.execute(
        "SELECT entidad_id, nombre FROM entidad_nombre WHERE nombre IS NOT NULL ORDER BY id"
    ):
        if len(d[f["entidad_id"]]) < MAX_VARIANTES_BUSQUEDA:
            d[f["entidad_id"]].append(f["nombre"])
    return d


def _enlaces(con: sqlite3.Connection) -> dict[int, list[dict]]:
    """eid -> [{k: etiqueta, u: url}] a partir de los IDs externos."""
    d: dict[int, list[dict]] = defaultdict(list)
    vistos: dict[int, set[str]] = defaultdict(set)
    marcas = ",".join("?" * len(ENLACES))
    for f in con.execute(
        f"SELECT entidad_id, namespace, valor FROM entidad_identificador "
        f"WHERE namespace IN ({marcas}) ORDER BY id",
        list(ENLACES),
    ):
        ns = f["namespace"]
        if ns in vistos[f["entidad_id"]]:
            continue  # un solo enlace por fuente: hay entidades con varios ids
        vistos[f["entidad_id"]].add(ns)
        etiqueta, plantilla = ENLACES[ns]
        d[f["entidad_id"]].append({"k": etiqueta, "u": plantilla.format(f["valor"])})
    return d


def _autoridades(con: sqlite3.Connection) -> list[dict]:
    por_autoridad: dict[str, dict] = {}
    for f in con.execute(
        "SELECT autoridad, sistema, generacion, anio_ac, ancla_troya_ac, es_preferida "
        "FROM generacion_ancla ORDER BY ancla_troya_ac DESC, generacion"
    ):
        a = por_autoridad.setdefault(
            f["autoridad"],
            {
                "nombre": f["autoridad"],
                "sistema": f["sistema"],
                "troya": f["ancla_troya_ac"],
                "preferida": bool(f["es_preferida"]),
                "anios": {},
            },
        )
        a["anios"][str(f["generacion"])] = f["anio_ac"]
    return list(por_autoridad.values())


def _agentes(con: sqlite3.Connection) -> dict[int, dict]:
    variantes = _variantes(con)
    enlaces = _enlaces(con)
    # papel es multi-etiqueta: Agamenon gobierna Micenas y combate en Troya
    papeles: dict[int, list[str]] = defaultdict(list)
    if con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='entidad_papel'"
    ).fetchone():
        for f in con.execute("SELECT entidad_id, papel FROM entidad_papel ORDER BY papel"):
            papeles[f["entidad_id"]].append(f["papel"])

    agentes = {}
    for f in con.execute(
        """
        SELECT g.entidad_id AS id, COALESCE(e.nombre_es, e.nombre) AS n, e.nombre AS orig,
               e.nombre_grc AS grc, g.generacion AS g, g.generacion_min AS gmin,
               g.generacion_max AS gmax, g.confianza AS conf, g.metodo AS m,
               g.transmite AS tr, te.clave AS t, e.descripcion AS d
          FROM entidad_generacion g
          JOIN entidad e ON e.id = g.entidad_id
          LEFT JOIN tipo_entidad te ON te.id = e.tipo_entidad_id
        """
    ):
        agentes[f["id"]] = {
            "id": f["id"],
            "n": f["n"],
            "grc": f["grc"],
            "g": f["g"],
            "gmin": f["gmin"],
            "gmax": f["gmax"],
            "conf": f["conf"],
            "m": f["m"],
            # transmite = 0 -> divinidad: existe en todas las generaciones, no en una
            "div": 0 if f["tr"] else 1,
            "t": f["t"],
            "d": f["d"],
            "p": papeles.get(f["id"], []),
            "q": clave_busqueda(
                f["n"], f["orig"], f["grc"], *variantes.get(f["id"], ())
            ),
            "enl": enlaces.get(f["id"], []),
        }
    return agentes


_SQL_AFIRMACIONES = """
    -- el lugar puede ser el objeto directo...
    SELECT r.id AS rid, r.sujeto_id AS s, r.objeto_id AS lugar, '' AS rol,
           p.clave AS pk, p.nombre_es AS pe, p.categoria AS cat,
           r.dato_incierto AS inc, r.duda_expresada AS duda,
           r.dato_implicito AS impl, r.alternativas_dadas AS alt,
           NULL AS obj_nombre
      FROM relacion r
      JOIN predicado p ON p.id = r.predicado_id
      JOIN entidad_generacion g ON g.entidad_id = r.sujeto_id
      JOIN lugar_detalle ld ON ld.entidad_id = r.objeto_id AND ld.latitud IS NOT NULL
    UNION ALL
    -- ...o venir de un rol, que es el caso mayoritario (29 % de relacion sin objeto)
    SELECT r.id, r.sujeto_id, rr.entidad_id, rr.rol,
           p.clave, p.nombre_es, p.categoria,
           r.dato_incierto, r.duda_expresada, r.dato_implicito, r.alternativas_dadas,
           COALESCE(o.nombre_es, o.nombre)
      FROM relacion r
      JOIN predicado p ON p.id = r.predicado_id
      JOIN entidad_generacion g ON g.entidad_id = r.sujeto_id
      JOIN relacion_rol rr ON rr.relacion_id = r.id
      JOIN lugar_detalle ld ON ld.entidad_id = rr.entidad_id AND ld.latitud IS NOT NULL
      LEFT JOIN entidad o ON o.id = r.objeto_id
"""


_REF_FINAL = re.compile(r"(\d+(?:[.,]\d+)*(?:\s*[-–]\s*\d+(?:[.,]\d+)*)?)\s*$")


def enlace_pasaje(
    scaife_url: str | None, cts_urn: str | None, obra_urn: str | None, cita: str | None
) -> str | None:
    """URL al texto en Scaife (Perseus), o None si no se puede resolver.

    Tres niveles, del mas exacto al reconstruido:

    1. `pasaje.scaife_url` tal cual — 3.497 de los 6.950 pasajes citados.
    2. `pasaje.cts_urn` montado sobre el lector de Scaife.
    3. `obra.cts_urn` + la referencia numerica del final de la cita
       (`Homer, Iliad 2.459-2.466` -> `...tlg001.perseus-eng3:2.459-2.466`): 145 mas.

    Los 3.308 restantes se quedan **sin enlace a proposito**: sus obras no tienen
    CTS URN (Estrabon, Plinio, Diodoro, los escolios D, Licofron, la Periegesis de
    Dionisio) y no hay forma de construir una URL que resuelva. Un enlace roto en
    la ficha es peor que ningun enlace.
    """
    if scaife_url:
        return scaife_url
    if cts_urn:
        return f"https://scaife.perseus.org/reader/{cts_urn}"
    if obra_urn and cita:
        m = _REF_FINAL.search(cita.strip())
        if m:
            ref = m.group(1).replace(" ", "").replace("–", "-")
            return f"https://scaife.perseus.org/reader/{obra_urn}:{ref}"
    return None


def _citas(con: sqlite3.Connection) -> tuple[dict[int, list[dict]], dict[int, list[str]]]:
    from .graph import cita_legible

    citas: dict[int, list[dict]] = defaultdict(list)
    vistas: dict[int, set[str]] = defaultdict(set)
    autores: dict[int, set[str]] = defaultdict(set)
    for f in con.execute(
        """
        SELECT rf.relacion_id AS rid, ps.cita, ps.scaife_url, ps.cts_urn,
               o.titulo, o.cts_urn AS obra_urn, a.nombre AS autor
          FROM relacion_fuente rf
          JOIN pasaje ps ON ps.id = rf.pasaje_id
          LEFT JOIN obra o ON o.id = ps.obra_id
          LEFT JOIN autor_antiguo a ON a.id = o.autor_id
        """
    ):
        texto = cita_legible(f["cita"], f["titulo"], f["autor"])
        if not texto or texto in vistas[f["rid"]]:
            continue
        vistas[f["rid"]].add(texto)
        url = enlace_pasaje(f["scaife_url"], f["cts_urn"], f["obra_urn"], f["cita"])
        citas[f["rid"]].append({"t": texto, "u": url} if url else {"t": texto})
        if f["autor"]:
            autores[f["rid"]].add(f["autor"])
    return citas, {k: sorted(v) for k, v in autores.items()}


def _contradicciones(con: sqlite3.Connection) -> list[dict]:
    """Solo las de ubicacion con las DOS coordenadas: es lo unico dibujable."""
    filas = []
    for f in con.execute(
        """
        SELECT c.id, c.descripcion AS d, COALESCE(s.nombre_es, s.nombre) AS sobre,
               ra.entidad_id AS la, rb.entidad_id AS lb, p.nombre_es AS pe,
               ga.generacion AS g
          FROM contradiccion c
          JOIN relacion rela ON rela.id = c.relacion_a_id
          JOIN predicado p ON p.id = rela.predicado_id
          JOIN entidad s ON s.id = rela.sujeto_id
          LEFT JOIN entidad_generacion ga ON ga.entidad_id = rela.sujeto_id
          JOIN relacion_rol ra ON ra.relacion_id = c.relacion_a_id AND ra.rol = 'en'
          JOIN relacion_rol rb ON rb.relacion_id = c.relacion_b_id AND rb.rol = 'en'
          JOIN lugar_detalle lda ON lda.entidad_id = ra.entidad_id AND lda.latitud IS NOT NULL
          JOIN lugar_detalle ldb ON ldb.entidad_id = rb.entidad_id AND ldb.latitud IS NOT NULL
         WHERE c.tipo = 'ubicacion' AND ra.entidad_id <> rb.entidad_id
        """
    ):
        filas.append(
            {
                "id": f["id"],
                "sobre": f["sobre"],
                "pe": f["pe"],
                "g": f["g"],
                "d": f["d"],
                "l": [f["la"], f["lb"]],
            }
        )
    return filas


def exportar_web(con: sqlite3.Connection, dest: Path = DEST) -> str:
    if not con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='entidad_generacion'"
    ).fetchone():
        raise LookupError(
            "falta entidad_generacion: ejecuta `uv run greek load generacional` antes de exportar"
        )

    agentes = _agentes(con)
    citas, autores = _citas(con)

    afirmaciones: list[dict] = []
    gens_por_lugar: dict[int, set[int]] = defaultdict(set)
    lugares_usados: set[int] = set()
    for f in con.execute(_SQL_AFIRMACIONES):
        ag = agentes.get(f["s"])
        if ag is None:
            continue
        lugar = f["lugar"]
        lugares_usados.add(lugar)
        gens_por_lugar[lugar].add(ag["g"])
        afirmaciones.append(
            {
                "l": lugar,
                "s": f["s"],
                "g": ag["g"],
                "pk": f["pk"],
                "pe": f["pe"] or f["pk"],
                "cat": f["cat"],
                "rol": f["rol"] or None,
                "obj": f["obj_nombre"],
                # los cuatro flags de incertidumbre viajan siempre: sin ellos el
                # mito se lee como dato afirmado
                "inc": 1 if f["inc"] else 0,
                "duda": 1 if f["duda"] else 0,
                "impl": 1 if f["impl"] else 0,
                "alt": 1 if f["alt"] else 0,
                "ci": citas.get(f["rid"], [])[:MAX_CITAS],
                "au": autores.get(f["rid"], []),
                "nci": len(citas.get(f["rid"], [])),
            }
        )

    contradicciones = _contradicciones(con)
    for c in contradicciones:
        lugares_usados.update(c["l"])

    lugares = []
    variantes = _variantes(con)
    enlaces = _enlaces(con)
    marcas = ",".join("?" * len(lugares_usados))
    for f in con.execute(
        f"""
        SELECT e.id, COALESCE(e.nombre_es, e.nombre) AS n, e.nombre AS orig,
               te.clave AS t, ld.latitud AS lat, ld.longitud AS lng,
               ld.location_precision AS prec, ld.precision_metros AS pm,
               ld.es_ficticio AS fic, ld.nombre_moderno AS mod, ld.pais_iso2 AS pais,
               ld.geo_tipo AS gt
          FROM entidad e
          JOIN lugar_detalle ld ON ld.entidad_id = e.id
          LEFT JOIN tipo_entidad te ON te.id = e.tipo_entidad_id
         WHERE e.id IN ({marcas}) AND ld.latitud IS NOT NULL
        """,
        list(lugares_usados),
    ):
        lugares.append(
            {
                "id": f["id"],
                "n": f["n"],
                "t": f["t"],
                "lat": round(f["lat"], 5),
                "lng": round(f["lng"], 5),
                "prec": f["prec"],
                "pm": f["pm"],
                "fic": 1 if f["fic"] else 0,
                "mod": f["mod"],
                "pais": f["pais"],
                "gt": f["gt"],
                "gens": sorted(gens_por_lugar.get(f["id"], ())),
                "q": clave_busqueda(
                    f["n"], f["orig"], f["mod"], *variantes.get(f["id"], ())
                ),
                "enl": enlaces.get(f["id"], []),
            }
        )

    usados = {a["s"] for a in afirmaciones}
    rango = con.execute(
        "SELECT MIN(generacion) lo, MAX(generacion) hi FROM entidad_generacion"
    ).fetchone()

    # Los filtros se construyen contando SOLO lo exportado: un chip que promete
    # 776 gobernantes y luego pinta 300 es peor que no tener el chip.
    n_papel: dict[str, int] = defaultdict(int)
    for eid in usados:
        for papel in agentes[eid]["p"]:
            n_papel[papel] += 1
    n_cat: dict[str, int] = defaultdict(int)
    for a in afirmaciones:
        n_cat[a["cat"] or "otra"] += 1

    datos = {
        "meta": {
            "generado": datetime.now(UTC).isoformat(timespec="seconds"),
            "gen_min": rango["lo"],
            "gen_max": rango["hi"],
            "gen_troya": 2,
            "gen_sin_fecha": -6,
            "anios_por_generacion": 33,
            "atribucion": ATRIBUCION,
            # dos ejes de filtro distintos: quien protagoniza y de que trata
            "papeles": [
                {"clave": k, "etiqueta": PAPELES_ES.get(k, k), "n": v}
                for k, v in sorted(n_papel.items(), key=lambda kv: -kv[1])
            ],
            "categorias": [
                {"clave": k, "etiqueta": CATEGORIAS_ES.get(k, k), "n": v}
                for k, v in sorted(n_cat.items(), key=lambda kv: -kv[1])
            ],
        },
        "autoridades": _autoridades(con),
        "lugares": lugares,
        "agentes": [a for i, a in agentes.items() if i in usados],
        "afirmaciones": afirmaciones,
        "contradicciones": contradicciones,
    }

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    kb = dest.stat().st_size // 1024
    return (
        f"{dest.relative_to(ROOT)}: {kb:,} KB · {len(lugares):,} lugares, "
        f"{len(datos['agentes']):,} agentes, {len(afirmaciones):,} afirmaciones, "
        f"{len(contradicciones):,} contradicciones de ubicacion, "
        f"{len(datos['autoridades'])} autoridades · generaciones "
        f"{rango['lo']}..{rango['hi']}"
    )
