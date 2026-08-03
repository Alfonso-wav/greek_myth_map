import pytest

from greek import fuzzy
from greek.db import connect, id_tipo_entidad, init_schema, registrar_fuente


def hay_veto_directo(con, a, b):
    """hay_veto sin indice precalculado: comprueba la via de consulta a la base."""
    return fuzzy.hay_veto(con, a, b)


@pytest.fixture
def con(tmp_path):
    c = connect(tmp_path / "test.db")
    init_schema(c)
    registrar_fuente(
        c,
        clave="test",
        nombre="fixture",
        licencia="n/a",
        fecha_descarga="2026-07-29",
        atribucion_texto="fixture",
    )
    yield c
    c.close()


def _entidad(con, nombre, tipo="heroe", **extra):
    fuente = con.execute("SELECT id FROM fuente_dataset WHERE clave='test'").fetchone()["id"]
    campos = {
        "nombre": nombre,
        "tipo_entidad_id": id_tipo_entidad(con, tipo),
        "fuente_dataset_id": fuente,
        **extra,
    }
    cur = con.execute(
        f"INSERT INTO entidad ({','.join(campos)}) VALUES ({','.join('?' * len(campos))})",
        list(campos.values()),
    )
    con.commit()
    return cur.lastrowid


def _id_externo(con, eid, namespace, valor):
    con.execute(
        "INSERT INTO entidad_identificador (entidad_id, namespace, valor) VALUES (?,?,?)",
        (eid, namespace, valor),
    )
    con.commit()


def _predicado(con, clave="father_of", categoria="genealogica"):
    cur = con.execute(
        "INSERT INTO predicado (clave, nombre_es, categoria) VALUES (?,?,?)",
        (clave, clave, categoria),
    )
    con.commit()
    return cur.lastrowid


def _relacion(con, sujeto, objeto, pid):
    fuente = con.execute("SELECT id FROM fuente_dataset WHERE clave='test'").fetchone()["id"]
    cur = con.execute(
        "INSERT INTO relacion (sujeto_id, predicado_id, objeto_id, fuente_dataset_id) "
        "VALUES (?,?,?,?)",
        (sujeto, pid, objeto, fuente),
    )
    con.commit()
    return cur.lastrowid


def test_fusiona_variantes_de_transliteracion(con):
    a = _entidad(con, "Kirke")
    b = _entidad(con, "Circe", nombre_es="Circe")
    informe = fuzzy.ejecutar(con, aplicar_cambios=True)

    assert len(informe.fusiones) == 1
    vivas = [f["nombre"] for f in con.execute("SELECT nombre FROM entidad")]
    assert vivas == ["Circe"]  # normalizado a un solo nombre, el de Wikidata

    # el nombre absorbido no se pierde
    nombres = {f["nombre"] for f in con.execute("SELECT nombre FROM entidad_nombre")}
    assert "Kirke" in nombres
    assert con.execute("SELECT COUNT(*) FROM fuzzy_fusion").fetchone()[0] == 1
    assert {a, b} & {f["id"] for f in con.execute("SELECT id FROM entidad")}


def test_ids_externos_discrepantes_vetan_la_fusion(con):
    a = _entidad(con, "Yolao")
    b = _entidad(con, "Yolao")
    _id_externo(con, a, "wikidata", "Q1")
    _id_externo(con, b, "wikidata", "Q2")

    informe = fuzzy.ejecutar(con, aplicar_cambios=True)

    assert not informe.fusiones
    assert informe.n_vetadas == 1
    assert con.execute("SELECT COUNT(*) FROM entidad").fetchone()[0] == 2
    # un ID externo discrepante zanja el caso: no se fusiona NI se encola para humano
    assert con.execute("SELECT COUNT(*) FROM entidad_revision").fetchone()[0] == 0
    assert hay_veto_directo(con, a, b) is not None


def test_tipos_distintos_no_se_fusionan(con):
    _entidad(con, "Escamandro", tipo="rio")
    _entidad(con, "Escamandro", tipo="heroe")
    informe = fuzzy.ejecutar(con, aplicar_cambios=True)
    assert not informe.fusiones
    assert con.execute("SELECT COUNT(*) FROM entidad").fetchone()[0] == 2


def test_banda_media_exige_corroboracion(con):
    # 'Alfesibea' vs 'Alfesibea de Frigia': score en banda media, sin vecino comun
    _entidad(con, "Anaxibia")
    _entidad(con, "Anaxibio")
    informe = fuzzy.ejecutar(con, aplicar_cambios=False)
    corroboradas = [c for c in informe.fusiones if c.banda == "corroborada"]
    assert not corroboradas or all(c.evidencia for c in corroboradas)


def test_corroboracion_por_vecino_genealogico(con):
    padre = _entidad(con, "Zeus", tipo="dios")
    pid = _predicado(con)
    a = _entidad(con, "Perseus")
    b = _entidad(con, "Perseo")
    _relacion(con, padre, a, pid)
    _relacion(con, padre, b, pid)

    assert fuzzy.corroboracion(con, a, b) is not None
    informe = fuzzy.ejecutar(con, aplicar_cambios=True)
    assert len(informe.fusiones) == 1
    # las relaciones se reapuntaron al superviviente, sin dejar huerfanos
    huerfanas = con.execute(
        "SELECT COUNT(*) FROM relacion r LEFT JOIN entidad e ON e.id = r.objeto_id "
        "WHERE r.objeto_id IS NOT NULL AND e.id IS NULL"
    ).fetchone()[0]
    assert huerfanas == 0


def test_no_fusiona_numerados(con):
    """Regresion: WRatio unia 'Tower 7' con 'tower (Arkoi)' a 95.0 en datos reales."""
    _entidad(con, "Tower 7", tipo="lugar")
    _entidad(con, "tower (Arkoi)", tipo="lugar")
    _entidad(con, "Tower 11", tipo="lugar")
    informe = fuzzy.ejecutar(con, aplicar_cambios=True)
    assert not informe.fusiones
    assert con.execute("SELECT COUNT(*) FROM entidad").fetchone()[0] == 3


def test_no_fusiona_homonimos_con_region_distinta(con):
    """Regresion: al descartar el parentesis, 'Kastri (Euboea)' y 'Kastri (Serres)'
    colapsaban al mismo 'kastri' y se fusionaban con score 100."""
    _entidad(con, "Kastri (Euboea)", tipo="lugar")
    _entidad(con, "Kastri (Serres)", tipo="lugar")
    informe = fuzzy.ejecutar(con, aplicar_cambios=True)
    assert not informe.fusiones
    assert con.execute("SELECT COUNT(*) FROM entidad").fetchone()[0] == 2


def test_deshacer_restaura_la_entidad(con):
    _entidad(con, "Kirke")
    _entidad(con, "Circe", nombre_es="Circe")
    fuzzy.ejecutar(con, aplicar_cambios=True)
    fusion_id = con.execute("SELECT id FROM fuzzy_fusion").fetchone()["id"]

    fuzzy.deshacer(con, fusion_id)

    nombres = {f["nombre"] for f in con.execute("SELECT nombre FROM entidad")}
    assert nombres == {"Kirke", "Circe"}
    assert con.execute("SELECT revertida FROM fuzzy_fusion").fetchone()["revertida"] == 1
    with pytest.raises(LookupError):
        fuzzy.deshacer(con, fusion_id)


def test_idempotente(con):
    _entidad(con, "Kirke")
    _entidad(con, "Circe", nombre_es="Circe")
    fuzzy.ejecutar(con, aplicar_cambios=True)
    n1 = con.execute("SELECT COUNT(*) FROM fuzzy_fusion").fetchone()[0]
    fuzzy.ejecutar(con, aplicar_cambios=True)
    n2 = con.execute("SELECT COUNT(*) FROM fuzzy_fusion").fetchone()[0]
    assert n1 == n2 == 1


def test_respeta_revisado_manual(con):
    _entidad(con, "Kirke", revisado_manual=1)
    _entidad(con, "Circe")
    informe = fuzzy.ejecutar(con, aplicar_cambios=True)
    assert not informe.fusiones
    assert con.execute("SELECT COUNT(*) FROM entidad").fetchone()[0] == 2
