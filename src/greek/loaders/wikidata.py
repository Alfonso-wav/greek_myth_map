"""Wikidata (SPARQL) -> nombre_es, descripcion, coordenadas de respaldo.

Regla: MANTO decide, Wikidata enriquece. Si discrepan en un hecho mitologico gana
MANTO; Wikidata solo aporta etiquetas, descripciones, enlaces y coordenadas de
relleno. El propio paper de la OGM documenta que Wikidata carece casi por completo
de la referencia a la fuente clasica, asi que no es autoridad sobre el contenido.

Clase raiz: Q22988604 "mythological Greek character".
"""

from __future__ import annotations

import sqlite3
import time
from datetime import UTC, datetime

import httpx

from ..db import insert_ignore, registrar_fuente

ENDPOINT = "https://query.wikidata.org/sparql"
UA = "greek-myth-db/0.1 (proyecto local de investigacion; contacto: local)"

CONSULTA = """
SELECT ?item ?itemLabel ?esLabel ?grcLabel ?desc ?pleiades ?limc ?coord WHERE {
  ?item wdt:P31/wdt:P279* wd:Q22988604 .
  OPTIONAL { ?item rdfs:label ?esLabel  FILTER (lang(?esLabel)  = "es") }
  OPTIONAL { ?item rdfs:label ?grcLabel FILTER (lang(?grcLabel) = "grc") }
  OPTIONAL { ?item schema:description ?desc FILTER (lang(?desc) = "es") }
  OPTIONAL { ?item wdt:P1584 ?pleiades }
  OPTIONAL { ?item wdt:P13094 ?limc }
  OPTIONAL { ?item wdt:P625 ?coord }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "es,en" }
}
"""


def consultar(
    consulta: str = CONSULTA, timeout: float = 180.0, intentos: int = 3
) -> list[dict]:
    """Consulta WDQS respetando el rate limit.

    WDQS devuelve 429 con Retry-After y en incidencias baja el limite a 1 req/min
    ("Aggressively rate-limiting to 1 req / min"). Un fallo aqui no debe tumbar la
    carga: el llamador lo convierte en un aviso, porque Wikidata solo enriquece.
    """
    espera = 5.0
    for intento in range(1, intentos + 1):
        resp = httpx.get(
            ENDPOINT,
            params={"query": consulta, "format": "json"},
            headers={"User-Agent": UA, "Accept": "application/sparql-results+json"},
            timeout=timeout,
            follow_redirects=True,
        )
        if resp.status_code == 429 and intento < intentos:
            pausa = float(resp.headers.get("Retry-After", espera))
            print(f"  [wikidata] 429, esperando {pausa:.0f}s (intento {intento}/{intentos})")
            time.sleep(min(pausa, 90.0))
            espera *= 2
            continue
        resp.raise_for_status()
        return resp.json()["results"]["bindings"]
    raise httpx.HTTPError(f"WDQS sigue limitando tras {intentos} intentos")


def cargar(con: sqlite3.Connection) -> str:
    fuente_id = registrar_fuente(
        con,
        clave="wikidata",
        nombre="Wikidata",
        version=datetime.now(UTC).date().isoformat(),
        url="https://query.wikidata.org",
        licencia="CC0",
        fecha_descarga=datetime.now(UTC).date().isoformat(),
        atribucion_texto="Wikidata contributors. CC0. https://www.wikidata.org",
    )

    try:
        filas = consultar()
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        # Wikidata solo enriquece: su caida no invalida la carga. Se avisa y sigue.
        return (
            f"wikidata: consulta SPARQL no disponible ({exc.__class__.__name__}: "
            f"{str(exc)[:120]}). El resto de la base no depende de ella; reintenta con "
            f"`greek load wikidata`."
        )

    n_enlazadas = n_es = n_coord = 0
    for f in filas:
        qid = _valor(f, "item")
        if not qid:
            continue
        qid = qid.rstrip("/").rsplit("/", 1)[-1]

        eid = _entidad(con, qid, _valor(f, "pleiades"))
        if eid is None:
            continue  # no creamos entidades nuevas desde Wikidata: MANTO es la espina dorsal
        n_enlazadas += 1

        insert_ignore(
            con,
            "entidad_identificador",
            {
                "entidad_id": eid,
                "namespace": "wikidata",
                "valor": qid,
                "uri": f"https://www.wikidata.org/entity/{qid}",
            },
        )

        nombre_es = _valor(f, "esLabel")
        if nombre_es:
            con.execute(
                "UPDATE entidad SET nombre_es = COALESCE(nombre_es, ?) WHERE id = ?",
                (nombre_es, eid),
            )
            insert_ignore(
                con,
                "entidad_nombre",
                {"entidad_id": eid, "nombre": nombre_es, "tipo": "es", "lengua_tag": "es"},
            )
            n_es += 1

        grc = _valor(f, "grcLabel")
        if grc:
            con.execute(
                "UPDATE entidad SET nombre_grc = COALESCE(nombre_grc, ?) WHERE id = ?",
                (grc, eid),
            )

        desc = _valor(f, "desc")
        if desc:
            con.execute(
                "UPDATE entidad SET descripcion = COALESCE(descripcion, ?) WHERE id = ?",
                (desc, eid),
            )

        limc = _valor(f, "limc")
        if limc:
            insert_ignore(
                con,
                "entidad_identificador",
                {"entidad_id": eid, "namespace": "digital_limc", "valor": limc},
            )

        coord = _valor(f, "coord")
        if coord and _rellenar_coordenada(con, eid, coord, fuente_id):
            n_coord += 1

        if n_enlazadas % 500 == 0:
            con.commit()

    con.commit()
    return (
        f"wikidata: {len(filas)} items consultados, {n_enlazadas} enlazados, "
        f"{n_es} nombres_es, {n_coord} coordenadas de respaldo"
    )


def _valor(fila: dict, clave: str) -> str | None:
    nodo = fila.get(clave)
    return nodo.get("value") if nodo else None


def _entidad(con: sqlite3.Connection, qid: str, pleiades_uri: str | None) -> int | None:
    row = con.execute(
        "SELECT entidad_id FROM entidad_identificador WHERE namespace = 'wikidata' AND valor = ?",
        (qid,),
    ).fetchone()
    if row:
        return row["entidad_id"]
    if pleiades_uri:
        pid = pleiades_uri.rstrip("/").rsplit("/", 1)[-1]
        row = con.execute(
            "SELECT entidad_id FROM entidad_identificador "
            "WHERE namespace = 'pleiades' AND valor = ?",
            (pid,),
        ).fetchone()
        if row:
            return row["entidad_id"]
    return None


def _rellenar_coordenada(con: sqlite3.Connection, eid: int, punto: str, fuente_id: int) -> bool:
    """Solo si no hay coordenada. Nunca sobreescribe Pleiades."""
    if not punto.startswith("Point("):
        return False
    try:
        lon, lat = (float(x) for x in punto[6:-1].split())
    except ValueError:
        return False

    row = con.execute(
        "SELECT latitud, geo_tipo FROM lugar_detalle WHERE entidad_id = ?", (eid,)
    ).fetchone()
    if row is None:
        con.execute(
            "INSERT INTO lugar_detalle (entidad_id, latitud, longitud, geo_tipo, "
            "es_ficticio, geo_fuente, fuente_dataset_id) VALUES (?,?,?,?,?,?,?)",
            (eid, lat, lon, "real_aproximado", 0, "wikidata", fuente_id),
        )
        return True
    if row["latitud"] is None and row["geo_tipo"] != "legendario_sin_ubicacion":
        con.execute(
            "UPDATE lugar_detalle SET latitud = ?, longitud = ?, geo_fuente = 'wikidata', "
            "geo_tipo = 'real_aproximado' WHERE entidad_id = ?",
            (lat, lon, eid),
        )
        return True
    return False
