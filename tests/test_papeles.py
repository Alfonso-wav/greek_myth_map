"""Tests de la clasificacion por papel.

`papeles_por_descripcion` es la regla de mas peso (la descripcion manda) y es
pura, asi que se prueba sola. Las reglas por predicado necesitan el dump y se
comprueban con `greek load papeles` contra 38 figuras de control.
"""

from greek.loaders.papeles import EXCLUYENTES, papeles_por_descripcion


def papeles(descripcion: str) -> set[str]:
    return {p for p, _ in papeles_por_descripcion(descripcion)}


def test_dios_y_diosa():
    assert papeles("diosa de la sabiduría y la guerra en la mitología griega") == {"dios"}
    assert papeles("dios de la profecía, luz y música en la mitología grecorromana") == {"dios"}


def test_dios_solo_en_singular():
    """El plural "de los dioses" NO cuenta, a proposito: es un genitivo y lo
    llevan mortales — Ganimedes es "copero de los dioses" y no es un dios. Zeus,
    cuya ficha dice "rey de los dioses", recibe `dios` de la semilla divina, que
    es dato de dominio y no depende de como este redactada la descripcion."""
    assert papeles("rey de los dioses en la mitología griega") == {"gobernante"}
    assert papeles("copero de los dioses") == set()
    assert papeles("dios del mar") == {"dios"}


def test_semidios_va_a_heroe_no_a_dios():
    """Heracles es "semidiós ... que realizó los doce trabajos" y el filtro de
    héroes tiene que encontrarlo."""
    assert papeles("semidiós de la mitología griega que realizó los doce trabajos") == {"heroe"}


def test_heroe():
    assert papeles("héroe principal de la guerra de Troya") == {"heroe"}


def test_liderar_una_expedicion_no_es_gobernar():
    """Jason es "heroe y lider de los argonautas": capitanea una expedicion, no
    reina. Solo `lider del ejercito` cuenta como gobierno (es la ficha de
    Agamenon, que manda sobre reyes)."""
    assert papeles("héroe y líder de los argonautas") == {"heroe"}
    assert papeles("líder del ejército griego durante la guerra de Troya") == {"gobernante"}


def test_rey():
    assert papeles("rey de Creta en la mitología griega") == {"gobernante"}
    assert papeles("último rey de Troya en la mitología griega") == {"gobernante"}


def test_monstruo():
    assert papeles("monstruo mitad toro, mitad hombre, de la mitología griega") == {"monstruo"}
    assert papeles("monstruo primordial de la mitología griega") == {"monstruo"}


def test_el_monstruo_de_la_frase_no_es_el_sujeto():
    """"héroe que mató a Medusa" o "...la Quimera": el monstruo es la victima, no
    la figura descrita. Belerofonte salia clasificado como monstruo."""
    assert papeles("héroe que montó a Pegaso y mató a la Quimera") == {"heroe"}
    assert papeles("rey mitológico de Atenas y matador del Minotauro") == {"gobernante"}


def test_personificacion_y_ninfa_son_dioses():
    assert "dios" in papeles("personificación de la luna en la mitología griega")
    assert "dios" in papeles("nereida, madre de Aquiles")


def test_titan_es_dios():
    assert "dios" in papeles("titán que robó el fuego a los dioses")


def test_ingles_tambien():
    """Parte de las descripciones de Wikidata no estan traducidas."""
    assert "dios" in papeles("goddess of the hunt in Greek mythology")
    assert "heroe" in papeles("hero of the Trojan war")
    assert "gobernante" in papeles("king of Athens")


def test_descripcion_sin_papel():
    """"padre de Teseo" no dice que es: se deja a las reglas por predicado."""
    assert papeles("padre de Teseo en la mitología griega") == set()
    assert papeles("hija de Eetes en la mitología griega") == set()


def test_dios_y_monstruo_son_excluyentes_los_demas_no():
    assert {"dios", "monstruo"} == EXCLUYENTES
    assert "gobernante" not in EXCLUYENTES
    assert "heroe" not in EXCLUYENTES


def test_profeta_y_artesano_son_acumulables():
    assert papeles("adivino de la mitología griega") == {"profeta"}
    assert "artesano" in papeles("dios herrero de la mitología griega")
    assert "dios" in papeles("dios herrero de la mitología griega")
