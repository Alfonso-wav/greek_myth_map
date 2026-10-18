"""Lectura de dumps directamente desde su ZIP, sin descomprimir a disco.

El ZIP de MANTO pesa 248 MB y descomprimido 5,4 GB, de los que el loader lee 56 MB:
`related_entities` (3,1 GB) y `mentioned_in_text` (830 MB) no se usan. Abrir cada CSV
como miembro del ZIP deja `data/raw/` en lo descargado y nada mas.

Los miembros se ordenan como los recorreria `Path.rglob` (ficheros de un directorio
antes que sus subdirectorios), para que `primero()` devuelva el mismo fichero que
devolvia `next(DIR.rglob(...))` cuando el patron casa en varias carpetas.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from fnmatch import fnmatchcase
from functools import cached_property
from pathlib import Path, PurePosixPath
from typing import TextIO


class Zip:
    def __init__(self, ruta: Path) -> None:
        self.ruta = ruta

    def existe(self) -> bool:
        return self.ruta.is_file()

    @cached_property
    def _zf(self) -> zipfile.ZipFile:
        return zipfile.ZipFile(self.ruta)

    @cached_property
    def miembros(self) -> list[str]:
        """Ficheros del ZIP (sin directorios), en orden de recorrido de rglob."""
        nombres = [n for n in self._zf.namelist() if not n.endswith("/")]
        return sorted(nombres, key=lambda n: (str(PurePosixPath(n).parent), PurePosixPath(n).name))

    def buscar(self, patron: str) -> list[str]:
        """Miembros cuyo nombre de fichero casa con el patron glob, en cualquier carpeta."""
        if not self.existe():
            return []
        return [n for n in self.miembros if fnmatchcase(PurePosixPath(n).name, patron)]

    def primero(self, patron: str) -> str | None:
        return next(iter(self.buscar(patron)), None)

    @contextmanager
    def abrir(self, miembro: str, encoding: str = "utf-8-sig") -> Iterator[TextIO]:
        with self._zf.open(miembro) as fb:
            yield io.TextIOWrapper(fb, encoding=encoding, newline="")

    def filas(self, miembro: str | None) -> Iterator[dict[str, str]]:
        if miembro is None:
            return
        with self.abrir(miembro) as fh:
            yield from csv.DictReader(fh)


def stem(miembro: str) -> str:
    return PurePosixPath(miembro).stem
