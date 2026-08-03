"""Semilla de eventos mayores + tabla de dataciones antiguas de la Guerra de Troya.

fuentes.md §2.6: las autoridades antiguas discrepan en 200 anios sobre la caida de
Troya. Guardar todas las variantes es un dato de calidad, no ruido. Preferida:
Eratostenes (1184/1183), que funciono como referencia universal en la Antiguedad y
coincide con la destruccion por incendio de Troya VIIa.

§5.2: la semilla manual de eventos mayores da mejor calidad que cualquier
heuristica de agrupacion. Aqui van los imprescindibles con su ciclo y generacion;
generacional.py les pone fecha.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from ..db import insert_ignore, registrar_fuente, upsert

# (autoridad, anio_ac, precision, es_preferida, nota)
DATACIONES_TROYA: tuple[tuple[str, int, str, int, str], ...] = (
    ("Duris de Samos", -1334, "anio", 0, ""),
    ("Eretes", -1291, "anio", 0, ""),
    (
        "Herodoto",
        -1250,
        "medio_siglo",
        0,
        "Herodoto no daba cifras: situaba la guerra en marco relativo (900-800 anios "
        "antes de su epoca). Fecha derivada, no atestiguada.",
    ),
    ("Dicearco", -1212, "anio", 0, ""),
    ("Marmol de Paros", -1209, "anio", 0, "Guerra 1217-1208; caida 1209/1208."),
    ("Timeo", -1193, "anio", 0, ""),
    ("Platon", -1193, "anio", 0, ""),
    (
        "Eratostenes",
        -1184,
        "anio",
        1,
        "Guerra 1194-1184. Referencia universal en la Antiguedad; concuerda con la "
        "destruccion por incendio de Troya VIIa. Metodo: cuenta atras desde la primera "
        "Olimpiada (776 a.C.) con listas regias y generacion regia de 40 anios.",
    ),
    ("Sosibio", -1172, "anio", 0, ""),
    ("Eforo", -1135, "anio", 0, ""),
    (
        "arqueologia LH IIIB/C",
        -1200,
        "medio_siglo",
        0,
        "Colapso de los palacios micenicos ~1200 a.C., final del LH IIIB.",
    ),
)

# (nombre, tipo, clave de ciclo, generacion). generacion None = sin fecha real.
EVENTOS_MAYORES: tuple[tuple[str, str, str, int | None], ...] = (
    ("Cosmogonia", "otro", "cosmogonia", None),
    ("Titanomaquia", "guerra", "titanomaquia", None),
    ("Gigantomaquia", "guerra", "gigantomaquia", None),
    ("Diluvio de Deucalion", "cataclismo", "primeros_mortales", -5),
    ("Llegada de Danao a Argos", "viaje", "ciclo_argivo", -4),
    ("Rapto de Europa", "rapto", "ciclo_cretense", -4),
    ("Fundacion de Tebas por Cadmo", "fundacion", "ciclo_tebano", -4),
    ("Perseo y Medusa", "duelo", "ciclo_argivo", -3),
    ("Belerofonte y la Quimera", "duelo", "ciclo_argivo", -3),
    ("Teseo y el Minotauro", "duelo", "teseida", -1),
    ("Los doce trabajos de Heracles", "trabajo", "heracleia", 0),
    ("Expedicion de los Argonautas", "expedicion", "argonautica", 0),
    ("Caceria de Calidon", "caceria", "caceria_calidonia", 0),
    ("Siete contra Tebas", "guerra", "ciclo_tebano", 0),
    ("Los Epigonos", "guerra", "ciclo_tebano", 1),
    ("Juicio de Paris", "juicio", "ciclo_troyano", 1),
    ("Rapto de Helena", "rapto", "ciclo_troyano", 1),
    ("Sacrificio de Ifigenia en Aulide", "sacrificio", "ciclo_troyano", 2),
    ("Guerra de Troya", "guerra", "ciclo_troyano", 2),
    ("Duelo de Aquiles y Hector", "duelo", "ciclo_troyano", 2),
    ("Caballo de Troya", "otro", "ciclo_troyano", 2),
    ("Saqueo de Ilion", "batalla", "ciclo_troyano", 2),
    ("Retorno de Odiseo", "viaje", "nostoi", 3),
    ("Orestiada", "castigo", "orestiada", 3),
    ("Retorno de los Heraclidas", "expedicion", "retorno_heraclidas", 4),
)


def cargar(con: sqlite3.Connection) -> str:
    fuente_id = registrar_fuente(
        con,
        clave="cronografos",
        nombre="Cronografos antiguos (tabla comparada de la caida de Troya)",
        version="fuentes.md §2.6",
        url="https://www.centuries.co.uk/2009-ancient%20chronography-kokkinos.pdf",
        licencia="Compilacion propia a partir de traducciones libres (Attalus) y bibliografia",
        fecha_descarga=datetime.now(UTC).date().isoformat(),
        atribucion_texto=(
            "Dataciones antiguas compiladas de Attalus (https://www.attalus.org) y de "
            "Kokkinos, Ancient Chronography, Eratosthenes and the Dating of the Fall of Troy."
        ),
    )

    ciclos = {f["clave"]: f["id"] for f in con.execute("SELECT clave, id FROM ciclo_mitico")}

    n_eventos = 0
    ids: dict[str, int] = {}
    for nombre, tipo, ciclo, generacion in EVENTOS_MAYORES:
        eid = upsert(
            con,
            "evento",
            {
                "nombre": nombre,
                "tipo": tipo,
                "ciclo_id": ciclos.get(ciclo),
                "generacion": generacion,
                "fecha_metodo": "sin_fecha" if generacion is None else None,
                "fecha_confianza": "nula" if generacion is None else None,
                "fuente_dataset_id": fuente_id,
            },
            conflicto=["nombre", "tipo"],
            actualizar=["ciclo_id", "generacion"],
        )
        if eid:
            ids[nombre] = eid
            n_eventos += 1

    troya_id = ids.get("Guerra de Troya")
    n_dat = 0
    if troya_id:
        for autoridad, anio, precision, preferida, nota in DATACIONES_TROYA:
            sistema = (
                "arqueologico" if autoridad.startswith("arqueologia") else "cronografo_antiguo"
            )
            insert_ignore(
                con,
                "evento_datacion",
                {
                    "evento_id": troya_id,
                    "autoridad": autoridad,
                    "sistema": sistema,
                    "anio_ac": anio,
                    "anio_min_ac": anio - 25 if precision != "anio" else anio - 10,
                    "anio_max_ac": anio + 25 if precision != "anio" else anio,
                    "precision": precision,
                    "es_preferida": preferida,
                    "fuente_dataset_id": fuente_id,
                    "nota": nota or None,
                },
            )
            n_dat += 1

        # la caida de Ilion comparte datacion con la guerra
        saqueo_id = ids.get("Saqueo de Ilion")
        if saqueo_id:
            insert_ignore(
                con,
                "evento_relacion",
                {"evento_a_id": troya_id, "evento_b_id": saqueo_id, "tipo": "parte_de"},
            )

    _encadenar(con, ids)
    n_bandos = _bandos(con, ids)
    n_lugares = _lugares(con, ids)
    con.commit()
    return (
        f"troya: {n_eventos} eventos mayores sembrados, "
        f"{n_dat} dataciones alternativas de la caida de Troya, "
        f"{n_bandos} bandos, {n_lugares} eventos localizados"
    )


# evento -> (bando, resultado). Solo lo que las fuentes antiguas dan por zanjado.
BANDOS: dict[str, tuple[tuple[str, str], ...]] = {
    "Guerra de Troya": (("aqueos", "victoria"), ("troyanos", "derrota")),
    "Saqueo de Ilion": (("aqueos", "victoria"), ("troyanos", "derrota")),
    "Titanomaquia": (("olimpicos", "victoria"), ("titanes", "derrota")),
    "Gigantomaquia": (("olimpicos", "victoria"), ("gigantes", "derrota")),
    "Siete contra Tebas": (("argivos", "derrota"), ("tebanos", "victoria")),
    "Los Epigonos": (("argivos", "victoria"), ("tebanos", "derrota")),
    "Retorno de los Heraclidas": (("heraclidas", "victoria"), ("aqueos", "derrota")),
}

# evento -> nombre del lugar EXACTO tal como aparece en la base. Mapeo explicito:
# es un dato afirmado a mano, no una coincidencia de cadenas. Los nombres llevan su
# cualificador regional porque sin el se cogen homonimos: hay un 'Troy (Egypt)' y un
# 'Thebes (Egypt)' que no son el Troya ni la Tebas del mito.
LUGARES: dict[str, tuple[str, ...]] = {
    "Guerra de Troya": ("Ilion", "Troia"),
    "Saqueo de Ilion": ("Ilion", "Troia"),
    "Caballo de Troya": ("Ilion", "Troia"),
    "Duelo de Aquiles y Hector": ("Ilion", "Troia"),
    "Sacrificio de Ifigenia en Aulide": ("Aulis (Boiotia)", "Aulis"),
    "Siete contra Tebas": ("Thebes (Boiotia)",),
    "Los Epigonos": ("Thebes (Boiotia)",),
    "Fundacion de Tebas por Cadmo": ("Thebes (Boiotia)",),
    "Teseo y el Minotauro": ("Knossos (Crete)", "Knossos"),
    "Caceria de Calidon": ("Calydon (Aitolia)", "Calydon"),
    "Expedicion de los Argonautas": ("Iolcos (Thessaly)", "Iolcos"),
    "Llegada de Danao a Argos": ("Argos (Argolid)", "Argos"),
    "Juicio de Paris": ("Mount Ida (Troad)", "Ida"),
    "Diluvio de Deucalion": ("Mount Parnassus (Phokis)", "Parnassus"),
    "Retorno de Odiseo": ("Ithaca (island)", "Ithaca"),
    "Orestiada": ("Mycenae (Argolid)", "Mycenae"),
}


def _bandos(con: sqlite3.Connection, ids: dict[str, int]) -> int:
    n = 0
    for evento, bandos in BANDOS.items():
        eid = ids.get(evento)
        if eid is None:
            continue
        for nombre, resultado in bandos:
            insert_ignore(
                con,
                "bando",
                {"evento_id": eid, "nombre": nombre, "resultado": resultado},
            )
            n += 1
    return n


def _lugares(con: sqlite3.Connection, ids: dict[str, int]) -> int:
    """Asigna evento.lugar_id buscando el nombre exacto entre las entidades lugar."""
    n = 0
    for evento, candidatos in LUGARES.items():
        eid = ids.get(evento)
        if eid is None:
            continue
        for nombre in candidatos:
            fila = con.execute(
                "SELECT e.id FROM entidad e JOIN tipo_entidad t ON t.id = e.tipo_entidad_id "
                "WHERE t.es_lugar = 1 AND e.nombre = ? "
                "ORDER BY (SELECT COUNT(*) FROM relacion r WHERE r.sujeto_id = e.id "
                "          OR r.objeto_id = e.id) DESC LIMIT 1",
                (nombre,),
            ).fetchone()
            if fila:
                con.execute(
                    "UPDATE evento SET lugar_id = COALESCE(lugar_id, ?) WHERE id = ?",
                    (fila["id"], eid),
                )
                n += 1
                break
    return n


def _encadenar(con: sqlite3.Connection, ids: dict[str, int]) -> None:
    """Causalidad minima entre los eventos del ciclo troyano."""
    cadena = (
        ("Juicio de Paris", "Rapto de Helena", "causa_de"),
        ("Rapto de Helena", "Guerra de Troya", "causa_de"),
        ("Sacrificio de Ifigenia en Aulide", "Guerra de Troya", "parte_de"),
        ("Duelo de Aquiles y Hector", "Guerra de Troya", "parte_de"),
        ("Caballo de Troya", "Saqueo de Ilion", "causa_de"),
        ("Guerra de Troya", "Retorno de Odiseo", "causa_de"),
        ("Sacrificio de Ifigenia en Aulide", "Orestiada", "causa_de"),
        ("Siete contra Tebas", "Los Epigonos", "causa_de"),
    )
    for a, b, tipo in cadena:
        if a in ids and b in ids:
            insert_ignore(
                con,
                "evento_relacion",
                {"evento_a_id": ids[a], "evento_b_id": ids[b], "tipo": tipo},
            )
