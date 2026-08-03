"""Digital Marmor Parium -> evento + evento_datacion (autoridad 'Marmol de Paros').

Unica fuente antigua que asigna anios concretos a eventos miticos: el Marmol de
Paros (IG XII.5.444), grabado en 264/263 a.C., cubre 1581/80 - 299/98 a.C. sin
distinguir mito de historia.

FUENTE REAL: la edicion EpiDoc del proyecto, no la tabla web. `chronology.html`
(la URL que cita fuentes.md §2.4) no contiene ninguna tabla: solo incrusta
timelines de Knightlab alimentadas por una Google Sheet que devuelve 401 al
exportar. El XML EpiDoc si trae las expresiones cronologicas marcadas:

    <seg type="entry" n="2">... <date from="-1573" to="-1572" when-custom="1310"
        datingMethod="#marmor_parium"><num type="acrophonic">...</num></date>.</seg>

`when-custom` es la cuenta original de la inscripcion: anios hacia atras e
INCLUSIVAMENTE desde 264/3 a.C. Se conserva en la nota de cada datacion junto a la
conversion, para que la convencion quede documentada y sea verificable.

LICENCIA: **CC BY-SA 4.0**, no "proyecto academico abierto" como decia fuentes.md.
El ShareAlike es virico: el texto griego se almacena como `descripcion`, asi que si
redistribuyes la base tienes que mantener la misma licencia o retirar esa columna.
Queda registrado en fuente_dataset.licencia y en notas.
"""

from __future__ import annotations

import re
import sqlite3
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

from ..db import RAW_DIR, insert_ignore, registrar_fuente, upsert

RUTA = RAW_DIR / "dmp" / "dmp_ig_12_5_444.xml"
TEI = {"t": "http://www.tei-c.org/ns/1.0"}
LINEA_BASE = -263  # a.C.: base para convertir la cuenta inclusiva del Marmol

# Palabra griega -> tipo de evento del esquema. El texto de la inscripcion esta en
# griego, asi que la clasificacion se hace sobre raices griegas.
TIPOS_GRC = (
    (("κατακλυσμ",), "cataclismo"),
    (("ἐβασίλευσε", "βασιλε", "ἄρχ"), "otro"),  # reinados y magistraturas
    (("ἑάλω", "ἐπόρθησ", "εἷλε"), "batalla"),  # tomas de ciudad
    (("στρατ", "ἔπλευσ", "ἀπῆρ"), "expedicion"),
    (("ἀγών", "ἀγῶν", "Ὀλυμπ", "ἐνίκησ", "Πυθ"), "juegos"),
    (("ἐγένετο", "ἐφάνη"), "otro"),
    (("ἀπέθανε", "ἐτελεύτησ"), "muerte"),
    (("ἐγεννήθη", "γενέσ"), "nacimiento"),
    (("μάχη", "πόλεμ", "ἐμαχέσ"), "batalla"),
    (("ἥρπασ",), "rapto"),
    (("θυσ", "ἔθυσ"), "sacrificio"),
    (("ἔκτισ", "ᾤκισ", "συνῴκισ"), "fundacion"),
    (("ποίησ", "εὗρε", "ἐδίδαξ"), "otro"),
)

_ESPACIOS = re.compile(r"\s+")


def _texto(nodo: ET.Element) -> str:
    """Texto plano del elemento, sin marcado epigrafico."""
    return _ESPACIOS.sub(" ", "".join(nodo.itertext())).strip()


def _tipo(texto: str) -> str:
    for raices, tipo in TIPOS_GRC:
        if any(r in texto for r in raices):
            return tipo
    return "otro"


def _protagonistas(entrada: ET.Element, limite: int = 3) -> list[str]:
    """persName/placeName de la entrada: sirven para nombrar el evento."""
    nombres: list[str] = []
    for etiqueta in ("persName", "placeName"):
        for nodo in entrada.iter(f"{{{TEI['t']}}}{etiqueta}"):
            valor = _texto(nodo).strip(" ,.·;")
            if valor and valor not in nombres:
                nombres.append(valor)
            if len(nombres) >= limite:
                return nombres
    return nombres


def cargar(con: sqlite3.Connection) -> str:
    if not RUTA.is_file():
        return f"dmp: falta {RUTA} — `greek fetch --source dmp`"

    fuente_id = registrar_fuente(
        con,
        clave="dmp",
        nombre="Digital Marmor Parium (edicion EpiDoc de IG XII.5.444)",
        version="dmp_ig_12_5_444.xml",
        url="https://github.com/OpenGreekAndLatin/DigitalMarmorParium",
        licencia="CC BY-SA 4.0",
        fecha_descarga=datetime.fromtimestamp(RUTA.stat().st_mtime, UTC).date().isoformat(),
        atribucion_texto=(
            "Digital Marmor Parium, Monica Berti, Universitat Leipzig. "
            "https://www.digitalmarmorparium.org — CC BY-SA 4.0"
        ),
        notas=(
            "ShareAlike virico: el texto griego se guarda en evento.descripcion. "
            f"El Marmol cuenta hacia atras e inclusivamente desde 264/3 a.C.; "
            f"conversion documentada con linea base {abs(LINEA_BASE)}/2 a.C. y el "
            "valor original en when-custom."
        ),
    )

    raiz = ET.parse(RUTA).getroot()
    n_eventos = n_dataciones = 0

    for entrada in raiz.iter(f"{{{TEI['t']}}}seg"):
        if entrada.get("type") != "entry":
            continue
        fecha = next(
            (d for d in entrada.iter(f"{{{TEI['t']}}}date") if d.get("from")),
            None,
        )
        if fecha is None:
            continue

        desde = _entero(fecha.get("from"))
        hasta = _entero(fecha.get("to"))
        if desde is None:
            continue

        n_entrada = entrada.get("n") or "?"
        texto = _texto(entrada)
        protagonistas = _protagonistas(entrada)
        nombre = f"Marmor Parium {n_entrada}: {', '.join(protagonistas) or texto[:60]}"[:180]

        evento_id = upsert(
            con,
            "evento",
            {
                "nombre": nombre,
                "tipo": _tipo(texto),
                "descripcion": texto,
                "fuente_dataset_id": fuente_id,
            },
            conflicto=["nombre", "tipo"],
            actualizar=["descripcion"],
        )
        if evento_id is None:
            continue
        n_eventos += 1

        cuenta = fecha.get("when-custom")
        insert_ignore(
            con,
            "evento_datacion",
            {
                "evento_id": evento_id,
                "autoridad": "Marmol de Paros",
                "sistema": "cronografo_antiguo",
                "anio_ac": desde,
                "anio_min_ac": min(desde, hasta) if hasta is not None else desde,
                "anio_max_ac": max(desde, hasta) if hasta is not None else desde,
                "precision": "anio",
                "es_preferida": 0,
                "fuente_dataset_id": fuente_id,
                "nota": (
                    f"Marmor Parium, entrada {n_entrada}. Cuenta original "
                    f"when-custom={cuenta} anios antes de 264/3 a.C., contados "
                    f"inclusivamente; conversion con linea base {abs(LINEA_BASE)}/2."
                ),
            },
        )
        n_dataciones += 1

        if n_eventos % 25 == 0:
            con.commit()

    con.commit()
    return (
        f"dmp: {n_eventos} eventos del Marmol de Paros, {n_dataciones} dataciones "
        f"absolutas (rango {_rango(con)})"
    )


def _rango(con: sqlite3.Connection) -> str:
    row = con.execute(
        "SELECT MIN(anio_ac) AS a, MAX(anio_ac) AS b FROM evento_datacion "
        "WHERE autoridad = 'Marmol de Paros'"
    ).fetchone()
    if row is None or row["a"] is None:
        return "vacio"
    return f"{abs(row['a'])}-{abs(row['b'])} a.C."


def _entero(valor: str | None) -> int | None:
    if not valor:
        return None
    try:
        return int(valor)
    except ValueError:
        return None
