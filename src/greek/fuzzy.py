"""Fuzzy join de entidades + normalizacion a un solo nombre canonico.

Contradice deliberadamente fuentes.md §1.1, que pedia cola de revision manual en
vez de fusion automatica. Decision del usuario. La contrapartida obligatoria es
que TODA fusion sea auditable y reversible: por eso `fuzzy_fusion.absorbida_json`
guarda la fila completa y la lista de filas reapuntadas, y `deshacer()` la
restaura sin recargar la base.

Bandas (fuzz.ratio sobre entidad.nombre_norm, mismo tipo_entidad obligatorio):

    >= 97   fusion automatica
    88-96   fusion solo si hay corroboracion (vecino genealogico o lugar comun)
    80-87   no fusiona: entidad_revision + homonimo_grupo comun
    < 80    entidades distintas

Dos vetos absolutos, ambos previos al score:

1. Mismo namespace externo con valores distintos (dos QIDs, dos manto_id, dos
   pleiades). Como entidad_identificador tiene UNIQUE(namespace, valor), compartir
   namespace ya implica valores distintos, asi que el par se descarta sin puntuar.
2. Designador distinto ('Tower 7' / 'Tower 11', 'Basilica A' / 'Basilica D').

Un ID externo que discrepa es evidencia mas fuerte que cualquier score.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime

from rapidfuzz import fuzz, process

from . import normalize
from .db import insert_ignore

# 97, no 95: sobre datos reales el tramo 95-96 mezclaba variantes que solo
# coinciden "casi" — 'Nymphs Sanctuary' con 'Nymphe Sanctuary', 'Ellinikou tower'
# con 'Elliniko tower'. Ahora esas caen en la banda que exige corroboracion, y en
# 'auto' solo queda lo practicamente identico (los duplicados reales puntuan 100).
UMBRAL_AUTO = 97.0
UMBRAL_CORROBORADA = 88.0
UMBRAL_REVISION = 80.0

# fuzz.ratio, NO fuzz.WRatio. WRatio aplica un boost de coincidencia parcial
# cuando las cadenas difieren mucho en longitud, y sobre nombres cortos eso
# produce falsos positivos con score de fusion automatica: en la primera pasada
# real fusiono 'Tower 7' con 'tower (Arkoi)' a 95.0. `ratio` es Levenshtein puro
# sobre la forma normalizada completa, sin premiar subcadenas.
SCORER = fuzz.ratio
ALGORITMO = "rapidfuzz.ratio"

# Namespaces cuya discrepancia veta la fusion. 'geonames' queda fuera a
# proposito: Pleiades+ es alineacion automatica y sus valores no son autoridad.
NAMESPACES_VETO = ("manto", "wikidata", "pleiades", "digital_limc")

# Prioridad para elegir el nombre canonico. (columna_entidad, etiqueta)
PRIORIDAD_CANONICO = (
    ("nombre_es", "wikidata:nombre_es"),
    ("nombre_latino", "manto:latino"),
    ("nombre", "nombre de trabajo"),
)

# Tablas que apuntan a entidad(id) y hay que reapuntar al fusionar.
# (tabla, columna). El orden importa poco; el reapuntado usa UPDATE OR IGNORE.
REFERENCIAS: tuple[tuple[str, str], ...] = (
    ("entidad_nombre", "entidad_id"),
    ("entidad_identificador", "entidad_id"),
    ("entidad_equivalencia", "entidad_a_id"),
    ("entidad_equivalencia", "entidad_b_id"),
    ("relacion", "sujeto_id"),
    ("relacion", "objeto_id"),
    ("relacion_rol", "entidad_id"),
    ("evento", "lugar_id"),
    ("evento_participante", "entidad_id"),
    ("lugar_detalle", "entidad_id"),
    ("lugar_jerarquia", "hijo_id"),
    ("lugar_jerarquia", "padre_id"),
    ("lugar_localizacion", "entidad_id"),
    ("artefacto", "lugar_creacion_id"),
    ("artefacto", "lugar_hallazgo_id"),
    ("artefacto_representa", "entidad_id"),
    ("inscripcion", "lugar_hallazgo_id"),
    ("fuzzy_fusion", "superviviente_id"),
)


@dataclass
class Candidato:
    a_id: int
    b_id: int
    score: float
    banda: str  # 'auto' | 'corroborada' | 'revision' | 'vetada'
    evidencia: str | None = None
    nombre_a: str = ""
    nombre_b: str = ""


@dataclass
class Informe:
    fusiones: list[Candidato] = field(default_factory=list)
    revisiones: list[Candidato] = field(default_factory=list)
    vetadas: list[Candidato] = field(default_factory=list)  # muestra, no el total
    n_vetadas: int = 0

    def resumen(self) -> str:
        truncado = "" if self.n_vetadas == len(self.vetadas) else f" (muestra {len(self.vetadas)})"
        return (
            f"fusiones={len(self.fusiones)} "
            f"(auto={sum(1 for c in self.fusiones if c.banda == 'auto')}, "
            f"corroboradas={sum(1 for c in self.fusiones if c.banda == 'corroborada')})  "
            f"revision={len(self.revisiones)}  vetadas={self.n_vetadas}{truncado}"
        )


# ------------------------------------------------------- normalizacion previa


def poblar_nombre_norm(con: sqlite3.Connection) -> int:
    """Rellena entidad.nombre_norm. Idempotente; hay que llamarlo antes de buscar."""
    filas = con.execute("SELECT id, nombre FROM entidad").fetchall()
    datos = [(normalize.normalizar(f["nombre"]), f["id"]) for f in filas]
    con.executemany("UPDATE entidad SET nombre_norm = ? WHERE id = ?", datos)
    con.commit()
    return len(datos)


# ------------------------------------------------------------ generacion de pares


def _bloques(con: sqlite3.Connection) -> dict[tuple[int | None, str], list[sqlite3.Row]]:
    """Agrupa entidades por (tipo_entidad, bloque de nombre) para no comparar todo con todo."""
    grupos: dict[tuple[int | None, str], list[sqlite3.Row]] = {}
    filas = con.execute(
        "SELECT id, nombre, nombre_norm, tipo_entidad_id, revisado_manual "
        "FROM entidad WHERE nombre_norm IS NOT NULL AND nombre_norm <> ''"
    ).fetchall()
    for f in filas:
        for b in normalize.variantes_bloque(f["nombre_norm"]):
            grupos.setdefault((f["tipo_entidad_id"], b), []).append(f)
    return grupos


def _ids_externos(con: sqlite3.Connection, entidad_id: int) -> dict[str, set[str]]:
    filas = con.execute(
        "SELECT namespace, valor FROM entidad_identificador WHERE entidad_id = ?",
        (entidad_id,),
    ).fetchall()
    out: dict[str, set[str]] = {}
    for f in filas:
        out.setdefault(f["namespace"], set()).add(f["valor"])
    return out


def indice_ids(con: sqlite3.Connection) -> dict[int, dict[str, set[str]]]:
    """Todos los IDs externos en memoria, de una consulta.

    Consultarlos por par costaba dos SELECT por candidato: con millones de pares
    eso era el 90% del tiempo de ejecucion.
    """
    indice: dict[int, dict[str, set[str]]] = {}
    for f in con.execute(
        "SELECT entidad_id, namespace, valor FROM entidad_identificador "
        f"WHERE namespace IN ({','.join('?' * len(NAMESPACES_VETO))})",
        NAMESPACES_VETO,
    ):
        indice.setdefault(f["entidad_id"], {}).setdefault(f["namespace"], set()).add(f["valor"])
    return indice


def hay_veto(
    con: sqlite3.Connection,
    a_id: int,
    b_id: int,
    indice: dict[int, dict[str, set[str]]] | None = None,
) -> str | None:
    """Devuelve el motivo del veto, o None si se puede fusionar."""
    if indice is not None:
        ids_a = indice.get(a_id, {})
        ids_b = indice.get(b_id, {})
    else:
        ids_a = _ids_externos(con, a_id)
        ids_b = _ids_externos(con, b_id)
    for ns in NAMESPACES_VETO:
        va, vb = ids_a.get(ns), ids_b.get(ns)
        if va and vb and not (va & vb):
            return f"{ns} discrepante: {sorted(va)} vs {sorted(vb)}"
    return None


def _vecinos_genealogicos(con: sqlite3.Connection, entidad_id: int) -> set[int]:
    filas = con.execute(
        """
        SELECT CASE WHEN r.sujeto_id = ? THEN r.objeto_id ELSE r.sujeto_id END AS vecino
          FROM relacion r JOIN predicado p ON p.id = r.predicado_id
         WHERE p.categoria IN ('genealogica','conyugal')
           AND (r.sujeto_id = ? OR r.objeto_id = ?)
        """,
        (entidad_id, entidad_id, entidad_id),
    ).fetchall()
    return {f["vecino"] for f in filas if f["vecino"] is not None}


def _lugares_asociados(con: sqlite3.Connection, entidad_id: int) -> set[int]:
    filas = con.execute(
        """
        SELECT rr.entidad_id AS lugar
          FROM relacion r
          JOIN relacion_rol rr ON rr.relacion_id = r.id
         WHERE rr.rol IN ('en','cerca_de','desde','hacia')
           AND (r.sujeto_id = ? OR r.objeto_id = ?)
        """,
        (entidad_id, entidad_id),
    ).fetchall()
    return {f["lugar"] for f in filas}


def corroboracion(con: sqlite3.Connection, a_id: int, b_id: int) -> str | None:
    """Evidencia extra para la banda 88-94. None = sin corroborar."""
    vecinos = _vecinos_genealogicos(con, a_id) & _vecinos_genealogicos(con, b_id)
    if vecinos:
        nombres = _nombres(con, sorted(vecinos)[:3])
        return f"vecino genealogico comun: {', '.join(nombres)}"

    lugares = _lugares_asociados(con, a_id) & _lugares_asociados(con, b_id)
    if lugares:
        nombres = _nombres(con, sorted(lugares)[:3])
        return f"lugar asociado comun: {', '.join(nombres)}"

    # mismo namespace externo con el MISMO valor: evidencia fuerte
    ids_a, ids_b = _ids_externos(con, a_id), _ids_externos(con, b_id)
    for ns in ids_a.keys() & ids_b.keys():
        if ids_a[ns] & ids_b[ns]:
            return f"{ns} coincidente: {sorted(ids_a[ns] & ids_b[ns])[0]}"

    return None


def _nombres(con: sqlite3.Connection, ids: list[int]) -> list[str]:
    if not ids:
        return []
    marcas = ",".join("?" * len(ids))
    filas = con.execute(f"SELECT nombre FROM entidad WHERE id IN ({marcas})", ids).fetchall()
    return [f["nombre"] for f in filas]


def _veto_numeracion(nombre_a: str, nombre_b: str) -> str | None:
    """Veto por numeracion distinta.

    Los numeros no admiten aproximacion: 'Tower 7' / 'Tower 11', 'Germania I' /
    'Germania II', 'Kastri 1' / 'Kastri 2' son entidades distintas aunque el
    resto de la cadena sea identico.
    """
    na, nb = normalize.numeros(nombre_a), normalize.numeros(nombre_b)
    if na != nb:
        return f"designador distinto: {na or '(ninguno)'} vs {nb or '(ninguno)'}"
    return None


def _firma_veto(indice: dict[int, dict[str, set[str]]], entidad_id: int) -> frozenset[str]:
    """Namespaces de veto que tiene esta entidad."""
    return frozenset(indice.get(entidad_id, {}))


def _pares_puntuables(
    filas: list[sqlite3.Row], indice: dict[int, dict[str, set[str]]]
) -> tuple[list[tuple[int, int]], int]:
    """(pares que hay que puntuar, numero de pares vetados sin puntuar).

    Un par se descarta sin calcular score si ambas entidades comparten algun
    namespace de veto: por UNIQUE(namespace, valor) sus valores son distintos, o
    seria la misma fila.
    """
    firmas = [_firma_veto(indice, f["id"]) for f in filas]
    puntuables: list[tuple[int, int]] = []
    omitidos = 0
    for i in range(len(filas)):
        for j in range(i + 1, len(filas)):
            if firmas[i] & firmas[j]:
                omitidos += 1
            else:
                puntuables.append((i, j))
    return puntuables, omitidos


def _muestra_vetadas(
    filas: list[sqlite3.Row], indice: dict[int, dict[str, set[str]]], tope: int
) -> list[Candidato]:
    """Unas pocas vetadas para el informe. Sin score: no se puntuaron a proposito."""
    muestra: list[Candidato] = []
    firmas = [_firma_veto(indice, f["id"]) for f in filas]
    for i in range(len(filas)):
        for j in range(i + 1, len(filas)):
            compartidos = firmas[i] & firmas[j]
            if not compartidos:
                continue
            ns = sorted(compartidos)[0]
            muestra.append(
                Candidato(
                    a_id=filas[i]["id"],
                    b_id=filas[j]["id"],
                    score=0.0,
                    banda="vetada",
                    evidencia=(
                        f"{ns} distinto: "
                        f"{sorted(indice[filas[i]['id']][ns])[0]} vs "
                        f"{sorted(indice[filas[j]['id']][ns])[0]} (no puntuado)"
                    ),
                    nombre_a=filas[i]["nombre"],
                    nombre_b=filas[j]["nombre"],
                )
            )
            if len(muestra) >= min(tope, 5):
                return muestra
    return muestra


def buscar_candidatos(
    con: sqlite3.Connection, forzar: bool = False, max_vetadas: int = 500
) -> Informe:
    """Genera el informe de fusiones sin tocar la base.

    `max_vetadas`: solo se retienen las primeras N vetadas para el informe. Un
    veto por ID externo discrepante NO es una ambiguedad pendiente — es una
    decision ya tomada por el dato — asi que no engorda `entidad_revision`;
    solo se cuenta.
    """
    informe = Informe()
    vistos: set[tuple[int, int]] = set()
    indice = indice_ids(con)

    for (_tipo, _bloque), filas in _bloques(con).items():
        if len(filas) < 2:
            continue

        # Poda estructural antes de puntuar. entidad_identificador tiene
        # UNIQUE(namespace, valor): dos entidades NUNCA comparten un ID externo.
        # Luego si ambas tienen 'pleiades', sus valores difieren por definicion y
        # el par esta vetado sin necesidad de calcular ningun score. Sin esta poda,
        # cargar solo Pleiades generaba 7,1M pares puntuados (295 s) que acababan
        # todos vetados.
        indices_a_puntuar, omitidos = _pares_puntuables(filas, indice)
        informe.n_vetadas += omitidos
        if omitidos and len(informe.vetadas) < max_vetadas:
            informe.vetadas.extend(_muestra_vetadas(filas, indice, max_vetadas))
        if not indices_a_puntuar:
            continue

        nombres = [f["nombre_norm"] for f in filas]
        matriz = process.cdist(nombres, nombres, scorer=SCORER, workers=-1)

        for i, j in indices_a_puntuar:
            fila_a, fila_b = filas[i], filas[j]
            score = float(matriz[i][j])
            if score >= UMBRAL_REVISION:
                par = (min(fila_a["id"], fila_b["id"]), max(fila_a["id"], fila_b["id"]))
                if par in vistos:
                    continue
                vistos.add(par)

                if not forzar and (fila_a["revisado_manual"] or fila_b["revisado_manual"]):
                    continue

                cand = Candidato(
                    a_id=par[0],
                    b_id=par[1],
                    score=score,
                    banda="revision",
                    nombre_a=fila_a["nombre"] if fila_a["id"] == par[0] else fila_b["nombre"],
                    nombre_b=fila_b["nombre"] if fila_b["id"] == par[1] else fila_a["nombre"],
                )

                motivo_veto = _veto_numeracion(fila_a["nombre"], fila_b["nombre"]) or hay_veto(
                    con, cand.a_id, cand.b_id, indice
                )
                if motivo_veto:
                    cand.banda = "vetada"
                    cand.evidencia = motivo_veto
                    informe.n_vetadas += 1
                    if len(informe.vetadas) < max_vetadas:
                        informe.vetadas.append(cand)
                    continue

                if score >= UMBRAL_AUTO:
                    cand.banda = "auto"
                    informe.fusiones.append(cand)
                elif score >= UMBRAL_CORROBORADA:
                    ev = corroboracion(con, cand.a_id, cand.b_id)
                    if ev:
                        cand.banda = "corroborada"
                        cand.evidencia = ev
                        informe.fusiones.append(cand)
                    else:
                        cand.evidencia = "banda 88-94 sin corroboracion"
                        informe.revisiones.append(cand)
                else:
                    cand.evidencia = "banda 80-87"
                    informe.revisiones.append(cand)

    return informe


# --------------------------------------------------------------- nombre canonico


def elegir_canonico(con: sqlite3.Connection, ids: list[int]) -> tuple[int, str, str]:
    """Devuelve (superviviente_id, nombre_canonico, motivo).

    Cadena de prioridad: nombre_es de Wikidata > forma latina de MANTO >
    romanizacion de Pleiades > entrada de Smith > la entidad mejor atestiguada
    (mas relaciones).
    """
    filas = {
        f["id"]: f
        for f in con.execute(
            f"SELECT * FROM entidad WHERE id IN ({','.join('?' * len(ids))})", ids
        ).fetchall()
    }

    for columna, etiqueta in PRIORIDAD_CANONICO:
        for eid in ids:
            valor = filas[eid][columna]
            if valor:
                return eid, valor, etiqueta

    # Pleiades / Smith via entidad_nombre
    for eid in ids:
        row = con.execute(
            "SELECT nombre, tipo FROM entidad_nombre "
            "WHERE entidad_id = ? AND tipo IN ('latino','moderno') LIMIT 1",
            (eid,),
        ).fetchone()
        if row:
            return eid, row["nombre"], f"entidad_nombre:{row['tipo']}"

    mejor = max(ids, key=lambda e: _grado(con, e))
    return mejor, filas[mejor]["nombre"], "mejor atestiguada"


def _grado(con: sqlite3.Connection, entidad_id: int) -> int:
    row = con.execute(
        "SELECT COUNT(*) AS n FROM relacion WHERE sujeto_id = ? OR objeto_id = ?",
        (entidad_id, entidad_id),
    ).fetchone()
    return row["n"]


# ------------------------------------------------------------------- fusion


def _snapshot(con: sqlite3.Connection, entidad_id: int) -> dict:
    """Fila completa + satelites. Es lo que permite deshacer la fusion."""
    fila = con.execute("SELECT * FROM entidad WHERE id = ?", (entidad_id,)).fetchone()
    return {
        "entidad": dict(fila) if fila else {},
        "nombres": [
            dict(r)
            for r in con.execute("SELECT * FROM entidad_nombre WHERE entidad_id = ?", (entidad_id,))
        ],
        "identificadores": [
            dict(r)
            for r in con.execute(
                "SELECT * FROM entidad_identificador WHERE entidad_id = ?", (entidad_id,)
            )
        ],
        "movimientos": {},  # se rellena en _reapuntar
    }


def _reapuntar(
    con: sqlite3.Connection, absorbida_id: int, superviviente_id: int
) -> dict[str, list[int]]:
    """Mueve toda referencia de absorbida -> superviviente.

    UPDATE OR IGNORE deja intactas las filas que violarian un UNIQUE (ya existia
    la equivalente en el superviviente); esas se borran despues por duplicadas.
    Registra los rowid movidos para poder revertir.
    """
    movidos: dict[str, list[int]] = {}
    for tabla, columna in REFERENCIAS:
        clave = f"{tabla}.{columna}"
        pendientes = [
            r["rid"]
            for r in con.execute(
                # alias obligatorio: si rowid tiene alias de PK (INTEGER PRIMARY KEY)
                # SQLite no siempre nombra la columna de salida 'rowid'
                f"SELECT rowid AS rid FROM {tabla} WHERE {columna} = ?",
                (absorbida_id,),
            )
        ]
        if not pendientes:
            continue
        con.execute(
            f"UPDATE OR IGNORE {tabla} SET {columna} = ? WHERE {columna} = ?",
            (superviviente_id, absorbida_id),
        )
        # las que siguen apuntando a la absorbida eran duplicados: fuera
        restantes = [
            r["rid"]
            for r in con.execute(
                # alias obligatorio: si rowid tiene alias de PK (INTEGER PRIMARY KEY)
                # SQLite no siempre nombra la columna de salida 'rowid'
                f"SELECT rowid AS rid FROM {tabla} WHERE {columna} = ?",
                (absorbida_id,),
            )
        ]
        if restantes:
            marcas = ",".join("?" * len(restantes))
            con.execute(f"DELETE FROM {tabla} WHERE rowid IN ({marcas})", restantes)
        movidos[clave] = [r for r in pendientes if r not in restantes]

    # auto-relaciones creadas por la fusion (A padre_de B con A y B fusionadas)
    con.execute("DELETE FROM relacion WHERE sujeto_id = objeto_id")
    con.execute("DELETE FROM entidad_equivalencia WHERE entidad_a_id = entidad_b_id")
    con.execute("DELETE FROM entidad_revision WHERE entidad_a_id = entidad_b_id")
    return movidos


def fusionar(
    con: sqlite3.Connection, cand: Candidato, umbral: float = UMBRAL_CORROBORADA
) -> int | None:
    """Fusiona el par y devuelve el id de fuzzy_fusion. Idempotente."""
    ids = [cand.a_id, cand.b_id]
    existe = con.execute(
        f"SELECT id FROM entidad WHERE id IN ({','.join('?' * len(ids))})", ids
    ).fetchall()
    if len(existe) < 2:
        return None  # ya fusionadas en una pasada anterior

    superviviente_id, nombre_canonico, motivo = elegir_canonico(con, ids)
    absorbida_id = cand.b_id if superviviente_id == cand.a_id else cand.a_id

    snap = _snapshot(con, absorbida_id)
    absorbida_nombre = snap["entidad"]["nombre"]

    # el nombre absorbido no se pierde: pasa a entidad_nombre
    for nombre, tipo in (
        (absorbida_nombre, "absorbido"),
        (snap["entidad"].get("nombre_grc"), "translit"),
        (snap["entidad"].get("nombre_translit"), "translit"),
        (snap["entidad"].get("nombre_latino"), "latino"),
        (snap["entidad"].get("nombre_es"), "es"),
    ):
        if nombre:
            insert_ignore(
                con,
                "entidad_nombre",
                {"entidad_id": superviviente_id, "nombre": nombre, "tipo": tipo},
            )

    # completa huecos del superviviente con lo que traia la absorbida
    for columna in (
        "nombre_grc",
        "nombre_translit",
        "nombre_latino",
        "nombre_es",
        "genero",
        "es_mortal",
        "generacion",
        "descripcion",
        "desambiguador",
        "tipo_entidad_id",
    ):
        valor = snap["entidad"].get(columna)
        if valor is not None:
            con.execute(
                f"UPDATE entidad SET {columna} = COALESCE({columna}, ?) WHERE id = ?",
                (valor, superviviente_id),
            )

    snap["movimientos"] = _reapuntar(con, absorbida_id, superviviente_id)
    con.execute("DELETE FROM entidad WHERE id = ?", (absorbida_id,))

    # normaliza a un solo nombre y recalcula la clave de comparacion
    con.execute(
        "UPDATE entidad SET nombre = ?, nombre_norm = ?, confianza = MIN(confianza, ?) "
        "WHERE id = ?",
        (
            nombre_canonico,
            normalize.normalizar(nombre_canonico),
            1.0 if cand.banda == "auto" else 0.9,
            superviviente_id,
        ),
    )

    cur = con.execute(
        """
        INSERT INTO fuzzy_fusion (superviviente_id, absorbida_id, absorbida_nombre,
                                  absorbida_json, score, algoritmo, umbral, banda,
                                  evidencia, fecha)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            superviviente_id,
            absorbida_id,
            absorbida_nombre,
            json.dumps(snap, ensure_ascii=False, default=str),
            cand.score,
            ALGORITMO,
            umbral,
            cand.banda,
            f"{cand.evidencia or ''} | canonico por {motivo}".strip(" |"),
            datetime.now(UTC).isoformat(timespec="seconds"),
        ),
    )
    return cur.lastrowid


def _ambas_existen(con: sqlite3.Connection, a_id: int, b_id: int) -> bool:
    row = con.execute(
        "SELECT COUNT(*) AS n FROM entidad WHERE id IN (?, ?)", (a_id, b_id)
    ).fetchone()
    return row["n"] == 2


def aplicar(con: sqlite3.Connection, informe: Informe) -> tuple[int, int]:
    """Aplica las fusiones del informe y encola las revisiones."""
    n_fusiones = 0
    for cand in sorted(informe.fusiones, key=lambda c: -c.score):
        if fusionar(con, cand) is not None:
            n_fusiones += 1

    # Solo las revisiones van a la cola humana. Las vetadas NO: un ID externo
    # discrepante ya zanja el caso, y encolarlas llenaba entidad_revision con
    # millones de pares que nadie tiene que decidir.
    n_revisiones = 0
    for cand in informe.revisiones:
        # el informe se calculo antes de fusionar: alguna de las dos entidades
        # puede haber sido absorbida ya, y entonces la FK de entidad_revision falla
        if not _ambas_existen(con, cand.a_id, cand.b_id):
            continue
        grupo = normalize.normalizar_base(cand.nombre_a)
        con.execute(
            "UPDATE entidad SET homonimo_grupo = COALESCE(homonimo_grupo, ?) WHERE id IN (?, ?)",
            (grupo, cand.a_id, cand.b_id),
        )
        insert_ignore(
            con,
            "entidad_revision",
            {
                "entidad_a_id": cand.a_id,
                "entidad_b_id": cand.b_id,
                "score": cand.score,
                "motivo": cand.evidencia,
                "decision": "pendiente",
            },
        )
        n_revisiones += 1

    con.commit()
    return n_fusiones, n_revisiones


# ------------------------------------------------------------------- deshacer


def deshacer(con: sqlite3.Connection, fusion_id: int) -> str:
    """Revierte una fusion desde su snapshot. Requiere absorbida_json intacto."""
    row = con.execute(
        "SELECT * FROM fuzzy_fusion WHERE id = ? AND revertida = 0", (fusion_id,)
    ).fetchone()
    if row is None:
        raise LookupError(f"fusion {fusion_id} inexistente o ya revertida")

    snap = json.loads(row["absorbida_json"])
    entidad = snap["entidad"]
    cols = ", ".join(entidad)
    marcas = ", ".join("?" * len(entidad))
    con.execute(f"INSERT INTO entidad ({cols}) VALUES ({marcas})", list(entidad.values()))

    for tabla, filas in (
        ("entidad_nombre", snap["nombres"]),
        ("entidad_identificador", snap["identificadores"]),
    ):
        for f in filas:
            f.pop("id", None)
            insert_ignore(con, tabla, f)

    for clave, rowids in snap.get("movimientos", {}).items():
        if not rowids:
            continue
        tabla, columna = clave.split(".")
        marcas = ",".join("?" * len(rowids))
        con.execute(
            f"UPDATE OR IGNORE {tabla} SET {columna} = ? WHERE rowid IN ({marcas})",
            [entidad["id"], *rowids],
        )

    con.execute("UPDATE fuzzy_fusion SET revertida = 1 WHERE id = ?", (fusion_id,))
    con.execute(
        "DELETE FROM entidad_nombre WHERE entidad_id = ? AND tipo = 'absorbido' AND nombre = ?",
        (row["superviviente_id"], row["absorbida_nombre"]),
    )
    con.commit()
    return f"revertida fusion {fusion_id}: restaurada '{row['absorbida_nombre']}'"


def ejecutar(
    con: sqlite3.Connection, aplicar_cambios: bool = False, forzar: bool = False
) -> Informe:
    poblar_nombre_norm(con)
    informe = buscar_candidatos(con, forzar=forzar)
    if aplicar_cambios:
        aplicar(con, informe)
    return informe
