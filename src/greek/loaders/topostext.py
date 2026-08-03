"""ToposText -> completa coordenadas donde Pleiades no llega + equivalencias Pleiades/DARE.

ToposText tiene ~8.137 lugares con mejor granularidad que Pleiades en Grecia
(santuarios, tumbas heroicas, fuentes). Solo rellena huecos: no sobreescribe una
coordenada de Pleiades marcada 'precise'.

Licencia: compartir con atribucion a la Fundacion Laskaridis. NO redistribuir el
corpus textual completo; aqui solo se usan lugares y equivalencias.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from ..db import RAW_DIR, id_tipo_entidad, insert_ignore, registrar_fuente
from ..normalize import normalizar

DIR = RAW_DIR / "topostext"

# Claves reales del geojson (verificadas contra places_2025-11-20): van en
# CamelCase, no en minusculas — 'Pleiades', 'ToposText', 'Wikidata', 'Greek'.
# `confidence` es la propia estimacion de ToposText sobre la identificacion.
GEO_TIPO_POR_CONFIANZA = {
    "high": "real_preciso",
    "medium": "real_aproximado",
    # 'Low' es exactamente el caso "identificacion tradicional, no hecho":
    # Escila en el estrecho de Mesina, la isla de Circe en el Monte Circeo.
    "low": "identificacion_tradicional",
}

MAPA_TIPO_LUGAR = {
    "polity": "lugar",
    "settlement": "lugar",
    "deme": "lugar",
    "site/excavation": "lugar",
    "prehistoric site": "lugar",
    "sanctuary/temple": "santuario",
    "church": "santuario",
    "oracle": "santuario",
    "river": "rio",
    "spring/fountain": "rio",
    "mountain": "montana",
    "cape": "montana",
    "pass/road": "montana",
    "island": "isla",
    "region/people": "region",
}


def cargar(con: sqlite3.Connection) -> str:
    geojson = DIR / "places.geojson"
    if not geojson.is_file():
        return (
            "topostext: falta data/raw/topostext/places.geojson — `greek fetch --source topostext`"
        )

    fuente_id = registrar_fuente(
        con,
        clave="topostext",
        nombre="ToposText",
        version=geojson.stem,
        url="https://topostext.org",
        licencia="Comparticion con atribucion (Fundacion Aikaterini Laskaridis)",
        fecha_descarga=datetime.fromtimestamp(geojson.stat().st_mtime, UTC).date().isoformat(),
        atribucion_texto=(
            "ToposText, Aikaterini Laskaridis Foundation / Pavla S.A. https://topostext.org"
        ),
        notas="No redistribuir el corpus textual completo.",
    )

    datos = json.loads(geojson.read_text(encoding="utf-8"))

    n_nuevos = n_enlazados = n_completados = n_miticos = 0
    for feature in datos.get("features", []):
        props = feature.get("properties") or {}
        geom = feature.get("geometry") or {}
        coords = geom.get("coordinates") or []
        if geom.get("type") != "Point" or len(coords) < 2:
            continue
        lon, lat = float(coords[0]), float(coords[1])

        nombre = (props.get("name") or "").strip()
        if not nombre:
            continue

        tt_id = _ultimo_segmento(props.get("ToposText"))
        pleiades_id = _ultimo_segmento(props.get("Pleiades"))
        qid = _ultimo_segmento(props.get("Wikidata"))
        tipo_bruto = (props.get("type") or "").strip()
        mitico = (props.get("region") or "").strip().lower() == "mythical"
        geo_tipo = GEO_TIPO_POR_CONFIANZA.get(
            (props.get("confidence") or "").strip().lower(), "real_aproximado"
        )

        eid = _localizar(con, pleiades_id, tt_id, qid)
        if eid is None:
            eid = con.execute(
                "INSERT INTO entidad (nombre, nombre_norm, nombre_grc, descripcion, "
                "tipo_entidad_id, fuente_dataset_id) VALUES (?,?,?,?,?,?)",
                (
                    nombre,
                    normalizar(nombre),
                    (props.get("Greek") or "").strip() or None,
                    (props.get("description") or "").strip() or None,
                    id_tipo_entidad(con, MAPA_TIPO_LUGAR.get(tipo_bruto, "lugar")),
                    fuente_id,
                ),
            ).lastrowid
            n_nuevos += 1
        else:
            n_enlazados += 1
            con.execute(
                "UPDATE entidad SET nombre_grc = COALESCE(nombre_grc, ?), "
                "descripcion = COALESCE(descripcion, ?) WHERE id = ?",
                (
                    (props.get("Greek") or "").strip() or None,
                    (props.get("description") or "").strip() or None,
                    eid,
                ),
            )

        for namespace, valor, uri in (
            ("topostext", tt_id, props.get("ToposText")),
            ("pleiades", pleiades_id, props.get("Pleiades")),
            ("wikidata", qid, props.get("Wikidata")),
        ):
            if valor:
                insert_ignore(
                    con,
                    "entidad_identificador",
                    {"entidad_id": eid, "namespace": namespace, "valor": valor, "uri": uri},
                )

        if mitico:
            # region 'Mythical': ToposText le da un punto, pero es identificacion
            # tradicional, no ubicacion establecida. No se degrada a NULL porque el
            # punto es informativo, pero queda marcado para no tratarlo como hecho.
            geo_tipo = "identificacion_tradicional"
            n_miticos += 1

        detalle = con.execute(
            "SELECT latitud, location_precision, geo_tipo FROM lugar_detalle WHERE entidad_id = ?",
            (eid,),
        ).fetchone()

        if detalle is None:
            con.execute(
                "INSERT INTO lugar_detalle (entidad_id, tipo_lugar, latitud, longitud, "
                "geo_tipo, es_ficticio, geo_fuente, nombre_moderno, fuente_dataset_id) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    eid,
                    tipo_bruto or None,
                    lat,
                    lon,
                    geo_tipo,
                    1 if mitico else 0,
                    "topostext",
                    (props.get("modern place") or "").strip() or None,
                    fuente_id,
                ),
            )
            n_completados += 1
        else:
            con.execute(
                "UPDATE lugar_detalle SET nombre_moderno = COALESCE(nombre_moderno, ?), "
                "tipo_lugar = COALESCE(tipo_lugar, ?) WHERE entidad_id = ?",
                ((props.get("modern place") or "").strip() or None, tipo_bruto or None, eid),
            )
            # solo rellena huecos o mejora un 'rough' de Pleiades; nunca pisa un
            # 'precise' ni le pone coordenadas a un lugar legendario
            hueco = detalle["latitud"] is None or detalle["location_precision"] == "rough"
            if hueco and detalle["geo_tipo"] != "legendario_sin_ubicacion":
                con.execute(
                    "UPDATE lugar_detalle SET latitud = ?, longitud = ?, "
                    "geo_fuente = 'topostext', geo_tipo = ? WHERE entidad_id = ?",
                    (lat, lon, geo_tipo, eid),
                )
                n_completados += 1

    con.commit()
    return (
        f"topostext: {n_nuevos} lugares nuevos, {n_enlazados} enlazados a lugares existentes, "
        f"{n_completados} coordenadas completadas, {n_miticos} marcados como identificacion "
        f"tradicional (region 'Mythical')"
    )


def _ultimo_segmento(uri: str | None) -> str:
    """'https://pleiades.stoa.org/places/786017' -> '786017'."""
    if not uri:
        return ""
    return str(uri).strip().rstrip("/").rsplit("/", 1)[-1]


def _localizar(con: sqlite3.Connection, pleiades_id: str, tt_id: str, qid: str) -> int | None:
    """Reconciliacion por ID externo, en orden de fiabilidad."""
    for namespace, valor in (
        ("pleiades", pleiades_id),
        ("topostext", tt_id),
        ("wikidata", qid),
    ):
        if not valor:
            continue
        row = con.execute(
            "SELECT entidad_id FROM entidad_identificador WHERE namespace = ? AND valor = ?",
            (namespace, valor),
        ).fetchone()
        if row:
            return row["entidad_id"]
    return None
