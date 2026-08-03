"""Forma normalizada de nombres: la clave de comparacion del fuzzy join.

Nunca se almacena como `entidad.nombre` — solo en `entidad.nombre_norm`, y solo
para comparar. El nombre canonico lo elige fuzzy.elegir_canonico().

Los pliegues grc->lat existen para que las tres convenciones que conviven en las
fuentes converjan:  Kirke (Theoi) ~ Circe (Wikipedia) ~ Kirke/Circe (MANTO).
"""

from __future__ import annotations

import re
import unicodedata

from unidecode import unidecode

# Pliegues aplicados en orden. Convierten transliteracion griega a la forma
# latina/castellana que usamos como canonica.
_DIGRAFOS: tuple[tuple[str, str], ...] = (
    ("kh", "c"),
    ("ch", "c"),
    ("th", "t"),
    ("ph", "f"),
    ("ps", "s"),
    ("rh", "r"),
    ("ai", "e"),
    ("ae", "e"),
    ("oi", "e"),
    ("oe", "e"),
    ("ei", "i"),
    ("ou", "u"),
    ("eu", "u"),
    ("k", "c"),
    ("y", "i"),
    ("z", "s"),
    ("w", "v"),
)

# Sufijos: -os/-us/-o -> -o ; -es/-is/-e -> -es. Colapsa Ouranos/Uranus/Urano.
_SUFIJOS: tuple[tuple[str, str], ...] = (
    ("os", "o"),
    ("us", "o"),
    ("on", "o"),
    ("um", "o"),
    ("es", "es"),
    ("is", "es"),
    ("as", "as"),
)

_PARENTESIS = re.compile(r"\s*[\(\[][^)\]]*[\)\]]")
_DESAMB = re.compile(r"\s*,\s*(hijo|hija|rey|reina|padre|madre|el|la)\b.*$", flags=re.IGNORECASE)
_NO_ALNUM = re.compile(r"[^a-z0-9 ]+")
# Designadores: cifras ('Tower 7'), numerales romanos ('Germania II') y letras
# sueltas ('Basilica D', 'Building Y', 'Fykti W blockhouse'). Todos identifican
# una entidad concreta dentro de una serie y no admiten aproximacion.
_DESIGNADOR = re.compile(r"(?<![^\W_])(\d+|[A-Za-z])(?![^\W_])")
_ESPACIOS = re.compile(r"\s+")
_REPETIDAS = re.compile(r"(.)\1+")


def sin_diacriticos(texto: str) -> str:
    """Transliteracion a ASCII + quita diacriticos.

    unidecode se aplica siempre: el griego politonico esta en U+0370-U+03FF, por
    debajo de cualquier umbral 'exotico', asi que condicionarlo por rango dejaba
    'Ἀχιλλεύς' en griego y el filtro [^a-z] posterior lo vaciaba.
    """
    desc = unicodedata.normalize("NFD", unidecode(texto))
    return "".join(c for c in desc if unicodedata.category(c) != "Mn")


def limpiar(nombre: str) -> str:
    """Nombre legible sin desambiguadores: 'Ifis (hijo de Alector)' -> 'Ifis'.

    Solo para agrupar homonimos (`homonimo_grupo`), NUNCA para comparar: el
    parentesis es justo lo que distingue 'Kastri (Euboea)' de 'Kastri (Serres)'.
    """
    n = _PARENTESIS.sub("", nombre)
    n = _DESAMB.sub("", n)
    return _ESPACIOS.sub(" ", n).strip()


def normalizar(nombre: str | None) -> str:
    """Clave de comparacion. Idempotente: normalizar(normalizar(x)) == normalizar(x).

    CONSERVA el desambiguador entre parentesis. Descartarlo fusionaba lugares
    distintos: 'Kastri (Euboea)' y 'Kastri (Serres)' colapsaban al mismo 'kastri'
    y el fuzzy join los unia con score 100.
    """
    if not nombre:
        return ""

    n = sin_diacriticos(nombre).lower()
    n = _NO_ALNUM.sub(" ", n)
    n = _ESPACIOS.sub(" ", n).strip()
    if not n:
        return ""

    return " ".join(_plegar(p) for p in n.split(" "))


def normalizar_base(nombre: str | None) -> str:
    """Clave para agrupar homonimos: normalizada Y sin desambiguador."""
    return normalizar(limpiar(nombre or ""))


def numeros(nombre: str | None) -> tuple[str, ...]:
    """Designadores del nombre, en minusculas. 'Basilica D' -> ('d',).

    Son significativos y no admiten aproximacion: 'Tower 7' / 'Tower 11',
    'Germania I' / 'Germania II', 'Basilica A' / 'Basilica D' y 'Building Y' /
    'Building Z' son entidades distintas por definicion, aunque el resto de la
    cadena sea identico y el score roce 100.
    """
    return tuple(sorted(m.lower() for m in _DESIGNADOR.findall(nombre or "")))


def _plegar(palabra: str, max_pasadas: int = 6) -> str:
    """Aplica los pliegues hasta punto fijo.

    Iterar es lo que hace `normalizar` idempotente: una sola pasada dejaba
    'ayax' -> 'aiax' (y->i) y una segunda lo movia a 'eax' (ai->e), asi que
    normalizar(normalizar(x)) != normalizar(x).
    """
    p = palabra
    for _ in range(max_pasadas):
        previo = p
        for viejo, nuevo in _DIGRAFOS:
            p = p.replace(viejo, nuevo)
        for viejo, nuevo in _SUFIJOS:
            if len(p) > len(viejo) + 1 and p.endswith(viejo):
                p = p[: -len(viejo)] + nuevo
                break
        p = _REPETIDAS.sub(r"\1", p)  # akhilleus -> achileus
        if p == previo:
            break
    return p


PREFIJO_BLOQUE = 3


def bloque(nombre_norm: str) -> str:
    """Clave de bloqueo para el fuzzy join: prefijo de la forma NORMALIZADA.

    Sin bloqueo, comparar 42.000 entidades son ~900M pares. Bloquear por inicial
    + longitud daba 7,1M pares (295 s), casi todos ruido. El prefijo de 3 deja
    decenas de miles.

    Es seguro porque la normalizacion ya hizo el trabajo pesado: 'Kirke' y
    'Circe' comparten prefijo ('cir') DESPUES de plegar, igual que 'Ouranos' y
    'Urano' ('ura'). El coste conocido es que pares que difieren en los 3
    primeros caracteres no se comparan ('achileus' vs 'aquiles'); esos se
    reconcilian por QID de Wikidata, no por fuzzy. Bajar el prefijo devuelve el
    coste cuadratico.
    """
    return nombre_norm[:PREFIJO_BLOQUE]


def variantes_bloque(nombre_norm: str) -> tuple[str, ...]:
    """Bloques en los que hay que indexar este nombre."""
    if not nombre_norm:
        return ()
    return (bloque(nombre_norm),)
