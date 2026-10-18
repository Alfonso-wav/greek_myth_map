"""Etiqueta castellana de los 165 predicados de MANTO.

MANTO no publica traduccion, y el loader dejaba en `predicado.nombre_es` la clave
con los guiones bajos cambiados por espacios: `makes sacrifice [of] [ind. obj.]`.
Eso se filtraba tal cual a la web, que esta entera en castellano.

Dos decisiones:

1. **Los corchetes desaparecen de la etiqueta.** En MANTO declaran las ranuras de
   argumento del predicado (`travels_[from]_[to]_[via]`), no forman parte del
   verbo. Esa informacion no se pierde: cada argumento viaja en `relacion_rol`
   con su rol ya en castellano (`desde`, `hacia`, `via`, `en`), y la proyeccion a
   grafo la expone en `rol_objeto`. Repetirla en el verbo solo hacia ruido.
2. **La traduccion es del verbo, en tercera persona y voz activa**, para que la
   frase «Agamenon · gobierna · Micenas» se lea sola. Los pasivos de MANTO
   (`is_depicted`, `is_mentioned`) se mantienen pasivos porque el sujeto es el
   paciente, y cambiarlos invertiria el sentido de la afirmacion.

Aplicar es idempotente: solo hace UPDATE de `nombre_es`.
"""

from __future__ import annotations

import re
import sqlite3

ES: dict[str, str] = {
    # --- genealogia
    "is_child_of": "es hijo de",
    "is_a_descendant_of": "es descendiente de",
    "is_sibling_of": "es hermano de",
    "is_twin_of": "es gemelo de",
    "is_claimed_as_ancestor": "es reclamado como antepasado",
    "has_no_children": "no tiene descendencia",
    "is_mother_by_parthenogenesis_of": "es madre por partenogénesis de",
    # --- union y matrimonio
    "is_spouse_of": "es cónyuge de",
    "marries": "se casa con",
    "has_sex_with": "se une a",
    "gives_in_marriage": "entrega en matrimonio",
    "offers_in_marriage": "ofrece en matrimonio",
    "desires": "desea",
    "rapes": "viola",
    "attempts_to_rape": "intenta violar",
    # --- nacimiento y crianza
    "is_born": "nace",
    "is_born_by_autochthony": "nace de la tierra",
    "gives_birth": "da a luz",
    "raises": "cría",
    "nurses": "amamanta",
    "is_nurse": "es nodriza",
    "exposes": "abandona al nacer",
    # --- muerte
    "kills": "mata a",
    "dies": "muere",
    "dies_by_suicide": "se suicida",
    "buries": "entierra",
    "recovers_the_body_of": "recupera el cuerpo de",
    "has_cenotaph": "tiene cenotafio",
    "has_post-mortem_existence": "pervive tras la muerte",
    "mourns": "llora a",
    "resurrects": "resucita a",
    "becomes_immortal": "se vuelve inmortal",
    "makes_immortal": "vuelve inmortal a",
    # --- guerra
    "fights": "combate contra",
    "attacks": "ataca a",
    "defeats": "derrota a",
    "conquers": "conquista",
    "wounds": "hiere a",
    "blinds": "ciega a",
    "wins_as_war_prize": "gana como botín",
    "warns": "advierte a",
    "sends": "envía a",
    "expels": "expulsa a",
    "imprisons": "encarcela a",
    "captures": "captura a",
    "releases": "libera a",
    "ransoms": "rescata mediante pago a",
    "guards": "guarda",
    "destroys": "destruye",
    "damages": "daña",
    "fortifies": "fortifica",
    "assembles": "reúne",
    "pledges_oath_with": "jura alianza con",
    "plots_against": "conspira contra",
    "threatens": "amenaza a",
    "quarrels_with": "riñe con",
    "offends": "ofende a",
    "insults": "insulta a",
    "mistreats": "maltrata a",
    "punishes": "castiga a",
    "curses": "maldice a",
    "drives_insane": "enloquece a",
    "deceives": "engaña a",
    "hinders": "estorba a",
    "puts_on_trial": "juzga a",
    "tests": "pone a prueba a",
    # --- politica y oficio
    "rules": "gobierna",
    "rules_as_eponym": "gobierna como epónimo",
    "is_lawgiver": "es legislador",
    "succeeds": "sucede en el trono",
    "leads": "acaudilla a",
    "speaks_in_assembly": "habla en la asamblea",
    "is_herald": "es heraldo",
    "is_charioteer": "es auriga",
    "is_helmsman": "es timonel",
    "is_teacher": "es maestro",
    "teaches": "enseña a",
    "is_healer": "es sanador",
    "heals": "sana a",
    "is_slave": "es esclavo",
    "sells_as_slave": "vende como esclavo a",
    "is_member_of": "pertenece a",
    "hosts": "hospeda a",
    "helps": "ayuda a",
    "requests_help": "pide ayuda a",
    "rescues": "rescata a",
    "protects": "protege a",
    "performs": "actúa",
    # --- fundacion y asentamiento
    "founds": "funda",
    "founds_as_eponym": "funda como epónimo",
    "is_eponym_of": "da nombre a",
    "settles": "se asienta en",
    "creates_humans": "crea a los hombres",
    "names": "pone nombre a",
    "changes_name_to": "cambia su nombre a",
    "changes_name_of": "cambia el nombre de",
    "derives_etymology": "toma su nombre de",
    # --- movimiento
    "travels": "viaja",
    "visits": "visita",
    "migrates": "emigra",
    "flees": "huye",
    "pursues": "persigue a",
    "searches_for": "busca a",
    "abducts": "rapta a",
    "takes": "se lleva",
    "crosses": "cruza",
    "goes_past": "pasa de largo por",
    "shipwrecks": "naufraga",
    "disappears": "desaparece",
    "hides": "se esconde",
    "abandons": "abandona a",
    "encounters": "se encuentra con",
    # --- geografia
    "resides": "reside",
    "is_located": "se ubica",
    "is_identified": "se identifica",
    "flows_into": "desemboca en",
    "is_entrance_to": "es entrada a",
    # --- culto
    "has_cult_site": "tiene santuario",
    "establishes_cult": "instaura el culto",
    "develops_cult": "desarrolla el culto",
    "initiates_into_cult": "inicia en el culto",
    "is_priest": "es sacerdote",
    "is_divine_patron": "es patrón divino",
    "makes_sacrifice": "sacrifica",
    "dedicates": "dedica",
    "offers": "ofrece",
    "purifies": "purifica a",
    "is_a_relic": "es reliquia",
    "is_moved": "es trasladada en época histórica",
    "appears_in_an_epiphany": "se aparece",
    "appears_in_an_epiphany_in_the_historical_period": "se aparece en época histórica",
    # --- profecia y dones
    "gives_prophecy": "profetiza",
    "is_prophet": "es profeta",
    "grants_power_of_prophecy": "concede el don profético",
    "grants_superhuman_power": "concede poder sobrehumano",
    "gives": "da",
    "gives_something": "entrega",
    "gives_special_gift": "hace un don extraordinario",
    "invents": "inventa",
    "creates": "crea",
    "possesses": "posee",
    "consumes": "consume",
    "bathes": "se baña en",
    "hunts": "caza",
    "holds": "celebra",
    "discards": "descarta",
    # --- competicion
    "competes": "compite",
    "wins_in_competition": "vence en la competición a",
    "holds_games": "celebra juegos",
    "establishes_games": "instituye juegos",
    # --- forma y transformacion
    "is_metamorphosed": "es metamorfoseado",
    "metamorphoses": "metamorfosea a",
    "takes_form_of": "toma la forma de",
    "has_hybrid_form": "tiene forma híbrida",
    "has_monstrous_form": "tiene forma monstruosa",
    # --- identidad y representacion
    "is_identified_as": "se identifica con",
    "[non-greek_entity]_is_identified_as_[greek_entity]": "se identifica con la figura griega",
    "is_alternative_name_for": "es otro nombre de",
    "is_conflated_with": "se confunde con",
    "is_compared_to": "se compara con",
    "is_contemporary_of": "es contemporáneo de",
    "is_associated_with": "se asocia con",
    "is_depicted": "es representado",
    "is_mentioned": "es mencionado",
    "comes_into_being": "surge",
}


def _base(clave: str) -> str:
    """Clave sin las ranuras de argumento: `travels_[from]_[to]_[via]` -> `travels`.

    El regex va sobre la cadena entera y no partiendo por `_`: hay ranuras que
    llevan guiones bajos dentro (`[fictional_alias_/_agent]`,
    `[relic_in_historical_period]`) y trocear primero dejaba pedazos sueltos
    como `invents_alias_/`.
    """
    sin_ranuras = re.sub(r"\[[^\]]*\]", "", clave)
    return re.sub(r"_+", "_", sin_ranuras).strip("_") or clave


def etiqueta(clave: str) -> str:
    """Etiqueta castellana; si no hay traduccion, la clave legible sin corchetes."""
    if clave in ES:
        return ES[clave]
    base = _base(clave)
    if base in ES:
        return ES[base]
    return base.replace("_", " ")


def cargar(con: sqlite3.Connection) -> str:
    filas = con.execute("SELECT id, clave FROM predicado").fetchall()
    traducidos = sin_traducir = 0
    faltan: list[str] = []
    for f in filas:
        clave = f["clave"]
        es = etiqueta(clave)
        con.execute("UPDATE predicado SET nombre_es = ? WHERE id = ?", (es, f["id"]))
        if clave in ES or _base(clave) in ES:
            traducidos += 1
        else:
            sin_traducir += 1
            faltan.append(clave)
    con.commit()
    aviso = f" · sin traducir: {', '.join(faltan[:5])}" if faltan else ""
    return (
        f"predicados_es: {traducidos}/{len(filas)} predicados con etiqueta castellana, "
        f"{sin_traducir} en clave legible{aviso}"
    )
