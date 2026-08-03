-- Papel de cada agente: dios, heroe, gobernante, monstruo... derivado, no dado.
--
-- MANTO NO distingue dios/heroe/mortal/monstruo: todo es `Agent` (de ahi el
-- tipo_entidad `agente`), y `entidad.genero`/`es_mortal` quedan a NULL porque el
-- export no los trae. Asi que el papel hay que derivarlo, y como es derivado se
-- guarda CON LA REGLA QUE LO DECIDIO: sin eso no hay forma de auditar por que
-- Heracles sale heroe y no dios.
--
-- Multi-etiqueta a proposito: Agamenon gobierna Micenas Y combate en Troya;
-- Heracles es heroe Y se vuelve inmortal. Obligar a un solo papel falsea el dato.

CREATE TABLE IF NOT EXISTS entidad_papel (
    entidad_id  INTEGER NOT NULL REFERENCES entidad(id) ON DELETE CASCADE,
    papel       TEXT NOT NULL CHECK (papel IN
                ('dios','heroe','gobernante','monstruo','deificado','profeta','artesano')),
    -- que lo decidio: 'descripcion:diosa', 'predicado:gives_prophecy',
    -- 'semilla_divina', 'culto_heroico'... La precedencia importa y queda escrita.
    regla       TEXT NOT NULL,
    confianza   TEXT NOT NULL CHECK (confianza IN ('alta','media','baja')),
    PRIMARY KEY (entidad_id, papel)
);

CREATE INDEX IF NOT EXISTS ix_entpapel_papel ON entidad_papel(papel);

DROP VIEW IF EXISTS vw_papeles;
CREATE VIEW vw_papeles AS
SELECT e.id                            AS entidad_id,
       COALESCE(e.nombre_es, e.nombre) AS etiqueta,
       e.nombre,
       g.generacion,
       GROUP_CONCAT(p.papel, ', ')     AS papeles,
       GROUP_CONCAT(p.regla, ' | ')    AS reglas
  FROM entidad e
  JOIN entidad_papel p ON p.entidad_id = e.id
  LEFT JOIN entidad_generacion g ON g.entidad_id = e.id
 GROUP BY e.id
 ORDER BY e.nombre;
