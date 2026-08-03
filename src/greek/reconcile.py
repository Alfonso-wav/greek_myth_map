"""Reconciliacion por identificador externo y deteccion de contradicciones.

El fuzzy join (fuzzy.py) es el fallback. Esto es la via prioritaria: IDs externos
exactos. Ademas detecta contradicciones entre versiones del mito, que es una
metrica de calidad: si `contradiccion` sale vacia, el modelo esta aplanado.
"""

from __future__ import annotations

import sqlite3

from .db import insert_ignore

PRIORIDAD = ("manto", "wikidata", "pleiades", "topostext", "digital_limc", "perseus_smith")


def entidad_por_ids(con: sqlite3.Connection, ids: dict[str, str]) -> int | None:
    """Busca una entidad por cualquiera de sus IDs externos, en orden de fiabilidad."""
    for namespace in PRIORIDAD:
        valor = ids.get(namespace)
        if not valor:
            continue
        row = con.execute(
            "SELECT entidad_id FROM entidad_identificador WHERE namespace = ? AND valor = ?",
            (namespace, str(valor)),
        ).fetchone()
        if row:
            return row["entidad_id"]
    return None


def detectar_contradicciones(con: sqlite3.Connection) -> int:
    """Registra versiones incompatibles del mito. Se ejecuta al final de la carga."""
    n = _contradicciones_genealogicas(con)
    n += _contradicciones_muerte(con)
    n += _contradicciones_ubicacion(con)
    con.commit()
    return n


def _registrar(con: sqlite3.Connection, a: int, b: int, tipo: str, desc: str) -> None:
    if a == b:
        return
    insert_ignore(
        con,
        "contradiccion",
        {
            "relacion_a_id": min(a, b),
            "relacion_b_id": max(a, b),
            "tipo": tipo,
            "descripcion": desc,
            "resuelta": 0,
        },
    )


def _contradicciones_genealogicas(con: sqlite3.Connection) -> int:
    """Mismo hijo, progenitores incompatibles segun fuentes distintas.

    Las Hesperides son hijas de Nix, de Nix y Erebo, de Atlas, de Forcis y Ceto o
    de Zeus y Temis segun la tradicion. Ninguna es "la correcta": se guardan todas
    y se marca el choque.

    Direccion: el predicado de MANTO es 'is child of', con SUJETO = hijo y
    OBJETO = progenitor. Y se exigen >= 3 progenitores distintos, porque tener
    padre y madre no es ninguna contradiccion: la senal es el tercero en adelante.
    """
    filas = con.execute(
        """
        WITH gen AS (
            SELECT r.id, r.sujeto_id AS hijo_id, r.objeto_id AS prog_id
              FROM relacion r JOIN predicado p ON p.id = r.predicado_id
             WHERE p.categoria = 'genealogica' AND p.clave LIKE '%child_of%'
               AND r.objeto_id IS NOT NULL
        ),
        multiples AS (
            SELECT hijo_id FROM gen
             GROUP BY hijo_id HAVING COUNT(DISTINCT prog_id) >= 3
        )
        SELECT ga.id AS a_id, gb.id AS b_id, h.nombre AS hijo,
               pa.nombre AS prog_a, pb.nombre AS prog_b
          FROM gen ga
          JOIN gen gb ON gb.hijo_id = ga.hijo_id AND gb.id > ga.id
                     AND gb.prog_id <> ga.prog_id
          JOIN multiples m ON m.hijo_id = ga.hijo_id
          JOIN entidad h  ON h.id = ga.hijo_id
          JOIN entidad pa ON pa.id = ga.prog_id
          JOIN entidad pb ON pb.id = gb.prog_id
        """
    ).fetchall()
    for f in filas:
        _registrar(
            con,
            f["a_id"],
            f["b_id"],
            "genealogia",
            f"{f['hijo']}: progenitor dado como {f['prog_a']} y como {f['prog_b']}",
        )
    return len(filas)


def _contradicciones_muerte(con: sqlite3.Connection) -> int:
    """Misma victima, distinto matador."""
    filas = con.execute(
        """
        SELECT ra.id AS a_id, rb.id AS b_id, v.nombre AS victima,
               ma.nombre AS mat_a, mb.nombre AS mat_b
          FROM relacion ra
          JOIN predicado p ON p.id = ra.predicado_id AND p.categoria = 'muerte'
          JOIN relacion rb ON rb.objeto_id = ra.objeto_id
                          AND rb.predicado_id = ra.predicado_id
                          AND rb.id > ra.id
                          AND rb.sujeto_id <> ra.sujeto_id
          JOIN entidad v  ON v.id = ra.objeto_id
          JOIN entidad ma ON ma.id = ra.sujeto_id
          JOIN entidad mb ON mb.id = rb.sujeto_id
        """
    ).fetchall()
    for f in filas:
        _registrar(
            con,
            f["a_id"],
            f["b_id"],
            "autoria_muerte",
            f"{f['victima']}: muerte atribuida a {f['mat_a']} y a {f['mat_b']}",
        )
    return len(filas)


def _contradicciones_ubicacion(con: sqlite3.Connection) -> int:
    """Misma relacion narrativa situada en lugares distintos."""
    filas = con.execute(
        """
        SELECT ra.id AS a_id, rb.id AS b_id, la.nombre AS lugar_a, lb.nombre AS lugar_b,
               s.nombre AS sujeto, p.clave AS predicado
          FROM relacion ra
          JOIN predicado p ON p.id = ra.predicado_id
          JOIN relacion_rol rra ON rra.relacion_id = ra.id AND rra.rol = 'en'
          JOIN relacion rb ON rb.sujeto_id = ra.sujeto_id
                          AND rb.predicado_id = ra.predicado_id
                          AND rb.objeto_id IS ra.objeto_id
                          AND rb.id > ra.id
          JOIN relacion_rol rrb ON rrb.relacion_id = rb.id AND rrb.rol = 'en'
                               AND rrb.entidad_id <> rra.entidad_id
          JOIN entidad la ON la.id = rra.entidad_id
          JOIN entidad lb ON lb.id = rrb.entidad_id
          JOIN entidad s  ON s.id = ra.sujeto_id
        """
    ).fetchall()
    for f in filas:
        _registrar(
            con,
            f["a_id"],
            f["b_id"],
            "ubicacion",
            f"{f['sujeto']} {f['predicado']}: situado en {f['lugar_a']} y en {f['lugar_b']}",
        )
    return len(filas)
