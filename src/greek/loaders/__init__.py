"""Loaders: uno por fuente. Cada uno registra su fila en fuente_dataset y hace upsert.

Orden de carga (fuentes.md §5.1). El fuzzy join va tras wikidata y antes de eventos.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from . import (
    dmp,
    generacional,
    manto,
    papeles,
    pleiades,
    predicados_es,
    topostext,
    troya,
    wikidata,
)

# clave -> callable(con) -> str (resumen)
LOADERS: dict[str, Callable[[sqlite3.Connection], str]] = {
    "pleiades": pleiades.cargar,
    "manto": manto.cargar,
    "topostext": topostext.cargar,
    "wikidata": wikidata.cargar,
    "dmp": dmp.cargar,
    "troya": troya.cargar,
    "generacional": generacional.cargar,
    "predicados-es": predicados_es.cargar,
    "papeles": papeles.cargar,
}

# orden de load-all; 'fuzzy' lo inserta el CLI en su posicion
ORDEN: tuple[str, ...] = (
    "pleiades",
    "manto",
    "topostext",
    "wikidata",
    "fuzzy",
    "dmp",
    "troya",
    "generacional",
    # van al final: derivan sobre lo ya cargado, no traen datos nuevos
    "predicados-es",
    # papeles necesita entidad_generacion (transmite=0 marca divinidad), asi que
    # va despues de generacional
    "papeles",
)

__all__ = ["LOADERS", "ORDEN"]
