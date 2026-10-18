"""Descarga de dumps a data/raw/. Cachea: no vuelve a bajar lo que ya esta.

Todo es automatico, incluido MANTO: el endpoint de ficheros de la API de Zenodo
sirve el ZIP sin autenticacion. Solo Wikidata y ChronOntology se consultan en
tiempo de carga en vez de bajarse.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx

from .db import RAW_DIR


@dataclass(frozen=True)
class Descarga:
    fuente: str
    url: str
    destino: str
    opcional: bool = False
    nota: str = ""


DESCARGAS: tuple[Descarga, ...] = (
    # MANTO: fuentes.md daba esto por "descarga manual", pero el endpoint de
    # ficheros de la API de Zenodo sirve el ZIP sin autenticacion (verificado con
    # Range: devuelve 206 y cabecera PK\x03\x04). 248 MB.
    Descarga(
        "manto",
        "https://zenodo.org/api/records/19446255/files/"
        "publication-2616-20260306061219.zip/content",
        "manto/manto_publication_2616.zip",
        nota=(
            "Si Zenodo cambia el nombre del fichero, saca el nuevo de "
            "https://zenodo.org/api/records/19446255 (campo files[].key)."
        ),
    ),
    Descarga(
        "pleiades",
        "https://atlantides.org/downloads/pleiades/gis/pleiades_gis_data.zip",
        "pleiades/pleiades_gis_data.zip",
    ),
    Descarga(
        "topostext",
        "https://topostext.org/downloads/ToposText_places_2025-11-20.geojson",
        "topostext/places.geojson",
    ),
    Descarga(
        "topostext",
        "https://topostext.org/downloads/ToposTextGazetteer.jsonld",
        "topostext/gazetteer.jsonld",
    ),
    Descarga(
        "topostext",
        "https://topostext.org/downloads/pelagios.ttl",
        "topostext/pelagios.ttl",
        opcional=True,
        nota=(
            "Comprobado 2026-07-29: devuelve 404 aunque sigue enlazado en TT-downloads "
            "(link rot). Traia las equivalencias Pleiades<->DARE. Mientras siga caido, "
            "esas equivalencias se obtienen de Wikidata (P1584) o del gazetteer JSON-LD."
        ),
    ),
    Descarga(
        "topostext",
        "https://topostext.org/downloads/topostext.void.ttl",
        "topostext/void.ttl",
        opcional=True,
        nota="Descriptor VoID del dataset: metadatos de la propia publicacion.",
    ),
    Descarga(
        "topostext",
        "https://topostext.org/downloads/ToposTextWorkTurtles.ttl",
        "topostext/works.ttl",
    ),
    # La tabla cronologica que cita fuentes.md (chronology.html) NO es parseable:
    # esa pagina solo incrusta timelines de Knightlab cuya fuente es una Google
    # Sheet que devuelve 401 al exportar. El dato machine-readable es la edicion
    # EpiDoc, con las expresiones cronologicas marcadas en <date from= to=>.
    Descarga(
        "dmp",
        "https://raw.githubusercontent.com/OpenGreekAndLatin/DigitalMarmorParium/HEAD/"
        "EpiDoc_versions/dmp_ig_12_5_444.xml",
        "dmp/dmp_ig_12_5_444.xml",
    ),
    Descarga(
        "dmp",
        "https://www.digitalmarmorparium.org/chronology.html",
        "dmp/chronology.html",
        opcional=True,
        nota="Solo contexto: la tabla real esta en iframes de Knightlab, no en el HTML.",
    ),
)

MANUAL = {
    "wikidata": (
        "Se obtiene por SPARQL en tiempo de carga: `greek load wikidata`. No hay dump que bajar."
    ),
    "chrono": ("ChronOntology: API en https://chronontology.dainst.org/ — se consulta al cargar."),
}


def descargar(fuente: str | None = None, forzar: bool = False) -> list[Path]:
    bajados: list[Path] = []
    pendientes = [d for d in DESCARGAS if fuente is None or d.fuente == fuente]

    if fuente in MANUAL:
        print(f"[{fuente}] {MANUAL[fuente]}")
    if not pendientes and fuente not in MANUAL:
        print(f"[fetch] fuente desconocida: {fuente}")
        return bajados

    fallos: list[tuple[Descarga, str]] = []

    with httpx.Client(follow_redirects=True, timeout=120.0) as cliente:
        for d in pendientes:
            destino = RAW_DIR / d.destino
            destino.parent.mkdir(parents=True, exist_ok=True)
            if destino.exists() and not forzar:
                print(f"[{d.fuente}] cache: {destino.relative_to(RAW_DIR)}")
            else:
                print(f"[{d.fuente}] bajando {d.url}")
                try:
                    with cliente.stream("GET", d.url) as resp:
                        resp.raise_for_status()
                        with destino.open("wb") as fh:
                            for trozo in resp.iter_bytes(chunk_size=65536):
                                fh.write(trozo)
                except httpx.HTTPError as exc:
                    # una URL caida no debe abortar el lote: estos datasets sufren
                    # link rot y el resto de fuentes sigue siendo utilizable
                    destino.unlink(missing_ok=True)
                    fallos.append((d, str(exc).split("\n")[0]))
                    print(f"[{d.fuente}] FALLO: {exc.__class__.__name__} — se continua")
                    continue
                print(f"[{d.fuente}] -> {destino} ({destino.stat().st_size:,} bytes)")
            # los ZIP no se descomprimen: los loaders leen sus CSV como miembros
            # (archivo.Zip). MANTO descomprimido son 5,4 GB y se usan 56 MB.
            bajados.append(destino)

    if fallos:
        print("\n--- descargas fallidas ---")
        for d, error in fallos:
            etiqueta = "opcional" if d.opcional else "REQUERIDA"
            print(f"  [{etiqueta}] {d.url}\n      {error}")
            if d.nota:
                print(f"      nota: {d.nota}")

    for clave, mensaje in MANUAL.items():
        if fuente is None:
            print(f"[{clave}] {mensaje}")

    return bajados
