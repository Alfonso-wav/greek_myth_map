-- Vistas de conveniencia. fuentes.md §4 "Vistas".

-- OJO A LA DIRECCION: el predicado real de MANTO es 'is child of', donde el
-- SUJETO es el hijo y el OBJETO el progenitor. La primera version de esta vista
-- asumia 'father_of' (sujeto = progenitor) y devolvia toda la genealogia del
-- reves. Los predicados con la direccion contraria van en el segundo bloque.
DROP VIEW IF EXISTS vw_genealogia;
CREATE VIEW vw_genealogia AS
SELECT r.id                AS relacion_id,
       p.clave             AS predicado,
       hijo.id             AS hijo_id,        hijo.nombre AS hijo,
       prog.id             AS progenitor_id,  prog.nombre AS progenitor,
       r.dato_incierto, r.alternativas_dadas, r.duda_expresada,
       o.titulo || ' ' || pa.cita AS fuente
FROM relacion r
JOIN predicado p  ON p.id = r.predicado_id
                 AND p.categoria = 'genealogica'
                 AND (p.clave LIKE '%child_of%' OR p.clave LIKE '%descendant_of%')
JOIN entidad hijo ON hijo.id = r.sujeto_id
JOIN entidad prog ON prog.id = r.objeto_id
LEFT JOIN relacion_fuente rf ON rf.relacion_id = r.id
LEFT JOIN pasaje pa ON pa.id = rf.pasaje_id
LEFT JOIN obra o    ON o.id = pa.obra_id
UNION ALL
SELECT r.id, p.clave,
       hijo.id, hijo.nombre,
       prog.id, prog.nombre,
       r.dato_incierto, r.alternativas_dadas, r.duda_expresada,
       o.titulo || ' ' || pa.cita
FROM relacion r
JOIN predicado p  ON p.id = r.predicado_id
                 AND p.categoria = 'genealogica'
                 AND (p.clave LIKE '%mother%of' OR p.clave LIKE '%father%of'
                      OR p.clave LIKE '%parent%of')
JOIN entidad prog ON prog.id = r.sujeto_id
JOIN entidad hijo ON hijo.id = r.objeto_id
LEFT JOIN relacion_fuente rf ON rf.relacion_id = r.id
LEFT JOIN pasaje pa ON pa.id = rf.pasaje_id
LEFT JOIN obra o    ON o.id = pa.obra_id;

DROP VIEW IF EXISTS vw_muertes;
CREATE VIEW vw_muertes AS
SELECT r.id,
       matador.nombre AS matador,
       victima.nombre AS victima,
       lug.nombre     AS lugar,
       arma.nombre    AS arma,
       e.nombre       AS evento,
       e.fecha_ac
FROM relacion r
JOIN predicado p     ON p.id = r.predicado_id AND p.clave = 'kills'
JOIN entidad matador ON matador.id = r.sujeto_id
JOIN entidad victima ON victima.id = r.objeto_id
LEFT JOIN relacion_rol rr_l ON rr_l.relacion_id = r.id AND rr_l.rol = 'en'
LEFT JOIN entidad lug       ON lug.id = rr_l.entidad_id
LEFT JOIN relacion_rol rr_a ON rr_a.relacion_id = r.id AND rr_a.rol = 'usando'
LEFT JOIN entidad arma      ON arma.id = rr_a.entidad_id
LEFT JOIN evento e          ON e.id = r.evento_id;

DROP VIEW IF EXISTS vw_lugares_mapa;
CREATE VIEW vw_lugares_mapa AS
SELECT e.id, e.nombre, e.nombre_es, ld.tipo_lugar,
       ld.latitud, ld.longitud, ld.precision_metros, ld.geo_tipo, ld.geo_fuente
FROM entidad e
JOIN lugar_detalle ld ON ld.entidad_id = e.id
WHERE ld.latitud IS NOT NULL
  AND ld.geo_tipo IN ('real_preciso','real_aproximado','identificacion_tradicional');

-- Todas las dataciones de un evento, lado a lado. La preferida marcada.
DROP VIEW IF EXISTS vw_cronologia;
CREATE VIEW vw_cronologia AS
SELECT ev.id AS evento_id, ev.nombre AS evento, c.nombre_es AS ciclo,
       d.autoridad, d.sistema, d.anio_ac, d.anio_min_ac, d.anio_max_ac,
       d.precision, d.es_preferida, d.nota
FROM evento ev
LEFT JOIN ciclo_mitico c    ON c.id = ev.ciclo_id
LEFT JOIN evento_datacion d ON d.evento_id = ev.id
ORDER BY ev.id, d.es_preferida DESC, d.anio_ac DESC;

-- Rastro del fuzzy join: que se fusiono con que y por que
DROP VIEW IF EXISTS vw_fusiones;
CREATE VIEW vw_fusiones AS
SELECT f.id, s.nombre AS superviviente, f.absorbida_nombre AS absorbida,
       f.score, f.banda, f.evidencia, f.fecha, f.revertida
FROM fuzzy_fusion f
JOIN entidad s ON s.id = f.superviviente_id
ORDER BY f.score ASC;   -- las mas dudosas primero

DROP VIEW IF EXISTS vw_huecos;
CREATE VIEW vw_huecos AS
SELECT 'lugar_sin_coordenadas' AS hueco, COUNT(*) AS n
  FROM lugar_detalle WHERE latitud IS NULL AND geo_tipo <> 'legendario_sin_ubicacion'
-- 'sin_fecha' no es un hueco: es la respuesta correcta para la cosmogonia
UNION ALL SELECT 'evento_sin_fecha', COUNT(*) FROM evento
  WHERE fecha_ac IS NULL AND fecha_metodo IS NOT 'sin_fecha'
UNION ALL SELECT 'evento_sin_lugar', COUNT(*) FROM evento WHERE lugar_id IS NULL
UNION ALL SELECT 'evento_sin_datacion', COUNT(*) FROM evento ev
  WHERE fecha_metodo IS NOT 'sin_fecha'
    AND NOT EXISTS (SELECT 1 FROM evento_datacion d WHERE d.evento_id = ev.id)
UNION ALL SELECT 'entidad_sin_tipo', COUNT(*) FROM entidad WHERE tipo_entidad_id IS NULL
UNION ALL SELECT 'relacion_sin_fuente', COUNT(*) FROM relacion r
  WHERE NOT EXISTS (SELECT 1 FROM relacion_fuente rf WHERE rf.relacion_id = r.id)
UNION ALL SELECT 'entidad_sin_id_externo', COUNT(*) FROM entidad e
  WHERE NOT EXISTS (SELECT 1 FROM entidad_identificador i WHERE i.entidad_id = e.id)
UNION ALL SELECT 'homonimo_sin_desambiguador', COUNT(*) FROM entidad e
  WHERE e.homonimo_grupo IS NOT NULL AND e.desambiguador IS NULL
UNION ALL SELECT 'revision_fuzzy_pendiente', COUNT(*) FROM entidad_revision
  WHERE decision = 'pendiente';
