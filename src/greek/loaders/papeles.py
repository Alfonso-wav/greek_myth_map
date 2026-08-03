"""Papel de cada agente: dios, heroe, gobernante, monstruo. Derivado.

MANTO no publica el tipo fino: todo agente es `Agent`, y `genero`/`es_mortal`
quedan a NULL. Hay que inferirlo, y la inferencia ingenua se equivoca en las
figuras mas importantes del corpus. Estas cuatro trampas estan comprobadas contra
figuras de control, no supuestas:

1. **Al heroe se le rinde culto igual que al dios.** Recibir sacrificio
   (`makes_sacrifice` con rol `objeto_indirecto`), tener sacerdote (`is_priest
   [of]`), que alguien instaure tu culto (`establishes_cult [of]`) o ser patron de
   algo (`is_divine_patron [of]`) marcaba como dioses a Heracles, Aquiles, Odiseo,
   Jason, Neoptolemo, Edipo y Pelope. Esas senales no son de divinidad: son de
   **culto**, y en Grecia el culto heroico es masivo. Aqui se usan al reves, como
   indicio de heroe.
2. **Los heroes se aparecen.** `appears_in_an_epiphany` lo tienen Aquiles,
   Heracles y Teseo — la epifania post mortem del heroe esta historicamente
   atestiguada (Teseo en Maraton). No sirve para distinguir dios.
3. **Los monstruos matan.** Definir heroe como "sujeto de predicado belico o de
   muerte" metia al Minotauro, a Escila y a Tifon entre los heroes.
4. **Los dioses gobiernan dominios.** `rules [direct obj]` lo tienen Zeus y Hades
   (el Hades, el reino). Sin precedencia, "gobernante" se llenaba de olimpicos y
   dejaba de servir para encontrar reyes.

De ahi la regla de oro: **la descripcion de Wikidata manda y los predicados solo
rellenan huecos.** La descripcion es texto humano y precisa ("diosa de la
sabiduria", "heroe principal de la guerra de Troya", "rey de Creta", "monstruo
mitad toro"), cubre 1.006 de los 5.353 agentes, y resuelve sola todas las figuras
que las reglas por predicado se comian.
"""

from __future__ import annotations

import re
import sqlite3

from ..db import SQL_DIR

# --------------------------------------------------------------- descripciones
# Se aplican en este orden; una descripcion puede disparar varios papeles
# ("rey de los dioses" -> dios + gobernante, que es exactamente lo que Zeus es).
PATRONES_DESC: list[tuple[str, str]] = [
    ("dios", r"\b(dios|diosa|deidad|divinidad|god|goddess)\b"),
    ("dios", r"\b(olimpic|olímpic|titan|titán|titanid|ninfa|náyade|nayade|nereida|oceánide|"
             r"oceanide|musa|nymph|personificaci[oó]n|personification)\w*"),
    # semidios -> heroe, no dios: Heracles es "semidios ... que realizo los doce
    # trabajos" y el filtro de heroes tiene que encontrarlo
    ("heroe", r"\b(semidi[oó]s|semidiosa|demigod)\b"),
    ("heroe", r"\b(h[eé]roe|hero[íi]na|\bhero\b|heroine)\b"),
    ("gobernante", r"\b(rey|reina|monarca|soberan\w+|gobernant\w+|king|queen|ruler)\b"),
    ("gobernante", r"\b(caudillo|l[íi]der del ej[eé]rcito|fundador\w*|founder)\b"),
    ("monstruo", r"\b(monstruo|monster|criatura|creature|drag[oó]n|dragon|quimera|"
                 r"c[íi]clope|cyclops|centauro|centaur|gigante|giant|serpiente)\b"),
    ("profeta", r"\b(adivino|profeta|profetisa|vidente|seer|prophet|or[áa]culo)\b"),
    ("artesano", r"\b(artesano|herrero|arquitecto|inventor|craftsman|smith)\b"),
]

# ------------------------------------------------------------------ predicados
# Predicados que SOLO un dios ejerce como sujeto. Comprobados uno a uno contra 13
# heroes de control: contaminacion cero. `appears_in_an_epiphany` esta fuera a
# proposito (ver trampa 2 del docstring).
PRED_DIOS = (
    "is_divine_patron%",
    "grants_power_of_prophecy%",
    "grants_superhuman_power%",
    "makes_immortal%",
    "gives_prophecy%",
)

# Recibir culto. NO es senal de divinidad (trampa 1): con la precedencia
# dios-primero, lo que queda marcado aqui es culto heroico.
CULTO_ROL: tuple[tuple[tuple[str, ...], str], ...] = (
    (("makes_sacrifice%", "dedicates%", "offers%"), "objeto_indirecto"),
    (("is_priest%", "establishes_cult%", "develops_cult%", "initiates_into_cult%"), "de"),
    (("is_divine_patron%",), "de"),
)
CULTO_SUJETO = ("has_cenotaph%", "is_claimed_as_ancestor%", "appears_in_an_epiphany%")

CAT_GOBIERNO = ("politica",)
PRED_GOBIERNO = ("founds", "founds_as_eponym%", "succeeds%")
CAT_HEROICA = ("belica", "muerte")
PRED_MONSTRUO = ("has_hybrid_form", "has_monstrous_form")
PRED_DEIFICADO = ("becomes_immortal",)


def _sujetos(con: sqlite3.Connection, patrones: tuple[str, ...]) -> set[int]:
    out: set[int] = set()
    for p in patrones:
        out |= {
            f[0]
            for f in con.execute(
                "SELECT DISTINCT r.sujeto_id FROM relacion r "
                "JOIN predicado p ON p.id = r.predicado_id WHERE p.clave LIKE ?",
                (p,),
            )
        }
    return out


def _sujetos_cat(con: sqlite3.Connection, cats: tuple[str, ...]) -> set[int]:
    marcas = ",".join("?" * len(cats))
    return {
        f[0]
        for f in con.execute(
            "SELECT DISTINCT r.sujeto_id FROM relacion r "
            f"JOIN predicado p ON p.id = r.predicado_id WHERE p.categoria IN ({marcas})",
            cats,
        )
    }


def _en_rol(con: sqlite3.Connection, patrones: tuple[str, ...], rol: str) -> set[int]:
    out: set[int] = set()
    for p in patrones:
        out |= {
            f[0]
            for f in con.execute(
                "SELECT DISTINCT rr.entidad_id FROM relacion_rol rr "
                "JOIN relacion r ON r.id = rr.relacion_id "
                "JOIN predicado p ON p.id = r.predicado_id "
                "WHERE p.clave LIKE ? AND rr.rol = ? AND rr.entidad_id IS NOT NULL",
                (p, rol),
            )
        }
    return out


#: `dios` y `monstruo` son afirmaciones de identidad EXCLUYENTE: o eres un dios o
#: no lo eres. `gobernante`, `heroe`, `profeta` y `artesano` son papeles que se
#: acumulan (Odiseo es rey Y heroe). La diferencia decide quien puede pisar a
#: quien: una descripcion humana gana a un predicado en las excluyentes, pero no
#: impide que un predicado anada un papel acumulable.
EXCLUYENTES = frozenset({"dios", "monstruo"})


def papeles_por_descripcion(descripcion: str) -> list[tuple[str, str]]:
    """[(papel, regla)] segun el texto de la descripcion.

    `monstruo` no se asigna si el mismo texto ya dijo dios, heroe o gobernante: la
    descripcion de Belerofonte es "heroe que monto a Pegaso y mato a la Quimera" y
    el patron capturaba a la Quimera, que es su victima, no lo que el es.
    """
    texto = descripcion.lower()
    salida: list[tuple[str, str]] = []
    vistos: set[str] = set()
    for papel, patron in PATRONES_DESC:
        if papel in vistos:
            continue
        m = re.search(patron, texto)
        if not m:
            continue
        if papel == "monstruo" and vistos & {"dios", "heroe", "gobernante"}:
            continue
        vistos.add(papel)
        salida.append((papel, f"descripcion:{m.group(0)[:24]}"))
    return salida


def cargar(con: sqlite3.Connection) -> str:
    con.executescript((SQL_DIR / "005_papeles.sql").read_text(encoding="utf-8"))
    con.commit()

    agentes = {
        f["id"]: f["descripcion"]
        for f in con.execute(
            "SELECT e.id, e.descripcion FROM entidad e "
            "JOIN tipo_entidad t ON t.id = e.tipo_entidad_id "
            "WHERE t.clave IN ('agente', 'colectivo')"
        )
    }
    no_transmite = {
        f[0] for f in con.execute("SELECT entidad_id FROM entidad_generacion WHERE transmite = 0")
    }
    con_generacion = {f[0] for f in con.execute("SELECT entidad_id FROM entidad_generacion")}

    pred_dios = _sujetos(con, PRED_DIOS) & set(agentes)
    monstruosos = _sujetos(con, PRED_MONSTRUO) & set(agentes)
    deificados = _sujetos(con, PRED_DEIFICADO) & set(agentes)
    gobierno = (
        _sujetos_cat(con, CAT_GOBIERNO) | _sujetos(con, PRED_GOBIERNO)
    ) & set(agentes)
    heroico = _sujetos_cat(con, CAT_HEROICA) & set(agentes)
    culto = _sujetos(con, CULTO_SUJETO) & set(agentes)
    for patrones, rol in CULTO_ROL:
        culto |= _en_rol(con, patrones, rol) & set(agentes)

    filas: list[tuple[int, str, str, str]] = []
    for eid, descripcion in agentes.items():
        papeles: dict[str, tuple[str, str]] = {}  # papel -> (regla, confianza)

        # 1. la descripcion manda
        if descripcion:
            for papel, regla in papeles_por_descripcion(descripcion):
                papeles[papel] = (regla, "alta")
        # ¿dijo la descripcion algo? Entonces las reglas por predicado no pueden
        # cambiar su identidad, solo anadirle papeles acumulables.
        descrito = bool(papeles)

        # 2. divinidad. La semilla es dato de dominio y vale siempre. El predicado
        #    solo si nadie describio la figura: `gives_prophecy` no es tan
        #    exclusivo como parecia — Quiron es un centauro y profetiza, y la regla
        #    lo convertia en dios pisando su propia descripcion.
        if "dios" not in papeles:
            if eid in no_transmite:
                papeles["dios"] = ("semilla_divina", "alta")
            elif eid in pred_dios and not descrito:
                papeles["dios"] = ("predicado:solo_divino", "media")

        es_dios = "dios" in papeles

        # 3. monstruo por forma, solo sin descripcion: `has_hybrid_form` como
        #    sujeto lo tienen tambien Heracles, Teseo y Egeo, y a esos tres su
        #    ficha ya los llama semidios y rey.
        if eid in monstruosos and not es_dios and not descrito:
            papeles.setdefault("monstruo", ("predicado:forma_monstruosa", "media"))

        es_monstruo = "monstruo" in papeles

        # 4. gobernante. Por predicado solo si NO es dios: `rules [direct obj]` lo
        #    tienen Zeus y Hades sobre sus dominios, y eso llenaba el filtro de
        #    olimpicos. Por descripcion si vale para un dios: Zeus es literalmente
        #    "rey de los dioses".
        #    Ser monstruo NO lo impide: Egeo gobierna Atenas seis veces y ademas
        #    tiene `has_monstrous_form`, que en la tradicion de los reyes
        #    autoctonos atenienses es su aspecto serpentino. Igual Midas y Ammon.
        if eid in gobierno and "gobernante" not in papeles and not es_dios:
            papeles["gobernante"] = ("predicado:gobierno", "media")

        # 5. heroe: mortal con agencia belica, o con culto heroico. Nunca dios ni
        #    monstruo — los monstruos tambien matan (trampa 3).
        if "heroe" not in papeles and not es_dios and not es_monstruo:
            if eid in heroico and eid in con_generacion:
                papeles["heroe"] = ("predicado:belica_o_muerte", "media")
            elif eid in culto:
                papeles["heroe"] = ("culto_heroico", "baja")

        # 6. deificado: mortal que se vuelve inmortal. Etiqueta extra, no excluye
        if eid in deificados:
            papeles.setdefault("deificado", ("predicado:becomes_immortal", "alta"))

        for papel, (regla, confianza) in papeles.items():
            filas.append((eid, papel, regla, confianza))

    con.execute("DELETE FROM entidad_papel")
    con.executemany(
        "INSERT OR IGNORE INTO entidad_papel (entidad_id, papel, regla, confianza) "
        "VALUES (?, ?, ?, ?)",
        filas,
    )
    con.commit()

    cuenta = dict(
        con.execute("SELECT papel, COUNT(*) FROM entidad_papel GROUP BY 1 ORDER BY 2 DESC")
    )
    con_papel = con.execute("SELECT COUNT(DISTINCT entidad_id) FROM entidad_papel").fetchone()[0]
    detalle = " · ".join(f"{k} {v}" for k, v in cuenta.items())
    return (
        f"papeles: {con_papel} de {len(agentes)} agentes clasificados "
        f"({con_papel * 100 // max(len(agentes), 1)} %) — {detalle}"
    )
