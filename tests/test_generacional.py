"""Tests de la derivacion generacional y de las etiquetas castellanas.

`_propagar` es una funcion pura sobre diccionarios, asi que se prueba el nucleo
del algoritmo sin base de datos. La semilla real va por ID de MANTO y necesita el
dump cargado; eso se comprueba con `greek load generacional` y las figuras de
control (Heracles 0, Troya 2, Deucalion -5).
"""

from greek.loaders.generacional import _propagar
from greek.loaders.predicados_es import _base, etiqueta


def test_propaga_hacia_los_hijos():
    """hijo = progenitor + 1."""
    res = _propagar({1: (0, "semilla")}, padres={2: {1}}, hijos={1: {2}}, bloqueados=set())
    assert res[2][0] == 1
    assert res[2][1] == 1  # a un salto del ancla


def test_propaga_hacia_los_progenitores():
    """progenitor = hijo - 1: es lo que resuelve las 556 raices que MANTO deja
    sin padres, como Antenor."""
    res = _propagar({2: (2, "semilla")}, padres={2: {1}}, hijos={1: {2}}, bloqueados=set())
    assert res[1][0] == 1


def test_cadena_de_tres_generaciones():
    res = _propagar(
        {1: (0, "semilla")},
        padres={2: {1}, 3: {2}},
        hijos={1: {2}, 2: {3}},
        bloqueados=set(),
    )
    assert (res[2][0], res[3][0]) == (1, 2)


def test_progenitor_bloqueado_no_transmite():
    """El caso Zeus: 68 hijos entre gen -7 y 3. Si transmitiera, el eje temporal
    se aplastaria, asi que sus hijos no heredan generacion por esa via."""
    res = _propagar({1: (-6, "semilla_divina")}, padres={2: {1}}, hijos={1: {2}}, bloqueados={1})
    assert 2 not in res


def test_progenitor_bloqueado_tampoco_recibe_de_sus_hijos():
    """Ni hacia arriba: la divinidad conserva su generacion teogonica, no la que
    implicarian sus hijos mortales."""
    res = _propagar({2: (0, "semilla")}, padres={2: {1}}, hijos={1: {2}}, bloqueados={1})
    assert 1 not in res


def test_el_otro_progenitor_si_transmite():
    """Heracles es hijo de Zeus (bloqueado) y de Alcmena (no): la generacion tiene
    que llegar por la via mortal."""
    res = _propagar(
        {10: (-1, "semilla")},  # Alcmena
        padres={20: {1, 10}},  # Heracles, hijo de Zeus(1) y Alcmena(10)
        hijos={1: {20}, 10: {20}},
        bloqueados={1},  # Zeus
    )
    assert res[20][0] == 0


def test_anclas_discrepantes_dan_la_mediana_y_el_rango():
    """Dos anclas a la misma distancia que implican generaciones distintas: gana
    la mediana y el rango queda registrado. El mito no tiene version canonica."""
    res = _propagar(
        {1: (0, "semilla"), 2: (4, "semilla")},
        padres={3: {1, 2}},
        hijos={1: {3}, 2: {3}},
        bloqueados=set(),
    )
    gen, dist, lo, hi = res[3]
    assert (lo, hi) == (1, 5)
    assert dist == 1
    assert lo <= gen <= hi


def test_el_rango_solo_mira_las_anclas_mas_cercanas():
    """Incluir las lejanas daba [-8, 9] para casi todo y no informaba de nada:
    1.239 de 1.242 entidades salian 'ambiguas'."""
    # 3 es hijo directo de 1 (1 salto) y tataranieto de 2 (3 saltos)
    res = _propagar(
        {1: (0, "semilla"), 2: (0, "semilla")},
        padres={3: {1, 4}, 4: {5}, 5: {2}},
        hijos={1: {3}, 4: {3}, 5: {4}, 2: {5}},
        bloqueados=set(),
    )
    gen, dist, lo, hi = res[3]
    assert dist == 1
    assert (lo, hi) == (1, 1), "la rama de 3 saltos no debe ensanchar el rango"
    assert gen == 1


def test_las_anclas_se_conservan_intactas():
    """Una figura de la semilla nunca cambia de generacion por lo que digan sus
    parientes: es el dato de dominio del que cuelga todo lo demas."""
    res = _propagar(
        {1: (0, "semilla"), 2: (2, "semilla")},
        padres={2: {1}},  # 2 es hijo de 1, lo que implicaria gen 1, no 2
        hijos={1: {2}},
        bloqueados=set(),
    )
    assert res[1][0] == 0
    assert res[2][0] == 2
    assert res[2][1] == 0  # distancia 0: es ancla, no derivada


def test_ciclo_genealogico_no_cuelga():
    """Hay 36 ciclos reales en la base (fuentes que discrepan de quien engendra a
    quien). El recorrido va sobre estados (entidad, generacion), asi que un ciclo
    termina por el tope de saltos en vez de girar para siempre."""
    res = _propagar(
        {1: (0, "semilla")},
        padres={1: {3}, 2: {1}, 3: {2}},
        hijos={3: {1}, 1: {2}, 2: {3}},
        bloqueados=set(),
    )
    assert res[1][0] == 0
    assert 2 in res and 3 in res


# ------------------------------------------------------- etiquetas castellanas


def test_base_quita_las_ranuras_de_argumento():
    assert _base("travels_[from]_[to]_[via]") == "travels"
    assert _base("rules_[direct_obj]") == "rules"
    assert _base("is_child_of") == "is_child_of"


def test_base_con_guiones_bajos_dentro_de_la_ranura():
    """Partir por `_` antes de quitar los corchetes dejaba `invents_alias_/`."""
    assert _base("invents_[fictional_alias_/_agent]") == "invents"
    assert _base("is_moved_[relic_in_historical_period]") == "is_moved"
    assert _base("[non-greek_entity]_is_identified_as_[greek_entity]") == "is_identified_as"


def test_etiqueta_traduce_y_no_deja_corchetes():
    assert etiqueta("is_child_of") == "es hijo de"
    assert etiqueta("has_cult_site_[in/on/at]") == "tiene santuario"
    assert etiqueta("makes_sacrifice_[of]_[ind._obj.]") == "sacrifica"
    assert etiqueta("derives_etymology_[from]") == "toma su nombre de"


def test_etiqueta_desconocida_cae_en_clave_legible():
    assert "[" not in etiqueta("predicado_inventado_[algo]")
    assert etiqueta("predicado_inventado_[algo]") == "predicado inventado"
