"""Control de calidad: ejecuta sql/qa.sql + vw_huecos + metricas de fuentes.md §6."""

from __future__ import annotations

import re
import sqlite3

from .db import SQL_DIR

RE_CHECK = re.compile(r"--\s*@check:\s*(\S+)")

# (etiqueta, sql, objetivo, comparador)
METRICAS: tuple[tuple[str, str, float, str], ...] = (
    (
        "entidades con >=1 id externo",
        "SELECT 100.0 * COUNT(DISTINCT i.entidad_id) / NULLIF((SELECT COUNT(*) FROM entidad),0) "
        "FROM entidad_identificador i",
        95.0,
        ">=",
    ),
    # Una relacion puede estar atestiguada por pasaje, artefacto o inscripcion.
    # Contar solo pasajes daba por "sin fuente" las 2.478 atestiguadas por vaso o
    # inscripcion, que es justo el material que MANTO anadio en 2023.
    (
        "relaciones con >=1 fuente",
        "SELECT 100.0 * COUNT(DISTINCT rf.relacion_id) / NULLIF((SELECT COUNT(*) FROM relacion),0) "
        "FROM relacion_fuente rf",
        90.0,
        ">=",
    ),
    (
        "relaciones con pasaje textual",
        "SELECT 100.0 * COUNT(DISTINCT rf.relacion_id) / NULLIF((SELECT COUNT(*) FROM relacion),0) "
        "FROM relacion_fuente rf WHERE rf.pasaje_id IS NOT NULL",
        85.0,
        ">=",
    ),
    (
        "lugares reales con coordenadas",
        "SELECT 100.0 * SUM(CASE WHEN latitud IS NOT NULL THEN 1 ELSE 0 END) / "
        "NULLIF(COUNT(*),0) FROM lugar_detalle WHERE geo_tipo <> 'legendario_sin_ubicacion'",
        90.0,
        ">=",
    ),
    # 'sin_fecha' se excluye del denominador: la cosmogonia y las teomaquias no
    # deben tener fecha, asi que contarlas como huecos exigiria inventarsela.
    (
        "eventos databales con >=1 datacion",
        "SELECT 100.0 * COUNT(DISTINCT d.evento_id) / NULLIF("
        "(SELECT COUNT(*) FROM evento WHERE fecha_metodo IS NOT 'sin_fecha'),0) "
        "FROM evento_datacion d JOIN evento e ON e.id = d.evento_id "
        "WHERE e.fecha_metodo IS NOT 'sin_fecha'",
        100.0,
        ">=",
    ),
    (
        "eventos databales con >=2 dataciones",
        "SELECT 100.0 * COUNT(*) / NULLIF("
        "(SELECT COUNT(*) FROM evento WHERE fecha_metodo IS NOT 'sin_fecha'),0) FROM "
        "(SELECT d.evento_id FROM evento_datacion d JOIN evento e ON e.id = d.evento_id "
        " WHERE e.fecha_metodo IS NOT 'sin_fecha' GROUP BY d.evento_id HAVING COUNT(*) >= 2)",
        40.0,
        ">=",
    ),
    (
        "contradicciones registradas",
        "SELECT COUNT(*) FROM contradiccion",
        200.0,
        ">=",
    ),
    (
        "tasa de fusion fuzzy (%)",
        "SELECT 100.0 * (SELECT COUNT(*) FROM fuzzy_fusion WHERE revertida = 0) / "
        "NULLIF((SELECT COUNT(*) FROM entidad),0)",
        8.0,
        "<=",
    ),
)


def _bloques_qa() -> list[tuple[str, str]]:
    """Parte sql/qa.sql en (etiqueta, sentencia) usando los marcadores @check."""
    texto = (SQL_DIR / "qa.sql").read_text(encoding="utf-8")
    bloques: list[tuple[str, str]] = []
    etiqueta = "sin_etiqueta"
    acumulado: list[str] = []

    for linea in texto.splitlines():
        m = RE_CHECK.search(linea)
        if m:
            if acumulado and "".join(acumulado).strip():
                bloques.append((etiqueta, "\n".join(acumulado)))
            etiqueta = m.group(1)
            acumulado = []
            continue
        acumulado.append(linea)
    if acumulado and "".join(acumulado).strip():
        bloques.append((etiqueta, "\n".join(acumulado)))

    return [(e, s) for e, s in bloques if s.strip() and not s.strip().startswith("--")]


def ejecutar(con: sqlite3.Connection, limite: int = 5) -> tuple[str, bool]:
    """Devuelve (informe, todo_ok)."""
    lineas: list[str] = ["=== checks (0 filas = correcto) ==="]
    ok = True

    for etiqueta, sentencia in _bloques_qa():
        for stmt in [s for s in sentencia.split(";") if s.strip()]:
            try:
                filas = con.execute(stmt).fetchall()
            except sqlite3.Error as exc:
                lineas.append(f"  ERROR  {etiqueta}: {exc}")
                ok = False
                continue
            if filas:
                ok = False
                lineas.append(f"  FALLA  {etiqueta}: {len(filas)} filas")
                for f in filas[:limite]:
                    lineas.append(f"           {tuple(f)}")
                if len(filas) > limite:
                    lineas.append(f"           ... y {len(filas) - limite} mas")
            else:
                lineas.append(f"  ok     {etiqueta}")

    lineas.append("")
    lineas.append("=== huecos ===")
    try:
        for f in con.execute("SELECT hueco, n FROM vw_huecos"):
            lineas.append(f"  {f['hueco']:<32} {f['n']:>8,}")
    except sqlite3.Error as exc:
        lineas.append(f"  ERROR vw_huecos: {exc}")

    lineas.append("")
    lineas.append("=== metricas (fuentes.md §6) ===")
    for etiqueta, sentencia, objetivo, comp in METRICAS:
        try:
            valor = con.execute(sentencia).fetchone()[0]
        except sqlite3.Error as exc:
            lineas.append(f"  ERROR  {etiqueta}: {exc}")
            ok = False
            continue
        valor = 0.0 if valor is None else float(valor)
        cumple = valor >= objetivo if comp == ">=" else valor <= objetivo
        marca = "ok    " if cumple else "BAJO  "
        if not cumple:
            ok = False
        lineas.append(f"  {marca} {etiqueta:<42} {valor:>8.1f}  (objetivo {comp} {objetivo})")

    if con.execute("SELECT COUNT(*) FROM contradiccion").fetchone()[0] == 0:
        lineas.append("")
        lineas.append(
            "  AVISO: contradiccion esta vacia. En mito griego eso significa modelo "
            "aplanado, no base limpia (fuentes.md §6)."
        )

    lineas.append("")
    lineas.append("=== volumen ===")
    for tabla in (
        "entidad",
        "entidad_identificador",
        "relacion",
        "relacion_rol",
        "relacion_fuente",
        "evento",
        "evento_datacion",
        "lugar_detalle",
        "pasaje",
        "predicado",
        "fuzzy_fusion",
        "entidad_revision",
    ):
        try:
            n = con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
            lineas.append(f"  {tabla:<24} {n:>9,}")
        except sqlite3.Error:
            lineas.append(f"  {tabla:<24} (no existe)")

    return "\n".join(lineas), ok
