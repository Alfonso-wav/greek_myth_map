"""El esquema debe impedir los errores de fuentes.md §7 por construccion."""

import sqlite3

import pytest

from greek.db import connect, init_schema, registrar_fuente
from greek.loaders import generacional, troya


@pytest.fixture
def con(tmp_path):
    c = connect(tmp_path / "test.db")
    init_schema(c)
    yield c
    c.close()


def _fuente(con):
    return registrar_fuente(
        con,
        clave="test",
        nombre="fixture",
        licencia="n/a",
        fecha_descarga="2026-07-29",
        atribucion_texto="fixture",
    )


def test_lugar_legendario_no_admite_coordenadas(con):
    fuente = _fuente(con)
    eid = con.execute(
        "INSERT INTO entidad (nombre, fuente_dataset_id) VALUES ('Tartaro', ?)", (fuente,)
    ).lastrowid
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO lugar_detalle (entidad_id, latitud, longitud, geo_tipo, "
            "fuente_dataset_id) VALUES (?,?,?,?,?)",
            (eid, 37.0, 22.0, "legendario_sin_ubicacion", fuente),
        )


def test_una_sola_datacion_preferida_por_evento(con):
    fuente = _fuente(con)
    ev = con.execute(
        "INSERT INTO evento (nombre, tipo, fuente_dataset_id) VALUES ('X','guerra',?)",
        (fuente,),
    ).lastrowid
    con.execute(
        "INSERT INTO evento_datacion (evento_id, autoridad, sistema, anio_ac, es_preferida, "
        "fuente_dataset_id) VALUES (?,'A','cronografo_antiguo',-1184,1,?)",
        (ev, fuente),
    )
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO evento_datacion (evento_id, autoridad, sistema, anio_ac, es_preferida, "
            "fuente_dataset_id) VALUES (?,'B','cronografo_antiguo',-1209,1,?)",
            (ev, fuente),
        )


def test_coordenadas_fuera_de_rango_rechazadas(con):
    fuente = _fuente(con)
    eid = con.execute(
        "INSERT INTO entidad (nombre, fuente_dataset_id) VALUES ('Raro', ?)", (fuente,)
    ).lastrowid
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO lugar_detalle (entidad_id, latitud, longitud, geo_tipo, "
            "fuente_dataset_id) VALUES (?,?,?,?,?)",
            (eid, 200.0, 22.0, "real_preciso", fuente),
        )


def test_semilla_troya_y_derivacion_generacional(con):
    resumen = troya.cargar(con)
    assert "eventos mayores" in resumen

    # Eratostenes es la preferida y las 11 variantes estan guardadas
    filas = con.execute(
        "SELECT autoridad, anio_ac, es_preferida FROM evento_datacion d "
        "JOIN evento e ON e.id = d.evento_id WHERE e.nombre = 'Guerra de Troya'"
    ).fetchall()
    assert len(filas) >= 10
    preferida = [f for f in filas if f["es_preferida"]]
    assert len(preferida) == 1
    assert preferida[0]["autoridad"] == "Eratostenes"
    assert preferida[0]["anio_ac"] == -1184

    generacional.cargar(con)

    # la cosmogonia NO recibe fecha inventada
    cosmo = con.execute(
        "SELECT fecha_ac, fecha_metodo FROM evento WHERE nombre = 'Cosmogonia'"
    ).fetchone()
    assert cosmo["fecha_ac"] is None
    assert cosmo["fecha_metodo"] == "sin_fecha"

    # los Heraclidas caen dos generaciones despues de Troya, en el LH IIIC
    herac = con.execute(
        "SELECT fecha_ac, fecha_confianza FROM evento WHERE nombre = 'Retorno de los Heraclidas'"
    ).fetchone()
    assert herac["fecha_ac"] == -1184 + 2 * 33
    assert herac["fecha_confianza"] == "baja"


def test_derivacion_generacional_formula():
    assert generacional.fecha_generacional(2) == -1184
    assert generacional.fecha_generacional(0) == -1250
    assert generacional.fecha_generacional(4) == -1118


def test_relacion_fuente_no_se_duplica_al_recargar(con):
    fuente = _fuente(con)
    eid = con.execute(
        "INSERT INTO entidad (nombre, fuente_dataset_id) VALUES ('Teseo', ?)", (fuente,)
    ).lastrowid
    pid = con.execute(
        "INSERT INTO predicado (clave, nombre_es, categoria) VALUES ('kills', 'mata', 'muerte')"
    ).lastrowid
    rid = con.execute(
        "INSERT INTO relacion (sujeto_id, predicado_id, fuente_dataset_id) VALUES (?,?,?)",
        (eid, pid, fuente),
    ).lastrowid
    obra = con.execute(
        "INSERT INTO obra (titulo, fuente_dataset_id) VALUES ('Biblioteca', ?)", (fuente,)
    ).lastrowid
    pasaje = con.execute(
        "INSERT INTO pasaje (obra_id, cita, fuente_dataset_id) VALUES (?, '3.15.8', ?)",
        (obra, fuente),
    ).lastrowid
    # dos cargas del mismo loader: pasaje_id informado y artefacto/inscripcion a NULL
    for _ in range(2):
        con.execute(
            "INSERT OR IGNORE INTO relacion_fuente (relacion_id, pasaje_id) VALUES (?,?)",
            (rid, pasaje),
        )
    assert con.execute("SELECT count(*) FROM relacion_fuente").fetchone()[0] == 1
