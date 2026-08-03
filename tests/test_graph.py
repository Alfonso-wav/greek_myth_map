"""Tests de las funciones puras de la proyeccion a Memgraph.

Solo lo que no necesita servidor: el mapeo predicado -> arista, la promocion del
rol a objeto y la construccion de la cita. La carga en si se comprueba a mano
con `greek graph --wipe` contra el contenedor.
"""

import pytest

from greek.graph import cita_legible, roles_objeto, tipo_arista


@pytest.mark.parametrize(
    ("clave", "esperado"),
    [
        ("is_child_of", "IS_CHILD_OF"),
        ("kills", "KILLS"),
        # los argumentos entre corchetes no son identificadores validos en Cypher
        ("rules_[direct_obj]", "RULES"),
        ("resides_[in/on/at]_[near]", "RESIDES"),
        ("gives_[dir._obj.]_[ind._obj.]", "GIVES"),
        ("has_post-mortem_existence_[in/on/at]", "HAS_POST_MORTEM_EXISTENCE"),
        ("takes_[dir._obj.]_[from]_[to]_[via]", "TAKES"),
        ("[non-greek_entity]_is_identified_as_[greek_entity]", "IS_IDENTIFIED_AS"),
    ],
)
def test_tipo_arista(clave, esperado):
    assert tipo_arista(clave) == esperado


def test_tipo_arista_nunca_vacio():
    """Un tipo de arista vacio es un error de sintaxis Cypher, no una arista sin nombre."""
    assert tipo_arista("[of]") == "REL"
    assert tipo_arista("") == "REL"


@pytest.mark.parametrize(
    ("clave", "esperado"),
    [
        # el rol que ocupa la posicion de objeto lo declara el propio predicado
        ("has_cult_site_[in/on/at]", ["en"]),
        ("travels_[from]_[to]_[via]", ["desde", "hacia", "via"]),
        ("derives_etymology_[from]", ["desde"]),
        ("is_depicted_[depiction:]", ["de"]),
        ("is_metamorphosed_[into]", ["en"]),
        ("gives_birth_[ind.obj]", ["objeto_indirecto"]),
        ("resides_[in/on/at]_[near]", ["en", "cerca_de"]),
        # sin argumentos declarados no hay objeto que promover: son afirmaciones
        # sobre el sujeto y van a `predicados_unarios`
        ("is_mentioned", []),
        ("has_hybrid_form", []),
        ("has_no_children", []),
    ],
)
def test_roles_objeto(clave, esperado):
    assert roles_objeto(clave) == esperado


def test_roles_objeto_sin_duplicar():
    """`[in/on/at]` y `[place]` mapean los dos a `en`: una sola entrada."""
    assert roles_objeto("holds_games_[in/on/at]_[place]") == ["en"]


@pytest.mark.parametrize(
    ("cita", "titulo", "autor", "esperado"),
    [
        # cita desnuda: hay que prefijar autor y obra
        ("1.7", "Apollodoros, Epitome", "Apollodoros", "Apollodoros, Epitome, 1.7"),
        # cita ya completa: prefijar produciria 'Pausanias, Pausanias, Pausanias 2.5.3'
        ("Pausanias 2.5.3", None, "Pausanias", "Pausanias 2.5.3"),
        (
            "Apollodoros, Epitome 1.10",
            "Apollodoros, Epitome",
            "Apollodoros",
            "Apollodoros, Epitome 1.10",
        ),
        ("Lycophron, Alexandra 569-591", "Alexandra", "Lycophron", "Lycophron, Alexandra 569-591"),
        (None, None, "Homer", "Homer"),
        (None, None, None, None),
    ],
)
def test_cita_legible(cita, titulo, autor, esperado):
    assert cita_legible(cita, titulo, autor) == esperado
