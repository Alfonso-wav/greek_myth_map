"""Tests del export a la web: enlaces a los textos y clave de busqueda."""

import pytest

from greek.db import connect, init_schema, registrar_fuente
from greek.export import _red, clave_busqueda, enlace_pasaje

SCAIFE = "https://scaife.perseus.org/reader/"


def test_scaife_url_directo_gana():
    """Es el enlace exacto al pasaje: 3.497 de los 6.950 pasajes citados."""
    assert enlace_pasaje(f"{SCAIFE}urn:x:1.3", "urn:y", "urn:z", "1.3") == f"{SCAIFE}urn:x:1.3"


def test_cts_urn_de_pasaje():
    assert enlace_pasaje(None, "urn:cts:greekLit:tlg0012.tlg001:1.1", None, None) == (
        f"{SCAIFE}urn:cts:greekLit:tlg0012.tlg001:1.1"
    )


def test_reconstruido_desde_el_urn_de_la_obra():
    """`Homer, Iliad 2.459-2.466` -> el URN de la obra mas la referencia final."""
    u = enlace_pasaje(
        None, None, "urn:cts:greekLit:tlg0012.tlg001.perseus-eng3", "Homer, Iliad 2.459-2.466"
    )
    assert u == f"{SCAIFE}urn:cts:greekLit:tlg0012.tlg001.perseus-eng3:2.459-2.466"


def test_reconstruido_con_cita_desnuda():
    assert enlace_pasaje(None, None, "urn:obra", "3.29-3.30") == f"{SCAIFE}urn:obra:3.29-3.30"
    assert enlace_pasaje(None, None, "urn:obra", "Vergil, Eclogues 9") == f"{SCAIFE}urn:obra:9"


def test_normaliza_el_guion_largo_y_los_espacios():
    """Las citas traen guion largo y espacios que Scaife no acepta en la ref."""
    assert enlace_pasaje(None, None, "urn:obra", "1.1 – 1.9") == f"{SCAIFE}urn:obra:1.1-1.9"


def test_sin_enlace_cuando_la_obra_no_tiene_urn():
    """Estrabon, Plinio, Diodoro y los escolios no tienen CTS URN: 3.308 pasajes
    se quedan sin enlace a proposito. Un enlace roto es peor que ninguno."""
    assert enlace_pasaje(None, None, None, "Strabo 9.2.27") is None
    assert enlace_pasaje(None, None, None, None) is None


def test_sin_enlace_si_la_cita_no_tiene_referencia_numerica():
    assert enlace_pasaje(None, None, "urn:obra", "Hesiod, Ehoiai fragmenta") is None


# ------------------------------------------------------------------ busqueda


def test_clave_incluye_transliteracion_y_forma_cruda():
    """La busqueda es SUBCADENA sobre las formas atestiguadas, no aproximada.

    `unidecode` transcribe khi como `kh`, asi que Ἀχιλλεύς entra al pajar como
    `akhilleus` — teclear `akhilleus` lo encuentra y `achilleus` no, porque esa
    grafia no la atestigua ninguna fuente del corpus. El limite es deliberado: el
    pajar trae todas las variantes reales (`Achilles`, `Kirke`, `Κίρκη`) y con eso
    basta, mientras que aproximar exigiria reimplementar en TypeScript los
    pliegues griego->latin de normalize.py, que se desincronizarian.
    """
    k = clave_busqueda("Achilles", "Ἀχιλλεύς")
    assert "achilles" in k
    assert "akhilleus" in k  # unidecode del griego
    assert "ἀχιλλεύς" in k  # forma cruda en minusculas


def test_clave_junta_las_variantes():
    """El pajar trae todas las variantes atestiguadas, asi que la busqueda puede
    ser una subcadena simple y no hay que reimplementar los pliegues de
    normalize.py en TypeScript."""
    k = clave_busqueda("Circe", "Circe", "Kirke", "Κίρκη")
    assert "kirke" in k
    assert "circe" in k


def test_clave_deduplica_palabras():
    """Las variantes repiten el nombre principal; sin deduplicar eran 1,1 MB de
    JSON sin ninguna coincidencia nueva."""
    k = clave_busqueda("Circe", "Circe", "Circe", "Kirke")
    assert k.split().count("circe") == 1


def test_clave_ignora_los_nulos_y_los_vacios():
    assert clave_busqueda(None, "", None) == ""
    assert clave_busqueda(None, "Zeus") == "zeus"


def test_clave_quita_la_puntuacion_de_los_cualificadores():
    """Los nombres llevan cualificador entre parentesis (`Zeus (Olympian)`) y sin
    limpiar quedaba el token `(olympian)`, que no casa al teclear `olympian`."""
    k = clave_busqueda("Zeus (Olympian)")
    assert "olympian" in k.split()


# ------------------------------------------------------------ vista de relaciones


@pytest.fixture
def con(tmp_path):
    c = connect(tmp_path / "test.db")
    init_schema(c)
    yield c
    c.close()


def _red_minima(con):
    """Heracles hijo de Zeus (dos fuentes), Heracles mata a Hilo (dos fuentes) y
    Heracles visita Tebas (lugar)."""
    f = registrar_fuente(
        con,
        clave="t",
        nombre="t",
        licencia="n/a",
        fecha_descarga="2026-10-18",
        atribucion_texto="t",
    )
    tipo = dict(con.execute("SELECT clave, id FROM tipo_entidad"))
    ids = {}
    for nombre, t in [
        ("Heracles", "agente"),
        ("Zeus", "agente"),
        ("Hilo", "agente"),
        ("Tebas", "lugar"),
    ]:
        ids[nombre] = con.execute(
            "INSERT INTO entidad (nombre, tipo_entidad_id, fuente_dataset_id) VALUES (?,?,?)",
            (nombre, tipo[t], f),
        ).lastrowid
    pred = {}
    for clave, cat in [
        ("is_child_of", "genealogica"),
        ("kills", "muerte"),
        ("visits", "geografica"),
    ]:
        pred[clave] = con.execute(
            "INSERT INTO predicado (clave, nombre_es, categoria) VALUES (?,?,?)",
            (clave, clave, cat),
        ).lastrowid

    def rel(s, p, o, duda=0):
        return con.execute(
            "INSERT INTO relacion (sujeto_id, predicado_id, objeto_id, duda_expresada, "
            "fuente_dataset_id) VALUES (?,?,?,?,?)",
            (ids[s], pred[p], ids[o], duda, f),
        ).lastrowid

    padre_a = rel("Heracles", "is_child_of", "Zeus", duda=1)
    padre_b = rel("Heracles", "is_child_of", "Zeus")
    mata_a = rel("Heracles", "kills", "Hilo", duda=1)
    mata_b = rel("Heracles", "kills", "Hilo", duda=1)
    rel("Heracles", "visits", "Tebas")
    return ids, (padre_a, padre_b, mata_a, mata_b)


def test_red_agrega_una_arista_por_terna(con):
    """Una fila de `relacion` por fuente; la vista dibuja UNA arista con `n`."""
    ids, _ = _red_minima(con)
    red = _red(con, {})
    padre = [a for a in red["aristas"] if a["o"] == ids["Zeus"]]
    assert len(padre) == 1
    assert padre[0]["n"] == 2


def test_red_excluye_lugares(con):
    """Los lugares ya tienen el mapa: aqui convertian a cada dios en una estrella
    de santuarios."""
    ids, _ = _red_minima(con)
    red = _red(con, {})
    assert ids["Tebas"] not in {n["id"] for n in red["nodos"]}


def test_red_flags_con_and(con):
    """Si una fuente duda y otra lo afirma, el hecho esta afirmado."""
    ids, _ = _red_minima(con)
    red = _red(con, {})
    por_objeto = {a["o"]: a for a in red["aristas"]}
    assert "duda" not in por_objeto[ids["Zeus"]]
    assert por_objeto[ids["Hilo"]]["duda"] == 1


def test_red_disputa_solo_genealogia_y_muerte(con):
    """Una contradiccion de ubicacion discute donde, no entre quienes."""
    ids, (padre_a, padre_b, mata_a, mata_b) = _red_minima(con)
    con.execute(
        "INSERT INTO contradiccion (relacion_a_id, relacion_b_id, tipo) VALUES (?,?,?)",
        (padre_a, padre_b, "genealogia"),
    )
    con.execute(
        "INSERT INTO contradiccion (relacion_a_id, relacion_b_id, tipo) VALUES (?,?,?)",
        (mata_a, mata_b, "ubicacion"),
    )
    por_objeto = {a["o"]: a for a in _red(con, {})["aristas"]}
    assert por_objeto[ids["Zeus"]].get("dis") == 1
    assert "dis" not in por_objeto[ids["Hilo"]]
