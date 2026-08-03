-- Seeds: vocabularios controlados. Idempotente.

-- ---------------------------------------------------------------- tipos
INSERT INTO tipo_entidad (clave, nombre_es, es_lugar, es_divino) VALUES
    ('dios',            'dios olimpico',      0, 1),
    ('titan',           'titan',              0, 1),
    ('primordial',      'primordial',         0, 1),
    ('daimon',          'daimon',             0, 1),
    ('heroe',           'heroe',              0, 0),
    ('mortal',          'mortal',             0, 0),
    ('monstruo',        'monstruo',           0, 0),
    ('ninfa',           'ninfa',              0, 1),
    ('grupo',           'grupo',              0, 0),
    ('pueblo',          'pueblo',             0, 0),
    ('lugar',           'lugar',              1, 0),
    ('rio',             'rio',                1, 1),
    ('montana',         'montana',            1, 0),
    ('isla',            'isla',               1, 0),
    ('region',          'region',             1, 0),
    ('santuario',       'santuario',          1, 0),
    ('objeto',          'objeto',             0, 0),
    ('animal',          'animal',             0, 0),
    ('personificacion', 'personificacion',    0, 1),
    ('constelacion',    'constelacion',       0, 0),
    ('inframundo',      'lugar del inframundo', 1, 0),
    -- Vocabulario real de MANTO (type_of_entity_6937): son las 7 clases que el
    -- dataset distingue de verdad, codificadas con el emoji de `Name`. MANTO no
    -- separa dios/heroe/mortal/monstruo: todo eso es 'Agent'.
    ('agente',          'agente (Agent de MANTO)', 0, 0),
    ('landmark',        'hito o monumento',   1, 0),
    ('colectivo',       'colectivo',          0, 0),
    ('evento_mitico',   'evento mitico',      0, 0),
    ('desconocido',     'sin clasificar',     0, 0)
ON CONFLICT (clave) DO NOTHING;

-- --------------------------------------------------------------- ciclos
INSERT INTO ciclo_mitico (clave, nombre_es, orden) VALUES
    ('cosmogonia',          'Cosmogonia',                    10),
    ('titanomaquia',        'Titanomaquia',                  20),
    ('gigantomaquia',       'Gigantomaquia',                 30),
    ('primeros_mortales',   'Primeros mortales y el Diluvio',40),
    ('ciclo_argivo',        'Ciclo argivo',                  50),
    ('ciclo_cretense',      'Ciclo cretense',                60),
    ('heracleia',           'Heracleia',                     70),
    ('argonautica',         'Argonautica',                   80),
    ('caceria_calidonia',   'Caceria de Calidon',            90),
    ('ciclo_tebano',        'Ciclo tebano',                 100),
    ('teseida',             'Teseida',                      110),
    ('ciclo_troyano',       'Ciclo troyano',                120),
    ('nostoi',              'Nostoi (los Retornos)',        130),
    ('orestiada',           'Orestiada',                    140),
    ('retorno_heraclidas',  'Retorno de los Heraclidas',    150)
ON CONFLICT (clave) DO NOTHING;

-- ------------------------------------------------------------- periodos
-- Cronologia heladica (fuentes.md §2.7). ChronOntology completa/corrige
-- estos valores al cargar; aqui van los anclajes minimos.
INSERT INTO periodo (clave, nombre, anio_inicio_ac, anio_fin_ac) VALUES
    ('EH',            'Heladico Antiguo',            -3200, -2050),
    ('MH',            'Heladico Medio',              -2050, -1550),
    ('LH',            'Heladico Reciente (micenico)', -1550, -1050),
    ('LH_I',          'LH I',                        -1550, -1500),
    ('LH_II',         'LH II',                       -1500, -1435),
    ('LH_IIIA1',      'LH IIIA1',                    -1435, -1390),
    ('LH_IIIA2',      'LH IIIA2',                    -1390, -1330),
    ('LH_IIIB',       'LH IIIB',                     -1330, -1200),
    ('LH_IIIC_early', 'LH IIIC Temprano',            -1200, -1125),
    ('LH_IIIC_mid',   'LH IIIC Medio',               -1125, -1070),
    ('LH_IIIC_late',  'LH IIIC Tardio',              -1070, -1050),
    ('submicenico',   'Submicenico',                 -1050, -1000),
    ('protogeom',     'Protogeometrico',             -1000,  -900)
ON CONFLICT (clave) DO NOTHING;
