-- =====================================================================
-- greek — esquema SQLite. Implementa .claude/fuentes.md §4.
-- Orden de CREATE reordenado respecto al documento para que toda FK
-- apunte a una tabla ya existente.
-- =====================================================================

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- =====================================================================
-- BLOQUE 0: PROCEDENCIA
-- =====================================================================

CREATE TABLE IF NOT EXISTS fuente_dataset (
    id                INTEGER PRIMARY KEY,
    clave             TEXT NOT NULL UNIQUE,   -- 'manto','pleiades','topostext','wikidata','dmp'
    nombre            TEXT NOT NULL,
    version           TEXT,                   -- release o fecha del dump
    url               TEXT,
    licencia          TEXT NOT NULL,
    doi               TEXT,
    fecha_descarga    TEXT NOT NULL,          -- ISO-8601
    atribucion_texto  TEXT NOT NULL,          -- cadena exacta a citar
    notas             TEXT
);

CREATE TABLE IF NOT EXISTS autor_antiguo (
    id              INTEGER PRIMARY KEY,
    nombre          TEXT NOT NULL,
    nombre_es       TEXT,
    manto_id        TEXT UNIQUE,
    wikidata_qid    TEXT,
    floruit_min_ac  INTEGER,                  -- negativo = a.C.
    floruit_max_ac  INTEGER,
    notas           TEXT
);

CREATE TABLE IF NOT EXISTS obra (
    id                  INTEGER PRIMARY KEY,
    autor_id            INTEGER REFERENCES autor_antiguo(id),
    titulo              TEXT NOT NULL,
    titulo_es           TEXT,
    lengua              TEXT CHECK (lengua IN ('grc','lat','otro')),
    genero              TEXT,                 -- epica, tragedia, mitografia, periegesis, cronica
    cts_urn             TEXT UNIQUE,          -- urn:cts:greekLit:tlg0012.tlg001
    fecha_comp_min_ac   INTEGER,
    fecha_comp_max_ac   INTEGER,
    manto_id            TEXT UNIQUE,
    wikidata_qid        TEXT,
    fuente_dataset_id   INTEGER NOT NULL REFERENCES fuente_dataset(id)
);

CREATE TABLE IF NOT EXISTS pasaje (
    id                  INTEGER PRIMARY KEY,
    obra_id             INTEGER NOT NULL REFERENCES obra(id),
    cita                TEXT NOT NULL,        -- '2.5.10', 'Il. 1.1-7'
    cts_urn             TEXT,
    scaife_url          TEXT,
    topostext_url       TEXT,
    manto_id            TEXT UNIQUE,
    -- fecha de evento tal como la asigna ToposText a nivel de parrafo
    tt_fecha_evento_ac  INTEGER,
    tt_fecha_precision  TEXT CHECK (tt_fecha_precision IN
                          ('anio','decada','medio_siglo','siglo','mitico_indef','historico_indef')),
    fuente_dataset_id   INTEGER NOT NULL REFERENCES fuente_dataset(id),
    UNIQUE (obra_id, cita)
);
CREATE INDEX IF NOT EXISTS ix_pasaje_obra ON pasaje(obra_id);

-- =====================================================================
-- BLOQUE 1: ENTIDADES
-- Modelo unificado (como MANTO): en mito griego un rio ES un dios y una
-- ciudad ES un eponimo. Separar "persona" de "lugar" en la raiz lo rompe.
-- =====================================================================

CREATE TABLE IF NOT EXISTS tipo_entidad (
    id        INTEGER PRIMARY KEY,
    clave     TEXT NOT NULL UNIQUE,
    nombre_es TEXT NOT NULL,
    es_lugar  INTEGER NOT NULL DEFAULT 0,
    es_divino INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS entidad (
    id                  INTEGER PRIMARY KEY,
    nombre              TEXT NOT NULL,        -- canonico, forma latina/castellana
    nombre_norm         TEXT,                 -- clave de fuzzy join (normalize.py)
    nombre_grc          TEXT,                 -- griego Unicode politonico
    nombre_translit     TEXT,                 -- Kirke, Ouranos
    nombre_latino       TEXT,                 -- Circe, Uranus
    nombre_es           TEXT,                 -- Circe, Urano  <- de Wikidata
    tipo_entidad_id     INTEGER REFERENCES tipo_entidad(id),
    genero              TEXT CHECK (genero IN ('m','f','otro','desconocido')),
    es_mortal           INTEGER,              -- NULL = indeterminado
    generacion          INTEGER,              -- generacion mitica relativa (fuentes.md §5.3)
    descripcion         TEXT,
    desambiguador       TEXT,                 -- 'hijo de Egipto', 'rey de Argos'
    homonimo_grupo      TEXT,                 -- agrupa entidades que comparten nombre
    fuente_dataset_id   INTEGER NOT NULL REFERENCES fuente_dataset(id),
    confianza           REAL DEFAULT 1.0,
    revisado_manual     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_entidad_nombre ON entidad(nombre);
CREATE INDEX IF NOT EXISTS ix_entidad_norm   ON entidad(nombre_norm);
CREATE INDEX IF NOT EXISTS ix_entidad_tipo   ON entidad(tipo_entidad_id);
CREATE INDEX IF NOT EXISTS ix_entidad_homon  ON entidad(homonimo_grupo);

CREATE TABLE IF NOT EXISTS entidad_nombre (
    id           INTEGER PRIMARY KEY,
    entidad_id   INTEGER NOT NULL REFERENCES entidad(id) ON DELETE CASCADE,
    nombre       TEXT NOT NULL,
    tipo         TEXT CHECK (tipo IN ('alternativo','epiteto','translit','latino','etrusco',
                                      'moderno','local','patronimico','es','absorbido')),
    lengua_tag   TEXT,                        -- BCP-47: grc, la, es, etr
    pasaje_id    INTEGER REFERENCES pasaje(id),
    UNIQUE (entidad_id, nombre, tipo)
);
CREATE INDEX IF NOT EXISTS ix_ent_nombre ON entidad_nombre(nombre);

-- Reconciliacion entre fuentes: prioridad maxima, por encima del fuzzy join
CREATE TABLE IF NOT EXISTS entidad_identificador (
    id           INTEGER PRIMARY KEY,
    entidad_id   INTEGER NOT NULL REFERENCES entidad(id) ON DELETE CASCADE,
    namespace    TEXT NOT NULL CHECK (namespace IN
                   ('manto','wikidata','pleiades','topostext','trismegistos',
                    'limc','digital_limc','perseus_smith','dbpedia','geonames','dare')),
    valor        TEXT NOT NULL,
    uri          TEXT,
    confianza    REAL DEFAULT 1.0,            -- <1.0 para alineaciones automaticas (Pleiades+)
    UNIQUE (namespace, valor)
);
CREATE INDEX IF NOT EXISTS ix_entid_ent ON entidad_identificador(entidad_id);

CREATE TABLE IF NOT EXISTS entidad_equivalencia (
    id           INTEGER PRIMARY KEY,
    entidad_a_id INTEGER NOT NULL REFERENCES entidad(id),
    entidad_b_id INTEGER NOT NULL REFERENCES entidad(id),
    tipo         TEXT NOT NULL CHECK (tipo IN
                   ('es_el_mismo','posiblemente_el_mismo','a_veces_confundido',
                    'forma_racionalizada','personificacion_de','identificado_con')),
    pasaje_id    INTEGER REFERENCES pasaje(id),
    nota         TEXT,
    CHECK (entidad_a_id <> entidad_b_id),
    UNIQUE (entidad_a_id, entidad_b_id, tipo)
);

-- =====================================================================
-- BLOQUE 3a: CRONOLOGIA Y CICLOS (antes de evento/relacion, que los referencian)
-- =====================================================================

CREATE TABLE IF NOT EXISTS ciclo_mitico (
    id          INTEGER PRIMARY KEY,
    clave       TEXT NOT NULL UNIQUE,
    nombre_es   TEXT NOT NULL,
    orden       INTEGER,        -- secuencia canonica aproximada
    descripcion TEXT
);

CREATE TABLE IF NOT EXISTS periodo (
    id                INTEGER PRIMARY KEY,
    clave             TEXT NOT NULL UNIQUE,   -- 'LH_IIIB', 'LH_IIIC_early'
    nombre            TEXT NOT NULL,
    anio_inicio_ac    INTEGER,
    anio_fin_ac       INTEGER,
    chronontology_uri TEXT,
    manto_id          TEXT
);

CREATE TABLE IF NOT EXISTS evento (
    id                INTEGER PRIMARY KEY,
    nombre            TEXT NOT NULL,
    nombre_es         TEXT,
    tipo              TEXT NOT NULL CHECK (tipo IN
                        ('guerra','batalla','duelo','asedio','expedicion','viaje','trabajo',
                         'caceria','certamen','juegos','fundacion','nacimiento','muerte',
                         'boda','rapto','metamorfosis','juicio','profecia','sacrificio',
                         'cataclismo','castigo','apoteosis','descenso_hades','otro')),
    ciclo_id          INTEGER REFERENCES ciclo_mitico(id),
    lugar_id          INTEGER REFERENCES entidad(id),   -- entidad de tipo lugar
    padre_evento_id   INTEGER REFERENCES evento(id),    -- batalla dentro de guerra
    descripcion       TEXT,
    resultado         TEXT,
    -- fecha "preferida" DESNORMALIZADA: derivado de evento_datacion, nunca el dato primario
    fecha_ac          INTEGER,
    fecha_min_ac      INTEGER,
    fecha_max_ac      INTEGER,
    fecha_metodo      TEXT CHECK (fecha_metodo IN
                        ('cronografo_antiguo','generacional','arqueologico','moderno','sin_fecha')),
    fecha_confianza   TEXT CHECK (fecha_confianza IN ('alta','media','baja','nula')),
    generacion        INTEGER,
    periodo_id        INTEGER REFERENCES periodo(id),
    fuente_dataset_id INTEGER NOT NULL REFERENCES fuente_dataset(id),
    UNIQUE (nombre, tipo)
);
CREATE INDEX IF NOT EXISTS ix_evento_ciclo ON evento(ciclo_id);
CREATE INDEX IF NOT EXISTS ix_evento_lugar ON evento(lugar_id);
CREATE INDEX IF NOT EXISTS ix_evento_fecha ON evento(fecha_ac);

-- =====================================================================
-- BLOQUE 2: RELACIONES (el corazon del modelo, ex MANTO `Tie`)
-- =====================================================================

CREATE TABLE IF NOT EXISTS predicado (
    id           INTEGER PRIMARY KEY,
    clave        TEXT NOT NULL UNIQUE,   -- 'kills','father_of','born_at','founder_of'
    nombre_es    TEXT NOT NULL,
    categoria    TEXT NOT NULL CHECK (categoria IN
                   ('genealogica','conyugal','belica','muerte','nacimiento','geografica',
                    'cultual','politica','transformacion','creacion','fundacion',
                    'profecia','oficio','competicion','objeto','otra')),
    inverso_id   INTEGER REFERENCES predicado(id),   -- father_of <-> child_of
    simetrico    INTEGER NOT NULL DEFAULT 0,         -- twin_of, has_children_with
    manto_id     TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS relacion (
    id                  INTEGER PRIMARY KEY,
    sujeto_id           INTEGER NOT NULL REFERENCES entidad(id),
    predicado_id        INTEGER NOT NULL REFERENCES predicado(id),
    objeto_id           INTEGER REFERENCES entidad(id),
    evento_id           INTEGER REFERENCES evento(id),
    timemark_when       TEXT,
    periodo_id          INTEGER REFERENCES periodo(id),
    -- flags de fiabilidad (ex MANTO). NO los aplanes: distinguen
    -- "Homero dice X" de "quiza se insinua X".
    dato_incierto       INTEGER NOT NULL DEFAULT 0,
    duda_expresada      INTEGER NOT NULL DEFAULT 0,
    alternativas_dadas  INTEGER NOT NULL DEFAULT 0,
    dato_implicito      INTEGER NOT NULL DEFAULT 0,
    comentario          TEXT,
    manto_id            TEXT UNIQUE,
    fuente_dataset_id   INTEGER NOT NULL REFERENCES fuente_dataset(id)
);
CREATE INDEX IF NOT EXISTS ix_rel_sujeto ON relacion(sujeto_id);
CREATE INDEX IF NOT EXISTS ix_rel_objeto ON relacion(objeto_id);
CREATE INDEX IF NOT EXISTS ix_rel_pred   ON relacion(predicado_id);
CREATE INDEX IF NOT EXISTS ix_rel_evento ON relacion(evento_id);

-- Los ~25 slots opcionales de MANTO, normalizados en vez de 25 columnas NULL
CREATE TABLE IF NOT EXISTS relacion_rol (
    id           INTEGER PRIMARY KEY,
    relacion_id  INTEGER NOT NULL REFERENCES relacion(id) ON DELETE CASCADE,
    rol          TEXT NOT NULL CHECK (rol IN
                   ('en','cerca_de','desde','hacia','via','con_intencion_de_ir_a','usando',
                    'de','para','en_direccion_a','contra','acerca_de','con_ayuda_de',
                    'por_orden_de','a_instigacion_de','con_participacion_de',
                    'segun_profecia_de','segun_profecia_sobre','para_vengar','para_ayudar',
                    'para_obtener','para_proteger','para_honrar','para_frustrar',
                    'para_castigar','y_conciben','objeto_indirecto')),
    entidad_id   INTEGER NOT NULL REFERENCES entidad(id),
    UNIQUE (relacion_id, rol, entidad_id)
);
CREATE INDEX IF NOT EXISTS ix_relrol_rel ON relacion_rol(relacion_id);
CREATE INDEX IF NOT EXISTS ix_relrol_ent ON relacion_rol(entidad_id);

-- =====================================================================
-- BLOQUE 5: MATERIAL COMPLEMENTARIO (antes de relacion_fuente, que lo referencia)
-- =====================================================================

CREATE TABLE IF NOT EXISTS artefacto (
    id                INTEGER PRIMARY KEY,
    nombre            TEXT,
    tipo              TEXT,          -- vaso, escultura, moneda, sarcofago, mosaico
    lugar_creacion_id INTEGER REFERENCES entidad(id),
    lugar_hallazgo_id INTEGER REFERENCES entidad(id),
    periodo_id        INTEGER REFERENCES periodo(id),
    coleccion         TEXT,
    limc_ref          TEXT,
    digital_limc_url  TEXT,
    bapd_url          TEXT,
    manto_id          TEXT UNIQUE,
    fuente_dataset_id INTEGER NOT NULL REFERENCES fuente_dataset(id)
);

CREATE TABLE IF NOT EXISTS inscripcion (
    id                INTEGER PRIMARY KEY,
    nombre            TEXT,
    ig_ref            TEXT,
    seg_ref           TEXT,
    lugar_hallazgo_id INTEGER REFERENCES entidad(id),
    periodo_id        INTEGER REFERENCES periodo(id),
    trismegistos_url  TEXT,
    manto_id          TEXT UNIQUE,
    fuente_dataset_id INTEGER NOT NULL REFERENCES fuente_dataset(id)
);

CREATE TABLE IF NOT EXISTS artefacto_representa (
    id           INTEGER PRIMARY KEY,
    artefacto_id INTEGER NOT NULL REFERENCES artefacto(id) ON DELETE CASCADE,
    entidad_id   INTEGER NOT NULL REFERENCES entidad(id),
    es_reportada INTEGER NOT NULL DEFAULT 0,   -- "se dice que representa"
    UNIQUE (artefacto_id, entidad_id)
);

CREATE TABLE IF NOT EXISTS relacion_fuente (
    id             INTEGER PRIMARY KEY,
    relacion_id    INTEGER NOT NULL REFERENCES relacion(id) ON DELETE CASCADE,
    pasaje_id      INTEGER REFERENCES pasaje(id),
    artefacto_id   INTEGER REFERENCES artefacto(id),
    inscripcion_id INTEGER REFERENCES inscripcion(id),
    es_indirecta   INTEGER NOT NULL DEFAULT 0,
    CHECK (pasaje_id IS NOT NULL OR artefacto_id IS NOT NULL OR inscripcion_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS ix_relfte_rel ON relacion_fuente(relacion_id);
-- Sin esta clave el INSERT OR IGNORE del loader no ignora nada y cada recarga de MANTO
-- duplicaba las 31.201 atestaciones. COALESCE porque en SQLite dos NULL no colisionan.
CREATE UNIQUE INDEX IF NOT EXISTS ux_relfte ON relacion_fuente(
    relacion_id, COALESCE(pasaje_id, 0), COALESCE(artefacto_id, 0), COALESCE(inscripcion_id, 0)
);

-- Contradicciones explicitas entre versiones del mito.
-- Si esta tabla sale vacia, el modelo esta aplanado: es un fallo.
CREATE TABLE IF NOT EXISTS contradiccion (
    id                   INTEGER PRIMARY KEY,
    relacion_a_id        INTEGER NOT NULL REFERENCES relacion(id),
    relacion_b_id        INTEGER NOT NULL REFERENCES relacion(id),
    tipo                 TEXT CHECK (tipo IN
                           ('genealogia','autoria_muerte','ubicacion','fecha','otra')),
    descripcion          TEXT,
    resuelta             INTEGER NOT NULL DEFAULT 0,
    version_preferida_id INTEGER REFERENCES relacion(id),
    criterio             TEXT,   -- 'fuente mas antigua', 'consenso mayoritario', 'Hesiodo'
    UNIQUE (relacion_a_id, relacion_b_id)
);

-- =====================================================================
-- BLOQUE 3b: DATACION Y PARTICIPACION
-- =====================================================================

-- Un evento tiene N dataciones segun N autoridades. Ninguna es "la" fecha.
CREATE TABLE IF NOT EXISTS evento_datacion (
    id                INTEGER PRIMARY KEY,
    evento_id         INTEGER NOT NULL REFERENCES evento(id) ON DELETE CASCADE,
    autoridad         TEXT NOT NULL,   -- 'Eratostenes','Marmol de Paros','Herodoto','Eusebio'
    sistema           TEXT NOT NULL CHECK (sistema IN
                        ('cronografo_antiguo','generacional','arqueologico','moderno')),
    anio_ac           INTEGER,         -- negativo. -1184 = 1184 a.C.
    anio_min_ac       INTEGER,
    anio_max_ac       INTEGER,
    precision         TEXT CHECK (precision IN
                        ('anio','lustro','decada','medio_siglo','siglo','vago')),
    es_preferida      INTEGER NOT NULL DEFAULT 0,
    pasaje_id         INTEGER REFERENCES pasaje(id),
    fuente_dataset_id INTEGER NOT NULL REFERENCES fuente_dataset(id),
    nota              TEXT,
    UNIQUE (evento_id, autoridad)
);
CREATE INDEX IF NOT EXISTS ix_evdat_evento ON evento_datacion(evento_id);
-- una sola datacion preferida por evento
CREATE UNIQUE INDEX IF NOT EXISTS ux_evdat_pref
    ON evento_datacion(evento_id) WHERE es_preferida = 1;

CREATE TABLE IF NOT EXISTS bando (
    id        INTEGER PRIMARY KEY,
    evento_id INTEGER NOT NULL REFERENCES evento(id) ON DELETE CASCADE,
    nombre    TEXT NOT NULL,     -- 'aqueos','troyanos','olimpicos','titanes'
    resultado TEXT CHECK (resultado IN ('victoria','derrota','tablas','desconocido')),
    UNIQUE (evento_id, nombre)
);

CREATE TABLE IF NOT EXISTS evento_participante (
    id         INTEGER PRIMARY KEY,
    evento_id  INTEGER NOT NULL REFERENCES evento(id) ON DELETE CASCADE,
    entidad_id INTEGER NOT NULL REFERENCES entidad(id),
    bando_id   INTEGER REFERENCES bando(id),
    rol        TEXT CHECK (rol IN
                 ('comandante','combatiente','victima','matador','instigador',
                  'aliado_divino','oponente_divino','espectador','arbitro',
                  'raptado','rescatador','tripulante','cazador','vencedor','vencido',
                  -- 'participante' y 'competidor' salen de los eventos de MANTO
                  -- (bodas, juegos funebres): hay implicacion sin combate ni rol fino
                  'participante','competidor')),
    resultado  TEXT CHECK (resultado IN
                 ('sobrevive','muere','herido','capturado','desconocido')),
    pasaje_id  INTEGER REFERENCES pasaje(id),
    UNIQUE (evento_id, entidad_id, rol)
);
CREATE INDEX IF NOT EXISTS ix_evpart_ent ON evento_participante(entidad_id);
CREATE INDEX IF NOT EXISTS ix_evpart_ev  ON evento_participante(evento_id);

CREATE TABLE IF NOT EXISTS evento_relacion (
    id          INTEGER PRIMARY KEY,
    evento_a_id INTEGER NOT NULL REFERENCES evento(id),
    evento_b_id INTEGER NOT NULL REFERENCES evento(id),
    tipo        TEXT NOT NULL CHECK (tipo IN
                  ('causa_de','consecuencia_de','anterior_a','simultaneo_a',
                   'parte_de','venganza_de')),
    CHECK (evento_a_id <> evento_b_id),
    UNIQUE (evento_a_id, evento_b_id, tipo)
);

CREATE TABLE IF NOT EXISTS evento_fuente (
    id           INTEGER PRIMARY KEY,
    evento_id    INTEGER NOT NULL REFERENCES evento(id) ON DELETE CASCADE,
    pasaje_id    INTEGER NOT NULL REFERENCES pasaje(id),
    es_principal INTEGER NOT NULL DEFAULT 0,
    UNIQUE (evento_id, pasaje_id)
);

-- =====================================================================
-- BLOQUE 4: GEOGRAFIA
-- =====================================================================

CREATE TABLE IF NOT EXISTS lugar_detalle (
    entidad_id         INTEGER PRIMARY KEY REFERENCES entidad(id) ON DELETE CASCADE,
    tipo_lugar         TEXT,          -- settlement, sanctuary, mountain, river, island,
                                      -- spring, tomb, cave, region, oracle, underworld
    latitud            REAL,          -- WGS-84 grados decimales con signo
    longitud           REAL,
    precision_metros   INTEGER,       -- Pleiades accuracy_radius / max_accuracy_meters
    location_precision TEXT CHECK (location_precision IN ('precise','rough')),
    bbox_wkt           TEXT,
    geo_tipo           TEXT NOT NULL CHECK (geo_tipo IN
                         ('real_preciso',                -- Micenas, Delfos
                          'real_aproximado',             -- Aulide, Colcos
                          'identificacion_tradicional',  -- Escila = estrecho de Mesina
                          'legendario_sin_ubicacion',    -- Hades, Tartaro, Eliseo
                          'sin_datos')),
    es_ficticio        INTEGER NOT NULL DEFAULT 0,
    geo_fuente         TEXT CHECK (geo_fuente IN
                         ('pleiades','topostext','wikidata','geonames','dare','manual')),
    nombre_moderno     TEXT,
    pais_iso2          TEXT,
    geonames_id        TEXT,
    anio_desde_ac      INTEGER,       -- Pleiades year_after_which
    anio_hasta_ac      INTEGER,       -- Pleiades year_before_which
    altitud_m          INTEGER,
    fuente_dataset_id  INTEGER NOT NULL REFERENCES fuente_dataset(id),
    CHECK ( (latitud IS NULL AND longitud IS NULL)
         OR (latitud BETWEEN -90 AND 90 AND longitud BETWEEN -180 AND 180) ),
    -- prohibe inventar coordenadas para el Tartaro. NO quitar este CHECK.
    CHECK ( geo_tipo <> 'legendario_sin_ubicacion' OR latitud IS NULL )
);
CREATE INDEX IF NOT EXISTS ix_lugar_coord ON lugar_detalle(latitud, longitud);
CREATE INDEX IF NOT EXISTS ix_lugar_tipo  ON lugar_detalle(tipo_lugar);

CREATE TABLE IF NOT EXISTS lugar_jerarquia (
    id       INTEGER PRIMARY KEY,
    hijo_id  INTEGER NOT NULL REFERENCES entidad(id),
    padre_id INTEGER NOT NULL REFERENCES entidad(id),
    tipo     TEXT CHECK (tipo IN ('parte_de','cerca_de','en','dentro_de')),
    certeza  TEXT CHECK (certeza IN ('certain','less-certain','uncertain')),
    CHECK (hijo_id <> padre_id),
    UNIQUE (hijo_id, padre_id, tipo)
);

CREATE TABLE IF NOT EXISTS lugar_localizacion (
    id                INTEGER PRIMARY KEY,
    entidad_id        INTEGER NOT NULL REFERENCES entidad(id) ON DELETE CASCADE,
    titulo            TEXT,
    geometria_wkt     TEXT,
    latitud           REAL,
    longitud          REAL,
    tipo_localizacion TEXT,     -- representative, associated modern, relocated modern
    precision         TEXT,
    accuracy_radius_m INTEGER,
    pleiades_uri      TEXT,
    es_representativa INTEGER NOT NULL DEFAULT 0,
    UNIQUE (entidad_id, pleiades_uri, titulo)
);
CREATE INDEX IF NOT EXISTS ix_lugarloc_ent ON lugar_localizacion(entidad_id);

-- =====================================================================
-- BLOQUE 6: FUZZY JOIN — auditoria y reversibilidad
-- Extension al esquema de fuentes.md §4. Sin `absorbida_json` la fusion
-- seria destructiva: es lo que hace posible `greek fuzzy --undo`.
-- =====================================================================

CREATE TABLE IF NOT EXISTS fuzzy_fusion (
    id               INTEGER PRIMARY KEY,
    superviviente_id INTEGER NOT NULL REFERENCES entidad(id),
    absorbida_id     INTEGER NOT NULL,      -- id ya inexistente en entidad
    absorbida_nombre TEXT NOT NULL,
    absorbida_json   TEXT NOT NULL,         -- fila completa + ids + nombres + relaciones
    score            REAL NOT NULL,
    algoritmo        TEXT NOT NULL,         -- 'rapidfuzz.WRatio'
    umbral           REAL NOT NULL,
    banda            TEXT NOT NULL CHECK (banda IN ('auto','corroborada','manual')),
    evidencia        TEXT,                  -- que la corroboro en la banda 88-94
    fecha            TEXT NOT NULL,
    revertida        INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_fusion_superv ON fuzzy_fusion(superviviente_id);

CREATE TABLE IF NOT EXISTS entidad_revision (
    id           INTEGER PRIMARY KEY,
    entidad_a_id INTEGER NOT NULL REFERENCES entidad(id),
    entidad_b_id INTEGER NOT NULL REFERENCES entidad(id),
    score        REAL NOT NULL,
    motivo       TEXT,          -- 'banda 80-87', 'ids externos discrepantes'
    decision     TEXT CHECK (decision IN ('pendiente','fusionar','separadas'))
                 DEFAULT 'pendiente',
    UNIQUE (entidad_a_id, entidad_b_id)
);
