-- Generacion mitica por entidad, y anclaje de generacion a anio segun autoridad antigua.
--
-- Mismo patron que evento_datacion / evento.fecha_ac: el dato con su procedencia vive
-- en la tabla, y entidad.generacion es la copia derivada de conveniencia.
--
-- Por que hace falta: MANTO publica el vocabulario `generation_11335.json` pero NINGUNA
-- entidad lo referencia (cero ocurrencias de [object=11335_...] en entity_6580.json), asi
-- que la generacion no viene en el dump y hay que derivarla.

CREATE TABLE IF NOT EXISTS entidad_generacion (
    entidad_id      INTEGER PRIMARY KEY REFERENCES entidad(id) ON DELETE CASCADE,
    generacion      INTEGER NOT NULL,       -- escala del proyecto: Troya = 2, Heracles = 0
    generacion_min  INTEGER,                -- si las anclas mas cercanas discrepan
    generacion_max  INTEGER,
    distancia       INTEGER NOT NULL,       -- saltos genealogicos hasta el ancla; 0 = semilla
    metodo          TEXT NOT NULL
                    CHECK (metodo IN ('semilla','semilla_divina','evento','genealogica')),
    -- 0 = progenitor que NO transmite cronologia. La paternidad divina no fecha nada:
    -- Zeus engendra en gen -3 (Perseo), 0 (Heracles) y 2. Si transmitiera, el eje
    -- temporal se aplanaria entero.
    transmite       INTEGER NOT NULL DEFAULT 1 CHECK (transmite IN (0,1)),
    confianza       TEXT NOT NULL CHECK (confianza IN ('alta','media','baja')),
    nota            TEXT
);

CREATE INDEX IF NOT EXISTS ix_entgen_generacion ON entidad_generacion(generacion);
CREATE INDEX IF NOT EXISTS ix_entgen_metodo ON entidad_generacion(metodo);

-- Generacion -> anio a.C. segun cada autoridad antigua. Las 11 autoridades no discrepan
-- en el orden de los hechos, solo en donde cae el ancla: Duris pone Troya en -1334 y
-- Eforo en -1135, casi 200 anios de diferencia sobre la misma secuencia.
CREATE TABLE IF NOT EXISTS generacion_ancla (
    id                   INTEGER PRIMARY KEY,
    autoridad            TEXT NOT NULL,
    sistema              TEXT NOT NULL,
    generacion           INTEGER NOT NULL,
    anio_ac              INTEGER NOT NULL,
    anio_min_ac          INTEGER,
    anio_max_ac          INTEGER,
    anios_por_generacion INTEGER NOT NULL,
    ancla_troya_ac       INTEGER NOT NULL,   -- el anio que esa autoridad da a la guerra
    es_preferida         INTEGER NOT NULL DEFAULT 0 CHECK (es_preferida IN (0,1)),
    UNIQUE (autoridad, generacion)
);

CREATE INDEX IF NOT EXISTS ix_genancla_autoridad ON generacion_ancla(autoridad);

-- Entidades con generacion, su lugar y su banda de anios segun la autoridad preferida.
DROP VIEW IF EXISTS vw_generaciones;
CREATE VIEW vw_generaciones AS
SELECT e.id            AS entidad_id,
       e.nombre,
       COALESCE(e.nombre_es, e.nombre) AS etiqueta,
       te.clave        AS tipo,
       g.generacion,
       g.generacion_min,
       g.generacion_max,
       g.metodo,
       g.confianza,
       g.transmite,
       a.anio_ac,
       a.autoridad
  FROM entidad_generacion g
  JOIN entidad e       ON e.id = g.entidad_id
  LEFT JOIN tipo_entidad te ON te.id = e.tipo_entidad_id
  LEFT JOIN generacion_ancla a
         ON a.generacion = g.generacion AND a.es_preferida = 1;
