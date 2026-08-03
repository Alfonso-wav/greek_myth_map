"""Conexion a SQLite, PRAGMAs y helpers de upsert.

Regla del proyecto: upsert siempre, nunca DELETE + recarga. Un DELETE masivo
destruye `entidad.revisado_manual` y las correcciones humanas.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = ROOT / "sql"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "greek.db"


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    """Abre la base con los PRAGMAs obligatorios.

    `foreign_keys` no se persiste en el fichero: hay que activarlo en CADA
    conexion o los CHECK de FK no se aplican.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    return con


def run_script(con: sqlite3.Connection, name: str) -> None:
    """Ejecuta un .sql de sql/ como script."""
    sql = (SQL_DIR / name).read_text(encoding="utf-8")
    con.executescript(sql)
    con.commit()


def init_schema(con: sqlite3.Connection) -> None:
    for script in (
        "001_schema.sql",
        "002_views.sql",
        "003_seed.sql",
        "004_generacion.sql",
        "005_papeles.sql",
    ):
        run_script(con, script)


# --------------------------------------------------------------------- upsert


def upsert(
    con: sqlite3.Connection,
    tabla: str,
    fila: dict,
    conflicto: Sequence[str],
    actualizar: Sequence[str] | None = None,
    columna_id: str = "id",
) -> int | None:
    """INSERT ... ON CONFLICT (conflicto) DO UPDATE ... RETURNING columna_id.

    `actualizar`: columnas a refrescar en caso de conflicto. Si es None se
    actualizan todas las de `fila` menos las de `conflicto`. Si va vacia, el
    conflicto es un no-op (DO NOTHING) y el id se recupera con un SELECT.

    Usa RETURNING a proposito: tras un ON CONFLICT DO UPDATE, `cursor.lastrowid`
    puede arrastrar el rowid de un INSERT anterior de la misma conexion y devolver
    un id ajeno a esta fila.
    """
    cols = list(fila)
    marcas = ", ".join("?" * len(cols))
    if actualizar is None:
        actualizar = [c for c in cols if c not in conflicto]

    sql = f"INSERT INTO {tabla} ({', '.join(cols)}) VALUES ({marcas}) "
    sql += f"ON CONFLICT ({', '.join(conflicto)}) DO "
    if actualizar:
        sets = ", ".join(f"{c} = excluded.{c}" for c in actualizar)
        sql += f"UPDATE SET {sets} "
    else:
        sql += "NOTHING "
    sql += f"RETURNING {columna_id}"

    row = con.execute(sql, [fila[c] for c in cols]).fetchone()
    if row is not None:
        return row[0]

    # DO NOTHING sin fila afectada: la fila ya existia tal cual
    where = " AND ".join(f"{c} = ?" for c in conflicto)
    row = con.execute(
        f"SELECT {columna_id} FROM {tabla} WHERE {where}",
        [fila[c] for c in conflicto],
    ).fetchone()
    return row[0] if row else None


def insert_ignore(con: sqlite3.Connection, tabla: str, fila: dict) -> None:
    cols = list(fila)
    marcas = ", ".join("?" * len(cols))
    con.execute(
        f"INSERT OR IGNORE INTO {tabla} ({', '.join(cols)}) VALUES ({marcas})",
        [fila[c] for c in cols],
    )


def insert_many_ignore(con: sqlite3.Connection, tabla: str, filas: Iterable[dict]) -> int:
    filas = list(filas)
    if not filas:
        return 0
    cols = list(filas[0])
    marcas = ", ".join("?" * len(cols))
    con.executemany(
        f"INSERT OR IGNORE INTO {tabla} ({', '.join(cols)}) VALUES ({marcas})",
        [[f.get(c) for c in cols] for f in filas],
    )
    return len(filas)


# ------------------------------------------------------------------- lookups


def registrar_fuente(con: sqlite3.Connection, **campos) -> int:
    """Alta idempotente en fuente_dataset. Toda carga debe pasar por aqui."""
    fid = upsert(con, "fuente_dataset", campos, conflicto=["clave"])
    con.commit()
    assert fid is not None
    return fid


def id_fuente(con: sqlite3.Connection, clave: str) -> int:
    row = con.execute("SELECT id FROM fuente_dataset WHERE clave = ?", (clave,)).fetchone()
    if row is None:
        raise LookupError(
            f"fuente_dataset '{clave}' no registrada. Llama a registrar_fuente() antes de cargar."
        )
    return row["id"]


def id_tipo_entidad(con: sqlite3.Connection, clave: str) -> int | None:
    row = con.execute("SELECT id FROM tipo_entidad WHERE clave = ?", (clave,)).fetchone()
    return row["id"] if row else None


def entidad_por_identificador(con: sqlite3.Connection, namespace: str, valor: str) -> int | None:
    """Reconciliacion prioritaria: por ID externo, nunca por nombre."""
    row = con.execute(
        "SELECT entidad_id FROM entidad_identificador WHERE namespace = ? AND valor = ?",
        (namespace, str(valor)),
    ).fetchone()
    return row["entidad_id"] if row else None
