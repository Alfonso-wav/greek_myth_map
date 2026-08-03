"""Proyeccion de greek.db a Memgraph, para explorarla desde Memgraph Lab.

Memgraph es **solo lectura y desechable**: la autoridad es `data/greek.db`. Toda
la proyeccion se reconstruye con `greek graph --wipe`, asi que no hay migraciones
ni estado que preservar aqui.

Decisiones del modelo, todas con motivo:

1. **Aristas directas, no relaciones reificadas.** `relacion` (sujeto, predicado,
   objeto) se proyecta como arista `(:Entidad)-[:IS_CHILD_OF]->(:Entidad)`, no como
   un nodo intermedio. Reificar haria el grafo el doble de profundo y arruinaria la
   exploracion en Lab: `(zeus)<-[:IS_CHILD_OF*1..4]-()` deja de existir.
2. **La atestacion va en propiedades de la arista** (`citas`, `autores`). Cypher no
   puede colgar un nodo de una arista, asi que un `:Pasaje` no puede apuntar a una
   `relacion`. Los `:Pasaje`/`:Obra`/`:Autor` existen igual como subgrafo aparte
   para navegar el aparato de fuentes; el enlace fino vive en la arista.
3. **Las contradicciones SI se reifican** (`:Contradiccion`), porque es lo unico que
   no cabe como propiedad: unen dos `relacion` distintas. Se calcula que entidad
   comparten (`:SOBRE`) y en que difieren (`:ALTERNATIVA`), que es la forma en que
   uno quiere leerlas: "de quien es hijo Acheloos segun quien".
4. **Los flags de incertidumbre viajan siempre** (`incierto`, `duda`, `alternativas`,
   `implicito`). Perderlos convierte el mito en dato afirmado, que es exactamente lo
   que el esquema evita.
5. `lat`/`lng` se llaman asi y no `latitud`/`longitud` porque son los nombres que
   Memgraph Lab reconoce para pintar la vista de mapa.
6. **`grado`** (numero de relaciones) va como propiedad para poder escalar el tamano
   del nodo en Lab: en un grafo de 51k entidades el ruido es el problema, no la falta
   de datos.

Idempotente: todo es `MERGE` por `gid` (el `id` de SQLite), asi que re-ejecutar no
duplica. `--wipe` solo hace falta si borraste filas en SQLite y quieres que
desaparezcan aqui.
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Iterator
from typing import Any

from neo4j import Driver, GraphDatabase

BOLT_URI = "bolt://localhost:7687"
LOTE = 5_000

# tipo_entidad.clave -> etiqueta de nodo adicional. Todas las entidades llevan
# ademas :Entidad, que es donde vive el indice unico.
ETIQUETA_TIPO = {
    "agente": "Agente",
    "lugar": "Lugar",
    "santuario": "Santuario",
    "rio": "Rio",
    "landmark": "Landmark",
    "montana": "Montana",
    "region": "Region",
    "isla": "Isla",
    "pueblo": "Pueblo",
    "objeto": "Objeto",
    "colectivo": "Colectivo",
    "constelacion": "Constelacion",
    "evento_mitico": "EventoMitico",
}

# Los lugares comparten un supertipo para poder consultarlos de golpe sin
# enumerar las ocho etiquetas geograficas.
TIPOS_LUGAR = {"lugar", "santuario", "rio", "landmark", "montana", "region", "isla", "pueblo"}

NAMESPACES_PLANOS = ("manto", "wikidata", "pleiades", "topostext")

MAX_VARIANTES = 15

# 29 % de `relacion` (9.023 de 31.199) tiene `objeto_id` NULL: en MANTO muchos
# predicados no llevan objeto directo y el destino real vive en `relacion_rol`.
# `has_cult_site_[in/on/at]` son 540 filas con 539 objetos NULL y el santuario en
# el rol `en`. Sin esto, la proyeccion creaba UNA arista HAS_CULT_SITE en lugar de
# 540 y perdia un tercio del grafo en silencio.
#
# Que rol es el objeto no se adivina con un orden global (`travels_[from]_[to]_[via]`
# quiere `hacia`, `derives_etymology_[from]` quiere `desde`, `is_depicted_[depiction:]`
# quiere `de`): lo declara el propio predicado en sus corchetes. Se crea una arista
# por cada rol que el predicado declara como argumento, con `rol_objeto` en la
# arista. Los roles que NO son argumentos declarados (`con_participacion_de`,
# `usando`) no se promueven: "Theseus dies con_participacion_de X" no es
# "Theseus dies X". Esos siguen accesibles como aristas :ROL.
ROL_DE_ARGUMENTO = {
    "in/on/at": "en",
    "place": "en",
    "into": "en",
    "relic_in_historical_period": "en",
    "to": "hacia",
    "from": "desde",
    "via": "via",
    "near": "cerca_de",
    "against": "contra",
    "for": "para",
    "to_honour": "para_honrar",
    "of": "de",
    "depiction:": "de",
    "someone": "de",
    "event": "de",
    "not_place": "de",
    "greek_entity": "de",
    "non-greek_entity": "de",
    "fictional_alias_/_agent": "de",
    "dir._obj.": "de",
    "direct_obj": "de",
    "d.obj": "de",
    "ind._obj.": "objeto_indirecto",
    "ind._obj": "objeto_indirecto",
    "ind.obj": "objeto_indirecto",
}


# ------------------------------------------------------------------ utilidades


def tipo_arista(clave: str) -> str:
    """`predicado.clave` -> tipo de arista Cypher.

    MANTO codifica los argumentos opcionales del predicado entre corchetes
    (`travels_[from]_[to]_[via]`), que no son identificadores validos. Se quitan
    los grupos y se deja el verbo: TRAVELS. Dos claves pueden colapsar al mismo
    tipo (`is_identified_as` y `[non-greek_entity]_is_identified_as_[greek_entity]`),
    por eso la clave completa se conserva en la propiedad `predicado`.
    """
    s = re.sub(r"\[[^\]]*\]", " ", clave)
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").upper()
    return s or "REL"


def roles_objeto(clave: str) -> list[str]:
    """Roles que el predicado declara como argumento, en orden de aparicion.

    `travels_[from]_[to]_[via]` -> ['desde', 'hacia', 'via']. Vacio si el
    predicado no declara argumentos (`is_mentioned`, `has_hybrid_form`): son
    afirmaciones sobre el sujeto y no tienen objeto que promover.
    """
    salida: list[str] = []
    for tok in re.findall(r"\[([^\]]*)\]", clave):
        rol = ROL_DE_ARGUMENTO.get(tok.strip().lower())
        if rol and rol not in salida:
            salida.append(rol)
    return salida


def _lotes(filas: Iterable[dict], n: int = LOTE) -> Iterator[list[dict]]:
    lote: list[dict] = []
    for f in filas:
        lote.append(f)
        if len(lote) >= n:
            yield lote
            lote = []
    if lote:
        yield lote


def _limpio(d: dict) -> dict:
    """Quita claves con None: `SET n += mapa` borraria la propiedad igualmente,
    pero enviarlas multiplica el payload por nada."""
    return {k: v for k, v in d.items() if v is not None}


class Sesion:
    """Envoltorio fino sobre el driver: ejecuta por lotes y cuenta."""

    def __init__(self, driver: Driver) -> None:
        self.driver = driver
        self.contadores: dict[str, int] = defaultdict(int)

    def ejecutar(self, cypher: str, **params: Any) -> None:
        with self.driver.session() as s:
            s.run(cypher, **params).consume()

    def por_lotes(self, etiqueta: str, cypher: str, filas: Iterable[dict]) -> int:
        total = 0
        with self.driver.session() as s:
            for lote in _lotes(filas):
                s.run(cypher, rows=lote).consume()
                total += len(lote)
        self.contadores[etiqueta] += total
        return total


# -------------------------------------------------------------------- esquema


def indices(con: sqlite3.Connection, ses: Sesion) -> None:
    etiquetas = [
        "Entidad",
        "Evento",
        "Datacion",
        "Autor",
        "Obra",
        "Pasaje",
        "Artefacto",
        "Inscripcion",
        "Periodo",
        "Ciclo",
        "Bando",
        "Contradiccion",
    ]
    for e in etiquetas:
        # El indice de etiqueta+propiedad es lo que hace que los MERGE de aristas
        # no degeneren en scan completo: sin el, 31k aristas tardan minutos.
        ses.ejecutar(f"CREATE INDEX ON :{e}(gid)")
    ses.ejecutar("CREATE INDEX ON :Entidad(nombre)")
    ses.ejecutar("CREATE INDEX ON :Entidad(nombre_norm)")
    ses.contadores["indices"] = len(etiquetas) + 2


def limpiar(ses: Sesion) -> None:
    ses.ejecutar("MATCH (n) DETACH DELETE n")


# ------------------------------------------------------------------ entidades


def _grados(con: sqlite3.Connection) -> dict[int, int]:
    g: dict[int, int] = defaultdict(int)
    for col in ("sujeto_id", "objeto_id"):
        for eid, n in con.execute(f"SELECT {col}, COUNT(*) FROM relacion GROUP BY 1"):
            g[eid] += n
    return g


def _agrupado(con: sqlite3.Connection, sql: str) -> dict[int, list]:
    d: dict[int, list] = defaultdict(list)
    for eid, valor in con.execute(sql):
        d[eid].append(valor)
    return d


def entidades(con: sqlite3.Connection, ses: Sesion) -> None:
    grado = _grados(con)
    variantes = _agrupado(
        con,
        "SELECT entidad_id, nombre FROM entidad_nombre WHERE nombre IS NOT NULL ORDER BY id",
    )
    ids = _agrupado(
        con,
        "SELECT entidad_id, namespace || ':' || valor FROM entidad_identificador ORDER BY id",
    )
    planos: dict[int, dict[str, str]] = defaultdict(dict)
    for eid, ns, valor in con.execute(
        "SELECT entidad_id, namespace, valor FROM entidad_identificador "
        f"WHERE namespace IN ({', '.join('?' * len(NAMESPACES_PLANOS))})",
        NAMESPACES_PLANOS,
    ):
        planos[eid].setdefault(ns, valor)

    # lugar_detalle y la localizacion representativa se aplanan como propiedades
    # del nodo: son 1:1 con la entidad y un nodo aparte solo anadiria un salto.
    geo: dict[int, dict] = {}
    for r in con.execute("SELECT * FROM lugar_detalle"):
        geo[r["entidad_id"]] = {
            "tipo_lugar": r["tipo_lugar"],
            "lat": r["latitud"],
            "lng": r["longitud"],
            "geo_tipo": r["geo_tipo"],
            "geo_fuente": r["geo_fuente"],
            "geo_precision": r["location_precision"],
            "precision_metros": r["precision_metros"],
            "es_ficticio": bool(r["es_ficticio"]) if r["es_ficticio"] is not None else None,
            "nombre_moderno": r["nombre_moderno"],
            "pais": r["pais_iso2"],
        }
    for r in con.execute(
        "SELECT entidad_id, latitud, longitud, precision FROM lugar_localizacion "
        "WHERE es_representativa = 1 AND latitud IS NOT NULL"
    ):
        d = geo.setdefault(r["entidad_id"], {})
        d.setdefault("lat", r["latitud"])
        d.setdefault("lng", r["longitud"])
        d.setdefault("geo_precision", r["precision"])

    por_tipo: dict[str, list[dict]] = defaultdict(list)
    sql = """
        SELECT e.*, te.clave AS tipo, te.es_divino, fd.clave AS fuente
        FROM entidad e
        LEFT JOIN tipo_entidad te ON te.id = e.tipo_entidad_id
        LEFT JOIN fuente_dataset fd ON fd.id = e.fuente_dataset_id
    """
    for r in con.execute(sql):
        eid = r["id"]
        tipo = r["tipo"] or "agente"
        props = {
            "nombre": r["nombre"],
            "nombre_norm": r["nombre_norm"],
            "nombre_es": r["nombre_es"],
            "nombre_grc": r["nombre_grc"],
            "nombre_translit": r["nombre_translit"],
            "nombre_latino": r["nombre_latino"],
            "tipo": tipo,
            "desambiguador": r["desambiguador"],
            "descripcion": r["descripcion"],
            "genero": r["genero"],
            "generacion": r["generacion"],
            "es_mortal": bool(r["es_mortal"]) if r["es_mortal"] is not None else None,
            "es_divino": bool(r["es_divino"]) if r["es_divino"] is not None else None,
            "revisado_manual": bool(r["revisado_manual"]),
            "fuente": r["fuente"],
            "grado": grado.get(eid, 0),
            "variantes": variantes.get(eid, [])[:MAX_VARIANTES],
            "ids": ids.get(eid, []),
        }
        props.update(planos.get(eid, {}))
        if eid in geo:
            props.update(geo[eid])
        por_tipo[tipo].append({"gid": eid, "props": _limpio(props)})

    for tipo, filas in por_tipo.items():
        etqs = [ETIQUETA_TIPO.get(tipo, "Otro")]
        if tipo in TIPOS_LUGAR:
            etqs.append("Lugar")
        etqs = sorted(set(etqs) - {"Entidad"})
        cypher = (
            "UNWIND $rows AS r "
            "MERGE (n:Entidad {gid: r.gid}) "
            f"SET n += r.props, n:{':'.join(etqs)}"
        )
        ses.por_lotes(f"entidad:{tipo}", cypher, filas)


#: papel -> etiqueta de nodo, para poder escribir `MATCH (h:Heroe)` en Lab
ETIQUETA_PAPEL = {
    "dios": "Dios",
    "heroe": "Heroe",
    "gobernante": "Gobernante",
    "monstruo": "Monstruo",
    "deificado": "Deificado",
    "profeta": "Profeta",
    "artesano": "Artesano",
}


def papeles(con: sqlite3.Connection, ses: Sesion) -> None:
    """`entidad_papel` como etiqueta de nodo y como propiedad `papeles`.

    Multi-etiqueta: Agamenon es `:Gobernante:Heroe`. Una etiqueta por papel
    porque en Cypher filtrar por etiqueta es lo natural, y la lista completa va
    tambien como propiedad para verla de un vistazo al pulsar el nodo.
    """
    if not con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='entidad_papel'"
    ).fetchone():
        ses.contadores["papeles (tabla ausente)"] = 0
        return

    for papel, etiqueta in ETIQUETA_PAPEL.items():
        filas = [
            {"gid": f[0]}
            for f in con.execute(
                "SELECT entidad_id FROM entidad_papel WHERE papel = ?", (papel,)
            )
        ]
        ses.por_lotes(
            f"papel:{papel}",
            f"UNWIND $rows AS r MATCH (n:Entidad {{gid: r.gid}}) SET n:{etiqueta}",
            filas,
        )

    agrupado: dict[int, list[str]] = defaultdict(list)
    reglas: dict[int, list[str]] = defaultdict(list)
    for f in con.execute("SELECT entidad_id, papel, regla FROM entidad_papel ORDER BY papel"):
        agrupado[f["entidad_id"]].append(f["papel"])
        reglas[f["entidad_id"]].append(f"{f['papel']}={f['regla']}")
    ses.por_lotes(
        "prop:papeles",
        "UNWIND $rows AS r MATCH (n:Entidad {gid: r.gid}) "
        "SET n.papeles = r.papeles, n.papeles_regla = r.reglas",
        (
            {"gid": gid, "papeles": ps, "reglas": reglas[gid]}
            for gid, ps in agrupado.items()
        ),
    )


def generaciones(con: sqlite3.Connection, ses: Sesion) -> None:
    """`entidad_generacion` como propiedades del nodo, para ordenar en el tiempo."""
    if not con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='entidad_generacion'"
    ).fetchone():
        ses.contadores["generaciones (tabla ausente)"] = 0
        return
    ses.por_lotes(
        "prop:generacion",
        "UNWIND $rows AS r MATCH (n:Entidad {gid: r.gid}) SET n += r.props",
        (
            {
                "gid": f["entidad_id"],
                "props": _limpio(
                    {
                        "generacion": f["generacion"],
                        "generacion_min": f["generacion_min"],
                        "generacion_max": f["generacion_max"],
                        "generacion_metodo": f["metodo"],
                        "generacion_confianza": f["confianza"],
                        # transmite = 0 -> divinidad: no fecha a su descendencia
                        "transmite_generacion": bool(f["transmite"]),
                    }
                ),
            }
            for f in con.execute("SELECT * FROM entidad_generacion")
        ),
    )


def jerarquia_lugares(con: sqlite3.Connection, ses: Sesion) -> None:
    filas = (
        {"a": r["hijo_id"], "b": r["padre_id"], "tipo": r["tipo"], "certeza": r["certeza"]}
        for r in con.execute("SELECT hijo_id, padre_id, tipo, certeza FROM lugar_jerarquia")
    )
    ses.por_lotes(
        "DENTRO_DE",
        "UNWIND $rows AS r "
        "MATCH (a:Entidad {gid: r.a}), (b:Entidad {gid: r.b}) "
        "MERGE (a)-[e:DENTRO_DE]->(b) SET e.tipo = r.tipo, e.certeza = r.certeza",
        filas,
    )


def equivalencias(con: sqlite3.Connection, ses: Sesion) -> None:
    filas = (
        {"a": r["entidad_a_id"], "b": r["entidad_b_id"], "tipo": r["tipo"], "nota": r["nota"]}
        for r in con.execute("SELECT * FROM entidad_equivalencia")
    )
    ses.por_lotes(
        "EQUIVALE_A",
        "UNWIND $rows AS r "
        "MATCH (a:Entidad {gid: r.a}), (b:Entidad {gid: r.b}) "
        "MERGE (a)-[e:EQUIVALE_A {tipo: r.tipo}]->(b) SET e.nota = r.nota",
        filas,
    )


# --------------------------------------------------------------------- fuentes


def fuentes(con: sqlite3.Connection, ses: Sesion) -> None:
    ses.por_lotes(
        "Autor",
        "UNWIND $rows AS r MERGE (n:Autor {gid: r.gid}) SET n += r.props",
        (
            {
                "gid": r["id"],
                "props": _limpio(
                    {
                        "nombre": r["nombre"],
                        "nombre_es": r["nombre_es"],
                        "wikidata": r["wikidata_qid"],
                        "floruit_min_ac": r["floruit_min_ac"],
                        "floruit_max_ac": r["floruit_max_ac"],
                    }
                ),
            }
            for r in con.execute("SELECT * FROM autor_antiguo")
        ),
    )
    ses.por_lotes(
        "Obra",
        "UNWIND $rows AS r MERGE (n:Obra {gid: r.gid}) SET n += r.props "
        "WITH n, r WHERE r.autor IS NOT NULL "
        "MATCH (a:Autor {gid: r.autor}) MERGE (a)-[:ESCRIBE]->(n)",
        (
            {
                "gid": r["id"],
                "autor": r["autor_id"],
                "props": _limpio(
                    {
                        "titulo": r["titulo"],
                        "titulo_es": r["titulo_es"],
                        "lengua": r["lengua"],
                        "genero": r["genero"],
                        "cts_urn": r["cts_urn"],
                        "fecha_comp_min_ac": r["fecha_comp_min_ac"],
                        "fecha_comp_max_ac": r["fecha_comp_max_ac"],
                    }
                ),
            }
            for r in con.execute("SELECT * FROM obra")
        ),
    )
    ses.por_lotes(
        "Pasaje",
        "UNWIND $rows AS r MERGE (n:Pasaje {gid: r.gid}) SET n += r.props "
        "WITH n, r WHERE r.obra IS NOT NULL "
        "MATCH (o:Obra {gid: r.obra}) MERGE (n)-[:EN_OBRA]->(o)",
        (
            {
                "gid": r["id"],
                "obra": r["obra_id"],
                "props": _limpio(
                    {
                        "cita": r["cita"],
                        "cts_urn": r["cts_urn"],
                        "scaife_url": r["scaife_url"],
                        "topostext_url": r["topostext_url"],
                        "fecha_evento_ac": r["tt_fecha_evento_ac"],
                    }
                ),
            }
            for r in con.execute("SELECT * FROM pasaje")
        ),
    )


# ------------------------------------------------------------------ relaciones


def cita_legible(cita: str | None, titulo: str | None, autor: str | None) -> str | None:
    """Una sola cadena por pasaje, sin repetir el autor tres veces.

    `pasaje.cita` viene de MANTO en dos formas: desnuda (`1.7`) y ya completa
    (`Apollodoros, Epitome 1.1-1.4`). Concatenar autor + titulo + cita a ciegas
    produce 'Pausanias, Pausanias, Pausanias 2.5.3'. Solo se prefija lo que la
    cita no trae ya.
    """
    partes = [p for p in (autor, titulo, cita) if p]
    if not partes:
        return None
    salida: list[str] = []
    for p in partes:
        if any(p in ya or ya.startswith(p) for ya in salida):
            continue
        salida = [s for s in salida if s not in p]
        salida.append(p)
    return ", ".join(salida)


def _atestacion(con: sqlite3.Connection) -> tuple[dict[int, list[str]], dict[int, list[str]]]:
    """rid -> lista de citas legibles, y rid -> autores citados.

    Va en la arista porque Cypher no admite aristas de aristas (ver docstring
    del modulo). `autores` esta duplicado a proposito: filtrar por autor es la
    consulta que uno hace de verdad ("todo lo que afirma Hesiodo").
    """
    citas: dict[int, list[str]] = defaultdict(list)
    autores: dict[int, set[str]] = defaultdict(set)
    sql = """
        SELECT rf.relacion_id AS rid, p.cita, o.titulo, a.nombre AS autor
        FROM relacion_fuente rf
        JOIN pasaje p ON p.id = rf.pasaje_id
        LEFT JOIN obra o ON o.id = p.obra_id
        LEFT JOIN autor_antiguo a ON a.id = o.autor_id
    """
    for r in con.execute(sql):
        texto = cita_legible(r["cita"], r["titulo"], r["autor"])
        if texto and texto not in citas[r["rid"]]:
            citas[r["rid"]].append(texto)
        if r["autor"]:
            autores[r["rid"]].add(r["autor"])
    return dict(citas), {k: sorted(v) for k, v in autores.items()}


def _roles(
    con: sqlite3.Connection,
) -> tuple[dict[int, list[str]], dict[int, list[tuple[str, int]]]]:
    """rid -> roles como texto legible, y rid -> [(rol, entidad_id)]."""
    sql = """
        SELECT rr.relacion_id AS rid, rr.rol, rr.entidad_id, e.nombre
        FROM relacion_rol rr
        LEFT JOIN entidad e ON e.id = rr.entidad_id
    """
    textos: dict[int, list[str]] = defaultdict(list)
    destinos: dict[int, list[tuple[str, int]]] = defaultdict(list)
    for r in con.execute(sql):
        textos[r["rid"]].append(f"{r['rol']}: {r['nombre']}" if r["nombre"] else r["rol"])
        if r["entidad_id"] is not None:
            destinos[r["rid"]].append((r["rol"], r["entidad_id"]))
    return dict(textos), dict(destinos)


def relaciones(con: sqlite3.Connection, ses: Sesion) -> None:
    citas, autores = _atestacion(con)
    textos_rol, destinos_rol = _roles(con)
    cache_roles_objeto: dict[str, list[str]] = {}

    sql = """
        SELECT r.*, p.clave AS predicado, p.nombre_es AS predicado_es,
               p.categoria, fd.clave AS fuente
        FROM relacion r
        JOIN predicado p ON p.id = r.predicado_id
        LEFT JOIN fuente_dataset fd ON fd.id = r.fuente_dataset_id
    """
    por_tipo: dict[str, list[dict]] = defaultdict(list)
    # Afirmaciones que no tienen objeto ni rol que promover: van como propiedad
    # de lista en el sujeto. `has_no_children` o `becomes_immortal` son hechos
    # sobre la figura, no aristas, y descartarlos las perderia del todo.
    unarias: dict[int, list[str]] = defaultdict(list)

    for r in con.execute(sql):
        rid, clave = r["id"], r["predicado"]
        props = _limpio(
            {
                "predicado": clave,
                "predicado_es": r["predicado_es"],
                "categoria": r["categoria"],
                "evento_gid": r["evento_id"],
                "timemark": r["timemark_when"],
                "incierto": bool(r["dato_incierto"]),
                "duda": bool(r["duda_expresada"]),
                "alternativas": bool(r["alternativas_dadas"]),
                "implicito": bool(r["dato_implicito"]),
                "comentario": r["comentario"],
                "fuente": r["fuente"],
                "citas": citas.get(rid, []),
                "autores": autores.get(rid, []),
                "roles": textos_rol.get(rid, []),
                "n_citas": len(citas.get(rid, [])),
            }
        )
        tipo = tipo_arista(clave)

        if r["objeto_id"] is not None:
            por_tipo[tipo].append(
                {"rid": rid, "s": r["sujeto_id"], "o": r["objeto_id"], "k": "", "props": props}
            )
            continue

        # objeto NULL: el destino esta en los roles que el predicado declara
        if clave not in cache_roles_objeto:
            cache_roles_objeto[clave] = roles_objeto(clave)
        admitidos = cache_roles_objeto[clave]
        emitidas = 0
        for rol, destino in destinos_rol.get(rid, []):
            if rol not in admitidos:
                continue
            por_tipo[tipo].append(
                {
                    "rid": rid,
                    "s": r["sujeto_id"],
                    "o": destino,
                    "k": rol,
                    "props": {**props, "rol_objeto": rol},
                }
            )
            emitidas += 1
        if emitidas == 0:
            unarias[r["sujeto_id"]].append(clave)

    for tipo, filas in sorted(por_tipo.items()):
        # La clave del MERGE incluye `k` (el rol promovido) porque una misma
        # relacion puede dar varias aristas: `travels_[from]_[to]_[via]` produce
        # una hacia el origen, otra al destino y otra a la escala.
        cypher = (
            "UNWIND $rows AS r "
            "MATCH (a:Entidad {gid: r.s}), (b:Entidad {gid: r.o}) "
            f"MERGE (a)-[e:{tipo} {{rid: r.rid, k: r.k}}]->(b) "
            "SET e += r.props"
        )
        ses.por_lotes(f"rel:{tipo}", cypher, filas)

    ses.por_lotes(
        "prop:predicados_unarios",
        "UNWIND $rows AS r MATCH (n:Entidad {gid: r.gid}) SET n.predicados_unarios = r.claves",
        ({"gid": gid, "claves": sorted(set(cs))} for gid, cs in unarias.items()),
    )


def roles(con: sqlite3.Connection, ses: Sesion) -> None:
    """`relacion_rol` como aristas :ROL del sujeto a la entidad del rol.

    Ya viaja como texto en `e.roles`, pero como arista se vuelve navegable: el
    rol `en` (9.528 filas) es lo que conecta un heroe con el lugar donde pasa la
    cosa, y el rol `usando` con el arma. Sin esto ese enlace no es recorrible.
    """
    sql = """
        SELECT rr.relacion_id AS rid, rr.rol, rr.entidad_id AS destino,
               r.sujeto_id AS origen, p.clave AS predicado
        FROM relacion_rol rr
        JOIN relacion r ON r.id = rr.relacion_id
        JOIN predicado p ON p.id = r.predicado_id
        WHERE rr.entidad_id IS NOT NULL
    """
    filas = (
        {
            "rid": r["rid"],
            "a": r["origen"],
            "b": r["destino"],
            "rol": r["rol"],
            "predicado": r["predicado"],
        }
        for r in con.execute(sql)
    )
    ses.por_lotes(
        "ROL",
        "UNWIND $rows AS r "
        "MATCH (a:Entidad {gid: r.a}), (b:Entidad {gid: r.b}) "
        "MERGE (a)-[e:ROL {rid: r.rid, rol: r.rol}]->(b) SET e.predicado = r.predicado",
        filas,
    )


# -------------------------------------------------------------- contradicciones


def contradicciones(con: sqlite3.Connection, ses: Sesion) -> None:
    """Reifica `contradiccion` y calcula sobre que discrepan las dos versiones.

    `:SOBRE` apunta a la figura de la que se discute y `:ALTERNATIVA` a cada
    version incompatible. Que posicion de la relacion es la discutida depende del
    tipo, y hay que leerlo igual que lo escribe `reconcile.py`:

    | tipo | comun (:SOBRE) | discutido (:ALTERNATIVA) |
    |---|---|---|
    | `genealogia`    | sujeto = el hijo   | objeto = el progenitor |
    | `autoria_muerte`| objeto = la victima| sujeto = el matador |
    | `ubicacion`     | sujeto (+ objeto)  | entidad del rol `en` |

    La tentacion es la diferencia simetrica de {sujeto, objeto, roles} de las dos
    relaciones, pero en `ubicacion` eso mete el arma y los ayudantes como si
    fueran ubicaciones alternativas: 'Theseus kills en el Laberinto usando la
    Clava con ayuda de Ariadna' devolvia Ariadna y la clava entre las
    alternativas. En `ubicacion` lo discutido es solo el rol `en`, que es
    exactamente lo que compara el detector.
    """
    _, destinos_rol = _roles(con)

    rel: dict[int, tuple[int | None, int | None, set[int], str]] = {}
    for r in con.execute(
        "SELECT r.id, r.sujeto_id, r.objeto_id, p.clave "
        "FROM relacion r JOIN predicado p ON p.id = r.predicado_id"
    ):
        en = {eid for rol, eid in destinos_rol.get(r["id"], []) if rol == "en"}
        rel[r["id"]] = (r["sujeto_id"], r["objeto_id"], en, r["clave"])

    def _dimension(tipo: str, a: tuple, b: tuple) -> tuple[set, set]:
        if tipo == "genealogia":
            return {a[0], b[0]}, {a[1], b[1]}
        if tipo == "autoria_muerte":
            return {a[1], b[1]}, {a[0], b[0]}
        if tipo == "ubicacion":
            return {a[0], b[0], a[1], b[1]}, a[2] ^ b[2]
        # tipo nuevo: cae al calculo generico sobre todas las posiciones
        lado_a, lado_b = {a[0], a[1]} | a[2], {b[0], b[1]} | b[2]
        return lado_a & lado_b, lado_a ^ lado_b

    nodos, sobre, alternativas = [], [], []
    for r in con.execute("SELECT * FROM contradiccion"):
        a, b = rel.get(r["relacion_a_id"]), rel.get(r["relacion_b_id"])
        if a is None or b is None:
            continue
        s_set, d_set = _dimension(r["tipo"], a, b)
        comun = sorted(x for x in s_set - d_set if x is not None)
        difiere = sorted(x for x in d_set if x is not None)
        cid = r["id"]
        nodos.append(
            {
                "gid": cid,
                "props": _limpio(
                    {
                        "tipo": r["tipo"],
                        "descripcion": r["descripcion"],
                        "resuelta": bool(r["resuelta"]),
                        "criterio": r["criterio"],
                        "predicados": sorted({a[3], b[3]}),
                        "rel_a": r["relacion_a_id"],
                        "rel_b": r["relacion_b_id"],
                    }
                ),
            }
        )
        sobre += [{"c": cid, "e": e} for e in comun]
        alternativas += [{"c": cid, "e": e} for e in difiere]

    ses.por_lotes(
        "Contradiccion",
        "UNWIND $rows AS r MERGE (n:Contradiccion {gid: r.gid}) SET n += r.props",
        nodos,
    )
    ses.por_lotes(
        "SOBRE",
        "UNWIND $rows AS r MATCH (c:Contradiccion {gid: r.c}), (e:Entidad {gid: r.e}) "
        "MERGE (c)-[:SOBRE]->(e)",
        sobre,
    )
    ses.por_lotes(
        "ALTERNATIVA",
        "UNWIND $rows AS r MATCH (c:Contradiccion {gid: r.c}), (e:Entidad {gid: r.e}) "
        "MERGE (c)-[:ALTERNATIVA]->(e)",
        alternativas,
    )


# --------------------------------------------------------------------- eventos


def eventos(con: sqlite3.Connection, ses: Sesion) -> None:
    ses.por_lotes(
        "Periodo",
        "UNWIND $rows AS r MERGE (n:Periodo {gid: r.gid}) SET n += r.props",
        (
            {
                "gid": r["id"],
                "props": _limpio(
                    {
                        "clave": r["clave"],
                        "nombre": r["nombre"],
                        "anio_inicio_ac": r["anio_inicio_ac"],
                        "anio_fin_ac": r["anio_fin_ac"],
                        "chronontology_uri": r["chronontology_uri"],
                    }
                ),
            }
            for r in con.execute("SELECT * FROM periodo")
        ),
    )
    ses.por_lotes(
        "Ciclo",
        "UNWIND $rows AS r MERGE (n:Ciclo {gid: r.gid}) SET n += r.props",
        (
            {
                "gid": r["id"],
                "props": _limpio(
                    {"clave": r["clave"], "nombre": r["nombre_es"], "orden": r["orden"]}
                ),
            }
            for r in con.execute("SELECT * FROM ciclo_mitico")
        ),
    )

    ses.por_lotes(
        "Evento",
        "UNWIND $rows AS r MERGE (n:Evento {gid: r.gid}) SET n += r.props",
        (
            {
                "gid": r["id"],
                "props": _limpio(
                    {
                        "nombre": r["nombre"],
                        "nombre_es": r["nombre_es"],
                        "tipo": r["tipo"],
                        "descripcion": r["descripcion"],
                        "resultado": r["resultado"],
                        # derivado de evento_datacion, no primario: si solo hay
                        # una fecha, es que solo hay una autoridad
                        "fecha_ac": r["fecha_ac"],
                        "fecha_min_ac": r["fecha_min_ac"],
                        "fecha_max_ac": r["fecha_max_ac"],
                        "fecha_metodo": r["fecha_metodo"],
                        "fecha_confianza": r["fecha_confianza"],
                        "generacion": r["generacion"],
                    }
                ),
            }
            for r in con.execute("SELECT * FROM evento")
        ),
    )

    # aristas del evento: lugar, evento padre, ciclo, periodo
    for etiqueta, tipo_rel, col, destino in (
        ("OCURRE_EN", "OCURRE_EN", "lugar_id", "Entidad"),
        ("PARTE_DE", "PARTE_DE", "padre_evento_id", "Evento"),
        ("DEL_CICLO", "DEL_CICLO", "ciclo_id", "Ciclo"),
        ("EN_PERIODO", "EN_PERIODO", "periodo_id", "Periodo"),
    ):
        filas = (
            {"a": r["id"], "b": r[col]}
            for r in con.execute(f"SELECT id, {col} FROM evento WHERE {col} IS NOT NULL")
        )
        ses.por_lotes(
            etiqueta,
            f"UNWIND $rows AS r MATCH (a:Evento {{gid: r.a}}), (b:{destino} {{gid: r.b}}) "
            f"MERGE (a)-[:{tipo_rel}]->(b)",
            filas,
        )

    ses.por_lotes(
        "EVENTO_REL",
        "UNWIND $rows AS r MATCH (a:Evento {gid: r.a}), (b:Evento {gid: r.b}) "
        "MERGE (a)-[:EVENTO_REL {tipo: r.tipo}]->(b)",
        (
            {"a": r["evento_a_id"], "b": r["evento_b_id"], "tipo": r["tipo"]}
            for r in con.execute("SELECT * FROM evento_relacion")
        ),
    )

    ses.por_lotes(
        "Bando",
        "UNWIND $rows AS r MERGE (n:Bando {gid: r.gid}) SET n += r.props "
        "WITH n, r MATCH (e:Evento {gid: r.evento}) MERGE (n)-[:BANDO_DE]->(e)",
        (
            {
                "gid": r["id"],
                "evento": r["evento_id"],
                "props": _limpio({"nombre": r["nombre"], "resultado": r["resultado"]}),
            }
            for r in con.execute("SELECT * FROM bando")
        ),
    )

    ses.por_lotes(
        "PARTICIPA_EN",
        "UNWIND $rows AS r "
        "MATCH (a:Entidad {gid: r.a}), (b:Evento {gid: r.b}) "
        "MERGE (a)-[e:PARTICIPA_EN {pid: r.pid}]->(b) SET e += r.props",
        (
            {
                "pid": r["id"],
                "a": r["entidad_id"],
                "b": r["evento_id"],
                "props": _limpio({"rol": r["rol"], "resultado": r["resultado"]}),
            }
            for r in con.execute("SELECT * FROM evento_participante WHERE entidad_id IS NOT NULL")
        ),
    )
    ses.por_lotes(
        "EN_BANDO",
        "UNWIND $rows AS r MATCH (a:Entidad {gid: r.a}), (b:Bando {gid: r.b}) "
        "MERGE (a)-[:EN_BANDO]->(b)",
        (
            {"a": r["entidad_id"], "b": r["bando_id"]}
            for r in con.execute(
                "SELECT entidad_id, bando_id FROM evento_participante "
                "WHERE bando_id IS NOT NULL AND entidad_id IS NOT NULL"
            )
        ),
    )

    # Las dataciones son nodos y no propiedades porque el invariante del modelo
    # es que un evento admite N fechas de N autoridades; aplanarlas a una
    # afirmaria lo que las fuentes antiguas no afirman.
    ses.por_lotes(
        "Datacion",
        "UNWIND $rows AS r MERGE (n:Datacion {gid: r.gid}) SET n += r.props "
        "WITH n, r MATCH (e:Evento {gid: r.evento}) "
        "MERGE (e)-[d:DATADO_EN]->(n) SET d.preferida = r.preferida",
        (
            {
                "gid": r["id"],
                "evento": r["evento_id"],
                "preferida": bool(r["es_preferida"]),
                "props": _limpio(
                    {
                        "autoridad": r["autoridad"],
                        "sistema": r["sistema"],
                        "anio_ac": r["anio_ac"],
                        "anio_min_ac": r["anio_min_ac"],
                        "anio_max_ac": r["anio_max_ac"],
                        "precision": r["precision"],
                        "es_preferida": bool(r["es_preferida"]),
                        "nota": r["nota"],
                    }
                ),
            }
            for r in con.execute("SELECT * FROM evento_datacion")
        ),
    )

    ses.por_lotes(
        "ATESTIGUA",
        "UNWIND $rows AS r MATCH (p:Pasaje {gid: r.p}), (e:Evento {gid: r.e}) "
        "MERGE (p)-[a:ATESTIGUA]->(e) SET a.principal = r.principal",
        (
            {"p": r["pasaje_id"], "e": r["evento_id"], "principal": bool(r["es_principal"])}
            for r in con.execute("SELECT * FROM evento_fuente WHERE pasaje_id IS NOT NULL")
        ),
    )


# ------------------------------------------------------------------- artefactos


def artefactos(con: sqlite3.Connection, ses: Sesion) -> None:
    ses.por_lotes(
        "Artefacto",
        "UNWIND $rows AS r MERGE (n:Artefacto {gid: r.gid}) SET n += r.props",
        (
            {
                "gid": r["id"],
                "props": _limpio(
                    {
                        "nombre": r["nombre"],
                        "tipo": r["tipo"],
                        "coleccion": r["coleccion"],
                        "limc_ref": r["limc_ref"],
                        "digital_limc_url": r["digital_limc_url"],
                        "bapd_url": r["bapd_url"],
                    }
                ),
            }
            for r in con.execute("SELECT * FROM artefacto")
        ),
    )
    ses.por_lotes(
        "REPRESENTA",
        "UNWIND $rows AS r MATCH (a:Artefacto {gid: r.a}), (e:Entidad {gid: r.e}) "
        "MERGE (a)-[x:REPRESENTA]->(e) SET x.reportada = r.reportada",
        (
            {"a": r["artefacto_id"], "e": r["entidad_id"], "reportada": bool(r["es_reportada"])}
            for r in con.execute("SELECT * FROM artefacto_representa")
        ),
    )
    for col, tipo_rel in (("lugar_creacion_id", "CREADO_EN"), ("lugar_hallazgo_id", "HALLADO_EN")):
        filas = (
            {"a": r["id"], "b": r[col]}
            for r in con.execute(f"SELECT id, {col} FROM artefacto WHERE {col} IS NOT NULL")
        )
        ses.por_lotes(
            tipo_rel,
            f"UNWIND $rows AS r MATCH (a:Artefacto {{gid: r.a}}), (b:Entidad {{gid: r.b}}) "
            f"MERGE (a)-[:{tipo_rel}]->(b)",
            filas,
        )
    ses.por_lotes(
        "Artefacto:DE_PERIODO",
        "UNWIND $rows AS r MATCH (a:Artefacto {gid: r.a}), (p:Periodo {gid: r.b}) "
        "MERGE (a)-[:DE_PERIODO]->(p)",
        (
            {"a": r["id"], "b": r["periodo_id"]}
            for r in con.execute(
                "SELECT id, periodo_id FROM artefacto WHERE periodo_id IS NOT NULL"
            )
        ),
    )

    ses.por_lotes(
        "Inscripcion",
        "UNWIND $rows AS r MERGE (n:Inscripcion {gid: r.gid}) SET n += r.props",
        (
            {
                "gid": r["id"],
                "props": _limpio(
                    {
                        "nombre": r["nombre"],
                        "ig_ref": r["ig_ref"],
                        "seg_ref": r["seg_ref"],
                        "trismegistos_url": r["trismegistos_url"],
                    }
                ),
            }
            for r in con.execute("SELECT * FROM inscripcion")
        ),
    )
    ses.por_lotes(
        "Inscripcion:HALLADA_EN",
        "UNWIND $rows AS r MATCH (i:Inscripcion {gid: r.a}), (b:Entidad {gid: r.b}) "
        "MERGE (i)-[:HALLADA_EN]->(b)",
        (
            {"a": r["id"], "b": r["lugar_hallazgo_id"]}
            for r in con.execute(
                "SELECT id, lugar_hallazgo_id FROM inscripcion WHERE lugar_hallazgo_id IS NOT NULL"
            )
        ),
    )


# ----------------------------------------------------------------------- pasos

PASOS: dict[str, Any] = {
    "entidades": entidades,
    "papeles": papeles,
    "generaciones": generaciones,
    "lugares": jerarquia_lugares,
    "equivalencias": equivalencias,
    "fuentes": fuentes,
    "relaciones": relaciones,
    "roles": roles,
    "contradicciones": contradicciones,
    "eventos": eventos,
    "artefactos": artefactos,
}

# Orden obligado: las aristas hacen MATCH de nodos que ya deben existir.
ORDEN = [
    "entidades",
    # ambos solo anaden etiquetas y propiedades a nodos ya creados
    "papeles",
    "generaciones",
    "lugares",
    "equivalencias",
    "fuentes",
    "relaciones",
    "roles",
    "contradicciones",
    "eventos",
    "artefactos",
]


def exportar(
    con: sqlite3.Connection,
    uri: str = BOLT_URI,
    solo: list[str] | None = None,
    wipe: bool = False,
) -> str:
    pasos = solo or ORDEN
    desconocidos = [p for p in pasos if p not in PASOS]
    if desconocidos:
        raise ValueError(f"pasos desconocidos: {desconocidos}. Validos: {sorted(PASOS)}")

    # Memgraph arranca sin autenticacion; el auth vacio es lo que espera.
    driver = GraphDatabase.driver(uri, auth=("", ""))
    try:
        driver.verify_connectivity()
    except Exception as exc:  # noqa: BLE001
        driver.close()
        raise RuntimeError(
            f"no hay Memgraph en {uri}: {exc}\n"
            "arranca el stack con `docker compose up -d` en la raiz del proyecto"
        ) from exc

    ses = Sesion(driver)
    try:
        if wipe:
            limpiar(ses)
        indices(con, ses)
        for nombre in ORDEN:
            if nombre in pasos:
                PASOS[nombre](con, ses)
        return _informe(ses)
    finally:
        driver.close()


def _informe(ses: Sesion) -> str:
    """Los totales se preguntan al grafo, no se suman de los contadores.

    Sumar los contadores del ETL cuenta las aristas como nodos y, al re-ejecutar
    sobre un grafo existente, cuenta filas enviadas en vez de filas creadas.
    """
    with ses.driver.session() as s:
        nodos = s.run("MATCH (n) RETURN count(*) AS n").single()["n"]
        aristas = s.run("MATCH ()-[r]->() RETURN count(*) AS n").single()["n"]

    lineas = [f"memgraph: {nodos:,} nodos, {aristas:,} aristas", "", "--- enviado ---"]
    c = ses.contadores
    for k in sorted(c):
        marca = "  <- 0 filas en greek.db" if c[k] == 0 else ""
        lineas.append(f"  {k:<34} {c[k]:>9,}{marca}")
    lineas += [
        "",
        "Lab: http://localhost:3000  (Quick Connect -> memgraph:7687)",
        "consultas de partida: cypher/consultas.cypher · estilo: cypher/greek.gss",
    ]
    return "\n".join(lineas)
