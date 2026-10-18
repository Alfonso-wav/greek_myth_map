# greek — base de datos relacional de mitología griega

Pipeline ETL que descarga datasets académicos abiertos de mito griego y los carga en una
**base SQLite local** (`data/greek.db`). Sin servidor, sin nube: fichero local.

Documento de diseño de referencia: **`.claude/fuentes.md`** — catálogo de fuentes, esquema SQL
completo, orden de ingesta, estrategia de fechas y coordenadas. **Léelo antes de tocar el
esquema o añadir un loader.** Este CLAUDE.md resume las reglas operativas; `fuentes.md` es la
autoridad sobre el contenido.

## Stack

- Python 3.11+, stdlib `sqlite3` (sin ORM). SQL explícito en `.sql` versionados.
- **`uv` gestiona paquetes y ejecución.** Deps declaradas en `pyproject.toml`, lockfile
  `uv.lock` **sí va a git**. No uses `pip`, `python -m venv` ni `requirements.txt`.
- Deps: `httpx` (descargas), `rapidfuzz` (fuzzy join), `unidecode` (normalización),
  `rdflib` solo para los `.ttl` de ToposText. `csv`/`json` de stdlib.
- Sin dependencias de LLM, sin scraping HTML salvo huecos concretos y licencia permisiva.

## Layout

```
greek/
  .claude/fuentes.md      # documento de diseño (autoridad)
  pyproject.toml          # deps + config, gestionado por uv
  uv.lock                 # lockfile, versionado
  data/
    raw/{manto,pleiades,topostext,wikidata,chrono,dmp}/   # dumps descargados, NO en git
    greek.db                                             # salida, NO en git
  sql/
    001_schema.sql        # DDL: bloques 0-5 de fuentes.md §4
    002_views.sql         # vistas de conveniencia (§4 "Vistas")
    003_seed.sql          # tipo_entidad, ciclo_mitico, periodo, fuente_dataset
    004_generacion.sql    # entidad_generacion + generacion_ancla + vw_generaciones
    qa.sql                # checks de §6
  docker-compose.yml      # Memgraph + Memgraph Lab (front de exploracion)
  cypher/
    consultas.cypher      # consultas de partida, verificadas contra el grafo
    greek.gss             # Graph Style Script para Lab
  src/greek/
    db.py                 # conexión, PRAGMAs, upsert helpers
    fetch.py              # descarga de dumps a data/raw/ (idempotente, cachea)
    loaders/              # un módulo por fuente: pleiades.py, manto.py, topostext.py,
                          # wikidata.py, dmp.py, eusebio.py, generacional.py
    reconcile.py          # matching entre fuentes por ID externo (§5.1)
    normalize.py          # forma canónica de nombres: pliegues grc→lat, sin acentos
    fuzzy.py              # fuzzy join + fusión + elección de nombre canónico
    qa.py                 # ejecuta sql/qa.sql + vw_huecos, informe a stdout
    graph.py              # proyeccion a Memgraph (solo lectura, desechable)
    export.py             # JSON estatico para la web del mapa
    cli.py                # `uv run greek <comando>`
  web/                    # Periégesis: mapa + eje generacional (React/TS/Vite/Leaflet)
    src/                  # datos.ts (indices), Mapa.tsx, Tiempo.tsx (slider+histo), Panel.tsx
    public/data/greek.json  # salida de `greek export-web`, SI en git (lo sirve GitHub Pages)
```

## Comandos

Todo pasa por `uv`. `uv run` sincroniza el entorno solo si hace falta; no hay que activar nada.

```bash
uv sync                                    # instala/actualiza el entorno desde uv.lock
uv add rapidfuzz                           # añadir dep (edita pyproject.toml + uv.lock)
uv add --dev pytest ruff                   # dep de desarrollo

uv run greek fetch [--source manto|pleiades|...]   # descarga dumps a data/raw/
uv run greek init                                  # crea esquema + seeds
uv run greek load <source>                         # carga una fuente
uv run greek load-all                              # orden de §5.1, incluye fuzzy
uv run greek fuzzy --dry-run                       # informe de fusiones sin aplicarlas
uv run greek fuzzy --apply                         # aplica fusiones ≥ umbral auto
uv run greek fuzzy --undo <fusion_id>              # revierte una fusión
uv run greek qa                                    # checks de calidad
uv run ruff check . && uv run pytest               # lint + tests
sqlite3 data/greek.db                              # inspección manual

docker compose up -d                               # Memgraph + Lab (front de grafo)
uv run greek graph --wipe                          # proyecta la base entera (~19 s)
uv run greek graph --only entidades relaciones     # recarga pasos sueltos

uv run greek export-web                            # JSON estatico -> web/public/data/
cd web && npm install && npm run dev               # Periégesis en local
```

Declara el entrypoint `greek` en `pyproject.toml` (`[project.scripts] greek = "greek.cli:main"`).

Cada carga es **re-ejecutable**. `load` dos veces = mismo resultado.

## Invariantes del modelo — no negociables

Vienen de `fuentes.md` §1 y §7. Romperlas degrada la base a nivel wiki.

1. **El nombre nunca es clave primaria.** ID sintético interno (`entidad.id`). La
   reconciliación **prioritaria** va por `entidad_identificador(namespace, valor)` — MANTO
   URI, Wikidata QID, Pleiades ID. El fuzzy join (ver sección propia) es el **fallback** para
   lo que no tiene ID externo compartido, y siempre deja rastro en `fuzzy_fusion`.
2. **Sin `padre_id`/`madre_id` en `entidad`.** El mito no tiene versión canónica. Toda
   relación es una fila en `relacion` (sujeto → predicado → objeto) con su pasaje fuente y
   sus cuatro flags: `dato_incierto`, `duda_expresada`, `alternativas_dadas`,
   `dato_implicito`. Preservar esos flags al cargar MANTO `Tie`.
3. **Sin coordenadas inventadas.** Hades/Tártaro/Eliseo → `geo_tipo =
   'legendario_sin_ubicacion'`, `latitud = NULL`, `es_ficticio = 1`. Un `CHECK` del esquema
   lo fuerza; no lo quites. Siempre registrar `geo_fuente` y `precision_metros`.
4. **`evento.fecha_ac` es derivado, no primario.** El dato real vive en `evento_datacion`
   (N dataciones por evento, una `es_preferida = 1`). Si un evento solo tiene una fecha,
   estás afirmando algo que las fuentes antiguas no afirman.
5. **Upsert, nunca `DELETE` + recarga.** `INSERT ... ON CONFLICT DO UPDATE` sobre las claves
   UNIQUE de ID externo. Un `DELETE FROM` masivo destruye `revisado_manual` y las
   correcciones humanas.
6. **`location_precision = 'rough'` no es una coordenada fiable** — puede ser el centroide de
   una caja de 100 km. Propagar el flag, no ocultarlo.
7. **Un solo nombre canónico por entidad.** Tras fusionar, `entidad.nombre` queda en forma
   **latina/castellana** (Circe, Urano, Aquiles) — nunca conviven `Kirke` y `Circe` como
   entidades ni como valor de `nombre`. Todas las variantes absorbidas (griego,
   transliteración, latín, etrusco, epítetos) se conservan en `entidad_nombre`: se normaliza
   la identidad, no se pierde información.
8. **MANTO decide, Wikidata enriquece.** Si discrepan en un hecho mitológico, gana MANTO.
   Wikidata solo para `nombre_es`, descripciones, enlaces y coordenadas de respaldo.

## Fuzzy join y normalización de nombres

Cuando dos filas de fuentes distintas no comparten ningún ID externo, se unen por **fuzzy
match** y el resultado se **normaliza a un solo nombre canónico**. Esto contradice
deliberadamente `fuentes.md` §1.1 (que pedía cola de revisión manual): decisión del usuario.
La contrapartida obligatoria es que **toda fusión sea auditable y reversible**.

### Forma normalizada (`normalize.py`)

`normalizar()` es la clave de comparación (`entidad.nombre_norm`), nunca se muestra:

1. `unidecode` **siempre** + NFD sin diacríticos (`Ἀχιλλεύς` → `achileus`; `Áyax` → `ayax`).
   El griego politónico vive en U+0370–U+03FF, por debajo de cualquier umbral "exótico":
   condicionar el `unidecode` por rango dejaba el nombre en griego y el filtro `[^a-z]`
   posterior lo vaciaba.
2. minúsculas, quitar puntuación, colapsar espacios.
3. pliegues griego→latín aplicados **hasta punto fijo** (`_plegar`): `k`→`c`, `ai`→`e`,
   `ou`→`u`, `y`→`i`, sufijos `-os`/`-us` → `-o`. Así `Kirke`=`Circe`, `Ouranos`=`Urano`.
   Iterar es lo que lo hace idempotente: una sola pasada dejaba `ayax`→`aiax` y la
   siguiente lo movía a `eax`.
4. **Conserva el desambiguador entre paréntesis.** Descartarlo fusionaba lugares distintos:
   `Kastri (Euboea)` y `Kastri (Serres)` colapsaban a `kastri` y se unían con score 100.
   Para agrupar homónimos hay `normalizar_base()`, que sí lo quita.

### Bandas de decisión

`rapidfuzz.fuzz.ratio` sobre la forma normalizada — **no `WRatio`**: su boost de coincidencia
parcial fusionó `'Tower 7'` con `'tower (Arkoi)'` a 95,0 en la primera pasada real.
**Prerrequisitos duros:** mismo `tipo_entidad` (un río-dios no se fusiona con una ciudad
homónima) y mismo designador.

| Score | Acción |
|---|---|
| ≥ 97 | fusión automática |
| 88–96 | fusión **solo si** comparten ≥1 relación genealógica o ≥1 lugar asociado; si no, a `entidad_revision` |
| 80–87 | no fusiona; `entidad_revision` + mismo `homonimo_grupo` |
| < 80 | entidades distintas |

El umbral automático es 97 y no 95 porque el tramo 95–96 mezclaba variantes que solo coinciden
"casi" (`Nymphs Sanctuary` con `Nymphe Sanctuary`); los duplicados reales puntúan 100.

**Veto por designador** (`normalize.numeros`): cifras, numerales romanos y letras sueltas
identifican un elemento dentro de una serie y no admiten aproximación. `Tower 7`/`Tower 11`,
`Germania I`/`Germania II`, `Basilica A`/`Basilica D`, `Building Y`/`Building Z` no se
fusionan aunque el resto de la cadena sea idéntico.

**Veto de fusión** (nunca fusionar, aunque el score sea 100): las dos entidades comparten un
namespace de `NAMESPACES_VETO` (`manto`, `wikidata`, `pleiades`, `digital_limc`). Como el
esquema tiene `UNIQUE(namespace, valor)`, compartir namespace implica valores distintos, así
que el veto se decide **sin puntuar el par**: es la poda que baja el fuzzy join de 295 s a
2,6 s sobre 42.000 entidades. Un ID externo que discrepa es evidencia más fuerte que cualquier
score. Los vetados **no** van a `entidad_revision`: el dato ya zanja el caso y encolarlos
llenaba la tabla con millones de pares que nadie tiene que decidir; solo se cuentan en el
informe.

### Elección del nombre canónico

Al fusionar, `entidad.nombre` = primer valor no nulo de esta cadena:

1. `nombre_es` de Wikidata (P1476/label es)
2. forma latina de MANTO
3. `romanized_form_1` de Pleiades (para lugares)
4. entrada de Smith (`smith:{nombre}-{n}`)
5. el nombre de la entidad con más relaciones (la mejor atestiguada)

Las demás variantes → `entidad_nombre` con su `tipo` y `lengua_tag`. Los
`entidad_identificador` de ambas se acumulan en la superviviente. Las `relacion`,
`relacion_rol`, `evento_participante` y `lugar_*` se reapuntan al `id` superviviente
(`UPDATE ... SET entidad_id = superviviente`), con `INSERT OR IGNORE` en las tablas que
tienen UNIQUE para absorber duplicados.

### Auditoría y reversibilidad

Dos tablas extra sobre el esquema de `fuentes.md` §4:

```sql
CREATE TABLE fuzzy_fusion (
    id                  INTEGER PRIMARY KEY,
    superviviente_id    INTEGER NOT NULL REFERENCES entidad(id),
    absorbida_id        INTEGER NOT NULL,      -- id ya inexistente en entidad
    absorbida_nombre    TEXT NOT NULL,
    absorbida_json      TEXT NOT NULL,         -- fila completa + sus ids/nombres/relaciones
    score               REAL NOT NULL,
    algoritmo           TEXT NOT NULL,         -- 'rapidfuzz.WRatio'
    umbral              REAL NOT NULL,
    banda               TEXT NOT NULL CHECK (banda IN ('auto','corroborada','manual')),
    evidencia           TEXT,                  -- qué la corroboró en la banda 88-94
    fecha               TEXT NOT NULL,
    revertida           INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE entidad_revision (
    id            INTEGER PRIMARY KEY,
    entidad_a_id  INTEGER NOT NULL REFERENCES entidad(id),
    entidad_b_id  INTEGER NOT NULL REFERENCES entidad(id),
    score         REAL NOT NULL,
    motivo        TEXT,          -- 'banda 80-87', 'ids externos discrepantes'
    decision      TEXT CHECK (decision IN ('pendiente','fusionar','separadas')),
    UNIQUE (entidad_a_id, entidad_b_id)
);
```

`absorbida_json` es lo que hace posible `fuzzy --undo`. Sin él la fusión es destructiva y hay
que recargar desde cero — no lo omitas.

Reglas de operación:

- `fuzzy --dry-run` **antes** de `--apply`, siempre. Revisa la banda 88–96 a ojo.
- El informe se calcula antes de fusionar, así que al aplicar hay que comprobar que ambas
  entidades de una revisión siguen existiendo: si una fue absorbida por una fusión anterior,
  el `INSERT` en `entidad_revision` falla por FK.
- Fusionar es **idempotente**: re-ejecutar no crea fusiones nuevas ni duplica filas.
- Nunca fusiones nada con `revisado_manual = 1` sin `--force`.
- Métrica de vigilancia: si `fuzzy_fusion` supera el ~8 % de `entidad`, el umbral está
  demasiado bajo — en mito griego los homónimos legítimos son masivos y una tasa de fusión
  alta significa que estás borrando personajes distintos, no deduplicando.

## Generación mítica (`loaders/generacional.py`) — eje temporal de la web

`entidad.generacion` no viene en el dump: MANTO publica `generation_11335.json` pero ninguna
entidad lo referencia. Se deriva de las 5.584 aristas `is child of`, y **dos enfoques obvios
fallan** (probados contra el dato, no descartados a priori):

1. **Profundidad desde las raíces genealógicas.** Hay 556 "raíces" y son heterogéneas: `Ge` es
   raíz por primordial, `Antenor (Trojan)` es raíz porque MANTO no anota a sus padres. Un BFS
   desde raíces mete a Antenor y su prole en la cosmogonía.
2. **Camino más largo desde los primordiales.** Da Heracles 28, Aquiles 18 y Atreo 7 con su
   hijo Agamenón en 26. El camino más largo cose tradiciones incompatibles que ninguna fuente
   afirma juntas, y los ríos-dioses, personificaciones y ninfas encadenan sin fin.

Lo que funciona: **semilla manual + BFS ±1**, mismo principio que ya usa el proyecto para los
eventos. Piezas no negociables:

- **La semilla va por ID de MANTO, nunca por nombre.** Hay homónimos que la romperían en
  silencio: `Tartaros (personification)`/`(Thessalian)`, `Hyperion (Titan)`/`(Mycenaean)`,
  `Phoibe (Titan)`/`(Messenian)`, `Coios (Titan)`/`(Messenian)`,
  `Deucalion (Thessalian)`/`(Cretan)`. Invariante 1.
- **La paternidad divina NO transmite cronología.** Zeus tiene 68 hijos entre gen −7 y 3;
  Poseidón 85 entre −5 y 3. Los dioses van en `SEMILLA_DIVINA` con `transmite = 0`, y además
  se **autodetectan** los que faltan por la regla "≥10 hijos repartidos en más de 2
  generaciones no es un eslabón cronológico" — esa regla sola encuentra a Poseidón, Zeus,
  Apolo, Ares, Océano, Ge, Hermes, Urano y Atlas. El umbral es 10 y no 7 porque con 7 caía
  `Theseus`, que es mortal y sí debe transmitir.
- **Escala del proyecto: Troya = 2**, calibrada con la semilla de eventos de `troya.py`
  (Deucalión −5, Perseo −3, Teseo −1, Heracles 0, Troya 2, Orestíada 3, Heraclidas 4). No
  inventes una segunda escala: `evento.generacion` ya usa esta y `GEN_SIN_FECHA = -6`.
- **El rango `generacion_min/max` sale solo de las anclas más cercanas.** Mirar todos los
  caminos daba `[-8, 9]` para casi todo y marcaba 1.239 de 1.242 entidades como ambiguas.
- Los huérfanos quedan a NULL. 1.372 entidades con generación de 2.696 con filiación (50 %);
  inventar el resto sería peor que el hueco.

`generacion_ancla` (tabla nueva, `sql/004_generacion.sql`) da generación → año por autoridad:
las 11 cronografías no discrepan en el orden, solo en dónde cae el ancla troyana, así que cada
una define su escala con la misma pendiente de 33 años/generación.

`loaders/predicados_es.py`: los 165 predicados con etiqueta castellana. `predicado.nombre_es`
venía siendo la clave con guiones bajos por espacios (`makes sacrifice [of] [ind. obj.]`) y eso
se filtraba a la web. Los corchetes se quitan del verbo porque son ranuras de argumento, no
parte del predicado, y esa información ya viaja en `relacion_rol` con el rol en castellano.
`_base()` quita las ranuras **con regex sobre la cadena entera**: partir por `_` primero deja
pedazos sueltos en `[fictional_alias_/_agent]` y `[relic_in_historical_period]`.

## Papel de cada agente (`loaders/papeles.py`) — filtros de la web

MANTO **no distingue dios/héroe/mortal/monstruo**: todo es `Agent`, y `genero`/`es_mortal`
quedan a NULL. Los filtros de la web («por dios, héroe, gobernador») exigen derivarlo, y la
inferencia ingenua se equivoca justo en las figuras centrales del corpus. Cuatro trampas
**comprobadas contra 38 figuras de control**, no supuestas:

1. **Al héroe se le rinde culto igual que al dios.** Recibir sacrificio, tener sacerdote, que
   alguien instaure tu culto o ser patrón de algo marcaba como dioses a Heracles, Aquiles,
   Odiseo, Jasón, Neoptólemo, Edipo y Pélope. No son señales de divinidad sino **de culto**, y
   el culto heroico griego es masivo. Aquí se usan al revés, como indicio de héroe.
2. **Los héroes se aparecen.** `appears_in_an_epiphany` lo tienen Aquiles, Heracles y Teseo (la
   epifanía post mortem del héroe está históricamente atestiguada). Inservible para divinidad.
3. **Los monstruos matan.** «Héroe = sujeto de predicado bélico o de muerte» metía al
   Minotauro, a Escila y a Tifón entre los héroes.
4. **Los dioses gobiernan dominios.** `rules [direct obj]` lo tienen Zeus y Hades (el reino).
   Sin precedencia, «gobernante» se llenaba de olímpicos y dejaba de servir para hallar reyes.

De ahí la regla de oro: **la descripción de Wikidata manda y los predicados solo rellenan
huecos.** Es texto humano y preciso («diosa de la sabiduría», «rey de Creta», «monstruo mitad
toro»), cubre 1.006 de 5.353 agentes y resuelve sola todo lo que las reglas por predicado se
comían.

Piezas que no conviene tocar sin volver a pasar los controles:

- **Multi-etiqueta, no excluyente.** Agamenón gobierna Micenas **y** combate en Troya; Heracles
  es héroe **y** deificado. Un solo papel por figura falsea el dato.
- **`dios` y `monstruo` son identidad excluyente; `gobernante`, `heroe`, `profeta` y `artesano`
  son papeles acumulables.** Esa distinción decide quién pisa a quién: una descripción humana
  gana a un predicado en las excluyentes, pero no impide que un predicado añada una acumulable.
  Sin ella, Odiseo perdía «héroe» al ganar «rey».
- **`monstruo` no se asigna si el mismo texto ya dijo dios/héroe/gobernante**: la ficha de
  Belerofonte es «héroe que montó a Pegaso y mató a la Quimera» y el patrón capturaba a la
  Quimera, que es su víctima.
- **`gives_prophecy` no es exclusivo de dioses**: Quirón es un centauro y profetiza. Por eso el
  bloque de predicados divinos solo actúa cuando la descripción no dijo nada.
- **Ser monstruo no impide gobernar**: Egeo gobierna Atenas seis veces y además tiene
  `has_monstrous_form`, que en la tradición de los reyes autóctonos atenienses es su aspecto
  serpentino. Igual Midas y Ámmon.
- **El plural «de los dioses» no cuenta como divinidad**: es genitivo y lo llevan mortales
  (Ganimedes, «copero de los dioses»). Zeus recibe `dios` de la semilla, no de su descripción.
- Cada fila guarda **la regla que la decidió** (`descripcion:diosa`, `predicado:gobierno`,
  `culto_heroico`, `semilla_divina`). Sin eso no hay forma de discutir por qué Heracles sale
  héroe y no dios.

Estado: 1.235 de 5.353 agentes clasificados (23 %) — gobernante 776, heroe 395, dios 167,
monstruo 96, deificado 28, profeta 6, artesano 3. **38/38 figuras de control correctas** y
ningún monstruo clasificado como héroe.

`graph.py` los proyecta como etiqueta de nodo (`:Dios`, `:Heroe`, `:Gobernante`, `:Monstruo`…)
además de propiedad, para poder escribir `MATCH (h:Heroe)-[:KILLS]->(m:Monstruo)`.

## Web del mapa (`export.py` + `web/`)

`greek export-web` escupe un JSON estático (2,9 MB: 1.104 lugares, 816 agentes, 9.937
afirmaciones, 3.409 contradicciones de ubicación, 11 autoridades). **No hay backend** y no hace
falta: el payload es diminuto porque solo salen los lugares que el mito toca y tienen
coordenada, no los 36.851 de Pleiades.

- El lugar de una afirmación puede venir del objeto directo **o de un rol** (`en`, `hacia`,
  `desde`): son 2.209 por objeto y 7.728 por rol. Mirar solo el objeto perdía el 78 %.
- **`DESIGN.md` (raíz) es la autoridad visual** de la web, que se llama **Periégesis**. Los
  colores, tipos y radios salen de `web/src/tokens.css`, generado con
  `node <design-md>/scripts/design.mjs tokens DESIGN.md --out web/src/tokens.css`; ningún color
  literal en componentes (`design.mjs drift DESIGN.md web/src` lo comprueba).
- React + TS + Vite + Leaflet con raster de OSM. El gris del mapa es un `filter` sobre
  `.leaflet-tile-pane`, no sobre el contenedor: si va al contenedor se come también los
  marcadores. En oscuro, `invert()` y luego `grayscale()`.
- Los marcadores van en canvas y leen sus colores de las variables CSS **al pintarse**: `Mapa`
  repinta cuando cambia `data-theme` o el esquema del sistema (`useEsquema`). Sin eso, al cambiar
  de tema conservaban la rampa del anterior.
- Atribución OSM (ODbL) y MANTO (CC BY-NC) en el mapa, obligatorias.
- Paleta: solo dos colores significan algo, la rampa de **tinta ferrogálica** azul (magnitud) y
  la **rúbrica** roja (contradicción). Validados con el validador de la guía de dataviz contra las
  superficies reales, en claro y oscuro, y la rúbrica contra **cada** paso de la rampa: peor par
  CVD ΔE 16,6 / 14,7 (la paleta sepia/verdigris anterior daba 9,2 y caía en la «crema con
  terracota» que prohíbe el manifiesto de diseño). La rampa de marcas es **ordinal de 4 pasos, no
  secuencial de 5**: el quinto era el más claro y no despegaba del fondo (el suelo es 2:1).
- El histograma se dibuja a píxeles reales con `ResizeObserver`; con
  `preserveAspectRatio="none"` el viewBox se estiraba 1,65× en X y deformaba el redondeo de 4 px
  y los huecos de 2 px.
- El histograma cuenta **solo afirmaciones no divinas**: la `g` de una divinidad es teogónica
  (−9..−5) y el mapa las trata como atemporales, así que contarlas por generación hacía que el
  histograma y el mapa dijeran cifras distintas.
- `contradiccion` guarda un par de relaciones por **cada** combinación de fuentes que discrepan,
  así que el panel deduplica por (figura, predicado, otro lugar): sin eso la misma disputa
  aparecía siete veces seguidas.
- **Los filtros son dos ejes distintos, y hay que rotularlos como tales**: *quién* protagoniza
  (`entidad_papel`, derivado) y *qué* clase de hecho es (`predicado.categoria`, que ya venía en
  la base). Meterlos en una sola fila de chips sugiere que son alternativas del mismo tipo.
- **Conjunto de filtros vacío = sin filtrar, nunca «ninguno».** Un chip apagado no puede vaciar
  el mapa.
- Los recuentos de los chips se calculan **sobre lo exportado**, no sobre la base: un chip que
  promete 776 gobernantes y luego pinta 374 es peor que no tener chip.
- Dos cifras que hay que recalcular tras filtrar, no heredar del total: las divinidades visibles
  (el pie prometía 2.026 con un filtro que dejaba 138) y las líneas de disputa, que deben tocar
  algún lugar visible — con «héroes + guerra» el mapa baja a 61 lugares y seguían pintándose las
  286 líneas, tapando justo lo que el filtro acababa de aislar.

### Vista de relaciones (`export._red` + `web/src/Red.tsx`)

Sustituto estático de Memgraph Lab para la web pública (Pages no corre servidores).
`export-web` escribe además `web/public/data/red.json` (1,6 MB, **también en git**), que el
navegador pide solo al abrir la vista. Grafo ego radial en SVG, sin dependencias.

- **Una arista por (sujeto, predicado, objeto, rol)**, con `n` = fuentes. Dibujar una por
  fila de `relacion` es lo que hacía ilegible Lab: N `IS_CHILD_OF` superpuestas.
- Objeto de `objeto_id` o de los roles argumento (`graph.roles_objeto`), igual que el grafo.
- Solo figuras (`TIPOS_RED`); los lugares ya tienen el mapa.
- Flags de incertidumbre agregados con **AND**: una fuente que duda no anula a otra que afirma.
- `dis` (rúbrica) solo para contradicciones de `genealogia`/`autoria_muerte`: las de
  `ubicacion` discuten dónde, no entre quiénes, y teñían casi todas las aristas de Heracles.
- Citas internadas en una tabla (`citas` + índices): repetidas por arista eran 1,4 MB.
- Si no caben todas las figuras en el anillo, **progenitores, parejas y hermanos entran
  siempre** y el resto por fuentes: recortar por fuentes a secas dejaba fuera progenitores
  citados una vez. La descendencia no tiene prioridad: los 63 hijos de Heracles llenaban el
  anillo y echaban todo el grupo de muerte y guerra.

### Enlaces a los textos y buscador por nombre

**Enlace al pasaje** (`export.enlace_pasaje`), tres niveles del más exacto al reconstruido:
`pasaje.scaife_url` (3.497 de los 6.950 pasajes citados) → `pasaje.cts_urn` → `obra.cts_urn` más
la referencia numérica del final de la cita (145 más). Total **55 % de las citas enlazadas**, y
las plantillas están comprobadas con HTTP 200 antes de generarse (10 URLs muestreadas al azar,
10/10 resuelven).

Los **3.308 pasajes restantes se quedan sin enlace a propósito**: sus obras no tienen CTS URN —
Estrabón, Plinio, Diodoro, los escolios D, Licofrón, la *Periegesis* de Dionisio. Un enlace roto
en la ficha es peor que ningún enlace, así que ahí se muestra el texto de la cita y nada más.
`pasaje.topostext_url` está a 0 en toda la base: no sirve como alternativa.

**Fichas externas**: Pleiades / ToposText / Wikidata para los 1.104 lugares, Wikidata para 575
de los 816 agentes. Las tres plantillas verificadas. **MANTO queda fuera** aunque tengamos el id
de 1.372 agentes: es un object id de Nodegoat y no hay URL pública estable que se pueda
comprobar — no se inventa.

**Buscador** (`export.clave_busqueda` + `datos.normalizarBusqueda`): casa por **subcadena**
contra un pajar que trae, por entidad, el nombre canónico, el castellano, el griego y hasta 12
variantes de `entidad_nombre`, cada una en su forma cruda **y** transliterada con `unidecode`.
Así «kirke», «Circe» y «Κίρκη» encuentran lo mismo.

- **La búsqueda casa contra figura O lugar.** Buscar «Ítaca» debe dejar el lugar aunque ningún
  agente se llame así, y «Odiseo» debe dejar los 68 sitios donde se le atestigua.
- **No se reimplementan los pliegues de `normalize.py` en TypeScript.** Es lógica delicada
  (iteración a punto fijo) y dos copias se desincronizan. En su lugar el pajar ya contiene todas
  las grafías atestiguadas, y el cliente solo baja a minúsculas y quita diacríticos, igual que
  el servidor. El coste conocido: `unidecode` transcribe khi como `kh`, así que `Ἀχιλλεύς` entra
  como `akhilleus` y teclear `achilleus` no lo encuentra — esa grafía no la atestigua ninguna
  fuente del corpus.
- **El pajar se deduplica por palabra.** Las variantes repiten el nombre principal muchas veces
  (`circe circe kirke circe circe`) y sin deduplicar eran 1,1 MB de JSON sin una sola
  coincidencia nueva.
- Hay que **limpiar la puntuación del cualificador**: los nombres son `Zeus (Olympian)` y sin
  quitar los paréntesis el token quedaba `(olympian)`, que no casa al teclear `olympian`.

## Proyección a Memgraph (`graph.py`) — front de exploración

`greek graph` vuelca la base en Memgraph para navegarla desde Memgraph Lab. **La autoridad
sigue siendo `data/greek.db`**: Memgraph es de lectura y desechable, se reconstruye entero con
`--wipe` y no hay camino de vuelta. Nada que se edite en Lab llega al SQLite. Es idempotente
(todo `MERGE` por `gid` = el `id` de SQLite), así que re-ejecutar no duplica.

Estado medido: **74.723 nodos, 142.324 aristas en 19 s**.

Decisiones del modelo y por qué:

1. **Aristas directas, no relaciones reificadas.** `relacion` → arista
   `(:Entidad)-[:IS_CHILD_OF]->(:Entidad)`. Reificar duplica la profundidad y mata la
   exploración: `(zeus)<-[:IS_CHILD_OF*1..3]-()` deja de existir.
2. **La atestación va en propiedades de la arista** (`citas`, `autores`, `n_citas`) porque
   **Cypher no admite aristas de aristas**: un `:Pasaje` no puede apuntar a una `relacion`.
   Los `:Pasaje`/`:Obra`/`:Autor` existen igual como subgrafo navegable aparte.
3. **Las contradicciones sí se reifican** (`:Contradiccion`) — es lo único que no cabe como
   propiedad, porque une dos `relacion` distintas.
4. Los cuatro flags de incertidumbre viajan en la arista (`incierto`, `duda`, `alternativas`,
   `implicito`). Perderlos convierte el mito en dato afirmado.
5. `lat`/`lng` se llaman así, no `latitud`/`longitud`: son los nombres que Lab reconoce para
   la vista de mapa. `grado` (nº de relaciones) va como propiedad para escalar el tamaño del
   nodo — con 40.000 lugares de Pleiades el problema es el ruido, no la falta de datos.

Tres trampas ya corregidas, que no conviene reintroducir:

- **El 29 % de `relacion` tiene `objeto_id` NULL** (9.023 de 31.199) y el destino real vive en
  `relacion_rol`. `has_cult_site_[in/on/at]` son 540 filas con 539 objetos NULL y el santuario
  en el rol `en`: un `MATCH (b {gid: r.o})` con `r.o` nulo no falla, **descarta la fila en
  silencio** y dejaba 1 arista `HAS_CULT_SITE` en lugar de 572. Qué rol ocupa la posición de
  objeto **lo declara el predicado en sus corchetes** (`ROL_DE_ARGUMENTO`): no hay orden global
  que valga, porque `travels_[from]_[to]_[via]` quiere `hacia`, `derives_etymology_[from]`
  quiere `desde` y `is_depicted_[depiction:]` quiere `de`. Se emite una arista por argumento
  declarado con `rol_objeto` en la arista; los roles que **no** son argumentos
  (`con_participacion_de`, `usando`) no se promueven — «Theseus dies con_participacion_de X»
  no es «Theseus dies X» — y siguen accesibles como aristas `:ROL`.
- **La dimensión en disputa de una contradicción depende del tipo**, y hay que leerla igual que
  la escribe `reconcile.py`: `genealogia` discute el objeto (progenitor), `autoria_muerte` el
  sujeto (matador) y `ubicacion` la entidad del rol `en`. La diferencia simétrica genérica de
  {sujeto, objeto, roles} devolvía a Ariadna y la clava como «ubicaciones alternativas» de
  Teseo, y mirar solo {sujeto, objeto} dejaba las 6.314 contradicciones de `ubicacion` con cero
  `:ALTERNATIVA` (comparan dos `kills` con la misma víctima).
- **`pasaje.cita` viene en dos formas**, desnuda (`1.7`) y ya completa (`Apollodoros, Epitome
  1.1-1.4`). Concatenar autor + título + cita a ciegas produce `Pausanias, Pausanias,
  Pausanias 2.5.3`; `cita_legible()` solo prefija lo que la cita no trae.

Al escribir Cypher contra esta proyección: los nombres llevan cualificador (`Zeus (Olympian)`,
`Heracles` sin k), entre dos nodos hay **una arista por fuente que lo afirma** (usa `DISTINCT`),
y para ancestros se usa `*BFS` — un `*..8` genealógico son 12,2 millones de caminos.

## Orden de carga (§5.1)

`fuente_dataset` → Pleiades → ChronOntology → MANTO Entity → MANTO Author/Text/Passage →
MANTO Interaction (predicados) → MANTO Tie → MANTO Artifact/Inscription → ToposText →
Wikidata → **fuzzy join + normalización de nombres** → Digital Marmor Parium →
Eusebio/Attalus → tabla troyana §2.6 → derivación generacional → Smith/Roscher → QA.

El fuzzy join va **después de Wikidata** (ya están todos los `nombre_es` y QIDs disponibles
para elegir canónico y para bloquear fusiones con IDs discrepantes) y **antes de eventos**
(así `evento_participante` apunta ya a IDs definitivos y no hay que reapuntarlo).

No cargues nada sin insertar antes su fila en `fuente_dataset` (versión, licencia,
`fecha_descarga`, `atribucion_texto`).

## Correcciones a fuentes.md verificadas contra las fuentes reales

`fuentes.md` es el documento de diseño y sigue siendo la autoridad conceptual, pero al
ejecutar el pipeline aparecieron varias desviaciones. Estas ganan, porque están comprobadas:

- **⚠️ Licencia de MANTO: `CC BY-NC 4.0`, no `CC-BY 4.0`.** El registro de Zenodo declara
  `cc-by-nc-4.0`; `fuentes.md` §2.1 y §3 afirman CC-BY 4.0 con "reutilización comercial y
  remezcla permitidas". **La cláusula NonCommercial prohíbe el uso comercial**, y como MANTO
  es la espina dorsal (entidades, relaciones, predicados, pasajes), la restricción afecta de
  hecho a toda la base. Si el proyecto tiene fin comercial, hay que aclararlo con MANTO antes
  de seguir.
- **MANTO no requiere descarga manual.** El endpoint de ficheros de la API de Zenodo sirve el
  ZIP (248 MB) sin autenticación, así que `greek fetch --source manto` lo baja solo:
  `zenodo.org/api/records/19446255/files/publication-2616-20260306061219.zip/content`.
- **El tipo de entidad de MANTO va en el emoji de `Name`**, no en ninguna columna: 👤 Agent
  (5.064), 🌍 Place (2.370), 🏛 Landmark (852), 🏺 Object (369), 👥 Collective (289),
  ⭐ Constellation (36), ⏳ Mythic Event (13). Suman los 8.993. MANTO **no** distingue
  dios/héroe/mortal/monstruo: todo eso es `Agent` (de ahí el `tipo_entidad` `agente`).
- **El predicado genealógico es `is child of`** (5.586 relaciones), con **sujeto = hijo y
  objeto = progenitor**. Asumir `father_of` (sujeto = progenitor) invierte toda la genealogía
  y deja el check de ciclos mirando 0 filas, en verde por vacío.
- **El export de MANTO cita 4.234 `Passage` que su propia tabla no incluye** (p. ej.
  `Strabo 9.2.27`, ni por id ni por etiqueta). Se reconstruyen 1.050 pasajes desde la etiqueta
  de la cita; descartarlos dejaba el 13,6 % de las relaciones sin atestación pese a estar
  citadas. Las fuentes de tipo papiro (18) se omiten: `relacion_fuente` no tiene columna.
- **`pasaje` tiene dos claves UNIQUE** (`manto_id` y `(obra_id, cita)`) y MANTO trae varios
  Passage con la misma cita en la misma obra: un solo `ON CONFLICT` no cubre las dos, hay que
  buscar por ambas.
- **Nodegoat exporta las referencias de dos formas y hay que leer las dos.** Además de la
  directa (`'{Campo} - Object ID'` con el id), **105 campos usan referencia por camino**: esa
  columna trae un id intermedio inservible y el objetivo real va incrustado en la etiqueta,
  `start-path [object=6580_11297468]👤 Osiris`. Lo usan `identified_with`, `kills`,
  `mother_of`, `dies_at`, `ruler_of`… Leer solo la forma directa resolvía 461 de 2.800 filas de
  `identified_with` y dejaba `entidad_equivalencia` casi vacía. `_refs_etiquetadas()` maneja
  ambas; usa siempre ese helper para un campo nuevo.
- **Los nombres de lugar llevan cualificador regional** (`Thebes (Boiotia)`, `Knossos (Crete)`,
  `Ithaca (island)`). Al mapear un evento a su lugar hay que dar el nombre completo: existen
  `Troy (Egypt)` y `Thebes (Egypt)`, que no son los del mito.
- **Género, generación y tipo fino de entidad NO están en el export público.** MANTO publica
  los vocabularios (`gender_7880.json`, `generation_11335.json`, `type_of_entity_6937.json`)
  pero **ninguna entidad los referencia**: cero ocurrencias de `[object=7880_…]`,
  `[object=11335_…]` y `[object=6937_…]` en `entity_6580.json`. Por eso `entidad.genero`,
  `es_mortal` y `generacion` quedan a NULL, y el tipo se deduce del emoji. No es un loader
  que falte: el dato no viene. Para tenerlo hay que ir a la API de Nodegoat o pedirlo a MANTO.

- **Digital Marmor Parium**: `chronology.html` (§2.4) **no contiene ninguna tabla** — solo
  incrusta timelines de Knightlab alimentadas por una Google Sheet que devuelve 401 al
  exportar. La fuente machine-readable es la edición EpiDoc:
  `github.com/OpenGreekAndLatin/DigitalMarmorParium/EpiDoc_versions/dmp_ig_12_5_444.xml`,
  con 93 entradas fechadas en `<date from= to= when-custom=>`. Y su licencia es
  **CC BY-SA 4.0**, no "proyecto académico abierto": el ShareAlike es vírico y el texto griego
  se guarda en `evento.descripcion`.
- **Fecha del Diluvio de Deucalión**: el XML da `from="-1528" to="-1527"`; `fuentes.md` §2.4
  dice 1529/28. La base sigue al XML.
- **`pelagios.ttl` de ToposText**: 404 comprobado (2026-07-29) aunque sigue enlazado en
  TT-downloads. Traía las equivalencias Pleiades↔DARE; mientras siga caído se obtienen de
  Wikidata (P1584). `fetch` lo marca opcional y continúa.
- **Cabeceras reales de Pleiades**: `places.csv` no trae `year_after_which`/`year_before_which`
  (están en `names.csv`/`location_points.csv`), `places_accuracy.csv` se indexa por `place_id`,
  `places_place_types.csv` ya trae la clave textual, y `location_points.csv` no tiene columnas
  lat/lon: hay que parsear `geometry_wkt` (`POINT (lon lat)`, en ese orden).
- **Claves del geojson de ToposText**: van en CamelCase (`Pleiades`, `ToposText`, `Wikidata`,
  `Greek`), no en minúsculas, y `confidence` (High/Medium/Low) mapea a `geo_tipo` —
  `Low` es exactamente el caso "identificación tradicional, no hecho".

## Licencias — comprobar antes de ingestar

Ingesta masiva OK: Pleiades (CC-BY 3.0), Wikidata (CC0), ChronOntology, ToposText (datos,
atribuyendo), Digital LIMC, DARE, y dominio público (Smith escaneado, Roscher, Higino/Grant,
Apolodoro/Frazer, Attalus).

**Restricciones que ya están dentro de la base:**

| Fuente | Licencia real | Consecuencia |
|---|---|---|
| MANTO | **CC BY-NC 4.0** | Sin uso comercial. Afecta a `entidad`, `relacion`, `predicado`, `pasaje`, `artefacto` — es decir, a casi todo |
| Digital Marmor Parium | **CC BY-SA 4.0** | ShareAlike vírico sobre el texto griego de `evento.descripcion` |

**Prohibido ingestar:** Theoi, Greek Mythology Link (Maicar), Smith & Trzaskoma (Hackett) —
sin licencia abierta, solo consulta humana. Perseus/Smith-XML es **CC BY-SA**: ShareAlike
vírico, tratar como texto de consulta, no almacenar.

**CC BY-SA ya presente en la base:** el texto griego del Marmor Parium (`evento.descripcion`
de los eventos con `fuente_dataset.clave = 'dmp'`). Si redistribuyes, o mantienes CC BY-SA o
vacías esa columna para esas filas.

`README.md` debe llevar la cadena de atribución de `fuentes.md` §9.

## Gotchas técnicos

- **Los ZIP no se descomprimen.** MANTO y Pleiades se leen como miembros del ZIP
  (`archivo.Zip`). MANTO descomprimido son 5,4 GB y el loader usa 56 MB:
  `related_entities` (3,1 GB) y `mentioned_in_text` (830 MB) no se leen. Un loader nuevo
  sobre un ZIP usa `Zip.primero()`/`Zip.filas()`, nunca `extractall`.
- CSV de Pleiades: **BOM UTF-8** → `encoding='utf-8-sig'`. Campos WKT llevan comas dentro de
  comillas: usa el módulo `csv`, no `split(',')`.
- URLs de descarga de ToposText en su HTML usan `\` → cambiar por `/`.
- `PRAGMA foreign_keys = ON` en **cada** conexión (SQLite no lo persiste). `journal_mode = WAL`.
- Años a.C. como **enteros negativos** (`-1184` = 1184 a.C.). Sin año 0.
- MANTO no tiene entidad `Evento`: los eventos se derivan (§5.2). La semilla manual de
  ~120-200 eventos mayores da mejor calidad que cualquier heurística.
- CTS URN es el identificador de pasaje canónico (`urn:cts:greekLit:tlg0012.tlg001`). Las
  URLs de GitHub de Perseus **no** son estables.
- Fechas derivadas por generaciones: `sistema = 'generacional'`, `fecha_confianza = 'baja'`.
  Cosmogonía y teomaquias: `fecha_ac = NULL`, `fecha_metodo = 'sin_fecha'`.
- Fuzzy join es cuadrático si lo haces ingenuo: con solo Pleiades cargado (42.257 entidades)
  la primera versión puntuaba 7,1M pares en 295 s. Dos podas, ambas en el código:
  bloqueo por `tipo_entidad` + **prefijo de 3 de la forma normalizada**
  (`normalize.PREFIJO_BLOQUE`), y descarte sin puntuar de los pares que comparten namespace de
  veto. Resultado: 2,6 s. El coste conocido del prefijo-3 es que no compara pares que difieren
  en los 3 primeros caracteres (`achileus` vs `aquiles`); esos se reconcilian por QID.
- `db.upsert` usa `RETURNING`, no `cursor.lastrowid`: tras un `ON CONFLICT DO UPDATE`,
  `lastrowid` arrastra el rowid de un INSERT anterior de la misma conexión y devuelve un id
  ajeno a la fila. Para tablas sin columna `id` (p. ej. `lugar_detalle`) pasa `columna_id`.
- `entidad` no tiene clave UNIQUE natural: un loader que haga `upsert` ciego duplica todo en
  cada recarga. Localiza la entidad por `entidad_identificador` y solo inserta si no existe.
- Pleiades codifica "desconocido" como `-1` en los campos de accuracy: conviértelo a NULL, no
  lo guardes como distancia.
- `uv run` en Windows resuelve bien las rutas del proyecto; no mezcles con un `.venv`
  activado a mano — deja que uv gestione el entorno.

## Definición de "hecho"

Tras cada carga, `uv run greek qa` y comprobar contra las métricas de §6:
entidades con ID externo >95 %, relaciones con pasaje >90 %, lugares reales con coordenadas
>90 %, eventos databales con datación 100 %, contradicciones registradas >200, tasa de fusión
`fuzzy_fusion / entidad` < 8 %.
**Si `contradiccion` sale a 0, el modelo está aplanado — es un fallo, no un éxito.**

Dos trampas al escribir checks, ya corregidas y que conviene no reintroducir:

- Los años a.C. son **enteros negativos**, así que "más antiguo" es "menor". El check de
  causalidad comparaba al revés y daba por invertida toda la cadena troyana, que era correcta.
- Los denominadores deben excluir `fecha_metodo = 'sin_fecha'`: exigir "100 % de eventos con
  datación" obliga a inventar una fecha para la cosmogonía, que es justo lo que el diseño
  prohíbe.
- El check de duplicados debe excluir los pares que comparten namespace de ID externo con
  valores distintos: si no, marca como "fuzzy join no convergido" miles de homónimos legítimos
  (las cinco Pylos de Pleiades).
- El rango geográfico griego (Iberia→India) solo aplica a lugares que participan del mito.
  Pleiades cubre todo el mundo antiguo y más allá; Great Zimbabwe fuera de rango no es un
  error de carga.

Estado real medido tras `load-all` completo (2026-08-03, 12,6 s sobre dumps ya descargados):

| | |
|---|---|
| entidades | 51.562 (100 % con ≥1 ID externo) |
| relaciones citadas | 31.199 · 99,9 % con fuente, 92,1 % con pasaje textual |
| roles de relación | 38.057 (`en`, `usando`, `contra`, `para_vengar`…) |
| pasajes / obras / autores | 7.037 / 533 / 269 |
| artefactos / representaciones | 1.602 / 5.426 · 33 inscripciones · 16 periodos |
| equivalencias de identidad | 658 (`identificado_con`, `a_veces_confundido`…) |
| contradicciones | 13.371 — ubicación 6.314, genealogía 5.998, autoría de muerte 1.059 |
| eventos / dataciones | 132 / 126 · 208 participantes · 14 bandos · 117 fuentes |
| lugares con coordenadas | 83,3 % — el resto son `unlocated` de Pleiades |
| fusiones fuzzy | 24, todas duplicados reales; 195 pares a revisión humana |
| pares vetados sin puntuar | 9,0 M |
| checks de `qa.sql` | 8/8 en verde · **ninguna tabla vacía** |

Columnas que siguen a NULL, y por qué (no son loaders pendientes salvo donde se indica):

| Columna | Con dato | Motivo |
|---|---|---|
| `entidad.genero`, `es_mortal`, `generacion` | 0 | **No vienen en el export de MANTO** (ver arriba) |
| `entidad.nombre_es` | 1.087 | Solo las entidades con QID compartido con Wikidata |
| `obra.cts_urn` | 66 de 106 posibles | 40 obras comparten URN de obra (ediciones del mismo texto) y `UNIQUE(cts_urn)` las rechaza |
| `evento.lugar_id` | 16 de 132 | Los 94 eventos del Marmor Parium dan el lugar en griego (`Ἀθήνησιν`); enlazarlo exigiría transliterar y arriesgar homónimos |
| `relacion.evento_id` | 232 | Solo las que citan uno de los 13 Mythic Event de MANTO; el resto necesita la derivación de eventos de §5.2 |

Dos métricas de §6 siguen por debajo del objetivo, ambas por motivos de la fuente, no del
pipeline:

- **lugares con coordenadas 83,3 %** (objetivo 90 %): los 7.366 restantes son lugares
  `unlocated` de Pleiades, que no tiene coordenada para ellos. Subirlo exige Wikidata P625 o
  DARE, no un cambio de código.
- **eventos con ≥2 dataciones 0,9 %** (objetivo 40 %): solo la Guerra de Troya tiene la tabla
  comparada de §2.6. Cada entrada del Marmor Parium trae una sola fecha; la segunda autoridad
  para esos 94 eventos tiene que venir de Eusebio/Attalus (loader pendiente).

`greek load wikidata` falla de forma intermitente: WDQS está limitando a 1 req/min y devuelve
JSON truncado por una incidencia suya. Está tratado como aviso, no como error — Wikidata solo
enriquece.

## Primer entregable

Pleiades + MANTO `Entity` + MANTO `Tie` con el esquema completo pero sin eventos: ~9.000
entidades, ~32.000 relaciones citadas, miles de lugares geolocalizados. Eventos y cronología
son la segunda iteración.
