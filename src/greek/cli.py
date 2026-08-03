"""CLI: `uv run greek <comando>`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import export, fetch, fuzzy, graph, qa, reconcile
from .db import DB_PATH, connect, init_schema
from .loaders import LOADERS, ORDEN


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="greek",
        description="Mitologia griega -> SQLite local. Fuentes y diseno: .claude/fuentes.md",
    )
    p.add_argument("--db", type=Path, default=DB_PATH, help=f"ruta de la base (def. {DB_PATH})")
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="descarga dumps a data/raw/")
    f.add_argument("--source", help="pleiades | topostext | dmp | manto | wikidata")
    f.add_argument("--force", action="store_true", help="rebaja aunque este en cache")

    sub.add_parser("init", help="crea esquema, vistas y seeds")

    lo = sub.add_parser("load", help="carga una fuente")
    lo.add_argument("source", choices=sorted(LOADERS))
    lo.add_argument("--inspect", action="store_true", help="solo MANTO: imprime cabeceras reales")

    sub.add_parser("load-all", help="carga completa en el orden de fuentes.md §5.1")

    fz = sub.add_parser("fuzzy", help="fuzzy join + normalizacion a un solo nombre")
    g = fz.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="informe sin tocar la base")
    g.add_argument("--apply", action="store_true", help="aplica las fusiones")
    g.add_argument("--undo", type=int, metavar="FUSION_ID", help="revierte una fusion")
    fz.add_argument("--force", action="store_true", help="incluye entidades revisadas a mano")
    fz.add_argument("--limit", type=int, default=30, help="filas a mostrar en el informe")

    sub.add_parser("contradicciones", help="detecta y registra versiones incompatibles")
    sub.add_parser("qa", help="checks de calidad y metricas")
    sub.add_parser("stats", help="resumen rapido de volumen")

    gr = sub.add_parser("graph", help="proyecta la base en Memgraph (front: Memgraph Lab)")
    gr.add_argument("--bolt", default=graph.BOLT_URI, help=f"URI bolt (def. {graph.BOLT_URI})")
    gr.add_argument(
        "--only",
        nargs="+",
        choices=sorted(graph.PASOS),
        metavar="PASO",
        help=f"solo estos pasos: {' '.join(graph.ORDEN)}",
    )
    gr.add_argument(
        "--wipe",
        action="store_true",
        help="borra el grafo antes de cargar (necesario si borraste filas en SQLite)",
    )

    ex = sub.add_parser("export-web", help="JSON estatico para la web del mapa")
    ex.add_argument("--dest", type=Path, default=export.DEST, help=f"salida (def. {export.DEST})")

    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.cmd == "fetch":
        fetch.descargar(args.source, forzar=args.force)
        return 0

    con = connect(args.db)
    try:
        if args.cmd == "init":
            init_schema(con)
            print(f"esquema creado en {args.db}")
            return 0

        if args.cmd == "load":
            if args.inspect:
                if args.source != "manto":
                    print("--inspect solo aplica a manto")
                    return 2
                from .loaders import manto

                print(manto.inspeccionar())
                return 0
            print(LOADERS[args.source](con))
            return 0

        if args.cmd == "load-all":
            for paso in ORDEN:
                if paso == "fuzzy":
                    informe = fuzzy.ejecutar(con, aplicar_cambios=True)
                    print(f"fuzzy: {informe.resumen()}")
                    continue
                print(LOADERS[paso](con))
            n = reconcile.detectar_contradicciones(con)
            print(f"contradicciones: {n} registradas")
            informe, ok = qa.ejecutar(con)
            print(informe)
            return 0 if ok else 1

        if args.cmd == "fuzzy":
            if args.undo is not None:
                print(fuzzy.deshacer(con, args.undo))
                return 0
            informe = fuzzy.ejecutar(con, aplicar_cambios=args.apply, forzar=args.force)
            print(_informe_fuzzy(informe, args.limit, aplicado=args.apply))
            return 0

        if args.cmd == "contradicciones":
            print(f"{reconcile.detectar_contradicciones(con)} contradicciones registradas")
            return 0

        if args.cmd == "qa":
            informe, ok = qa.ejecutar(con)
            print(informe)
            return 0 if ok else 1

        if args.cmd == "graph":
            print(graph.exportar(con, uri=args.bolt, solo=args.only, wipe=args.wipe))
            return 0

        if args.cmd == "export-web":
            print(export.exportar_web(con, args.dest))
            return 0

        if args.cmd == "stats":
            for tabla in ("entidad", "relacion", "evento", "lugar_detalle", "fuzzy_fusion"):
                n = con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
                print(f"{tabla:<16} {n:>9,}")
            return 0
    finally:
        con.close()

    return 2


def _informe_fuzzy(informe: fuzzy.Informe, limite: int, aplicado: bool) -> str:
    lineas = [f"fuzzy: {informe.resumen()}", ""]
    if not aplicado:
        lineas.append("(dry-run: nada escrito en la base)")
        lineas.append("")

    if informe.fusiones:
        lineas.append("--- fusiones ---")
        for c in sorted(informe.fusiones, key=lambda c: c.score)[:limite]:
            lineas.append(
                f"  {c.score:5.1f} [{c.banda:<12}] {c.nombre_a!r} + {c.nombre_b!r}"
                + (f"  <- {c.evidencia}" if c.evidencia else "")
            )
        if len(informe.fusiones) > limite:
            lineas.append(f"  ... y {len(informe.fusiones) - limite} mas")

    if informe.vetadas:
        lineas.append("")
        lineas.append(
            f"--- omitidos sin puntuar: {informe.n_vetadas:,} pares en los que ambas "
            "entidades tienen el mismo ID externo con valores distintos. Ni se fusionan "
            "ni se encolan: el dato ya zanja el caso ---"
        )
        for c in informe.vetadas[:limite]:
            lineas.append(f"  {c.score:5.1f} {c.nombre_a!r} vs {c.nombre_b!r}  <- {c.evidencia}")
        if informe.n_vetadas > limite:
            lineas.append(f"  ... y {informe.n_vetadas - limite:,} mas")

    if informe.revisiones:
        lineas.append("")
        lineas.append("--- a entidad_revision (decision humana) ---")
        for c in informe.revisiones[:limite]:
            lineas.append(f"  {c.score:5.1f} {c.nombre_a!r} vs {c.nombre_b!r}  <- {c.evidencia}")
        if len(informe.revisiones) > limite:
            lineas.append(f"  ... y {len(informe.revisiones) - limite} mas")

    return "\n".join(lineas)


if __name__ == "__main__":
    sys.exit(main())
