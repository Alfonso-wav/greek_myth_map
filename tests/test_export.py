"""Tests del export a la web: enlaces a los textos y clave de busqueda."""

from greek.export import clave_busqueda, enlace_pasaje

SCAIFE = "https://scaife.perseus.org/reader/"


def test_scaife_url_directo_gana():
    """Es el enlace exacto al pasaje: 3.497 de los 6.950 pasajes citados."""
    assert enlace_pasaje(f"{SCAIFE}urn:x:1.3", "urn:y", "urn:z", "1.3") == f"{SCAIFE}urn:x:1.3"


def test_cts_urn_de_pasaje():
    assert enlace_pasaje(None, "urn:cts:greekLit:tlg0012.tlg001:1.1", None, None) == (
        f"{SCAIFE}urn:cts:greekLit:tlg0012.tlg001:1.1"
    )


def test_reconstruido_desde_el_urn_de_la_obra():
    """`Homer, Iliad 2.459-2.466` -> el URN de la obra mas la referencia final."""
    u = enlace_pasaje(
        None, None, "urn:cts:greekLit:tlg0012.tlg001.perseus-eng3", "Homer, Iliad 2.459-2.466"
    )
    assert u == f"{SCAIFE}urn:cts:greekLit:tlg0012.tlg001.perseus-eng3:2.459-2.466"


def test_reconstruido_con_cita_desnuda():
    assert enlace_pasaje(None, None, "urn:obra", "3.29-3.30") == f"{SCAIFE}urn:obra:3.29-3.30"
    assert enlace_pasaje(None, None, "urn:obra", "Vergil, Eclogues 9") == f"{SCAIFE}urn:obra:9"


def test_normaliza_el_guion_largo_y_los_espacios():
    """Las citas traen guion largo y espacios que Scaife no acepta en la ref."""
    assert enlace_pasaje(None, None, "urn:obra", "1.1 – 1.9") == f"{SCAIFE}urn:obra:1.1-1.9"


def test_sin_enlace_cuando_la_obra_no_tiene_urn():
    """Estrabon, Plinio, Diodoro y los escolios no tienen CTS URN: 3.308 pasajes
    se quedan sin enlace a proposito. Un enlace roto es peor que ninguno."""
    assert enlace_pasaje(None, None, None, "Strabo 9.2.27") is None
    assert enlace_pasaje(None, None, None, None) is None


def test_sin_enlace_si_la_cita_no_tiene_referencia_numerica():
    assert enlace_pasaje(None, None, "urn:obra", "Hesiod, Ehoiai fragmenta") is None


# ------------------------------------------------------------------ busqueda


def test_clave_incluye_transliteracion_y_forma_cruda():
    """La busqueda es SUBCADENA sobre las formas atestiguadas, no aproximada.

    `unidecode` transcribe khi como `kh`, asi que Ἀχιλλεύς entra al pajar como
    `akhilleus` — teclear `akhilleus` lo encuentra y `achilleus` no, porque esa
    grafia no la atestigua ninguna fuente del corpus. El limite es deliberado: el
    pajar trae todas las variantes reales (`Achilles`, `Kirke`, `Κίρκη`) y con eso
    basta, mientras que aproximar exigiria reimplementar en TypeScript los
    pliegues griego->latin de normalize.py, que se desincronizarian.
    """
    k = clave_busqueda("Achilles", "Ἀχιλλεύς")
    assert "achilles" in k
    assert "akhilleus" in k  # unidecode del griego
    assert "ἀχιλλεύς" in k  # forma cruda en minusculas


def test_clave_junta_las_variantes():
    """El pajar trae todas las variantes atestiguadas, asi que la busqueda puede
    ser una subcadena simple y no hay que reimplementar los pliegues de
    normalize.py en TypeScript."""
    k = clave_busqueda("Circe", "Circe", "Kirke", "Κίρκη")
    assert "kirke" in k
    assert "circe" in k


def test_clave_deduplica_palabras():
    """Las variantes repiten el nombre principal; sin deduplicar eran 1,1 MB de
    JSON sin ninguna coincidencia nueva."""
    k = clave_busqueda("Circe", "Circe", "Circe", "Kirke")
    assert k.split().count("circe") == 1


def test_clave_ignora_los_nulos_y_los_vacios():
    assert clave_busqueda(None, "", None) == ""
    assert clave_busqueda(None, "Zeus") == "zeus"


def test_clave_quita_la_puntuacion_de_los_cualificadores():
    """Los nombres llevan cualificador entre parentesis (`Zeus (Olympian)`) y sin
    limpiar quedaba el token `(olympian)`, que no casa al teclear `olympian`."""
    k = clave_busqueda("Zeus (Olympian)")
    assert "olympian" in k.split()
