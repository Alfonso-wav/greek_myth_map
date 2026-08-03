-- Control de calidad. fuentes.md §6. Cada bloque devuelve 0 filas si todo va bien.
-- Lo ejecuta `greek qa`; los nombres en el comentario -- @check: son las etiquetas
-- que imprime el informe.

-- @check: ciclos_genealogicos  (nadie es su propio antepasado)
-- El predicado de MANTO es 'is child of': sujeto = hijo, objeto = progenitor, asi
-- que se asciende sujeto -> objeto. Con 'father_of' hardcodeado este check no
-- miraba ninguna fila y pasaba en verde por vacio.
WITH RECURSIVE asc_(raiz, ancestro, prof) AS (
    SELECT r.sujeto_id, r.objeto_id, 1
      FROM relacion r JOIN predicado p ON p.id = r.predicado_id
     WHERE p.categoria = 'genealogica' AND p.clave LIKE '%child_of%'
       AND r.objeto_id IS NOT NULL
    UNION ALL
    SELECT a.raiz, r.objeto_id, a.prof + 1
      FROM asc_ a
      JOIN relacion r  ON r.sujeto_id = a.ancestro
      JOIN predicado p ON p.id = r.predicado_id
     WHERE p.categoria = 'genealogica' AND p.clave LIKE '%child_of%'
       AND r.objeto_id IS NOT NULL AND a.prof < 25
)
SELECT DISTINCT raiz AS entidad_id FROM asc_ WHERE raiz = ancestro;

-- @check: coordenadas_fuera_del_mundo_mitico  (Iberia -> Caucaso -> India)
-- Solo se aplica a lugares que participan del mito. Pleiades cubre TODO el mundo
-- antiguo y mas alla (Great Zimbabwe, el Limpopo): esos estan fuera del rango
-- griego sin que eso sea un error de carga, asi que no se cuentan aqui.
SELECT e.id, e.nombre, ld.latitud, ld.longitud
  FROM lugar_detalle ld JOIN entidad e ON e.id = ld.entidad_id
 WHERE ld.latitud IS NOT NULL
   AND (ld.latitud NOT BETWEEN 20 AND 60 OR ld.longitud NOT BETWEEN -12 AND 80)
   AND (EXISTS (SELECT 1 FROM entidad_identificador i
                 WHERE i.entidad_id = e.id AND i.namespace = 'manto')
     OR EXISTS (SELECT 1 FROM evento ev WHERE ev.lugar_id = e.id)
     OR EXISTS (SELECT 1 FROM relacion_rol rr WHERE rr.entidad_id = e.id));

-- @check: coordenadas_imposibles  (fuera del planeta: fallo de parseo, no de alcance)
SELECT e.id, e.nombre, ld.latitud, ld.longitud
  FROM lugar_detalle ld JOIN entidad e ON e.id = ld.entidad_id
 WHERE ld.latitud IS NOT NULL
   AND (ld.latitud NOT BETWEEN -90 AND 90 OR ld.longitud NOT BETWEEN -180 AND 180);

-- @check: fechas_incoherentes  (min <= preferida <= max, y a.C. => negativo)
SELECT id, evento_id, autoridad, anio_ac, anio_min_ac, anio_max_ac
  FROM evento_datacion
 WHERE (anio_min_ac IS NOT NULL AND anio_ac IS NOT NULL AND anio_ac < anio_min_ac)
    OR (anio_max_ac IS NOT NULL AND anio_ac IS NOT NULL AND anio_ac > anio_max_ac)
    OR anio_ac > 0;

-- @check: causalidad_invertida
-- Los anios a.C. se guardan como enteros NEGATIVOS, asi que "mas antiguo" es
-- "menor". La causa debe ser anterior: a.fecha_ac <= b.fecha_ac. Se marca error
-- el caso contrario. (La version inicial de este check tenia el signo al reves y
-- daba por invertida toda la cadena troyana, que era correcta.)
SELECT er.id, a.nombre AS causa, a.fecha_ac, b.nombre AS efecto, b.fecha_ac
  FROM evento_relacion er
  JOIN evento a ON a.id = er.evento_a_id
  JOIN evento b ON b.id = er.evento_b_id
 WHERE er.tipo = 'causa_de'
   AND a.fecha_ac IS NOT NULL AND b.fecha_ac IS NOT NULL
   AND a.fecha_ac > b.fecha_ac;

-- @check: participantes_imposibles  (nadie combate en eventos separados >150 anios)
SELECT p1.entidad_id, e.nombre, ev1.nombre AS evento_a, ev1.fecha_ac,
       ev2.nombre AS evento_b, ev2.fecha_ac
  FROM evento_participante p1
  JOIN evento_participante p2 ON p2.entidad_id = p1.entidad_id AND p2.evento_id > p1.evento_id
  JOIN evento ev1 ON ev1.id = p1.evento_id
  JOIN evento ev2 ON ev2.id = p2.evento_id
  JOIN entidad e  ON e.id = p1.entidad_id
 WHERE ev1.fecha_ac IS NOT NULL AND ev2.fecha_ac IS NOT NULL
   AND ABS(ev1.fecha_ac - ev2.fecha_ac) > 150;

-- @check: evento_en_no_lugar  (evento.lugar_id debe ser una entidad de tipo lugar)
SELECT ev.id AS evento_id, e.id AS entidad_id, e.nombre, t.clave AS tipo
  FROM evento ev
  JOIN entidad e      ON e.id = ev.lugar_id
  JOIN tipo_entidad t ON t.id = e.tipo_entidad_id
 WHERE t.es_lugar = 0;

-- @check: lugar_ficticio_con_coordenadas  (redundante con el CHECK, por si se altero)
SELECT entidad_id, latitud, longitud, geo_tipo
  FROM lugar_detalle
 WHERE geo_tipo = 'legendario_sin_ubicacion' AND latitud IS NOT NULL;

-- @check: duplicados_no_resueltos  (el fuzzy join no convergio)
-- Mismo nombre normalizado y mismo tipo, sin explicacion. Dos entidades con el
-- mismo ID externo y valores distintos SI tienen explicacion (son lugares
-- distintos que se llaman igual, p. ej. las cinco Pylos de Pleiades): esas se
-- excluyen, o el check marcaria miles de homonimos legitimos.
SELECT a.id AS a_id, b.id AS b_id, a.nombre, a.nombre_norm
  FROM entidad a
  JOIN entidad b
    ON b.nombre_norm = a.nombre_norm
   AND b.tipo_entidad_id IS a.tipo_entidad_id
   AND b.id > a.id
 WHERE a.nombre_norm IS NOT NULL AND a.nombre_norm <> ''
   AND NOT EXISTS (
        SELECT 1 FROM entidad_identificador ia
          JOIN entidad_identificador ib ON ib.namespace = ia.namespace
         WHERE ia.entidad_id = a.id AND ib.entidad_id = b.id
           AND ia.namespace IN ('manto','wikidata','pleiades','digital_limc'))
   AND NOT EXISTS (
        SELECT 1 FROM entidad_revision r
         WHERE (r.entidad_a_id = a.id AND r.entidad_b_id = b.id)
            OR (r.entidad_a_id = b.id AND r.entidad_b_id = a.id));

-- @check: fusiones_sin_rastro  (toda fusion debe guardar su json para --undo)
SELECT id, absorbida_nombre FROM fuzzy_fusion
 WHERE absorbida_json IS NULL OR absorbida_json = '' OR absorbida_json = '{}';

-- @check: relacion_apunta_a_entidad_absorbida  (reapuntado incompleto)
SELECT r.id, r.sujeto_id, r.objeto_id
  FROM relacion r
 WHERE r.sujeto_id IN (SELECT absorbida_id FROM fuzzy_fusion WHERE revertida = 0)
    OR r.objeto_id IN (SELECT absorbida_id FROM fuzzy_fusion WHERE revertida = 0);
