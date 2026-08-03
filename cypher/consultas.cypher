// Consultas de partida para Memgraph Lab sobre la proyeccion de greek.db.
// Todas verificadas contra el grafo cargado: pega una en Lab y ejecutala.
//
// Modelo en cuatro lineas:
//   (:Entidad) lleva ademas :Agente|:Lugar|:Rio|:Santuario|:Objeto|... y props
//   nombre, nombre_es, nombre_grc, tipo, grado, lat/lng, manto, wikidata, pleiades
//   Aristas de mito = tipo del predicado MANTO (IS_CHILD_OF, KILLS, MARRIES...)
//   con props predicado, citas[], autores[], roles[], incierto, duda, implicito
//   (:Contradiccion)-[:SOBRE]->(de quien) y -[:ALTERNATIVA]->(las versiones)
//
// DOS AVISOS que arruinan cualquier consulta escrita a ojo:
//
//  a) LOS NOMBRES LLEVAN CUALIFICADOR. Es 'Zeus (Olympian)', no 'Zeus'; es
//     'Heracles', no 'Herakles'; hay 'Zeus (Cretan)' y 'Heracles (Egyptian)'
//     como entidades distintas. Nunca busques por igualdad exacta a ciegas:
//        MATCH (e:Entidad) WHERE e.nombre STARTS WITH 'Zeus' RETURN e.nombre, e.grado
//     ORDER BY e.grado DESC te dice cual es "el" Zeus.
//
//  b) EL GRAFO GENEALOGICO NO ES UN ARBOL. Cada figura tiene N progenitores
//     alternativos segun la fuente, asi que un `*..8` sin acotar explota:
//     la ascendencia de Aquiles a 8 saltos son 12,2 MILLONES de caminos.
//     Para ancestros usa *BFS (un camino por nodo alcanzado), no *..n.
//     Por lo mismo, entre dos figuras hay varias aristas del mismo tipo (una por
//     fuente que lo afirma): casi siempre quieres DISTINCT o count(DISTINCT ...).
//
//  c) `rol_objeto`: MANTO deja sin objeto directo el 29 % de las relaciones y
//     pone el destino en un rol (`has_cult_site` -> rol `en`). Esas aristas
//     llevan `rol_objeto` con el rol que ocupa la posicion de objeto, y una
//     relacion como `travels_[from]_[to]_[via]` produce TRES aristas TRAVELS:
//     `desde`, `hacia` y `via`. Filtra por `r.rol_objeto` cuando importe.


// ---------------------------------------------------------------- 1. orientarse

// que hay: recuento por etiqueta
MATCH (n) RETURN labels(n) AS etiquetas, count(*) AS n ORDER BY n DESC;

// los predicados mas usados
MATCH ()-[r]->() RETURN type(r) AS arista, count(*) AS n ORDER BY n DESC LIMIT 30;

// las 40 entidades mejor atestiguadas: por aqui se empieza a explorar.
// `grado` = numero de relaciones; el 80 % de la base son lugares de Pleiades
// con una sola mencion, asi que sin ordenar por grado solo ves ruido.
MATCH (e:Entidad) WHERE e.grado > 0
RETURN e.nombre, e.tipo, e.grado ORDER BY e.grado DESC LIMIT 40;

// buscar por cualquier variante (griego, transliteracion, latin, epiteto).
// Asi se encuentra 'Cape Circaion (Italy)' buscando 'Kirkaion'.
MATCH (e:Entidad) WHERE any(v IN e.variantes WHERE toLower(v) CONTAINS 'kirkaion')
RETURN e.nombre, e.tipo, e.variantes, e.ids;

// afirmaciones sobre una figura que no son aristas porque no tienen objeto
// (`has_no_children`, `becomes_immortal`, `is_mentioned`)
MATCH (e:Entidad) WHERE e.predicados_unarios IS NOT NULL
RETURN e.nombre, e.predicados_unarios LIMIT 30;


// ------------------------------------------------ 1bis. papeles y generacion

// Los papeles son DERIVADOS y multi-etiqueta: `:Dios`, `:Heroe`, `:Gobernante`,
// `:Monstruo`, `:Deificado`, `:Profeta`, `:Artesano`. MANTO no los publica (todo
// es `Agent`), asi que se infieren — la regla que lo decidio va en
// `n.papeles_regla`, para poder discutirla.
MATCH (n) WHERE n:Dios OR n:Heroe OR n:Gobernante OR n:Monstruo
RETURN labels(n) AS etiquetas, count(*) AS n ORDER BY n DESC;

// por que esta figura tiene los papeles que tiene
MATCH (n:Entidad {nombre: 'Heracles'}) RETURN n.papeles, n.papeles_regla, n.generacion;

// dioses con mas santuarios (Apolo 26, Zeus 19, Cibeles 16)
MATCH (d:Dios)-[:HAS_CULT_SITE]->(l:Lugar)
RETURN d.nombre AS dios, count(DISTINCT l) AS santuarios ORDER BY santuarios DESC LIMIT 15;

// quien mata monstruos: el catalogo de hazanas, dibujado
MATCH camino = (:Heroe)-[:KILLS]->(:Monstruo) RETURN camino LIMIT 200;

// gobernantes por generacion: la curva del mito, de la teogonia a los Heraclidas
MATCH (g:Gobernante) WHERE g.generacion IS NOT NULL
RETURN g.generacion AS gen, count(*) AS gobernantes ORDER BY gen;

// heroes de la generacion de Troya y donde se les atestigua
MATCH (h:Heroe {generacion: 2})-[r]->(l:Lugar) WHERE l.lat IS NOT NULL
RETURN h.nombre, r.predicado_es, l.nombre LIMIT 60;

// figuras con mas papeles a la vez (Heracles: heroe, gobernante y deificado)
MATCH (n:Entidad) WHERE n.papeles IS NOT NULL AND size(n.papeles) > 2
RETURN n.nombre, n.papeles, n.generacion ORDER BY size(n.papeles) DESC LIMIT 20;

// la generacion de una figura, con su rango si las anclas discrepan
MATCH (n:Entidad) WHERE n.generacion_confianza = 'baja' AND n.generacion_min <> n.generacion_max
RETURN n.nombre, n.generacion, n.generacion_min, n.generacion_max, n.generacion_metodo LIMIT 25;

// las divinidades no transmiten cronologia: por eso el eje temporal existe
MATCH (n:Entidad) WHERE n.transmite_generacion = false
RETURN n.nombre, n.generacion, size([(h)-[:IS_CHILD_OF]->(n) | h]) AS hijos
ORDER BY hijos DESC LIMIT 15;


// ------------------------------------------------------------- 2. genealogia

// OJO con la direccion: en MANTO el predicado es `is child of`, sujeto = hijo.
// Los hijos de Zeus son los que APUNTAN a Zeus. Son 295 aristas para 68 hijos
// distintos: DISTINCT porque varias fuentes afirman la misma filiacion.
MATCH (hijo)-[:IS_CHILD_OF]->(:Entidad {nombre: 'Zeus (Olympian)'})
RETURN DISTINCT hijo.nombre, hijo.tipo, hijo.grado ORDER BY hijo.grado DESC;

// arbol descendente de Zeus, 2 generaciones, dibujado como grafo en Lab.
// 2 y no 3 a proposito: a 3 saltos son >30k caminos y el canvas se atasca.
MATCH camino = (:Entidad {nombre: 'Zeus (Olympian)'})<-[:IS_CHILD_OF*1..2]-()
RETURN camino LIMIT 400;

// ascendencia de Aquiles: *BFS devuelve UN camino por antepasado alcanzado,
// que es lo que uno quiere. Con *..8 esto son 12 millones de filas.
MATCH camino = (:Entidad {nombre: 'Achilles'})-[:IS_CHILD_OF *BFS ..8]->()
RETURN camino;

// misma cosa como tabla: antepasados y a que distancia
MATCH camino = (:Entidad {nombre: 'Achilles'})-[:IS_CHILD_OF *BFS ..8]->(ancestro)
RETURN size(relationships(camino)) AS saltos, ancestro.nombre ORDER BY saltos;

// hermanos completos: comparten los dos progenitores
MATCH (a)-[:IS_CHILD_OF]->(p)<-[:IS_CHILD_OF]-(b)
WHERE a.gid < b.gid
WITH a, b, count(DISTINCT p) AS progenitores_comunes
WHERE progenitores_comunes = 2
RETURN a.nombre, b.nombre LIMIT 50;

// ciclos genealogicos: nadie es su propio antepasado. Salen 36, y NO es un bug:
// son fuentes distintas discrepando sobre quien engendra a quien.
MATCH camino = (a:Entidad)-[:IS_CHILD_OF*2..6]->(a) RETURN camino LIMIT 10;


// ------------------------------------------------- 3. contradicciones (el nucleo)

// las figuras con mas versiones incompatibles. Heracles gana con 1.830.
MATCH (c:Contradiccion)-[:SOBRE]->(e:Entidad)
RETURN e.nombre, c.tipo, count(*) AS versiones
ORDER BY versiones DESC LIMIT 30;

// una contradiccion dibujada: de quien se discute y cuales son las versiones
MATCH (c:Contradiccion)-[:SOBRE]->(e:Entidad)
WHERE e.nombre STARTS WITH 'Acheloos'
MATCH camino = (c)-[:SOBRE|ALTERNATIVA]->()
RETURN camino;

// los progenitores alternativos de una misma figura.
// DISTINCT obligatorio: la misma pareja aparece en varias contradicciones.
MATCH (c:Contradiccion {tipo: 'genealogia'})-[:SOBRE]->(e:Entidad {nombre: 'Adonis'})
MATCH (c)-[:ALTERNATIVA]->(alt)
RETURN collect(DISTINCT alt.nombre) AS progenitores_alternativos;

// quien mato a quien segun quien
MATCH (c:Contradiccion {tipo: 'autoria_muerte'})-[:SOBRE]->(victima)
MATCH (c)-[:ALTERNATIVA]->(matador)
WITH victima, collect(DISTINCT matador.nombre) AS matadores
RETURN victima.nombre, matadores ORDER BY size(matadores) DESC LIMIT 25;

// donde discrepan sobre la ubicacion de algo
MATCH (c:Contradiccion {tipo: 'ubicacion'})-[:SOBRE]->(e)
MATCH (c)-[:ALTERNATIVA]->(l:Lugar)
WITH e, collect(DISTINCT l.nombre) AS lugares
WHERE size(lugares) > 3
RETURN e.nombre, lugares ORDER BY size(lugares) DESC LIMIT 20;


// ----------------------------------------------------- 4. incertidumbre y fuentes

// afirmaciones que la propia fuente marca como dudosas
MATCH (a)-[r]->(b) WHERE r.duda OR r.incierto
RETURN a.nombre, r.predicado, b.nombre, r.citas LIMIT 50;

// dato implicito: nadie lo dice, se deduce del texto
MATCH (a)-[r]->(b) WHERE r.implicito
RETURN a.nombre, r.predicado, b.nombre, r.citas LIMIT 50;

// afirmaciones SIN atestacion textual: el hueco de calidad, por predicado
MATCH ()-[r]->() WHERE r.n_citas = 0 AND r.predicado IS NOT NULL
RETURN r.predicado, count(*) AS sin_pasaje ORDER BY sin_pasaje DESC LIMIT 20;

// todo lo que afirma un autor concreto
MATCH (a)-[r]->(b) WHERE 'Hesiod' IN r.autores
RETURN a.nombre, r.predicado, b.nombre, r.citas LIMIT 100;

// que autores sostienen mas afirmaciones. Pausanias 5.483, Apolodoro 3.363.
// El `IS NOT NULL` es obligatorio: UNWIND sobre null aborta la consulta, y las
// aristas de estructura (:ROL, :DENTRO_DE) no tienen `autores`.
MATCH ()-[r]->() WHERE r.autores IS NOT NULL
UNWIND r.autores AS autor
RETURN autor, count(*) AS afirmaciones ORDER BY afirmaciones DESC LIMIT 25;

// el aparato de fuentes como grafo: autor -> obras -> pasajes
MATCH camino = (:Autor {nombre: 'Homer'})-[:ESCRIBE]->(:Obra)<-[:EN_OBRA]-(:Pasaje)
RETURN camino LIMIT 200;


// ----------------------------------------------------------- 5. geografia y mapa

// vista de mapa en Lab: ejecuta y cambia a la pestana Map.
// El LIMIT importa: hay 36.848 lugares con coordenada.
MATCH (l:Lugar) WHERE l.lat IS NOT NULL AND l.es_ficticio <> true
RETURN l LIMIT 2000;

// solo los lugares DEL MITO, no todo Pleiades: donde alguien vive, muere,
// nace, reina, funda o tiene culto. Atenas, Tebas, Argos a la cabeza.
MATCH (a:Agente)-[:RESIDES|DIES|IS_BORN|RULES|FOUNDS|HAS_CULT_SITE]->(l:Lugar)
WHERE l.lat IS NOT NULL
RETURN l, count(*) AS menciones ORDER BY menciones DESC LIMIT 500;

// coordenada poco fiable: 'rough' puede ser el centroide de una caja de 100 km
MATCH (l:Lugar) WHERE l.geo_precision = 'rough'
RETURN l.nombre, l.lat, l.lng, l.precision_metros LIMIT 50;

// lugares legendarios sin ubicacion: la coordenada NULL es correcta, es el Hades
MATCH (l:Lugar) WHERE l.es_ficticio = true RETURN l.nombre, l.geo_tipo;

// jerarquia geografica: que hay dentro de Beocia
MATCH camino = (:Entidad)-[:DENTRO_DE*1..3]->(:Entidad {nombre: 'Boiotia'})
RETURN camino LIMIT 200;

// el itinerario de una figura: todo lugar al que la ata cualquier predicado.
// `rol_objeto` distingue de donde sale, a donde va y por donde pasa.
MATCH (a:Entidad {nombre: 'Odysseus'})-[r]->(l:Lugar)
RETURN r.predicado, r.rol_objeto, l.nombre, l.lat, l.lng, r.citas;

// solo los destinos de un viaje, no las escalas ni el origen
MATCH (a:Agente)-[r:TRAVELS {rol_objeto: 'hacia'}]->(l:Lugar)
RETURN a.nombre, l.nombre, r.citas LIMIT 50;


// -------------------------------------------------------- 6. eventos y cronologia

// cronologia completa (anios a.C. = enteros NEGATIVOS: mas antiguo es menor).
// nombre_es esta a NULL en los 94 eventos del Marmor Parium: usa coalesce.
MATCH (e:Evento)-[d:DATADO_EN]->(f:Datacion) WHERE d.preferida
RETURN coalesce(e.nombre_es, e.nombre) AS evento, f.anio_ac, f.autoridad, f.sistema
ORDER BY f.anio_ac;

// donde las cronologias antiguas discrepan. Solo la Guerra de Troya tiene la
// tabla comparada: 11 autoridades entre -1334 y -1135.
MATCH (e:Evento)-[:DATADO_EN]->(f:Datacion)
WITH e, collect(f.autoridad + ' ' + toString(f.anio_ac)) AS fechas
WHERE size(fechas) > 1
RETURN coalesce(e.nombre_es, e.nombre) AS evento, fechas;

// los bandos de la Guerra de Troya.
// evento_participante.bando_id esta vacio en greek.db, asi que :EN_BANDO no
// existe todavia: los bandos solo cuelgan del evento.
MATCH camino = (:Evento {nombre: 'Guerra de Troya'})<-[:BANDO_DE]-(:Bando)
RETURN camino;

// los eventos con participantes de verdad (los 13 Mythic Event de MANTO)
MATCH (a:Agente)-[p:PARTICIPA_EN]->(e:Evento)
RETURN e.nombre, count(*) AS participantes ORDER BY participantes DESC LIMIT 10;

// una boda con toda su lista de invitados, dibujada
MATCH camino = (:Agente)-[:PARTICIPA_EN]->(:Evento {nombre: 'the Wedding of Peleus and Thetis'})
RETURN camino;

// eventos sin fecha A PROPOSITO: cosmogonia y teomaquias no se datan
MATCH (e:Evento) WHERE e.fecha_metodo = 'sin_fecha'
RETURN e.nombre, e.tipo, e.fecha_metodo;


// ------------------------------------------------------- 7. iconografia y cultos

// las figuras mas representadas en vasos y esculturas
MATCH (a:Artefacto)-[:REPRESENTA]->(e:Entidad)
RETURN e.nombre, count(*) AS piezas ORDER BY piezas DESC LIMIT 30;

// artefactos de Heracles con procedencia conocida (ojo: 'Heracles', sin k)
MATCH camino = (l:Entidad)<-[:HALLADO_EN]-(:Artefacto)-[:REPRESENTA]->(:Entidad {nombre: 'Heracles'})
RETURN camino LIMIT 200;

// donde se han hallado mas piezas
MATCH (:Artefacto)-[:HALLADO_EN]->(l:Entidad)
RETURN l.nombre, count(*) AS piezas ORDER BY piezas DESC LIMIT 20;

// sitios de culto por divinidad. Apolo 46, Zeus 21, Poseidon 21.
// Estas 572 aristas solo existen porque el lugar se promueve desde el rol `en`:
// `has_cult_site_[in/on/at]` tiene objeto_id NULL en 539 de sus 540 filas.
MATCH (d:Entidad)-[:HAS_CULT_SITE]->(l:Lugar)
RETURN d.nombre, collect(DISTINCT l.nombre)[..10] AS sitios, count(DISTINCT l) AS n
ORDER BY n DESC LIMIT 15;


// ------------------------------------------------------------- 8. reconciliacion

// identidades equiparadas entre culturas (Osiris = Dioniso, etc.)
MATCH camino = (:Entidad)-[:EQUIVALE_A]->(:Entidad) RETURN camino LIMIT 200;

// homonimos legitimos: misma forma normalizada, entidades distintas
// (las cinco Pylos de Pleiades). No son duplicados sin fusionar.
MATCH (a:Entidad), (b:Entidad)
WHERE a.nombre_norm = b.nombre_norm AND a.gid < b.gid
RETURN DISTINCT a.nombre, b.nombre, a.tipo, a.ids, b.ids LIMIT 50;

// entidades sin ningun ID externo: debe salir 0
MATCH (e:Entidad) WHERE e.ids IS NULL OR size(e.ids) = 0 RETURN count(*) AS sin_id;

// las figuras con mas variantes de nombre absorbidas por el fuzzy join
MATCH (e:Entidad) WHERE size(e.variantes) > 3
RETURN e.nombre, e.variantes ORDER BY size(e.variantes) DESC LIMIT 25;


// ------------------------------------------------------------- 9. camino mas corto

// como se conectan dos figuras, por cualquier tipo de relacion.
// *BFS es obligatorio aqui: sin el, un *..6 no acotado no vuelve.
MATCH (a:Entidad {nombre: 'Odysseus'}), (b:Entidad {nombre: 'Heracles'})
MATCH camino = (a)-[*BFS ..6]-(b)
RETURN camino;

// solo por sangre
MATCH (a:Entidad {nombre: 'Helen'}), (b:Entidad {nombre: 'Achilles'})
MATCH camino = (a)-[:IS_CHILD_OF *BFS ..10]-(b)
RETURN camino;

// el rol `en` (9.528 filas) es lo que ata una accion a su escenario:
// la arista :ROL lo hace recorrible
MATCH (a:Agente)-[r:ROL {rol: 'en'}]->(l:Lugar)
RETURN a.nombre, r.predicado, l.nombre LIMIT 50;
