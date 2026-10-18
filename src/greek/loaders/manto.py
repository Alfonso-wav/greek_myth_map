"""MANTO -> entidad, identificadores, autor/obra/pasaje, predicado, relacion, roles.

Espina dorsal del proyecto: 8.993 entidades y ~32.000 relaciones tipadas con cita
textual. DOI 10.5281/zenodo.19446255.

LICENCIA — **CC BY-NC 4.0**, no "CC-BY 4.0" como afirma fuentes.md §2.1. El registro
de Zenodo declara `cc-by-nc-4.0`: la clausula NonCommercial prohibe el uso comercial,
al contrario de lo que decia el documento de diseno ("reutilizacion comercial y
remezcla permitidas"). Como MANTO es la espina dorsal, **toda la base hereda de hecho
la restriccion NC**. Queda registrado en fuente_dataset.licencia y en el README.

ESTRUCTURA REAL DEL DUMP (verificada, difiere de lo que asumia la primera version):

El export de Nodegoat trae, ademas de los JSON grandes, un CSV plano por tabla y un
CSV por campo. Los CSV son la via buena: cabeceras nombradas y sin cargar 221 MB de
JSON en memoria.

    entity_objects_6580.csv      Object ID, Name, Information, Pleiades, ToposText,
                                 "Somewhere in or near", Commentary
    tie_objects_6582.csv         Object ID, Predicate, "Data uncertain",
                                 "Doubt or disbelief expressed", "Alternatives given",
                                 "Data implicit", "Timemark: when", Commentary
    passage_objects_6581.csv     Object ID, Name, Title, "Scaife URL"
    text_objects_7140.csv        Object ID, Name, Author
    author_objects_7139.csv      Object ID, Name, Commentary
    interaction_objects_6583.csv Object ID, Name  (los 165 predicados)
    {campo}_object_definitions_{id}.csv
                                 Object ID, "{Campo} - Object ID", "{Campo}"
                                 -> subject, direct_object, source, in/on/at, using,
                                    against, to_avenge, wikidata, trismegistos...

El nombre de fichero de cada CSV de definicion es el que da el nombre del campo: de
ahi salen los 234 campos del modelo sin tener que adivinar alias.

El TIPO de entidad no viene en ninguna columna: MANTO lo codifica con el **emoji**
que prefija `Name` (👤 Agent, 🌍 Place, 🏛 Landmark, 🏺 Object, 👥 Collective,
⭐ Constellation, ⏳ Mythic Event). Los recuentos por emoji suman exactamente 8.993.

Los cuatro flags de incertidumbre (Data uncertain, Doubt or disbelief expressed,
Alternatives given, Data implicit) vienen como 'Yes'/'No' y se preservan tal cual:
son lo que distingue "Homero dice X" de "quiza se insinua X".
"""

from __future__ import annotations

import csv
import re
import sqlite3
from collections.abc import Iterator

from ..archivo import Zip, stem
from ..db import (
    RAW_DIR,
    entidad_por_identificador,
    id_tipo_entidad,
    insert_ignore,
    registrar_fuente,
    upsert,
)
from ..normalize import normalizar

# Se lee del ZIP sin descomprimir: descomprimido son 5,4 GB y el loader usa 56 MB.
ZIP = Zip(RAW_DIR / "manto" / "manto_publication_2616.zip")

# El emoji que prefija Name es el unico portador del tipo de entidad.
EMOJI_TIPO = {
    "👤": "agente",  # Agent: dioses, heroes, mortales, monstruos, ninfas
    "🌍": "lugar",  # Place
    "🏛": "landmark",  # Landmark: santuarios, tumbas, monumentos
    "🏺": "objeto",  # Object
    "👥": "colectivo",  # Collective
    "⭐": "constelacion",  # Constellation
    "⏳": "evento_mitico",  # Mythic Event
}

# campo del dump -> namespace de entidad_identificador
IDS_ENTIDAD = {
    "wikidata": "wikidata",
    "trismegistos": "trismegistos",
    "digital_limc": "digital_limc",
    "limc_headword": "limc",
}

# CSV de definicion -> rol de relacion_rol. Nombres tal cual aparecen en el dump.
ROLES = {
    "inonat": "en",
    "near": "cerca_de",
    "from": "desde",
    "to": "hacia",
    "via": "via",
    "while_intending_to_go_to": "con_intencion_de_ir_a",
    "using": "usando",
    "of": "de",
    "for": "para",
    "into": "en_direccion_a",
    "against": "contra",
    "concerning": "acerca_de",
    "with_the_aid_of": "con_ayuda_de",
    "at_the_command_of": "por_orden_de",
    "at_the_instigation_of": "a_instigacion_de",
    "with_the_involvement_of": "con_participacion_de",
    "in_accordance_with_a_prophecy_from": "segun_profecia_de",
    "in_accordance_with_a_prophecy_about": "segun_profecia_sobre",
    "to_avenge": "para_vengar",
    "to_aid": "para_ayudar",
    "to_obtain": "para_obtener",
    "to_protect": "para_proteger",
    "to_honor": "para_honrar",
    "to_thwart": "para_frustrar",
    "to_punish": "para_castigar",
    "and_they_conceive": "y_conciben",
    "indirect_object_tofor": "objeto_indirecto",
}

# palabra clave del predicado -> categoria del esquema
CATEGORIAS = (
    # El predicado genealogico real de MANTO es 'is child of' (5.586 relaciones):
    # el SUJETO es el hijo y el OBJETO el progenitor. Ojo al invertirlo en vistas.
    (
        ("father", "mother", "parent", "child", "children", "son", "daughter", "descend",
         "sibling", "brother", "sister", "twin", "ancestor"),
        "genealogica",
    ),
    (("imprison", "binds", "releases", "frees"), "otra"),
    (("marri", "spouse", "wife", "husband", "consort", "lover", "conceiv"), "conyugal"),
    (("kill", "slay", "murder", "dies", "death"), "muerte"),
    (("wound", "fight", "battle", "war", "conquer", "besieg", "defeat", "attack",
      "blind", "harm"), "belica"),
    (("born", "birth", "nurs", "rais", "gives birth"), "nacimiento"),
    (("buri", "dwell", "live", "situated", "near", "at ", "flow", "locat",
      "encompass", "part of"), "geografica"),
    (("cult", "worship", "sacrific", "priest", "sanctuar", "temple", "dedicat",
      "relic", "honor"), "cultual"),
    (("rul", "king", "queen", "reign", "throne", "lawgiver", "leader", "led by",
      "enslav"), "politica"),
    (("transform", "metamorph", "turn into", "becom", "rationaliz"), "transformacion"),
    (("creat", "invent", "establish", "makes"), "creacion"),
    (("found", "coloni", "eponym", "settl", "fortif"), "fundacion"),
    (("prophec", "oracle", "foretell", "seer", "prophet"), "profecia"),
    (("competes", "contest", "game", "race", "wrestl", "victor"), "competicion"),
    (("uses", "wield", "carri", "gift", "holds", "weapon", "depict"), "objeto"),
    (("teacher", "healer", "herald", "charioteer", "helmsman", "nurse",
      "patron"), "oficio"),
)

# 'Yes'/'No' de los flags
_SI = {"yes", "y", "true", "1", "si"}
# el emoji + la glosa <q>...</q> se quitan del nombre; la glosa es el desambiguador
_GLOSA = re.compile(r"<q>(.*?)</q>", re.DOTALL)
# referencia por camino de Nodegoat: '[object=6580_11297468]'
_PATH_OBJ = re.compile(r"\[object=(\d+)_(\d+)\]")
_MARCADO = re.compile(r"<[^>]+>")
_ESPACIOS = re.compile(r"\s+")


# ------------------------------------------------------------------ lectura


def _ruta(nombre: str) -> str | None:
    return ZIP.primero(nombre)


def _ruta_definicion(campo: str) -> str | None:
    """Los CSV de definicion llevan el id numerico en el nombre: `using_..._18085.csv`."""
    return ZIP.primero(f"{campo}_object_definitions_*.csv")


def _leer(ruta: str | None) -> Iterator[dict[str, str]]:
    yield from ZIP.filas(ruta)


def _tabla(nombre: str) -> Iterator[dict[str, str]]:
    yield from _leer(_ruta(nombre))


def _definicion(campo: str) -> Iterator[dict[str, str]]:
    yield from _leer(_ruta_definicion(campo))


def _valor_ref(fila: dict[str, str], campo_legible: str) -> str:
    """Id del objeto referenciado, con su prefijo de tipo si lo trae.

    Las fuentes vienen prefijadas con el type_id: '6581_11291596' es un Passage,
    '11352_...' un Artifact, '11376_...' una Inscription. El prefijo es lo que
    permite mandar cada atestacion a su columna de relacion_fuente.
    """
    return (fila.get(f"{campo_legible} - Object ID") or "").strip()


def _partir_ref(ref: str) -> tuple[str | None, str]:
    """'6581_11291596' -> ('6581', '11291596'); '8188822' -> (None, '8188822')."""
    if "_" in ref:
        tipo, _, valor = ref.rpartition("_")
        return tipo, valor
    return None, ref


def _columna_ref(ruta: str) -> str:
    """Nombre legible de la columna de referencia de un CSV de definicion."""
    with ZIP.abrir(ruta) as fh:
        for col in next(csv.reader(fh), []):
            if col.endswith(" - Object ID"):
                return col[: -len(" - Object ID")]
    return ""


def partir_nombre(bruto: str) -> tuple[str, str, str | None]:
    """'👤 Abas (Argive I) <q>son of Lynceus</q>' -> ('👤', 'Abas (Argive I)', 'son of...')."""
    texto = (bruto or "").strip()
    emoji = texto[0] if texto and ord(texto[0]) > 0x2000 else ""
    if emoji:
        texto = texto[1:]
    glosa_m = _GLOSA.search(texto)
    glosa = _MARCADO.sub("", glosa_m.group(1)).strip() if glosa_m else None
    texto = _GLOSA.sub("", texto)
    nombre = _ESPACIOS.sub(" ", _MARCADO.sub("", texto)).strip()
    return emoji, nombre, glosa or None


def _flag(valor: str | None) -> int:
    return 1 if (valor or "").strip().lower() in _SI else 0


def _categoria(clave: str) -> str:
    """Categoria del predicado por palabra clave, con frontera de palabra.

    La comparacion por subcadena suelta clasificaba 'imprisons' como genealogica
    (contiene 'son') y 'has_no_children' junto a 'is_child_of'. Con \\b delante,
    'son' ya no casa dentro de 'impri-sons'.
    """
    minus = clave.lower().replace("_", " ")
    for palabras, categoria in CATEGORIAS:
        if any(re.search(rf"\b{re.escape(p)}", minus) for p in palabras):
            return categoria
    return "otra"


def _id_externo(valor: str | None) -> str:
    """'https://www.trismegistos.org/name/20959' -> '20959'; 'Q305607' -> 'Q305607'."""
    texto = (valor or "").strip()
    if not texto:
        return ""
    if texto.startswith("http"):
        return texto.rstrip("/").rsplit("/", 1)[-1]
    return texto


def inspeccionar() -> str:
    """Cabeceras reales del dump, para verificar el mapeo antes de cargar."""
    if not ZIP.existe():
        return f"manto: no existe {ZIP.ruta}. Ejecuta `greek fetch --source manto`."
    lineas: list[str] = []
    for nombre in (
        "entity_objects_6580.csv",
        "tie_objects_6582.csv",
        "passage_objects_6581.csv",
        "text_objects_7140.csv",
        "author_objects_7139.csv",
        "interaction_objects_6583.csv",
    ):
        ruta = _ruta(nombre)
        if ruta is None:
            lineas.append(f"{nombre}: NO ENCONTRADO")
            continue
        filas = list(_leer(ruta))
        lineas.append(f"{nombre}: {len(filas)} filas")
        if filas:
            lineas.append(f"  columnas: {list(filas[0])}")

    lineas.append("")
    lineas.append("CSV de definicion encontrados (campo -> id):")
    encontrados = sorted(
        (
            stem(p).rsplit("_object_definitions_", 1)
            for p in ZIP.buscar("*_object_definitions_*.csv")
        ),
        key=lambda x: x[0],
    )
    lineas.append("  " + ", ".join(f"{c}={i}" for c, i in encontrados[:40]))
    lineas.append(f"  ... {len(encontrados)} en total")

    faltan = [c for c in (*ROLES, *IDS_ENTIDAD, "subject", "direct_object", "source")
              if _ruta_definicion(c) is None]
    lineas.append("")
    lineas.append(f"campos esperados que faltan: {faltan or 'ninguno'}")
    return "\n".join(lineas)


# -------------------------------------------------------------------- carga


def cargar(con: sqlite3.Connection) -> str:
    if _ruta("entity_objects_6580.csv") is None:
        return (
            f"manto: no encontrado entity_objects_6580.csv en {ZIP.ruta}. "
            "Ejecuta `greek fetch --source manto`."
        )

    fuente_id = registrar_fuente(
        con,
        clave="manto",
        nombre="MANTO (Mapping Ancient Narratives, Territories, Objects)",
        version="publication 2616 / 2026-03-06 (release v.1, 2026-04-10)",
        url="https://zenodo.org/records/19446255",
        licencia="CC BY-NC 4.0",
        doi="10.5281/zenodo.19446255",
        fecha_descarga=_fecha(),
        atribucion_texto=(
            "MANTO (Mapping Ancient Narratives, Territories, Objects), Greta Hawes, "
            "R. Scott Smith et al. CC BY-NC 4.0. https://www.manto-myth.org "
            "DOI: 10.5281/zenodo.19446255"
        ),
        notas=(
            "El registro de Zenodo declara cc-by-nc-4.0 (NO comercial), no la CC-BY 4.0 "
            "que afirma fuentes.md §2.1. Al ser la espina dorsal, la restriccion NC "
            "afecta de hecho a toda la base."
        ),
    )

    n_ent, mapa_ent = _cargar_entidades(con, fuente_id)
    n_ids = _cargar_identificadores(con, mapa_ent)
    n_aut, n_obra, mapa_pas = _cargar_textos(con, fuente_id)
    mapa_art, mapa_ins = _cargar_artefactos(con, fuente_id)
    n_pred, mapa_pred = _cargar_predicados(con)
    n_rel, n_rol, n_fte = _cargar_relaciones(
        con, fuente_id, mapa_ent, mapa_pred, mapa_pas, mapa_art, mapa_ins
    )
    _cargar_equivalencias(con, mapa_ent)
    _cargar_iconografia(con, mapa_ent, mapa_art)
    n_per, mapa_per = _cargar_periodos(con)
    _enlazar_periodos(con, mapa_per, mapa_art, mapa_ins)
    n_ev, _ = _cargar_eventos_miticos(con, fuente_id)
    n_cts = _completar_cts_obras(con)

    # se cuentan FILAS, no intentos de insercion: las relaciones inversas de MANTO
    # estan materializadas en las dos direcciones y el UNIQUE las colapsa
    def filas(tabla: str) -> int:
        return con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]

    return (
        f"manto: {n_ent} entidades ({n_ids} ids externos), {n_aut} autores, "
        f"{n_obra} obras ({n_cts} con CTS URN), {len(mapa_pas)} pasajes, "
        f"{len(mapa_art)} artefactos ({filas('artefacto_representa')} representaciones), "
        f"{len(mapa_ins)} inscripciones, {n_per} periodos, {n_pred} predicados, "
        f"{n_rel} relaciones, {n_rol} roles, {n_fte} atestaciones, "
        f"{filas('entidad_equivalencia')} equivalencias, {n_ev} eventos miticos "
        f"({filas('evento_participante')} participantes)"
    )


def _fecha() -> str:
    from datetime import UTC, datetime

    if _ruta("entity_objects_6580.csv") is None:
        return datetime.now(UTC).date().isoformat()
    # la fecha del ZIP es la de descarga; la de un CSV extraido era la de extraccion
    return datetime.fromtimestamp(ZIP.ruta.stat().st_mtime, UTC).date().isoformat()


def _cargar_entidades(con: sqlite3.Connection, fuente_id: int) -> tuple[int, dict[str, int]]:
    """entity_objects_6580.csv -> entidad. Devuelve {manto_id: entidad_id}."""
    tipos = {clave: id_tipo_entidad(con, clave) for clave in set(EMOJI_TIPO.values())}
    mapa: dict[str, int] = {}
    n = 0

    for fila in _tabla("entity_objects_6580.csv"):
        manto_id = (fila.get("Object ID") or "").strip()
        emoji, nombre, glosa = partir_nombre(fila.get("Name", ""))
        if not manto_id or not nombre:
            continue

        pleiades = _id_externo(fila.get("Pleiades"))
        topostext = _id_externo(fila.get("ToposText"))
        tipo_id = tipos.get(EMOJI_TIPO.get(emoji, ""))

        # Reconciliacion por ID externo, en orden de fiabilidad. Nunca por nombre.
        eid = entidad_por_identificador(con, "manto", manto_id)
        if eid is None and pleiades:
            eid = entidad_por_identificador(con, "pleiades", pleiades)
        if eid is None and topostext:
            eid = entidad_por_identificador(con, "topostext", topostext)

        descripcion = (fila.get("Commentary") or "").strip() or None
        desambiguador = glosa or (fila.get("Information") or "").strip() or None

        if eid is None:
            eid = con.execute(
                "INSERT INTO entidad (nombre, nombre_norm, descripcion, desambiguador, "
                "tipo_entidad_id, fuente_dataset_id) VALUES (?,?,?,?,?,?)",
                (nombre, normalizar(nombre), descripcion, desambiguador, tipo_id, fuente_id),
            ).lastrowid
        else:
            # MANTO decide: pisa nombre y tipo, completa el resto
            con.execute(
                "UPDATE entidad SET nombre = ?, nombre_norm = ?, "
                "tipo_entidad_id = COALESCE(?, tipo_entidad_id), "
                "descripcion = COALESCE(descripcion, ?), "
                "desambiguador = COALESCE(desambiguador, ?) WHERE id = ?",
                (nombre, normalizar(nombre), tipo_id, descripcion, desambiguador, eid),
            )

        mapa[manto_id] = eid
        insert_ignore(
            con,
            "entidad_identificador",
            {
                "entidad_id": eid,
                "namespace": "manto",
                "valor": manto_id,
                "uri": f"https://resource.manto.unh.edu/{manto_id}",
            },
        )
        for namespace, valor, uri in (
            ("pleiades", pleiades, (fila.get("Pleiades") or "").strip() or None),
            ("topostext", topostext, (fila.get("ToposText") or "").strip() or None),
        ):
            if valor:
                insert_ignore(
                    con,
                    "entidad_identificador",
                    {"entidad_id": eid, "namespace": namespace, "valor": valor, "uri": uri},
                )
        n += 1
        if n % 1000 == 0:
            con.commit()

    con.commit()
    return n, mapa


def _cargar_identificadores(con: sqlite3.Connection, mapa_ent: dict[str, int]) -> int:
    """wikidata / trismegistos / digital_limc / limc_headword desde sus CSV."""
    n = 0
    for campo, namespace in IDS_ENTIDAD.items():
        for ruta in ZIP.buscar(f"{campo}_object_definitions_*.csv"):
            columna = _columna_ref(ruta) or campo
            for fila in _leer(ruta):
                eid = mapa_ent.get((fila.get("Object ID") or "").strip())
                if eid is None:
                    continue
                # los CSV de ID no son referencias: el valor va en su propia columna
                bruto = fila.get(columna) or fila.get(campo) or fila.get(campo.title())
                valor = _id_externo(bruto)
                if not valor:
                    continue
                insert_ignore(
                    con,
                    "entidad_identificador",
                    {
                        "entidad_id": eid,
                        "namespace": namespace,
                        "valor": valor,
                        "uri": (bruto or "").strip() if str(bruto).startswith("http") else None,
                    },
                )
                n += 1
    # nombres alternativos: mismo patron, a entidad_nombre
    for ruta in ZIP.buscar("alternative_name*_object_definitions_*.csv"):
        columna = _columna_ref(ruta)
        for fila in _leer(ruta):
            eid = mapa_ent.get((fila.get("Object ID") or "").strip())
            if eid is None:
                continue
            bruto = fila.get(columna) if columna else None
            for clave in ("Alternative Name", "Alternative Names", "alternative_names"):
                bruto = bruto or fila.get(clave)
            _, alterno, _ = partir_nombre(str(bruto or ""))
            if alterno:
                insert_ignore(
                    con,
                    "entidad_nombre",
                    {"entidad_id": eid, "nombre": alterno, "tipo": "alternativo"},
                )
    con.commit()
    return n


def _cargar_textos(
    con: sqlite3.Connection, fuente_id: int
) -> tuple[int, int, dict[str, int]]:
    autores: dict[str, int] = {}
    for fila in _tabla("author_objects_7139.csv"):
        manto_id = (fila.get("Object ID") or "").strip()
        _, nombre, _ = partir_nombre(fila.get("Name", ""))
        if not manto_id or not nombre:
            continue
        aid = upsert(
            con,
            "autor_antiguo",
            {
                "nombre": nombre,
                "manto_id": manto_id,
                "notas": (fila.get("Commentary") or "").strip() or None,
            },
            conflicto=["manto_id"],
        )
        if aid:
            autores[manto_id] = aid
    con.commit()

    obras: dict[str, int] = {}
    for fila in _tabla("text_objects_7140.csv"):
        manto_id = (fila.get("Object ID") or "").strip()
        _, titulo, _ = partir_nombre(fila.get("Name", ""))
        if not manto_id or not titulo:
            continue
        oid = upsert(
            con,
            "obra",
            {
                "autor_id": autores.get((fila.get("Author - Object ID") or "").strip()),
                "titulo": titulo,
                "manto_id": manto_id,
                "fuente_dataset_id": fuente_id,
            },
            conflicto=["manto_id"],
        )
        if oid:
            obras[manto_id] = oid
    con.commit()

    pasajes: dict[str, int] = {}
    for fila in _tabla("passage_objects_6581.csv"):
        manto_id = (fila.get("Object ID") or "").strip()
        obra_id = obras.get((fila.get("Title - Object ID") or "").strip())
        _, cita, _ = partir_nombre(fila.get("Name", ""))
        if not manto_id or obra_id is None or not cita:
            continue
        scaife = (fila.get("Scaife URL") or "").strip() or None
        pid = _pasaje_id(con, manto_id, obra_id, cita, scaife, fuente_id)
        if pid:
            pasajes[manto_id] = pid
    con.commit()
    return len(autores), len(obras), pasajes


def _pasaje_id(
    con: sqlite3.Connection,
    manto_id: str,
    obra_id: int,
    cita: str,
    scaife: str | None,
    fuente_id: int,
) -> int | None:
    """Localiza o crea el pasaje. Dos claves UNIQUE, no una.

    `pasaje` tiene UNIQUE(manto_id) y UNIQUE(obra_id, cita), y MANTO trae varios
    Passage distintos con la misma cita en la misma obra. Un solo ON CONFLICT no
    cubre las dos claves, asi que se busca por ambas y los manto_id duplicados
    acaban apuntando al mismo pasaje.
    """
    fila = con.execute("SELECT id FROM pasaje WHERE manto_id = ?", (manto_id,)).fetchone()
    if fila:
        return fila["id"]

    fila = con.execute(
        "SELECT id, manto_id FROM pasaje WHERE obra_id = ? AND cita = ?", (obra_id, cita)
    ).fetchone()
    if fila:
        if fila["manto_id"] is None:
            con.execute("UPDATE pasaje SET manto_id = ? WHERE id = ?", (manto_id, fila["id"]))
        return fila["id"]

    return con.execute(
        "INSERT INTO pasaje (obra_id, cita, cts_urn, scaife_url, manto_id, fuente_dataset_id) "
        "VALUES (?,?,?,?,?,?)",
        # el CTS URN canonico esta dentro de la Scaife URL
        (obra_id, cita, _cts(scaife), scaife, manto_id, fuente_id),
    ).lastrowid


def _cts(scaife_url: str | None) -> str | None:
    """.../reader/urn:cts:greekLit:tlg0548.tlg002.perseus-eng2:1.3 -> el URN."""
    if not scaife_url or "urn:cts:" not in scaife_url:
        return None
    return "urn:cts:" + scaife_url.split("urn:cts:", 1)[1].split("?")[0].strip()


def _cargar_predicados(con: sqlite3.Connection) -> tuple[int, dict[str, int]]:
    mapa: dict[str, int] = {}
    for fila in _tabla("interaction_objects_6583.csv"):
        manto_id = (fila.get("Object ID") or "").strip()
        _, nombre, _ = partir_nombre(fila.get("Name", ""))
        if not manto_id or not nombre:
            continue
        clave = nombre.lower().replace(" ", "_")
        pid = upsert(
            con,
            "predicado",
            {
                "clave": clave,
                "nombre_es": nombre,  # traduccion al castellano: pendiente, manual
                "categoria": _categoria(nombre),
                "manto_id": manto_id,
            },
            conflicto=["clave"],
            actualizar=["categoria", "manto_id"],
        )
        if pid:
            mapa[manto_id] = pid
    con.commit()
    return len(mapa), mapa


def _refs_etiquetadas(campo: str) -> dict[str, list[tuple[str | None, str, str]]]:
    """{objeto_id: [(tipo, id_referenciado, etiqueta)]} de un CSV de definicion.

    Nodegoat exporta las referencias de DOS formas y hay que soportar las dos:

    1. Directa: la columna '{Campo} - Object ID' trae el id (opcionalmente con
       prefijo de tipo, '6581_11291596').
    2. Por camino: esa columna trae un id intermedio inservible y el objetivo real
       va incrustado en la etiqueta, 'start-path [object=6580_11297468]👤 Osiris'.
       Lo usan 105 campos, entre ellos `identified_with`, `kills` y `mother_of`
       (las relaciones inversas materializadas sobre Entity). Leer solo la forma
       directa dejaba `identified_with` en 461 de 2.800 filas resueltas.
    """
    ruta = _ruta_definicion(campo)
    if ruta is None:
        return {}
    columna = _columna_ref(ruta)
    out: dict[str, list[tuple[str | None, str, str]]] = {}
    for fila in _leer(ruta):
        oid = (fila.get("Object ID") or "").strip()
        if not oid:
            continue
        etiqueta = (fila.get(columna) or "").strip()
        caminos = _PATH_OBJ.findall(etiqueta)
        if caminos:
            objetivos = [(tipo, ident, etiqueta) for tipo, ident in caminos]
        else:
            directo = _valor_ref(fila, columna)
            if not directo:
                continue
            tipo, ident = _partir_ref(directo)
            objetivos = [(tipo, ident, etiqueta)]
        out.setdefault(oid, []).extend(objetivos)
    return out


def _referencias_etiquetadas(campo: str) -> dict[str, list[tuple[str, str]]]:
    """{objeto_id: [(ref_con_tipo, etiqueta)]}, como la esperan las fuentes."""
    return {
        oid: [(f"{tipo}_{ident}" if tipo else ident, etiqueta) for tipo, ident, etiqueta in refs]
        for oid, refs in _refs_etiquetadas(campo).items()
    }


def _referencias_planas(campo: str) -> dict[str, list[str]]:
    """Solo los ids que apuntan a Entity (type_id 6580) o sin tipo declarado."""
    return {
        oid: [ident for tipo, ident, _ in refs if tipo in (None, "6580")]
        for oid, refs in _refs_etiquetadas(campo).items()
    }


def _cargar_artefactos(
    con: sqlite3.Connection, fuente_id: int
) -> tuple[dict[str, int], dict[str, int]]:
    """artifact + inscription: las relaciones que no citan texto citan estos."""
    artefactos: dict[str, int] = {}
    for fila in _tabla("artifact_objects_11352.csv"):
        manto_id = (fila.get("Object ID") or "").strip()
        _, nombre, _ = partir_nombre(fila.get("Name", ""))
        if not manto_id or not nombre:
            continue
        aid = upsert(
            con,
            "artefacto",
            {
                "nombre": nombre,
                "coleccion": (fila.get("Collection") or "").strip() or None,
                "bapd_url": (fila.get("PALP (Space)") or "").strip() or None,
                "manto_id": manto_id,
                "fuente_dataset_id": fuente_id,
            },
            conflicto=["manto_id"],
        )
        if aid:
            artefactos[manto_id] = aid
    con.commit()

    inscripciones: dict[str, int] = {}
    for fila in _tabla("inscription_objects_11376.csv"):
        manto_id = (fila.get("Object ID") or "").strip()
        _, nombre, _ = partir_nombre(fila.get("Name", ""))
        if not manto_id or not nombre:
            continue
        iid = upsert(
            con,
            "inscripcion",
            {
                "nombre": nombre,
                "manto_id": manto_id,
                "fuente_dataset_id": fuente_id,
            },
            conflicto=["manto_id"],
        )
        if iid:
            inscripciones[manto_id] = iid
    con.commit()
    return artefactos, inscripciones


def _cargar_relaciones(
    con: sqlite3.Connection,
    fuente_id: int,
    mapa_ent: dict[str, int],
    mapa_pred: dict[str, int],
    mapa_pas: dict[str, int],
    mapa_art: dict[str, int],
    mapa_ins: dict[str, int],
) -> tuple[int, int, int]:
    sujetos = _referencias_planas("subject")
    objetos = _referencias_planas("direct_object")
    # con prefijo de tipo + etiqueta legible: la etiqueta permite reconstruir los
    # pasajes que el export de MANTO cita pero no incluye en su tabla Passage
    fuentes = _referencias_etiquetadas("source")
    roles_ref = {campo: _referencias_planas(campo) for campo in ROLES}
    obras_por_titulo = {
        f["titulo"].lower(): f["id"] for f in con.execute("SELECT id, titulo FROM obra")
    }
    n_reconstruidos = 0

    n_rel = n_rol = n_fte = 0
    for fila in _tabla("tie_objects_6582.csv"):
        tie_id = (fila.get("Object ID") or "").strip()
        pred_id = mapa_pred.get((fila.get("Predicate - Object ID") or "").strip())
        if not tie_id or pred_id is None:
            continue

        sujeto_ids = [mapa_ent[s] for s in sujetos.get(tie_id, []) if s in mapa_ent]
        if not sujeto_ids:
            continue
        objeto_ids = [mapa_ent[o] for o in objetos.get(tie_id, []) if o in mapa_ent]

        rid = upsert(
            con,
            "relacion",
            {
                "sujeto_id": sujeto_ids[0],
                "predicado_id": pred_id,
                "objeto_id": objeto_ids[0] if objeto_ids else None,
                "timemark_when": (fila.get("Timemark: when") or "").strip() or None,
                "dato_incierto": _flag(fila.get("Data uncertain")),
                "duda_expresada": _flag(fila.get("Doubt or disbelief expressed")),
                "alternativas_dadas": _flag(fila.get("Alternatives given")),
                "dato_implicito": _flag(fila.get("Data implicit")),
                "comentario": (fila.get("Commentary") or "").strip() or None,
                "manto_id": tie_id,
                "fuente_dataset_id": fuente_id,
            },
            conflicto=["manto_id"],
        )
        if rid is None:
            continue
        n_rel += 1

        # sujetos y objetos adicionales van como roles, no se pierden
        for extra in sujeto_ids[1:]:
            insert_ignore(
                con, "relacion_rol", {"relacion_id": rid, "rol": "de", "entidad_id": extra}
            )
            n_rol += 1
        for extra in objeto_ids[1:]:
            insert_ignore(
                con,
                "relacion_rol",
                {"relacion_id": rid, "rol": "objeto_indirecto", "entidad_id": extra},
            )
            n_rol += 1

        for campo, rol in ROLES.items():
            for ref in roles_ref.get(campo, {}).get(tie_id, []):
                objetivo = mapa_ent.get(ref)
                if objetivo is None:
                    continue
                insert_ignore(
                    con, "relacion_rol", {"relacion_id": rid, "rol": rol, "entidad_id": objetivo}
                )
                n_rol += 1

        # Una atestacion puede ser un pasaje, un artefacto o una inscripcion. El
        # prefijo de tipo de la referencia decide la columna; ignorar los dos
        # ultimos dejaba ~6.700 relaciones sin fuente pese a estar atestiguadas.
        for ref, etiqueta in fuentes.get(tie_id, []):
            tipo, valor = _partir_ref(ref)
            destino = {
                "6581": ("pasaje_id", mapa_pas),
                "11352": ("artefacto_id", mapa_art),
                "11376": ("inscripcion_id", mapa_ins),
                # 11379 = papyrus: 18 referencias y relacion_fuente no tiene columna
                # para papiros. Se omiten a proposito; documentado en el resumen.
            }.get(tipo or "6581")
            if destino is None:
                continue
            columna, mapa = destino
            objetivo = mapa.get(valor)
            if objetivo is None and columna == "pasaje_id" and etiqueta:
                objetivo = _pasaje_reconstruido(
                    con, valor, etiqueta, obras_por_titulo, fuente_id
                )
                if objetivo is not None:
                    mapa[valor] = objetivo
                    n_reconstruidos += 1
            if objetivo is None:
                continue
            insert_ignore(con, "relacion_fuente", {"relacion_id": rid, columna: objetivo})
            n_fte += 1

        if n_rel % 2000 == 0:
            con.commit()

    con.commit()
    if n_reconstruidos:
        print(
            f"  [manto] {n_reconstruidos} pasajes reconstruidos desde la etiqueta de la "
            f"cita: el export referencia Passage que su propia tabla no incluye"
        )
    return n_rel, n_rol, n_fte


# campo del dump -> tipo de entidad_equivalencia
EQUIVALENCIAS = {
    "is_the_same_as": "es_el_mismo",
    "alternative_name_for": "es_el_mismo",
    "possibly_the_same_as": "posiblemente_el_mismo",
    "sometimes_conflated_with": "a_veces_confundido",
    "identified_with": "identificado_con",
    "identified_with_the_author": "identificado_con",
    "identified_with_the_mythical_figure": "identificado_con",
    "rationalized_form": "forma_racionalizada",
    "rationalized_form_of": "forma_racionalizada",
    "personification_of": "personificacion_de",
}


_RANGO_PERIODO = re.compile(
    r"(\d+)\s*(BCE|CE)?\s*[-–]\s*(\d+)\s*(BCE|CE)", re.IGNORECASE
)


def _cargar_periodos(con: sqlite3.Connection) -> tuple[int, dict[str, int]]:
    """time_period_11356.json -> periodo. El rango va dentro del nombre.

    'Late Classical (ca. 400-330 BCE)' -> -400/-330; 'Early Imperial (ca. 31 BCE-79
    CE)' -> -31/79. Son los periodos historicos con que MANTO fecha artefactos e
    inscripciones; no sustituyen a la cronologia heladica de 003_seed.sql.
    """
    ruta = _ruta("time_period_11356.json")
    if ruta is None:
        return 0, {}
    import json

    with ZIP.abrir(ruta, encoding="utf-8") as fh:
        datos = json.load(fh)
    mapa: dict[str, int] = {}
    for manto_id, obj in datos.items():
        nombre = ((obj or {}).get("object") or {}).get("object_name") or ""
        nombre = nombre.strip()
        if not nombre:
            continue
        m = _RANGO_PERIODO.search(nombre)
        inicio = fin = None
        if m:
            era_inicio = (m.group(2) or m.group(4)).upper()
            inicio = -int(m.group(1)) if era_inicio == "BCE" else int(m.group(1))
            fin = -int(m.group(3)) if m.group(4).upper() == "BCE" else int(m.group(3))
        clave = re.sub(r"[^a-z0-9]+", "_", nombre.split("(")[0].strip().lower()).strip("_")
        pid = upsert(
            con,
            "periodo",
            {
                "clave": clave or f"manto_{manto_id}",
                "nombre": nombre,
                "anio_inicio_ac": inicio,
                "anio_fin_ac": fin,
                "manto_id": manto_id,
            },
            conflicto=["clave"],
            actualizar=["manto_id"],
        )
        if pid:
            mapa[manto_id] = pid
    con.commit()
    return len(mapa), mapa


def _enlazar_periodos(
    con: sqlite3.Connection,
    mapa_per: dict[str, int],
    mapa_art: dict[str, int],
    mapa_ins: dict[str, int],
) -> int:
    """artefacto/inscripcion/relacion -> periodo, segun quien sea el dueno de la fila."""
    n = 0
    for campo in ("period", "timemark_period"):
        for oid, refs in _refs_etiquetadas(campo).items():
            periodo_id = next(
                (mapa_per[i] for _t, i, _e in refs if i in mapa_per), None
            )
            if periodo_id is None:
                continue
            for tabla, mapa in (
                ("artefacto", mapa_art),
                ("inscripcion", mapa_ins),
                ("relacion", None),
            ):
                if mapa is not None:
                    destino = mapa.get(oid)
                    if destino is None:
                        continue
                    con.execute(
                        f"UPDATE {tabla} SET periodo_id = COALESCE(periodo_id, ?) WHERE id = ?",
                        (periodo_id, destino),
                    )
                else:
                    con.execute(
                        "UPDATE relacion SET periodo_id = COALESCE(periodo_id, ?) "
                        "WHERE manto_id = ?",
                        (periodo_id, oid),
                    )
                n += 1
                break
    con.commit()
    return n


def _cargar_equivalencias(con: sqlite3.Connection, mapa_ent: dict[str, int]) -> int:
    """Identidades disputadas: 'posiblemente el mismo que', 'a veces confundido con'.

    Es la tabla que evita fusionar lo que las fuentes antiguas ya discuten: MANTO
    distingue 'is the same as' (7 casos) de 'sometimes conflated with' (1.218) y de
    'identified with' (4.467, sobre todo sincretismos griego-romano-egipcio).
    """
    n = 0
    for campo, tipo in EQUIVALENCIAS.items():
        for oid, refs in _referencias_planas(campo).items():
            a = mapa_ent.get(oid)
            if a is None:
                continue
            for ref in refs:
                b = mapa_ent.get(ref)
                if b is None or b == a:
                    continue
                insert_ignore(
                    con,
                    "entidad_equivalencia",
                    {
                        "entidad_a_id": min(a, b),
                        "entidad_b_id": max(a, b),
                        "tipo": tipo,
                        "nota": f"MANTO: {campo.replace('_', ' ')}",
                    },
                )
                n += 1
    con.commit()
    return n


def _cargar_iconografia(
    con: sqlite3.Connection, mapa_ent: dict[str, int], mapa_art: dict[str, int]
) -> tuple[int, int]:
    """artefacto_representa + lugar de creacion/hallazgo del artefacto.

    Los CSV de 'depictions' existen en las dos direcciones (entidad->artefacto y
    artefacto->entidad), asi que cada lado se resuelve probando ambos mapas.
    """
    n_repr = 0
    for campo, reportada in (
        ("depictions", 0),
        ("has_depictions_of", 0),
        ("reported_depictions", 1),
        ("reported_to_have_depictions_of", 1),
    ):
        for oid, refs in _referencias_planas(campo).items():
            for ref in refs:
                artefacto_id = mapa_art.get(oid) or mapa_art.get(ref)
                entidad_id = mapa_ent.get(ref) or mapa_ent.get(oid)
                if artefacto_id is None or entidad_id is None:
                    continue
                insert_ignore(
                    con,
                    "artefacto_representa",
                    {
                        "artefacto_id": artefacto_id,
                        "entidad_id": entidad_id,
                        "es_reportada": reportada,
                    },
                )
                n_repr += 1

    n_lug = 0
    for campo, columna in (
        ("place_of_creation", "lugar_creacion_id"),
        ("place_of_recovery", "lugar_hallazgo_id"),
    ):
        for oid, refs in _referencias_planas(campo).items():
            artefacto_id = mapa_art.get(oid)
            if artefacto_id is None:
                continue
            for ref in refs:
                lugar_id = mapa_ent.get(ref)
                if lugar_id is None:
                    continue
                con.execute(
                    f"UPDATE artefacto SET {columna} = COALESCE({columna}, ?) WHERE id = ?",
                    (lugar_id, artefacto_id),
                )
                n_lug += 1
                break
    con.commit()
    return n_repr, n_lug


# nombre del evento -> tipo de evento del esquema
_TIPO_EVENTO_MITICO = (
    ("funeral games", "juegos"),
    ("games", "juegos"),
    ("wedding", "boda"),
    ("flood", "cataclismo"),
    ("search", "viaje"),
    ("war", "guerra"),
)


def _cargar_eventos_miticos(con: sqlite3.Connection, fuente_id: int) -> tuple[int, int]:
    """Las entidades ⏳ Mythic Event de MANTO -> evento, con sus participantes.

    MANTO no tiene tabla Evento (fuentes.md §2.1), pero SI tiene 13 entidades de
    tipo Mythic Event, y las relaciones las referencian por rol: 'X lucha con Y
    [en] la Boda de Peirithous'. Ese rol es el puente que puebla relacion.evento_id,
    evento_participante y evento_fuente, que si no quedan vacias.
    """
    entidades = con.execute(
        "SELECT e.id, e.nombre, e.desambiguador FROM entidad e "
        "JOIN tipo_entidad t ON t.id = e.tipo_entidad_id WHERE t.clave = 'evento_mitico'"
    ).fetchall()

    n_eventos = n_part = 0
    for ent in entidades:
        nombre = ent["nombre"]
        minus = nombre.lower()
        tipo = next((t for clave, t in _TIPO_EVENTO_MITICO if clave in minus), "otro")

        evento_id = upsert(
            con,
            "evento",
            {
                "nombre": nombre,
                "tipo": tipo,
                "descripcion": ent["desambiguador"],
                "lugar_id": _lugar_del_nombre(con, nombre),
                "fuente_dataset_id": fuente_id,
            },
            conflicto=["nombre", "tipo"],
            actualizar=["descripcion", "lugar_id"],
        )
        if evento_id is None:
            continue
        n_eventos += 1

        # relaciones que ocurren "en" este evento
        relaciones = con.execute(
            "SELECT DISTINCT rr.relacion_id FROM relacion_rol rr WHERE rr.entidad_id = ?",
            (ent["id"],),
        ).fetchall()
        for r in relaciones:
            con.execute(
                "UPDATE relacion SET evento_id = COALESCE(evento_id, ?) WHERE id = ?",
                (evento_id, r["relacion_id"]),
            )
            n_part += _participantes(con, evento_id, r["relacion_id"])

    con.commit()
    return n_eventos, n_part


def _participantes(con: sqlite3.Connection, evento_id: int, relacion_id: int) -> int:
    """Sujeto y objeto de la relacion -> evento_participante, con rol segun predicado."""
    fila = con.execute(
        "SELECT r.sujeto_id, r.objeto_id, p.categoria FROM relacion r "
        "JOIN predicado p ON p.id = r.predicado_id WHERE r.id = ?",
        (relacion_id,),
    ).fetchone()
    if fila is None:
        return 0

    roles = {
        "muerte": ("matador", "victima"),
        "belica": ("combatiente", "combatiente"),
        "competicion": ("competidor", "competidor"),
    }.get(fila["categoria"], ("participante", "participante"))

    n = 0
    for entidad_id, rol in ((fila["sujeto_id"], roles[0]), (fila["objeto_id"], roles[1])):
        if entidad_id is None:
            continue
        insert_ignore(
            con,
            "evento_participante",
            {"evento_id": evento_id, "entidad_id": entidad_id, "rol": rol},
        )
        n += 1

    # el pasaje que atestigua la relacion atestigua tambien el evento
    for f in con.execute(
        "SELECT pasaje_id FROM relacion_fuente WHERE relacion_id = ? AND pasaje_id IS NOT NULL",
        (relacion_id,),
    ):
        insert_ignore(
            con, "evento_fuente", {"evento_id": evento_id, "pasaje_id": f["pasaje_id"]}
        )
    return n


def _lugar_del_nombre(con: sqlite3.Connection, nombre: str) -> int | None:
    """'the Funeral Games of Pelias (Iolcos)' -> entidad lugar 'Iolcos'.

    El parentesis de los nombres de MANTO trae el lugar. Solo se aplica a 13 filas
    y se exige que la entidad encontrada sea de tipo lugar, asi que es verificable
    a ojo; no es un fuzzy join encubierto.
    """
    m = re.search(r"\(([^)]+)\)\s*$", nombre)
    if not m:
        return None
    fila = con.execute(
        "SELECT e.id FROM entidad e JOIN tipo_entidad t ON t.id = e.tipo_entidad_id "
        "WHERE t.es_lugar = 1 AND e.nombre = ? "
        "ORDER BY (SELECT COUNT(*) FROM relacion r WHERE r.sujeto_id = e.id) DESC LIMIT 1",
        (m.group(1).strip(),),
    ).fetchone()
    return fila["id"] if fila else None


def _completar_cts_obras(con: sqlite3.Connection) -> int:
    """obra.cts_urn a partir del CTS de sus pasajes (quitando el sufijo de pasaje).

    'urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.1' -> la obra es
    'urn:cts:greekLit:tlg0012.tlg001.perseus-grc2'.
    """
    filas = con.execute(
        "SELECT obra_id, cts_urn FROM pasaje WHERE cts_urn IS NOT NULL "
        "GROUP BY obra_id HAVING COUNT(*) > 0"
    ).fetchall()
    n = 0
    for f in filas:
        urn = f["cts_urn"].rsplit(":", 1)[0] if f["cts_urn"].count(":") > 3 else f["cts_urn"]
        try:
            con.execute(
                "UPDATE obra SET cts_urn = ? WHERE id = ? AND cts_urn IS NULL",
                (urn, f["obra_id"]),
            )
            n += 1
        except sqlite3.IntegrityError:
            # dos obras comparten URN de obra (ediciones distintas del mismo texto)
            continue
    con.commit()
    return n


def _pasaje_reconstruido(
    con: sqlite3.Connection,
    manto_id: str,
    etiqueta: str,
    obras_por_titulo: dict[str, int],
    fuente_id: int,
) -> int | None:
    """Crea el pasaje a partir de su etiqueta ('📖 Strabo 9.2.27').

    El export de MANTO cita 4.234 Passage que no estan en passage_objects_6581.csv
    (p. ej. 'Strabo 9.2.27'): ni por id ni por etiqueta. Descartarlos dejaba el 13,6 %
    de las relaciones sin atestacion pese a estar citadas en la fuente. La etiqueta
    trae obra + cita, que es exactamente lo que necesita `pasaje`.
    """
    _, texto, _ = partir_nombre(etiqueta)
    if not texto:
        return None

    # el titulo de la obra es el prefijo mas largo que ya conocemos
    titulo_id = None
    resto = texto
    for titulo in sorted(obras_por_titulo, key=len, reverse=True):
        if texto.lower().startswith(titulo):
            titulo_id = obras_por_titulo[titulo]
            resto = texto[len(titulo) :].strip(" ,.")
            break

    if titulo_id is None:
        # sin obra conocida: el prefijo no numerico hace de titulo
        corte = re.search(r"\s\d", texto)
        titulo = (texto[: corte.start()] if corte else texto).strip(" ,.")
        resto = texto[corte.start() :].strip(" ,.") if corte else ""
        if not titulo:
            return None
        # obra.titulo no es UNIQUE (lo son cts_urn y manto_id), asi que no hay
        # ON CONFLICT posible: busqueda explicita y despues INSERT.
        fila = con.execute("SELECT id FROM obra WHERE titulo = ?", (titulo,)).fetchone()
        titulo_id = (
            fila["id"]
            if fila
            else con.execute(
                "INSERT INTO obra (titulo, fuente_dataset_id) VALUES (?,?)",
                (titulo, fuente_id),
            ).lastrowid
        )
        if titulo_id is None:
            return None
        obras_por_titulo[titulo.lower()] = titulo_id

    return _pasaje_id(con, manto_id, titulo_id, resto or texto, None, fuente_id)
