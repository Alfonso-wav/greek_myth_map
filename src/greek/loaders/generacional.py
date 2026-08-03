"""Derivacion generacional: generacion por entidad, fechas de evento y fecha preferida.

fuentes.md §5.3. Mismo metodo que usaron los cronografos antiguos, asi que es
defendible — pero se marca SIEMPRE sistema='generacional' y confianza='baja', y
no se mezcla con las dataciones de cronografo antiguo.

    ANCLA:       caida de Troya = -1184 (Eratostenes), final de la generacion 2
    GENERACION:  33 anios (Hecateo via Herodoto: 3 generaciones por siglo)
    fecha_ac = ANCLA - (GEN_TROYA - generacion) * 33

Cosmogonia y teomaquias: fecha_ac = NULL, metodo='sin_fecha'. No se inventa un
numero para "antes del tiempo".

------------------------------------------------------------------------------
`entidad.generacion`: como se deriva y por que asi

MANTO publica el vocabulario `generation_11335.json` pero **ninguna entidad lo
referencia**, asi que la generacion hay que derivarla de las 5.584 aristas
`is child of`. Dos intentos que NO funcionan, probados contra el dato:

1. **Profundidad desde las raices genealogicas.** Hay 556 "raices" (sin progenitor
   registrado) y son heterogeneas: `Ge` es raiz porque es primordial, y
   `Antenor (Trojan)` es raiz porque MANTO no anota a sus padres. Un BFS desde las
   raices mete a Antenor y su prole en la cosmogonia.
2. **Camino mas largo desde los primordiales.** Da Heracles=28, Aquiles=18,
   Atreo=7 con su hijo Agamenon en 26. El camino mas largo cose tradiciones
   incompatibles que ninguna fuente afirma juntas, y los rios-dioses,
   personificaciones y ninfas encadenan sin fin.

Lo que si funciona: **semilla manual de figuras canonicas + BFS +-1**. Es el mismo
principio que ya aplica el proyecto a los eventos ("la semilla manual de ~120-200
eventos mayores da mejor calidad que cualquier heuristica"). La generacion mitica es
dato de dominio, no una propiedad del grafo.

Y la pieza que lo hace funcionar: **la paternidad divina no transmite cronologia.**
Zeus tiene 68 hijos repartidos entre gen -7 y gen 3; Poseidon 85 entre -5 y 3. Si un
dios transmite generacion, el eje temporal se aplasta. Los dioses van en
`SEMILLA_DIVINA` con `transmite = 0`, y ademas se **autodetectan** los que no estan
en la lista (rios-dioses, personificaciones) por la regla "un progenitor con >= 10
hijos repartidos en mas de 2 generaciones no es un eslabon cronologico". Esa regla
sola encuentra a Poseidon, Zeus, Apolo, Ares, Oceano, Ge, Hermes, Urano y Atlas.
"""

from __future__ import annotations

import collections
import sqlite3
import statistics
from datetime import UTC, datetime

from ..db import SQL_DIR, insert_ignore, registrar_fuente

ANCLA_TROYA = -1184
GEN_TROYA = 2
ANIOS_GENERACION = 33
GEN_SIN_FECHA = -6  # gen <= -6: cosmogonia y teomaquias, sin fecha real

# Semilla anclada por **ID de MANTO, nunca por nombre**: hay homonimos que la
# romperian en silencio — `Tartaros (personification)` vs `(Thessalian)`,
# `Hyperion (Titan)` vs `(Mycenaean)`, `Phoibe (Titan)` vs `(Messenian)`,
# `Coios (Titan)` vs `(Messenian)`, `Deucalion (Thessalian)` vs `(Cretan)`.
# Invariante 1 del proyecto: el nombre no es clave.
#
# Escala calibrada con la semilla de eventos de `troya.py`: Diluvio de Deucalion
# = -5, Perseo = -3, Teseo/Minotauro = -1, trabajos de Heracles = 0, Guerra de
# Troya = 2, Orestiada = 3, retorno de los Heraclidas = 4.
SEMILLA_MORTAL: dict[str, int] = {
    "8188163": -5,  # Deucalion (Thessalian)
    "8182047": -5,  # Agenor (f. of Europe)
    "8188472": -4,  # Hellen
    "8187926": -4,  # Cadmos (Theban)
    "9587654": -4,  # Danaos
    "8189209": -3,  # Perseus (Argive)
    "8187896": -3,  # Bellerophon
    "8190002": -3,  # Sisyphos
    "8187869": -3,  # Athamas (Orchomenian)
    "8182088": -3,  # Aiolos (eponym)
    "8189261": -2,  # Phrixos
    "8189835": -2,  # Minos
    "8189123": -2,  # Pasiphae (Cretan)
    "8188128": -2,  # Daidalos
    "8182072": -2,  # Aigeus (Athenian)
    "8190057": -1,  # Tantalos (Lydian)
    "8188822": -1,  # Theseus
    "8187817": -1,  # Ariadne
    "8182163": -1,  # Amphitryon
    "8182112": -1,  # Alcmene
    "8182092": -1,  # Aison
    "8189147": -1,  # Pelias (Thessalian)
    "8182069": -1,  # Aietes
    "8188628": -1,  # Laios
    "8188478": 0,  # Heracles
    "8188831": 0,  # Pelops (Pisan)
    "8188623": 0,  # Jason (Argonaut)
    "8189762": 0,  # Medeia
    "8190182": 0,  # Oedipus
    "8187873": 1,  # Atreus
    "8190134": 1,  # Thyestes (Mycenaean)
    "8190161": 1,  # Tydeus
    "8189319": 1,  # Polyneices
    "8188282": 1,  # Eteocles (Theban)
    "8182206": 1,  # Antigone (Theban)
    "8189347": 1,  # Priam
    "8189146": 1,  # Peleus
    "8188626": 1,  # Laertes
    "8182203": 1,  # Anticleia (Ithacan)
    "8189878": 1,  # Nestor
    "8190162": 1,  # Tyndareos
    "8189669": 1,  # Leda
    "8182035": 2,  # Agamemnon
    "8189802": 2,  # Menelaos
    "8182080": 2,  # Aigisthos
    "8188173": 2,  # Diomedes (Argive I)
    "8188465": 2,  # Hector (Trojan)
    "8182124": 2,  # Alexander (Trojan) = Paris
    "8182084": 2,  # Aineias
    "9746393": 2,  # Agenor (Trojan)
    "8182012": 2,  # Achilles
    "8189902": 2,  # Odysseus
    "8189173": 2,  # Penelope
    "8189153": 2,  # Helen
    "8182111": 2,  # Alcmaion (epigonos)
    "8189871": 3,  # Neoptolemos
    "8189078": 3,  # Orestes (s. of Agamemnon)
    "8190074": 3,  # Telemachos
    "8188598": 3,  # Iphigeneia
}

# Dioses: generacion teogonica solo para ordenarlos, y `transmite = 0`. Todas
# caen en gen <= -5, por debajo de GEN_SIN_FECHA, asi que no reciben fecha: es
# correcto, "antes del tiempo" no se datea.
SEMILLA_DIVINA: dict[str, int] = {
    "9878180": -9,  # Chaos
    "8188388": -9,  # Ge
    "9878184": -9,  # Nyx
    "9878189": -9,  # Pontos (personification)
    "8360058": -9,  # Tartaros (personification)
    "9878183": -9,  # Erebos (personification)
    "9878186": -9,  # Aither
    "9878187": -9,  # Hemera
    "9878181": -9,  # Eros
    "8188400": -8,  # Ouranos
    "8188399": -8,  # Oceanos (Titan)
    "8188408": -8,  # Tethys
    "8188393": -8,  # Iapetos
    "8188416": -8,  # Theia
    "8188392": -8,  # Hyperion (Titan)
    "8188062": -8,  # Coios (Titan)
    "8188401": -8,  # Phoibe (Titan)
    "8188417": -8,  # Themis
    "8188397": -8,  # Mnemosyne
    "8187986": -8,  # Ceto (d. of Pontos)
    "8190100": -8,  # Thaumas (early god)
    "8188102": -7,  # Cronos
    "8187872": -7,  # Atlas
    "8189357": -7,  # Prometheus (fire-stealer)
    "8194729": -7,  # Helios
    "8189993": -7,  # Selene
    "8188245": -7,  # Eos
    "8189875": -7,  # Nereus
    "8188419": -6,  # Zeus (Olympian)
    "8188403": -6,  # Poseidon
    "8188404": -6,  # Hades
    "8188390": -6,  # Hera
    "8188155": -6,  # Demeter
    "8188391": -6,  # Hestia
    "8189678": -6,  # Leto
    "8182161": -6,  # Amphitrite
    "8190121": -6,  # Thetis
    "8182233": -5,  # Apollo
    "8187829": -5,  # Artemis
    "8187870": -5,  # Athena
    "8182253": -5,  # Ares
    "8188480": -5,  # Hermes
    "8182231": -5,  # Aphrodite
    "8188476": -5,  # Hephaistos
    "8188175": -5,  # Dionysos (Olympian)
    "8189204": -5,  # Persephone
    "8189107": -5,  # Pan (god)
    "8188609": -5,  # Iris
}

# Umbral del autodetector de progenitores no-transmisores. 10 y no menos porque
# con 7 caia `Theseus` (7 hijos en gens -1..3 por ambiguedad de fuentes), que es
# un heroe mortal y si debe transmitir. Los dioses reales tienen decenas.
MIN_HIJOS_NO_TRANSMISOR = 10
MAX_SPREAD_GENERACIONAL = 2
MAX_SALTOS = 12  # mas alla de 12 saltos del ancla la generacion ya no dice nada

# Anclaje arqueologico por ventana generacional (fuentes.md §2.7)
PERIODO_POR_GEN = {
    0: "LH_IIIB",
    1: "LH_IIIB",
    2: "LH_IIIB",
    3: "LH_IIIC_early",
    4: "LH_IIIC_early",
}


def fecha_generacional(generacion: int, ancla: int = ANCLA_TROYA) -> int:
    return ancla - (GEN_TROYA - generacion) * ANIOS_GENERACION


# --------------------------------------------------- generacion por entidad


def _grafo_filial(con: sqlite3.Connection) -> tuple[dict[int, set[int]], dict[int, set[int]]]:
    """hijo -> {progenitores} y progenitor -> {hijos}, sin duplicar aristas.

    DISTINCT es imprescindible: entre dos figuras hay una fila de `relacion` por
    cada fuente que afirma la filiacion (Heracles tiene 77 afirmaciones de
    `is child of`), y sin colapsarlas el recuento de hijos del autodetector se
    dispara.
    """
    padres: dict[int, set[int]] = collections.defaultdict(set)
    hijos: dict[int, set[int]] = collections.defaultdict(set)
    for f in con.execute(
        """
        SELECT DISTINCT r.sujeto_id AS h, r.objeto_id AS p
          FROM relacion r JOIN predicado p ON p.id = r.predicado_id
         WHERE p.clave LIKE '%child_of%' AND r.objeto_id IS NOT NULL
        """
    ):
        padres[f["h"]].add(f["p"])
        hijos[f["p"]].add(f["h"])
    return padres, hijos


def _anclas(con: sqlite3.Connection) -> tuple[dict[int, tuple[int, str]], list[str]]:
    """eid -> (generacion, metodo). Semilla manual + participantes de eventos datados."""
    id_de_manto = {
        f["valor"]: f["entidad_id"]
        for f in con.execute(
            "SELECT valor, entidad_id FROM entidad_identificador WHERE namespace = 'manto'"
        )
    }
    anclas: dict[int, tuple[int, str]] = {}
    perdidas: list[str] = []
    for tabla, metodo in ((SEMILLA_DIVINA, "semilla_divina"), (SEMILLA_MORTAL, "semilla")):
        for manto, gen in tabla.items():
            eid = id_de_manto.get(manto)
            if eid is None:
                perdidas.append(f"{metodo}:{manto}")
                continue
            anclas[eid] = (gen, metodo)

    # Los participantes de los eventos con generacion manual amplian la semilla
    # sin decidir nada nuevo: la generacion ya la fijo `troya.py`.
    for f in con.execute(
        """
        SELECT DISTINCT ep.entidad_id AS eid, ev.generacion AS gen
          FROM evento_participante ep JOIN evento ev ON ev.id = ep.evento_id
         WHERE ev.generacion IS NOT NULL AND ep.entidad_id IS NOT NULL
        """
    ):
        anclas.setdefault(f["eid"], (f["gen"], "evento"))
    return anclas, perdidas


def _propagar(
    anclas: dict[int, tuple[int, str]],
    padres: dict[int, set[int]],
    hijos: dict[int, set[int]],
    bloqueados: set[int],
) -> dict[int, tuple[int, int, int, int]]:
    """BFS multi-fuente +-1 sobre la filiacion. eid -> (gen, distancia, min, max).

    Se recorre el estado `(entidad, generacion)`, no `(entidad)`: una figura puede
    ser alcanzada con generaciones distintas por ramas distintas, y eso es dato,
    no error. Gana la generacion implicada por las anclas **mas cercanas**, y si
    esas discrepan se guarda el rango — el mito no tiene version canonica.
    """
    cand: dict[int, list[tuple[int, int]]] = {e: [(g, 0)] for e, (g, _) in anclas.items()}
    cola = collections.deque((e, g, 0) for e, (g, _) in anclas.items())
    visto = {(e, g) for e, (g, _) in anclas.items()}

    while cola:
        e, g, d = cola.popleft()
        if d >= MAX_SALTOS:
            continue
        if e not in bloqueados:  # hacia abajo: hijo = progenitor + 1
            for h in hijos.get(e, ()):
                if (h, g + 1) in visto:
                    continue
                visto.add((h, g + 1))
                cand.setdefault(h, []).append((g + 1, d + 1))
                cola.append((h, g + 1, d + 1))
        for p in padres.get(e, ()):  # hacia arriba: progenitor = hijo - 1
            if p in bloqueados or (p, g - 1) in visto:
                continue
            visto.add((p, g - 1))
            cand.setdefault(p, []).append((g - 1, d + 1))
            cola.append((p, g - 1, d + 1))

    salida: dict[int, tuple[int, int, int, int]] = {}
    for e, cs in cand.items():
        dmin = min(d for _, d in cs)
        cercanas = sorted(g for g, d in cs if d == dmin)
        # el rango sale solo de las anclas mas cercanas: incluir las lejanas daba
        # [-8, 9] para casi todo y no informaba de nada
        salida[e] = (int(statistics.median(cercanas)), dmin, cercanas[0], cercanas[-1])
    return salida


def derivar_entidades(con: sqlite3.Connection) -> str:
    """Calcula `entidad_generacion` y sincroniza `entidad.generacion`."""
    anclas, perdidas = _anclas(con)
    padres, hijos = _grafo_filial(con)
    nodos = set(padres) | set(hijos)

    bloqueados = {e for e, (_, m) in anclas.items() if m == "semilla_divina"}
    res: dict[int, tuple[int, int, int, int]] = {}
    for _ in range(6):
        res = _propagar(anclas, padres, hijos, bloqueados)
        nuevos = {
            p
            for p, hs in hijos.items()
            if p not in bloqueados and len(hs) >= MIN_HIJOS_NO_TRANSMISOR
            for gs in [[res[h][0] for h in hs if h in res]]
            if len(gs) >= 3 and max(gs) - min(gs) > MAX_SPREAD_GENERACIONAL
        }
        if not nuevos:
            break
        bloqueados |= nuevos

    con.execute("DELETE FROM entidad_generacion")
    filas = []
    for eid, (gen, dist, lo, hi) in res.items():
        metodo = anclas[eid][1] if eid in anclas else "genealogica"
        confianza = (
            "alta"
            if metodo in ("semilla", "semilla_divina")
            else "media"
            if dist <= 2 and lo == hi
            else "baja"
        )
        filas.append(
            {
                "entidad_id": eid,
                "generacion": gen,
                "generacion_min": lo,
                "generacion_max": hi,
                "distancia": dist,
                "metodo": metodo,
                "transmite": 0 if eid in bloqueados else 1,
                "confianza": confianza,
                "nota": (
                    None
                    if lo == hi
                    else f"las anclas a {dist} salto(s) implican entre {lo} y {hi}"
                ),
            }
        )
    for f in filas:
        insert_ignore(con, "entidad_generacion", f)
    con.execute("UPDATE entidad SET generacion = NULL WHERE generacion IS NOT NULL")
    con.execute(
        "UPDATE entidad SET generacion = "
        "(SELECT g.generacion FROM entidad_generacion g WHERE g.entidad_id = entidad.id) "
        "WHERE id IN (SELECT entidad_id FROM entidad_generacion)"
    )
    con.commit()

    n_amb = sum(1 for f in filas if f["generacion_min"] != f["generacion_max"])
    aviso = f" · {len(perdidas)} semillas sin entidad" if perdidas else ""
    return (
        f"{len(filas)} entidades con generacion de {len(nodos)} con filiacion "
        f"({len(filas) * 100 // max(len(nodos), 1)} %) · {len(bloqueados)} progenitores "
        f"no transmiten · {n_amb} con rango ambiguo{aviso}"
    )


# ------------------------------------------------- anclaje generacion -> anio


def anclar_autoridades(con: sqlite3.Connection) -> str:
    """Rellena `generacion_ancla`: una escala completa por autoridad antigua.

    Las 11 autoridades no discrepan en el ORDEN de los hechos, solo en donde cae
    el ancla troyana: Duris en -1334, Eforo en -1135. Asi que cada una define su
    propia escala con la misma pendiente de 33 anios por generacion, y cambiar de
    autoridad re-fecha el mito entero sin reordenarlo.
    """
    autoridades = con.execute(
        """
        SELECT d.autoridad, d.sistema, d.anio_ac, d.anio_min_ac, d.anio_max_ac, d.es_preferida
          FROM evento_datacion d JOIN evento e ON e.id = d.evento_id
         WHERE e.nombre = 'Guerra de Troya' AND d.anio_ac IS NOT NULL
         ORDER BY d.anio_ac DESC
        """
    ).fetchall()
    if not autoridades:
        return "generacion_ancla: sin dataciones de la Guerra de Troya, nada que anclar"

    rango = con.execute(
        "SELECT MIN(generacion) lo, MAX(generacion) hi FROM entidad_generacion"
    ).fetchone()
    lo = min(rango["lo"] if rango["lo"] is not None else GEN_SIN_FECHA, GEN_SIN_FECHA)
    hi = max(rango["hi"] if rango["hi"] is not None else GEN_TROYA, GEN_TROYA + 2)

    con.execute("DELETE FROM generacion_ancla")
    n = 0
    for a in autoridades:
        for gen in range(lo, hi + 1):
            anio = fecha_generacional(gen, a["anio_ac"])
            insert_ignore(
                con,
                "generacion_ancla",
                {
                    "autoridad": a["autoridad"],
                    "sistema": a["sistema"],
                    "generacion": gen,
                    "anio_ac": anio,
                    "anio_min_ac": anio - ANIOS_GENERACION,
                    "anio_max_ac": anio + ANIOS_GENERACION,
                    "anios_por_generacion": ANIOS_GENERACION,
                    "ancla_troya_ac": a["anio_ac"],
                    "es_preferida": a["es_preferida"],
                },
            )
            n += 1
    con.commit()
    return (
        f"generacion_ancla: {n} filas · {len(autoridades)} autoridades "
        f"({autoridades[0]['autoridad']} {autoridades[0]['anio_ac']} … "
        f"{autoridades[-1]['autoridad']} {autoridades[-1]['anio_ac']}) "
        f"· generaciones {lo}..{hi}"
    )


def cargar(con: sqlite3.Connection) -> str:
    fuente_id = registrar_fuente(
        con,
        clave="generacional",
        nombre="Derivacion generacional (metodo de Eratostenes)",
        version="fuentes.md §5.3",
        url="https://www.centuries.co.uk/2009-ancient%20chronography-kokkinos.pdf",
        licencia="Derivacion propia",
        fecha_descarga=datetime.now(UTC).date().isoformat(),
        atribucion_texto=(
            "Fechas derivadas por desplazamiento generacional respecto al ancla de "
            "Eratostenes (caida de Troya 1184/1183 a.C.), generacion de 33 anios "
            "(Hecateo via Herodoto)."
        ),
    )

    # El esquema de generacion es posterior a 001-003; IF NOT EXISTS lo hace
    # idempotente y evita obligar a un `init` completo sobre una base ya cargada.
    con.executescript((SQL_DIR / "004_generacion.sql").read_text(encoding="utf-8"))
    con.commit()
    informe_entidades = derivar_entidades(con)

    periodos = {f["clave"]: f["id"] for f in con.execute("SELECT clave, id FROM periodo")}

    n_derivadas = n_sin_fecha = 0
    filas = con.execute(
        """
        SELECT ev.id, ev.nombre, ev.generacion
          FROM evento ev
         WHERE NOT EXISTS (SELECT 1 FROM evento_datacion d
                            WHERE d.evento_id = ev.id AND d.sistema <> 'generacional')
        """
    ).fetchall()

    for f in filas:
        gen = f["generacion"]
        if gen is None or gen <= GEN_SIN_FECHA:
            con.execute(
                "UPDATE evento SET fecha_ac = NULL, fecha_min_ac = NULL, fecha_max_ac = NULL, "
                "fecha_metodo = 'sin_fecha', fecha_confianza = 'nula' WHERE id = ?",
                (f["id"],),
            )
            n_sin_fecha += 1
            continue

        anio = fecha_generacional(gen)
        insert_ignore(
            con,
            "evento_datacion",
            {
                "evento_id": f["id"],
                "autoridad": "derivado generacional",
                "sistema": "generacional",
                "anio_ac": anio,
                "anio_min_ac": anio - ANIOS_GENERACION,
                "anio_max_ac": anio + ANIOS_GENERACION,
                "precision": "vago",
                "es_preferida": 0,
                "fuente_dataset_id": fuente_id,
                "nota": (
                    f"Generacion {gen} respecto al ancla troyana (gen {GEN_TROYA} = "
                    f"{abs(ANCLA_TROYA)} a.C., Eratostenes), {ANIOS_GENERACION} anios/gen. "
                    "La caida de Troya cae al FINAL de la gen 2, no en su centro: los "
                    "cronografos antiguos corregian por media generacion."
                ),
            },
        )
        con.execute(
            "UPDATE evento SET periodo_id = COALESCE(periodo_id, ?) WHERE id = ?",
            (periodos.get(PERIODO_POR_GEN.get(gen, "")), f["id"]),
        )
        n_derivadas += 1

    con.commit()
    n_pref = marcar_preferidas(con)
    n_sync = sincronizar(con)
    informe_anclas = anclar_autoridades(con)
    return (
        f"generacional: {n_derivadas} fechas derivadas, {n_sin_fecha} sin fecha (correcto), "
        f"{n_pref} preferidas marcadas, {n_sync} eventos sincronizados\n"
        f"  entidades: {informe_entidades}\n"
        f"  {informe_anclas}"
    )


def marcar_preferidas(con: sqlite3.Connection) -> int:
    """Elige una datacion preferida por evento si no hay ninguna.

    Prioridad: cronografo antiguo (Eratostenes primero) > arqueologico > generacional.
    """
    sin_preferida = con.execute(
        """
        SELECT ev.id FROM evento ev
         WHERE EXISTS (SELECT 1 FROM evento_datacion d WHERE d.evento_id = ev.id)
           AND NOT EXISTS (SELECT 1 FROM evento_datacion d
                            WHERE d.evento_id = ev.id AND d.es_preferida = 1)
        """
    ).fetchall()

    n = 0
    for f in sin_preferida:
        elegida = con.execute(
            """
            SELECT id FROM evento_datacion WHERE evento_id = ?
             ORDER BY CASE WHEN autoridad = 'Eratostenes' THEN 0
                           WHEN sistema = 'cronografo_antiguo' THEN 1
                           WHEN sistema = 'arqueologico' THEN 2
                           ELSE 3 END,
                      CASE precision WHEN 'anio' THEN 0 WHEN 'lustro' THEN 1
                           WHEN 'decada' THEN 2 ELSE 3 END
             LIMIT 1
            """,
            (f["id"],),
        ).fetchone()
        if elegida:
            con.execute(
                "UPDATE evento_datacion SET es_preferida = 1 WHERE id = ?", (elegida["id"],)
            )
            n += 1
    con.commit()
    return n


def sincronizar(con: sqlite3.Connection) -> int:
    """Copia la datacion preferida a evento.fecha_* (campo derivado, no primario)."""
    filas = con.execute(
        """
        SELECT d.evento_id, d.anio_ac, d.anio_min_ac, d.anio_max_ac, d.sistema, d.precision
          FROM evento_datacion d WHERE d.es_preferida = 1
        """
    ).fetchall()

    confianza = {"anio": "alta", "lustro": "alta", "decada": "media", "medio_siglo": "media"}
    for f in filas:
        metodo = {
            "cronografo_antiguo": "cronografo_antiguo",
            "arqueologico": "arqueologico",
            "generacional": "generacional",
            "moderno": "moderno",
        }.get(f["sistema"], "moderno")
        con.execute(
            "UPDATE evento SET fecha_ac = ?, fecha_min_ac = ?, fecha_max_ac = ?, "
            "fecha_metodo = ?, fecha_confianza = ? WHERE id = ?",
            (
                f["anio_ac"],
                f["anio_min_ac"],
                f["anio_max_ac"],
                metodo,
                "baja" if f["sistema"] == "generacional" else confianza.get(f["precision"], "baja"),
                f["evento_id"],
            ),
        )
    con.commit()
    return len(filas)
