from greek.normalize import (
    bloque,
    limpiar,
    normalizar,
    normalizar_base,
    numeros,
    variantes_bloque,
)


def test_idempotente():
    for nombre in ("Kirke", "Áyax", "Ἀχιλλεύς", "Ifis (hijo de Alector)"):
        una = normalizar(nombre)
        assert normalizar(una) == una


def test_pliegues_grc_lat_convergen():
    # el objetivo del fuzzy join: las tres convenciones caen en la misma clave
    assert normalizar("Kirke") == normalizar("Circe")
    assert normalizar("Ouranos") == normalizar("Uranus") == normalizar("Urano")
    assert normalizar("Kirke") == normalizar("Κίρκη")
    # 'Aigeus'/'Egeo' NO convergen del todo: eso lo resuelve la banda 88-94 del
    # fuzzy join, no la normalizacion. Documentado a proposito.


def test_diacriticos_y_griego():
    assert normalizar("Áyax") == normalizar("Ayax")
    assert normalizar("Ἀχιλλεύς")  # no vacio: unidecode transliteró


def test_desambiguador_se_conserva_al_comparar():
    # el parentesis distingue lugares homonimos: no puede desaparecer de la clave
    assert normalizar("Kastri (Euboea)") != normalizar("Kastri (Serres)")
    assert normalizar("Ifis (hijo de Alector)") != normalizar("Ifis")
    # solo se descarta para agrupar homonimos
    assert limpiar("Ifis (hijo de Alector)") == "Ifis"
    assert normalizar_base("Kastri (Euboea)") == normalizar_base("Kastri (Serres)")


def test_numeros_son_significativos():
    assert numeros("Tower 7") != numeros("Tower 11")
    assert numeros("Germania I") != numeros("Germania II")
    assert numeros("Kastri 1") == ("1",)
    assert numeros("Delphi") == ()


def test_nombres_distintos_no_colisionan():
    assert normalizar("Heracles") != normalizar("Perseo")
    assert normalizar("Atenea") != normalizar("Artemisa")


def test_vacio():
    assert normalizar(None) == ""
    assert normalizar("") == ""
    assert bloque("") == ""
    assert variantes_bloque("") == ()


def test_bloque_incluye_su_propia_variante():
    n = normalizar("Agamenon")
    assert bloque(n) in variantes_bloque(n)
