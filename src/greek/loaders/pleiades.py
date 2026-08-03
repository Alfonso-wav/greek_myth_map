"""Pleiades -> entidad(tipo lugar) + lugar_detalle + lugar_localizacion + jerarquia.

CSV con BOM UTF-8: encoding='utf-8-sig' obligatorio. Los campos WKT llevan comas
dentro de comillas, asi que hay que usar el modulo csv, nunca split(',').

Trampa critica: location_precision='rough' puede ser el centroide de una caja de
100 km. Se propaga a lugar_detalle.location_precision, no se oculta.
"""

from __future__ import annotations

import csv
import re
import sqlite3
from pathlib import Path

from ..db import (
    RAW_DIR,
    entidad_por_identificador,
    id_tipo_entidad,
    insert_ignore,
    registrar_fuente,
    upsert,
)
from ..normalize import normalizar

GIS = RAW_DIR / "pleiades"

# place_type de Pleiades -> tipo_entidad del esquema.
# Claves verificadas contra place_types.csv del paquete GIS real.
MAPA_TIPO = {
    "settlement": "lugar",
    "settlement-modern": "lugar",
    "townhouse": "lugar",
    "villa": "lugar",
    "fort": "lugar",
    "fortification": "lugar",
    "sanctuary": "santuario",
    "temple": "santuario",
    "church": "santuario",
    "oracle": "santuario",
    "mountain": "montana",
    "hill": "montana",
    "pass": "montana",
    "river": "rio",
    "stream": "rio",
    "spring": "rio",
    "lake": "lugar",
    "island": "isla",
    "islands": "isla",
    "region": "region",
    "province": "region",
    "people": "pueblo",
    "tumulus": "lugar",
    "tomb": "lugar",
    "cemetery": "lugar",
    "cave": "lugar",
}

RE_PUNTO = re.compile(r"POINT\s*\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s*\)", re.IGNORECASE)


def _abrir(nombre: str) -> list[dict]:
    ruta = _localizar(nombre)
    if ruta is None:
        return []
    with ruta.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _localizar(nombre: str) -> Path | None:
    """El ZIP puede extraer con o sin subcarpeta."""
    for cand in (GIS / nombre, *GIS.glob(f"**/{nombre}")):
        if cand.is_file():
            return cand
    return None


def _entero(valor: str | None) -> int | None:
    if not valor or not valor.strip():
        return None
    try:
        return int(float(valor))
    except ValueError:
        return None


def _real(valor: str | None) -> float | None:
    if not valor or not valor.strip():
        return None
    try:
        return float(valor)
    except ValueError:
        return None


def _metros(valor: str | None) -> int | None:
    """Pleiades codifica 'desconocido' como -1: eso es un NULL, no una distancia."""
    n = _entero(valor)
    return None if n is None or n < 0 else n


def _geo_tipo(lat: float | None, precision: str | None, max_m: int | None) -> str:
    if lat is None:
        return "sin_datos"
    if precision == "rough" or (max_m is not None and max_m > 5000):
        return "real_aproximado"
    return "real_preciso"


def cargar(con: sqlite3.Connection) -> str:
    places = _abrir("places.csv")
    if not places:
        return (
            "pleiades: no encontrado data/raw/pleiades/places.csv — "
            "ejecuta `greek fetch --source pleiades`"
        )

    fuente_id = registrar_fuente(
        con,
        clave="pleiades",
        nombre="Pleiades: A community-built gazetteer and graph of ancient places",
        version="gis_data",
        url="https://pleiades.stoa.org/downloads",
        licencia="CC-BY 3.0",
        fecha_descarga=_fecha_fichero("places.csv"),
        atribucion_texto=(
            "Pleiades: A community-built gazetteer and graph of ancient places. "
            "Ancient World Mapping Center & Institute for the Study of the Ancient World. "
            "CC-BY 3.0. https://pleiades.stoa.org"
        ),
    )

    # places_accuracy.csv se indexa por place_id, no por id
    accuracy = {f["place_id"]: f for f in _abrir("places_accuracy.csv") if f.get("place_id")}
    tipos = _tipos_por_lugar()
    tipo_desconocido = id_tipo_entidad(con, "lugar")

    n = 0
    for p in places:
        pid = p.get("id")
        if not pid:
            continue
        titulo = (p.get("title") or "").strip()
        if not titulo:
            continue

        acc = accuracy.get(pid, {})
        max_m = _metros(acc.get("max_accuracy_meters"))
        lat = _real(p.get("representative_latitude"))
        lon = _real(p.get("representative_longitude"))
        precision = (p.get("location_precision") or "").strip() or None

        clave_tipo = MAPA_TIPO.get(tipos.get(pid, ""), "lugar")
        tipo_id = id_tipo_entidad(con, clave_tipo) or tipo_desconocido

        # idempotencia: la entidad se localiza por su ID externo, no por nombre.
        # entidad no tiene clave UNIQUE natural, asi que un upsert ciego duplicaria
        # los ~40.000 lugares en cada recarga.
        entidad_id = entidad_por_identificador(con, "pleiades", pid)
        if entidad_id is None:
            entidad_id = con.execute(
                "INSERT INTO entidad (nombre, nombre_norm, descripcion, tipo_entidad_id, "
                "fuente_dataset_id) VALUES (?,?,?,?,?)",
                (
                    titulo,
                    normalizar(titulo),
                    (p.get("description") or "").strip() or None,
                    tipo_id,
                    fuente_id,
                ),
            ).lastrowid
            insert_ignore(
                con,
                "entidad_identificador",
                {
                    "entidad_id": entidad_id,
                    "namespace": "pleiades",
                    "valor": pid,
                    "uri": p.get("uri"),
                },
            )
        else:
            con.execute(
                "UPDATE entidad SET nombre = ?, nombre_norm = ?, "
                "descripcion = COALESCE(descripcion, ?), "
                "tipo_entidad_id = COALESCE(?, tipo_entidad_id) WHERE id = ?",
                (
                    titulo,
                    normalizar(titulo),
                    (p.get("description") or "").strip() or None,
                    tipo_id,
                    entidad_id,
                ),
            )

        upsert(
            con,
            "lugar_detalle",
            {
                "entidad_id": entidad_id,
                "tipo_lugar": tipos.get(pid),
                "latitud": lat,
                "longitud": lon,
                "precision_metros": max_m,
                "location_precision": precision if precision in ("precise", "rough") else None,
                "bbox_wkt": p.get("bounding_box_wkt") or None,
                "geo_tipo": _geo_tipo(lat, precision, max_m),
                "es_ficticio": 0,
                "geo_fuente": "pleiades",
                "anio_desde_ac": _entero(p.get("year_after_which")),
                "anio_hasta_ac": _entero(p.get("year_before_which")),
                "fuente_dataset_id": fuente_id,
            },
            conflicto=["entidad_id"],
            columna_id="entidad_id",  # lugar_detalle no tiene columna `id`
        )
        n += 1
        if n % 2000 == 0:
            con.commit()

    con.commit()
    n_nombres = _cargar_nombres(con)
    n_jerarquia = _cargar_conexiones(con)
    n_loc = _cargar_localizaciones(con, fuente_id)

    return (
        f"pleiades: {n} lugares, {n_nombres} nombres antiguos, "
        f"{n_jerarquia} relaciones jerarquicas, {n_loc} localizaciones"
    )


def _fecha_fichero(nombre: str) -> str:
    from datetime import UTC, datetime

    ruta = _localizar(nombre)
    if ruta is None:
        return datetime.now(UTC).date().isoformat()
    return datetime.fromtimestamp(ruta.stat().st_mtime, UTC).date().isoformat()


def _tipos_por_lugar() -> dict[str, str]:
    """place_id -> place_type. places_place_types.csv ya trae la clave textual."""
    validas = {f["key"] for f in _abrir("place_types.csv") if f.get("key")}
    out: dict[str, str] = {}
    for f in _abrir("places_place_types.csv"):
        pid, tipo = f.get("place_id"), f.get("place_type")
        if pid and tipo and (not validas or tipo in validas):
            out.setdefault(pid, tipo)
    return out


def _pleiades_a_entidad(con: sqlite3.Connection) -> dict[str, int]:
    return {
        f["valor"]: f["entidad_id"]
        for f in con.execute(
            "SELECT valor, entidad_id FROM entidad_identificador WHERE namespace = 'pleiades'"
        )
    }


def _cargar_nombres(con: sqlite3.Connection) -> int:
    mapa = _pleiades_a_entidad(con)
    n = 0
    for f in _abrir("names.csv"):
        eid = mapa.get(f.get("place_id") or "")
        if eid is None:
            continue
        for campo, tipo in (
            ("attested_form", "local"),
            ("romanized_form_1", "latino"),
            ("romanized_form_2", "alternativo"),
            ("romanized_form_3", "alternativo"),
        ):
            valor = (f.get(campo) or "").strip()
            if not valor:
                continue
            insert_ignore(
                con,
                "entidad_nombre",
                {
                    "entidad_id": eid,
                    "nombre": valor,
                    "tipo": tipo,
                    "lengua_tag": f.get("language_tag") or None,
                },
            )
            n += 1
    con.commit()
    return n


def _cargar_conexiones(con: sqlite3.Connection) -> int:
    mapa = _pleiades_a_entidad(con)
    tipos = {
        "part_of_admin": "parte_de",
        "part_of_physical": "parte_de",
        "part_of_regional": "parte_de",
        "connection": "cerca_de",
        "at": "en",
        "near": "cerca_de",
        "within": "dentro_de",
    }
    n = 0
    for f in _abrir("connections.csv"):
        # connects_to es una URI: https://pleiades.stoa.org/places/433032
        hijo = mapa.get(f.get("place_id") or "")
        padre = mapa.get(_id_de_uri(f.get("connects_to")))
        if hijo is None or padre is None or hijo == padre:
            continue
        insert_ignore(
            con,
            "lugar_jerarquia",
            {
                "hijo_id": hijo,
                "padre_id": padre,
                "tipo": tipos.get((f.get("connection_type") or "").strip(), "cerca_de"),
                "certeza": (f.get("certainty") or "").strip() or None,
            },
        )
        n += 1
    con.commit()
    return n


def _id_de_uri(valor: str | None) -> str:
    if not valor:
        return ""
    return valor.rstrip("/").rsplit("/", 1)[-1]


def _punto_wkt(wkt: str | None) -> tuple[float | None, float | None]:
    """'POINT (14.489 40.750)' -> (lat, lon). WKT va en orden lon lat."""
    if not wkt:
        return None, None
    m = RE_PUNTO.search(wkt)
    if not m:
        return None, None
    return float(m.group(2)), float(m.group(1))


def _cargar_localizaciones(con: sqlite3.Connection, fuente_id: int) -> int:
    mapa = _pleiades_a_entidad(con)
    n = 0
    for f in _abrir("location_points.csv"):
        eid = mapa.get(f.get("place_id") or "")
        if eid is None:
            continue
        lat, lon = _punto_wkt(f.get("geometry_wkt"))
        insert_ignore(
            con,
            "lugar_localizacion",
            {
                "entidad_id": eid,
                "titulo": f.get("title") or None,
                "geometria_wkt": f.get("geometry_wkt") or None,
                "latitud": lat,
                "longitud": lon,
                "tipo_localizacion": f.get("location_type") or None,
                "precision": f.get("location_precision") or None,
                "accuracy_radius_m": _metros(f.get("accuracy_radius")),
                "pleiades_uri": f.get("uri") or None,
                "es_representativa": 0,
            },
        )
        n += 1
        if n % 5000 == 0:
            con.commit()
    con.commit()
    return n
