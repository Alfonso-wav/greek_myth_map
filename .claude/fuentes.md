\# fuentes.md — Base de datos relacional de mitología griega



> \*\*Propósito de este archivo.\*\* Documento de trabajo para Claude Code. Contiene: (1) el catálogo de fuentes evaluadas y priorizadas, (2) el esquema SQLite propuesto, (3) el orden de ingesta, (4) la estrategia para resolver los dos requisitos difíciles — \*\*coordenadas de cada ubicación\*\* y \*\*fecha de cada evento\*\* —, y (5) los errores de diseño que hay que evitar.

>

> Fecha de investigación: 2026-07-29.



\---



\## 0. Resumen ejecutivo — leer esto primero



Existe una fuente que resuelve el 70 % del problema y que probablemente no conocías: \*\*MANTO\*\* (Mapping Ancient Narratives, Territories, Objects). Es un dataset académico de mito griego, \*\*ya relacional\*\*, con \*\*8.993 entidades\*\* y \*\*32.122 relaciones tipadas\*\* extraídas de los textos antiguos, publicado en CSV/JSON bajo \*\*CC-BY 4.0\*\*, con identificadores estables y enlaces cruzados a Wikidata, Pleiades, ToposText y Trismegistos.



La arquitectura recomendada es:



| Capa | Fuente | Qué aporta |

|---|---|---|

| \*\*Espina dorsal\*\* | MANTO | Entidades (dioses, héroes, mortales, monstruos, grupos, lugares, objetos) + red de relaciones con predicado tipado y cita textual |

| \*\*Geografía\*\* | Pleiades + ToposText | Latitud/longitud WGS-84, precisión, jerarquía territorial |

| \*\*Cronología\*\* | Digital Marmor Parium + Eusebio + tabla de cronógrafos antiguos + cronología heládica | Fechas absolutas (a.C.) para eventos míticos |

| \*\*Enriquecimiento\*\* | Wikidata / Smith's Dictionary / Hyginus / Apolodoro | Descripciones en prosa, epítetos, nombres alternativos, listas de participantes |

| \*\*Verificación manual\*\* | Theoi, Gantz, Grimal, LIMC | Control de calidad, desambiguación, resolución de contradicciones |



\*\*No empieces scrapeando Wikipedia ni Theoi.\*\* Empieza descargando MANTO y Pleiades, que son datos limpios, citables y con licencia abierta. El scraping solo se justifica para rellenar huecos concretos.



\---



\## 1. Las tres decisiones de diseño que condicionan todo



Antes del catálogo de fuentes, tres advertencias. Si el esquema no las contempla, la base de datos será de mala calidad por mucho que los datos sean buenos.



\### 1.1 El problema de los homónimos



En mito griego los nombres se repiten masivamente. Hay decenas de personajes distintos llamados \*Ífis\*, \*Anfítemis\*, \*Alfesibea\*, \*Anaxibia\*, \*Amico\*, \*Aloeo\*... La propia Wikipedia mantiene una lista de "figuras menores" donde la glosa de muchísimas entradas es literalmente "nombre de varias figuras mitológicas". Hay al menos tres \*Yolao\*, varios \*Perieres\*, y "Apolodoro" es a la vez un mitógrafo y varios personajes.



\*\*Consecuencia obligatoria:\*\* el nombre \*\*nunca\*\* puede ser clave primaria ni clave de unión (`JOIN`). Toda entidad se identifica por un ID sintético interno, y la reconciliación entre fuentes se hace \*\*exclusivamente\*\* por identificadores externos (MANTO URI, Wikidata QID, Pleiades ID). Cualquier matching por cadena de texto debe pasar por una tabla de revisión manual.



\### 1.2 El problema de las versiones contradictorias



El mito griego no tiene una versión canónica. Las Hespérides son hijas de Nix según Hesíodo, de Nix y Érebo en otra tradición, de Atlas en otra, de Atlas y Hésperis, de Forcis y Ceto, o de Zeus y Temis. Ninguna es "la correcta". Igual con la genealogía de casi cualquier figura, con quién mató a quién, y con dónde ocurrió cada cosa.



\*\*Consecuencia obligatoria:\*\* las relaciones \*\*no\*\* son campos de la tabla de personajes (`padre\_id`, `madre\_id` está mal). Son \*\*afirmaciones\*\* en una tabla propia, cada una con su fuente textual y sus banderas de incertidumbre. Este es exactamente el modelo de MANTO (su tabla `Tie`): sujeto → predicado → objeto, más la cita que lo respalda, más flags `data\_uncertain`, `doubt\_expressed`, `alternatives\_given`, `data\_implicit`.



Si aplanas esto para "simplificar", pierdes la calidad que pides.



\### 1.3 El problema de los lugares que no existen



Pides latitud y longitud de cada ubicación. Se puede hacer para la gran mayoría, pero hay que ser honesto con las categorías:



| Categoría | Ejemplos | Coordenadas |

|---|---|---|

| Real, localizado con precisión | Micenas, Delfos, Olimpia, Troya, Tirinto, Pilos | Sí, precisión métrica |

| Real, localización aproximada o discutida | Ítaca homérica, Aulis, Áulide, Colcos | Sí, con radio de error grande |

| Real pero identificación mítica disputada | Escila y Caribdis (estrecho de Mesina), Isla de Circe (Monte Circeo), Ogigia | Sí, marcadas como identificación tradicional, no como hecho |

| Legendario sin correlato geográfico | Hades, Tártaro, Eliseo, Islas de los Bienaventurados, Olimpo \*como morada divina\* (distinto del monte físico) | \*\*No.\*\* `NULL` + flag |



\*\*Consecuencia obligatoria:\*\* la tabla de lugares necesita `geo\_tipo` (enum) y `es\_ficticio` (bool), y las coordenadas deben ir acompañadas de `precision\_metros` y `geo\_fuente`. Nunca inventes coordenadas para el Tártaro para que la columna no quede vacía; eso convierte un dato ausente en un dato falso.



\---



\## 2. Catálogo de fuentes



\### NIVEL 0 — Espina dorsal



\#### 2.1 MANTO ⭐ fuente principal



\- \*\*Qué es:\*\* dataset académico de Linked Open Data que modela el mundo narrativo del mito griego y su impacto en el paisaje del Mediterráneo. Dirigido por Greta Hawes (Macquarie) y R. Scott Smith (New Hampshire). Construido sobre Nodegoat.

\- \*\*Volumen (release 2026-03-06):\*\*

&#x20; - `Entity`: 8.993 — dioses, héroes, mortales, monstruos, grupos, pueblos, lugares, ríos, objetos

&#x20; - `Tie`: 32.122 — relaciones tipadas con cita de fuente

&#x20; - `Passage`: 5.990 — pasajes concretos con URL a Scaife Viewer

&#x20; - `Artifact`: 1.602 — vasos, esculturas, monedas con representaciones

&#x20; - `Text`: 533, `Author`: 269, `Inscription`: 33, `Collection`: 84

&#x20; - `Interaction` (catálogo de predicados): \*\*165\*\*

\- \*\*Cobertura textual:\*\* Homero (\*Ilíada\*, \*Odisea\*), corpus hesiódico completo (\*Teogonía\*, \*Catálogo de mujeres\*, \*Escudo\*, \*Trabajos\*, fragmentos), \*Biblioteca\* de Apolodoro, \*Descripción de Grecia\* de Pausanias, Apolonio de Rodas, tragedia, y desde 2023 también artefactos arqueológicos.

\- \*\*Licencia:\*\* CC-BY 4.0. Reutilización comercial y remezcla permitidas con atribución.

\- \*\*Acceso:\*\*

&#x20; - Portal + modelo de datos: `https://manto.unh.edu/publication.s/2616`

&#x20; - Descarga completa ZIP (CSV + JSON): Zenodo, DOI `10.5281/zenodo.19446254` — registro: `https://zenodo.org/records/19446255`

&#x20; - Descargas por tabla, patrón de URL:

&#x20;   `https://manto.unh.edu/publication.p/120.m/2616/{TIMESTAMP}/download.v/data/{tabla}\_{id}.json`

&#x20;   Tablas e IDs: `entity\_6580`, `tie\_6582`, `passage\_6581`, `artifact\_11352`, `text\_7140`, `author\_7139`, `inscription\_11376`, `papyrus\_11379`, `collection\_11357`, `interaction\_6583`, `type\_of\_entity\_6937`, `gender\_7880`, `generation\_11335`, `local\_generation\_11334`, `temporality\_7335`, `time\_period\_11356`

&#x20; - API de Nodegoat disponible

&#x20; - Documentación: `https://www.manto-myth.org/documentation` (Manual for Data Collection + Data Management Plan). \*\*Léelo antes de mapear campos.\*\*

\- \*\*Campos clave de `Entity`:\*\* nombre, nombres alternativos, tipo de entidad, género, `Location`/`In`/`Near` (con coordenadas), `Pleiades`, `ToposText`, `Wikidata`, `Trismegistos`, `LIMC headword`, `Digital LIMC`, `Part of`, `Commentary`, más \~130 relaciones inversas materializadas (`Killed by`, `Born at`, `Buried at`, `Founder of`, `Ruler of`, `Transformed into`, `Cult site of`, `Used to kill`...).

\- \*\*Campos clave de `Tie`:\*\* `Source` (pasaje/artefacto/inscripción), `Subject`, `Predicate`, `Direct Object`, `Indirect Object`, y \~25 slots de rol opcionales: `in/on/at`, `near`, `from`, `to`, `via`, `while intending to go to`, `using`, `of`, `for`, `into`, `against`, `concerning`, `with the aid of`, `at the command of`, `at the instigation of`, `with the involvement of`, `in accordance with a prophecy from/about`, `to avenge`, `to aid`, `to obtain`, `to protect`, `to honor`, `to thwart`, `to punish`, `and they conceive`. Más `Timemark: when`, `Timemark: period`, y los cuatro flags de incertidumbre.

\- \*\*Nota de oro:\*\* los slots `against`, `to avenge`, `using`, `with the aid of` + los predicados `Kills`, `Wounded by`, `Conquered by`, `Competes in`, `Led by` te dan los \*\*combates y enfrentamientos\*\* casi listos. Es la mejor fuente para el requisito de "combates, enfrentamientos".

\- \*\*Limitación:\*\* MANTO no tiene una entidad `Evento` de primera clase. Los eventos hay que \*\*derivarlos\*\* por agrupación de `Tie`s (ver §5.2). Los `Generation` / `Local Generation` dan cronología \*relativa\* por generaciones, no fechas absolutas.



\#### 2.2 Pleiades — gazetteer de lugares antiguos ⭐ fuente geográfica principal



\- \*\*Qué es:\*\* gazetteer colaborativo de lugares antiguos, con cobertura exhaustiva del mundo griego y romano. Derivado del \*Barrington Atlas\*. Instituciones: ISAW (NYU) + Ancient World Mapping Center (UNC).

\- \*\*Licencia:\*\* CC-BY 3.0.

\- \*\*Acceso — usa el paquete GIS, es el que trae lat/long limpio:\*\*

&#x20; - `https://atlantides.org/downloads/pleiades/gis/pleiades\_gis\_data.zip`

&#x20; - README de campos: `https://atlantides.org/downloads/pleiades/gis/`

&#x20; - Página general de descargas: `https://pleiades.stoa.org/downloads`

&#x20; - Espejo Git: `https://github.com/isawnyu/pleiades.datasets` (rama `main`, carpeta `data/gis`)

&#x20; - GeoJSON abreviado: `https://github.com/ryanfb/pleiades-geojson`

&#x20; - Alineación con Wikidata: `https://github.com/isawnyu/pleiades\_wikidata`

&#x20; - Alineación con GeoNames: Pleiades+ (en la página de descargas)

\- \*\*Ficheros del paquete GIS y para qué sirven:\*\*

&#x20; - `places.csv` → \*\*la tabla base de lugares.\*\* Campos: `id`, `title`, `description`, `representative\_latitude`, `representative\_longitude`, `location\_precision`, `bounding\_box\_wkt`, `year\_after\_which`, `year\_before\_which`, `uri`

&#x20; - `places\_accuracy.csv` → `min\_accuracy\_meters`, `max\_accuracy\_meters`, `accuracy\_hull`, `location\_types`. \*\*Únela siempre.\*\*

&#x20; - `locations.csv` / `location\_points.csv` / `location\_polygons.csv` / `location\_linestrings.csv` → geometrías individuales por lugar, con `accuracy\_radius` en metros y `location\_type` (ojo a `associated modern` vs `relocated modern`)

&#x20; - `names.csv` → nombres antiguos, `attested\_form` en griego Unicode, `romanized\_form\_1/2/3`, `language\_tag` (BCP-47)

&#x20; - `connections.csv` + `connection\_types.csv` → jerarquía y relaciones espaciales entre lugares

&#x20; - `place\_types.csv` + `places\_place\_types.csv` → tipología (settlement, sanctuary, mountain, river, island...)

\- \*\*Metadatos técnicos:\*\* WGS-84, grados decimales con signo, CSV coma, UTF-8 \*\*con BOM\*\* (quítalo al parsear en Python: `encoding='utf-8-sig'`).

\- \*\*Trampa crítica:\*\* si `location\_precision = 'rough'`, el punto representativo puede ser simplemente el centroide de una caja enorme. No lo trates como coordenada fiable. Propaga `location\_precision` y `max\_accuracy\_meters` a tu tabla.

\- \*\*Nota:\*\* Pleiades no es relacional por debajo (es un grafo), así que sus exportaciones CSV son de fidelidad parcial. El JSON completo es más rico si necesitas algo que falte.



\#### 2.3 ToposText — lugares + textos + \*\*fechas de evento\*\*



\- \*\*Qué es:\*\* biblioteca de textos antiguos en traducción inglesa, geoindexada. Financiado por la Fundación Aikaterini Laskaridis. Premio Digital Humanities 2016.

\- \*\*Volumen:\*\* \~860 obras / \~20 millones de palabras; \*\*8.137 lugares mapeados\*\* desde España hasta la India; \*\*21.000 nombres propios\*\*; \~277.000 referencias antiguas etiquetadas.

\- \*\*Licencia:\*\* compartición explícita bajo atribución a ToposText (miembro de la red Pelagios). Copyright de la Fundación Laskaridis — atribuye y no redistribuyas el corpus textual completo.

\- \*\*Descargas\*\* (`https://topostext.org/TT-downloads` — ojo, las URLs del HTML usan `\\`, cámbialos por `/`):

&#x20; - `https://topostext.org/downloads/ToposText\_places\_2025-11-20.geojson` (5,6 MB) → \*\*lugares con coordenadas\*\*

&#x20; - `https://topostext.org/downloads/ToposTextGazetteer.jsonld` (9 MB) → lugares \*\*con citas de textos antiguos\*\*, formato World Historical Gazetteer

&#x20; - `https://topostext.org/downloads/pelagios.ttl` (5,4 MB) → RDF con \*\*equivalencias Pleiades y DARE\*\* → tu tabla de reconciliación

&#x20; - `https://topostext.org/downloads/ToposTextWorkTurtles.ttl` (1,1 MB) → metadatos Dublin Core del corpus de obras

&#x20; - KMZ por región y por tipo de feature

\- \*\*⭐ Por qué es decisivo para tu requisito de fechas:\*\* ToposText asigna una \*\*fecha de evento a cada párrafo\*\* de cada texto. Y documenta su convención de precisión con una honestidad que puedes replicar directamente:

&#x20; - `\~1000 BC` = el autor se refiere a tiempo mitológico (no es una fecha real)

&#x20; - `\~1 BC` = fecha histórica indeterminada, probablemente pre-imperial

&#x20; - años en múltiplos de 100 o 50 (500 BC, 350 BC) = margen de ±25 años

&#x20; - fechas fiables al año solo en textos históricos organizados anualmente

\- \*\*Uso recomendado:\*\* fuente de fechas de \*contexto narrativo\* y de cobertura geográfica complementaria a Pleiades (ToposText tiene \~8.100 lugares frente a la cobertura más amplia pero menos centrada en Grecia de Pleiades). Ideal para lugares griegos de detalle fino: santuarios, tumbas heroicas, fuentes.



\---



\### NIVEL 1 — Cronología: cómo poner fecha a un mito



Este es el requisito más delicado. No existe "la fecha" de un evento mítico. Existen \*\*varias tradiciones cronológicas antiguas que dan cifras distintas\*\*, más un anclaje arqueológico independiente. El esquema debe guardar todas y exponer una preferida.



\#### 2.4 Digital Marmor Parium ⭐ fuente cronológica principal



\- \*\*Qué es:\*\* edición digital del \*\*Mármol de Paros\*\* (\*Marmor Parium\*), inscripción helenística en mármol de Paros grabada en 264/263 a.C. Proyecto dirigido por Monica Berti, Universidad de Leipzig, dentro del \*Digital Fragmenta Historicorum Graecorum\*.

\- \*\*Por qué es único:\*\* es \*\*la única fuente antigua que asigna años concretos a eventos mitológicos\*\*. Cubre 1581/80 – 299/98 a.C. mezclando sin distinción lo que hoy llamamos mito y lo que llamamos historia. Los griegos consideraban la Guerra de Troya y el viaje de los Argonautas como historia, y de hecho la inscripción dedica más detalle a la Edad Heroica que a los eventos verificables cercanos a su propia fecha.

\- \*\*Acceso:\*\*

&#x20; - `http://www.digitalmarmorparium.org/`

&#x20; - \*\*Tabla cronológica completa de eventos:\*\* `https://www.digitalmarmorparium.org/chronology.html` ← esto es lo que quieres para poblar `evento\_datacion`

&#x20; - `http://opengreekandlatin.github.io/DigitalMarmorParium/`

&#x20; - XML de la edición IG XII.5.444 codificado según \*\*EpiDoc\*\*, con las expresiones cronológicas marcadas

&#x20; - Traducción inglesa navegable con lugares etiquetados: `https://topostext.org/work/119` (traducción de Gillian Newing 2001, con permiso del Ashmolean; 247 referencias a 98 lugares antiguos)

&#x20; - Traducción también en `https://www.attalus.org/translate/chronicles.html`

\- \*\*Ejemplos de datación que aporta\*\* (convertidos a a.C.):

&#x20; - Cécrope primer rey de Atenas: 1581/80

&#x20; - Deucalión rey en Licorea (Parnaso): \~1573

&#x20; - Disputa de Ares y Poseidón en Atenas (origen del Areópago): \~1531

&#x20; - \*\*Diluvio de Deucalión: 1529/28\*\*

&#x20; - Helen y el origen del nombre "helenos": \~1520

&#x20; - Anfictión y la liga anfictiónica en las Termópilas: \~1521

&#x20; - \*\*Caída de Troya: 1209/1208\*\* (la Guerra de Troya, 1217–1208)

\- \*\*Nota técnica:\*\* el Mármol data hacia atrás e \*\*inclusivamente\*\* desde 264/3 a.C. Para convertir sumas es más limpio partir de una línea base de 263/2 a.C.: p. ej. "945 años hasta la caída de Troya" → 1208/7 a.C. Documenta la convención que elijas.



\#### 2.5 Crónica de Eusebio (y Jerónimo)



\- \*\*Qué es:\*\* \*Chronicon\* de Eusebio de Cesarea (s. IV), que incorpora cronología mítica griega procedente de eruditos helenísticos (Apolodoro, Diodoro Sículo, Castor de Rodas, Porfirio). El original griego está perdido; sobrevive en traducción armenia (s. V) y, el libro 2, en la traducción latina de Jerónimo.

\- \*\*Qué aporta:\*\* \*\*listas regias con duración de reinado en años\*\* para Argos, Atenas, Sicione, Micenas, Esparta, Corinto, más sincronismos con Egipto y Asiria. Es el material que permite construir cronología mítica \*por reinados\* en vez de por generaciones.

\- Ejemplo de la serie argiva: Ínaco 50 años → Foroneo 60 → Apis 35 → Argos 70 → Críaso 54 → Forbas 35 → Tríopas 46 → Crótopo 21 → Esténelo → \*Dánao 50\* → Linceo 41 → Abas 23 → Preto 17 → Acrisio 31. Con anotaciones de sincronismo del tipo "en su reinado apareció la flota de los Argonautas y Heracles", "en su reinado fue tomada Ilión".

\- \*\*Acceso (traducciones inglesas libres):\*\*

&#x20; - Attalus (Smith / Pearse et al., desde el latín de Schoene-Petermann): `https://www.attalus.org/translate/eusebius1.html` y `https://www.attalus.org/armenian/euseb10.htm`

&#x20; - Traducción de Robert Bedrosian desde el armenio clásico: PDF en Internet Archive, ítem `EusebiusChroniclechronicon`

&#x20; - Índice general de crónicas griegas en Attalus: `https://www.attalus.org/translate/chronicles.html` — incluye además \*\*Canon Astronómico\*\*, \*Chronicon Paschale\*, \*Chronographeion Syntomon\*, Juan Malalas, Jorge Sincelo, y los fragmentos de \*\*Apolodoro de Atenas\*\* (FGrH 244)

\- \*\*Advertencia:\*\* Eusebio y Jerónimo tienen errores propios acumulados y datan la Creación en 5200 a.C. Usa las duraciones de reinado como estructura relativa; los absolutos hay que anclarlos.



\#### 2.6 Tabla de dataciones antiguas de la Guerra de Troya



La Guerra de Troya es el evento pivote de toda la cronología mítica: casi todo se data por generaciones antes o después de ella. Las autoridades antiguas discrepan en \*\*200 años\*\*. Guarda todas las variantes; es un dato de calidad, no ruido.



| Autoridad antigua | Fecha de la caída de Troya |

|---|---|

| Duris de Samos | 1334 a.C. |

| Eretes | 1291 a.C. |

| Heródoto | \~1250 a.C. |

| Dicearco | 1212 a.C. |

| \*\*Mármol de Paros\*\* | \*\*1209/1208 a.C.\*\* |

| Timeo | 1193 a.C. |

| Platón | 1193 a.C. |

| \*\*Eratóstenes\*\* | \*\*1184/1183 a.C.\*\* (guerra 1194–1184) |

| Sosibio | 1172 a.C. |

| Éforo | 1135 a.C. |



\- \*\*Recomendación de campo `preferida`:\*\* usa \*\*Eratóstenes (1184/1183)\*\*. Es la que funcionó como punto de referencia universal en la Antigüedad, y es la que coincide aproximadamente con la destrucción por incendio de \*\*Troya VIIa\*\* en el registro arqueológico. Marca las demás como variantes.

\- Método de Eratóstenes, útil si necesitas derivar fechas de otros eventos: contaba hacia atrás desde la primera Olimpiada (776 a.C.) usando listas regias espartanas y de Sardes, con la convención de \*\*una generación ≈ 40 años\*\* para reyes y ≈ 33,3 años (tres generaciones por siglo, según Hecateo vía Heródoto) para genealogías normales. Fuentes de detalle: Kokkinos, \*Ancient Chronography, Eratosthenes and the Dating of the Fall of Troy\* (PDF libre en `https://www.centuries.co.uk/2009-ancient%20chronography-kokkinos.pdf`).

\- Nota: Heródoto no daba números; situaba la guerra en un marco relativo (entre el nacimiento de Heracles y el de Pan, 900–800 años antes de su época). Marca su fecha como `derivada`, no `atestiguada`.



\#### 2.7 Anclaje arqueológico — cronología heládica



Para dar `fecha\_min` / `fecha\_max` defendibles a eventos y a fases de ocupación de lugares.



\- \*\*Fuentes:\*\*

&#x20; - Aegean Prehistoric Archaeology (Dartmouth): `https://sites.dartmouth.edu/aegean-prehistory/chronology/`

&#x20; - John Younger (Univ. of Kansas), tabla de cronología egea: `http://people.ku.edu/\~jyounger/aegeanchron.html`

&#x20; - \*Mycenaean Greece and Homeric Tradition\* (eCampusOntario, acceso abierto): capítulo "Chronology"

&#x20; - iDAI \*\*ChronOntology\*\* (`https://chronontology.dainst.org/`) → \*\*vocabulario controlado de periodos con URIs\*\*. MANTO ya lo usa para su clasificación `Time Period`. Úsalo tú también: te da la tabla `periodo` gratis y alineada con MANTO.

\- \*\*Marcos de referencia útiles:\*\*

&#x20; - Heládico (Edad del Bronce continental griego): \~3200 – \~1050 a.C.

&#x20; - Heládico Reciente / Micénico: \~1550 – \~1050 a.C.

&#x20; - LH IIIA1: \~1435/1406 – 1390/1370 a.C. (C-14 de Tsoungiza)

&#x20; - Transición LH IIIA1→IIIA2: entre 1390 y 1375 a.C. (Wiener)

&#x20; - Transición LH IIIA2→IIIB1: entre 1330 y 1290 a.C.

&#x20; - \*\*Colapso de los palacios micénicos (Micenas, Tirinto, Pilos): \~1200 a.C.\*\*, final del LH IIIB. La destrucción del Palacio de Néstor en Pilos se sitúa en la transición LH IIIB→IIIC, \~3150–3130 años BP.

&#x20; - LH IIIC: \~1200–1050 a.C., subdividido en Temprano (\~1200–1125), Medio (\~1125–1070), Tardío (\~1070–1050)

&#x20; - Submicénico → Protogeométrico: transición mal fijada; el hueco entre el final del LH IIIC y la colonización arcaica carece de anclajes absolutos directos y depende de material levantino comparado y de series de C-14 (Lefkandi, Kalapodi, Corinto)

\- \*\*Cómo usarlo:\*\* para eventos del ciclo troyano y de los Retornos, `fecha\_min = -1250`, `fecha\_max = -1150`, `metodo = 'arqueologico'`. Para eventos anteriores (Argonautas, Tebas, Heracles) usa el desplazamiento generacional respecto a Troya (§5.3).



\---



\### NIVEL 2 — Enriquecimiento y prosa



\#### 2.8 Wikidata



\- \*\*Qué es:\*\* grafo de conocimiento abierto. Clase raíz relevante: \*\*`Q22988604`\*\* "mythological Greek character".

\- \*\*Volumen:\*\* \~5.400 ítems de mito griego, \~283–289 propiedades distintas en uso. El trabajo académico \*Greek Mythology as a Knowledge Graph\* (Semantic Web Journal) identificó \*\*34 propiedades\*\* como el subconjunto realmente relevante del dominio, y las usó para construir la \*\*Ontology of Greek Mythology (OGM)\*\*, publicada en `http://purl.org/umu/ogm`. Merece la pena revisar ese subconjunto antes de decidir tus predicados: es un filtro ya validado.

\- \*\*Licencia:\*\* CC0. Sin restricciones.

\- \*\*Acceso:\*\* Wikidata Query Service (SPARQL), `https://query.wikidata.org`. Formatos de salida CSV/JSON.

\- \*\*Qué aporta bien:\*\* etiquetas multilingües (\*\*incluido español\*\* — resuelve tu columna `nombre\_es`), enlaces a Wikipedia, imágenes de Commons, alineación con Pleiades / Digital LIMC (propiedad \*\*P13094\*\*) / Trismegistos, coordenadas P625 para lugares.

\- \*\*Qué aporta mal:\*\* el propio paper citado documenta que Wikidata tiene numerosas inconsistencias y afirmaciones incompletas sobre mitología griega, y \*\*carece casi por completo de la referencia a la fuente clásica\*\* que fundamenta cada afirmación. Es decir: buena para etiquetas y enlaces, mala como autoridad sobre el contenido del mito.

\- \*\*Regla:\*\* Wikidata \*\*enriquece\*\*, MANTO \*\*decide\*\*. Si discrepan en un hecho mitológico, gana MANTO.

\- Consultas de arranque: filtra por `wdt:P31/wdt:P279\* wd:Q22988604`, y trae `?item ?itemLabel ?greekLabel ?esLabel ?pleiades ?limc ?coord`.



\#### 2.9 Smith, \*Dictionary of Greek and Roman Biography and Mythology\*



\- \*\*Qué es:\*\* diccionario biográfico de la Antigüedad clásica en 3 volúmenes, >3.700 páginas, editado por William Smith (1844–1849). Muchas de las entradas mitológicas las escribió Leonhard Schmitz. \*\*Sigue siendo el diccionario prosopográfico clásico más completo y de dominio público.\*\*

\- \*\*Por qué te sirve muchísimo:\*\* es exactamente el género que necesitas para poblar descripciones — una entrada por personaje, con genealogía y \*\*citas a las fuentes antiguas\*\*. Y resuelve homónimos numerándolos (`smith:herodotus-1`).

\- \*\*Licencia:\*\* obra en dominio público. \*\*Cuidado:\*\* la edición digital de Perseus se distribuye bajo \*\*CC BY-SA\*\*. Si incorporas su XML tal cual, la cláusula \*ShareAlike\* puede contaminar tu base. Si eso te importa, usa los escaneos/OCR de Internet Archive (dominio público puro) o trata las entradas de Perseus como texto de consulta, no como campo almacenado.

\- \*\*Acceso:\*\*

&#x20; - Perseus, edición TEI-XML de los 3 volúmenes en un solo fichero: `https://www.perseus.tufts.edu/hopper/text?doc=Perseus:text:1999.04.0104`

&#x20; - XML descargable por entrada (enlace \*XML\* al pie de cada entrada) o completo desde GitHub: `https://github.com/PerseusDL/canonical-pdlrefwk`

&#x20; - URIs estables de entidad: `http://data.perseus.org/people/smith:{nombre}-{n}` → \*\*úsalos como identificador externo más en tu tabla de IDs\*\*

&#x20; - Escaneos en dominio público: Internet Archive, ítems `dictionarygreek09smitgoog`, `in.ernet.dli.2015.275010`, `dli.ernet.625`, `dli.ernet.626`

&#x20; - También en Wikisource

\- \*\*Compañeros del mismo Smith, igualmente útiles:\*\* \*Dictionary of Greek and Roman Geography\* (para lugares) y \*Dictionary of Greek and Roman Antiquities\* (en `canonical-pdlrefwk` como `viaf88890045.001.xml`).

\- \*\*Caveat:\*\* erudición de 1849. Correcta en datos primarios y citas; anticuada en interpretación. Guarda `fuente\_dataset` para poder revisar.



\#### 2.10 Mitógrafos antiguos — los manuales que ya son bases de datos



Estas dos obras son, literalmente, catálogos antiguos de mito. Son las mejores fuentes para poblar eventos, participantes y listas.



\*\*Pseudo-Apolodoro, \*Biblioteca\*\*\*

\- Compendio de mito procedente de la épica antigua y los trágicos, probablemente compilación del s. II d.C. Estructura: Libro 1 (dioses y linaje de Deucalión), Libro 2 (linaje de Ínaco), Libro 3 (linaje de Agénor), Epítome (de Teseo al final de la Guerra de Troya). \*\*La estructura del texto es genealógica: es un árbol, mapea directo a tu esquema.\*\*

\- Traducción de Frazer (Loeb 1921), en dominio público: `https://www.theoi.com/Text/Apollodorus1.html` (y siguientes)

\- Griego + inglés en Perseus (`canonical-greekLit`), con CTS URN

\- Ya procesado en MANTO



\*\*Higino, \*Fabulae\*\*\*

\- Manual latino de mitología, junto a Apolodoro el más completo que sobrevive. Consiste en \*\*narraciones cortas y listas\*\* en secciones discretas, no en narrativa continua: prácticamente un dump de datos. Contiene material de versiones perdidas.

\- Traducción de Mary Grant (1960), hoy en dominio público, con \*\*592 referencias etiquetadas a 236 lugares antiguos\*\*: `https://topostext.org/work/206`

\- CTS URN: `urn:cts:latinLit:phi1263.phi001` · Wikidata `Q3738147`

\- El prefacio es una teogonía en forma de lista pura ("de Caligine, Chaos; de Chaos y Caligine: Nox, Dies, Erebus, Aether") — ideal para test de ingesta.

\- Traducción moderna de referencia si necesitas comparar: Smith \& Trzaskoma, \*Apollodorus' Library and Hyginus' Fabulae\*, Hackett 2007 (incluye 19 tablas genealógicas, 3 mapas, índice de pueblos y lugares, índice de autores citados). \*\*Comercial: no la ingestes, úsala para validar.\*\*



\#### 2.11 Perseus Digital Library / Open Greek and Latin



\- Textos griegos y latinos en TEI-XML con \*\*CTS URN\*\* — el identificador canónico de pasaje que debes usar en tu tabla `pasaje`, porque es el que usa MANTO en su campo `Scaife URL`.

\- Repos: `https://github.com/PerseusDL/canonical-greekLit`, `canonical-latinLit`, `canonical-pdlrefwk`

\- Estructura de fichero: `canonical-NAMESPACE/data/TEXTGROUP/WORK/TEXTGROUP-WORK-VERSION.xml` (ej. `tlg0012/tlg0012.tlg001.perseus-grc2.xml` = Ilíada)

\- Empaquetado alternativo en text-fabric: `https://github.com/pthu/greek\_literature`

\- Licencia: CC BY-SA (Perseus). Atribución obligatoria + mantener el \*availability statement\*.

\- \*\*Advertencia del propio Perseus:\*\* las URLs de GitHub \*\*no\*\* son identificadores estables. Usa CTS URN o las Perseus Stable URIs.



\#### 2.12 ToposText como corpus de personas



Además de lugares, ToposText mantiene un índice de \~21.000 nombres propios con las fuentes antiguas que los mencionan (`https://topostext.org/the-people`). Útil como red de seguridad para detectar personajes que MANTO no cubre todavía.



\#### 2.13 Digital LIMC — iconografía



\- \*\*Qué es:\*\* plataforma digital y grafo de conocimiento del \*Lexicon Iconographicum Mythologiae Classicae\*, fruto de 40+ años de trabajo de especialistas de casi 40 países bajo patrocinio UNESCO. Da acceso a \~50.000 objetos y fotografías antiguas.

\- \*\*Por qué importa:\*\* es \*\*el estándar de desambiguación de figuras mitológicas\*\* y un hub de interoperabilidad. Tiene propiedad propia en Wikidata (\*\*P13094\*\*) y ya hay >1.650 figuras, yacimientos, lugares e instituciones interconectados.

\- \*\*Acceso:\*\* `https://weblimc.org/` · dataset abierto en la DaSCH Service Platform (Swiss National Data and Service Center for the Humanities), proyecto `080E`. Artículo descriptivo: \*Journal of Open Humanities Data\*, `10.5334/johd.403`. LIMC-France: bases `LIMC-icon`, `LIMC-biblio`, `LIMC-abrev`.

\- \*\*Uso:\*\* puebla `entidad\_identificador` con el LIMC headword (MANTO ya lo trae) y usa LIMC como árbitro cuando dos fuentes discrepen sobre si dos nombres son la misma figura.



\#### 2.14 Theoi Project



\- Enciclopedia de mito griego, \~1.500 páginas y \~1.200 imágenes, creada por Aaron Atsma. Perfiles por deidad/criatura con resumen enciclopédico + \*\*citas extensas de fuentes clásicas\*\*. Incluye el árbol genealógico completo del panteón en 8 láminas indexadas más una tabla específica de la \*Teogonía\* de Hesíodo, un bestiario, y una biblioteca de textos clásicos con poetas menores difíciles de encontrar en otro sitio.

\- URLs: `https://www.theoi.com/` · árbol: `https://www.theoi.com/Tree.html` · dioses: `.../greek-mythology/greek-gods.html`

\- \*\*Convención de nombres:\*\* usa transliteración griega en las páginas de biografía (\*Kirke\*, \*Ouranos\*, \*Apollon\*) y formas latinas en índices e introducciones. Tenlo en cuenta al reconciliar: es una fuente frecuente de duplicados.

\- ⚠️ \*\*Licencia: sitio con copyright, sin licencia abierta.\*\* No hagas scraping masivo para poblar la base. Úsalo como referencia de verificación humana. Si necesitas su contenido estructurado, el paper de la OGM documenta un flujo de extracción semántica desde Theoi para anclar afirmaciones en fuentes clásicas — y también documenta que ese flujo \*\*no escala bien automáticamente\*\*.



\#### 2.15 Greek Mythology Link (Carlos Parada)



\- Sitio de Carlos Parada, ex-profesor de Clásicas en la Universidad de Lund, autor de \*Genealogical Guide to Greek Mythology\* (1993, SIMA 107).

\- \*\*Volumen:\*\* el \*Genealogical Guide\* (edición digital revisada) es un diccionario de \*\*más de 6.500 entradas\*\*, probablemente el catálogo más completo del último siglo. Se basa \*\*exclusivamente en fuentes primarias\*\* (autores del 800 a.C. al 600 d.C.) y está completamente referenciado. Incluye una \*\*Referencia Geográfica de más de 1.000 entradas\*\* con la historia mítica de ciudades, lugares y pueblos, incluyendo sucesión de tronos.

\- URLs: `https://www.maicar.com/GML/` · geografía: `https://www.maicar.com/GML/002GR/grAbae.html` (serie alfabética) · guía: `https://www.maicar.com/GML/GGGM.html`

\- ⚠️ Copyright de Maicar Förlag. Igual que Theoi: \*\*verificación, no ingesta\*\*. La versión digital del libro es comercial.

\- \*\*Valor específico:\*\* las listas de sucesión regia por ciudad son justo lo que necesitas para poblar reinados y dinastías, y son difíciles de obtener de otra fuente estructurada.



\#### 2.16 Roscher, \*Ausführliches Lexikon der griechischen und römischen Mythologie\*



\- Léxico monumental de mitología griega y romana (Wilhelm Heinrich Roscher, 1884–1937). \*\*Dominio público.\*\* Más exhaustivo que Smith en figuras oscuras y en variantes locales de culto.

\- Internet Archive, ítems de la serie `ausfhrlicheslexi\*` (ej. `ausfhrlicheslexi11rosc`: vol. 1 Aba–Evan; vol. 1.2 Euxistratos–Hysiris; vol. 2.1 Iache–Kyzikos...)

\- En alemán, OCR de calidad variable. Reserva para los casos donde ninguna otra fuente dice nada.



\#### 2.17 DARE — Digital Atlas of the Roman Empire



\- SIG histórico creado por Johan Åhlfeldt, inspirado en el \*Barrington Atlas\* y construido sobre digitalizaciones de Pleiades y DARMC, con un objetivo de precisión más alto e integración de imagen satélite y mapas topográficos nacionales.

\- \*\*Ubicación actual:\*\* `https://dh.gu.se/dare/` (Centre for Digital Humanities, Universidad de Gotemburgo). La antigua URL de Lund `dare.ht.lu.se` está muerta — no la uses.

\- Teselas bajo licencia CC; API y descarga de datos crudos disponibles.

\- \*\*Uso:\*\* capa base cartográfica si vas a visualizar, y fuente de contraste de coordenadas. Las equivalencias Pleiades↔DARE ya vienen en el `pelagios.ttl` de ToposText.



\#### 2.18 GeoNames y World Historical Gazetteer



\- \*\*GeoNames:\*\* para vincular el lugar antiguo con su localidad moderna. La alineación automática Pleiades↔GeoNames existe como \*\*Pleiades+\*\*, concebida originalmente por Leif Isaksen en el proyecto Google Ancient Places y mantenida por Ryan Baumann. Es \*experimental\*: empareja URIs cuando parece probable que sean el mismo lugar. Trátala como sugerencia con `confianza`, no como hecho.

\- \*\*World Historical Gazetteer\*\* (`https://whgazetteer.org/`): aloja un subconjunto de Pleiades (asentamientos, monumentos, rasgos geográficos físicos) y es el formato en que ToposText publica su gazetteer JSON-LD. Datos publicados por sus creadores bajo CC BY 4.0.



\#### 2.19 Datasets pequeños y prefabricados



Útiles solo para prototipar rápido o para test fixtures. \*\*Calidad muy inferior\*\* a las fuentes de Nivel 0: sin citas, sin desambiguación de homónimos, cobertura de decenas o cientos de figuras frente a miles.



\- `https://github.com/katkaypettitt/greek-gods` — CSV scrapeado de dioses con nombre griego, categoría y glosa

\- `npm: greek-mythology-data` — JSON con nombre, nombre griego, nombre romano, categoría, descripción

\- `https://github.com/newsh/GreekAPI` — API REST JSON

\- `https://github.com/StephenForte/greek-gods-family-tree` — MIT, estructura con `generation` (0=primordial, 1=titán, 2-3=olímpico/menor) y array de `children`

\- Wikipedia como fuente de listas para \*checklist de cobertura\* (no de contenido): `List\_of\_mortals\_in\_Greek\_mythology`, `List\_of\_minor\_Greek\_mythological\_figures`, `Family\_tree\_of\_the\_Greek\_gods`, `List\_of\_kings\_of\_Argos`, `List\_of\_Etruscan\_names\_for\_Greek\_heroes` (esta última útil para la tabla de nombres alternativos: Achle=Aquiles, Hercle=Heracles, Uthste=Odiseo...)

\- \*Greek Mythic Genealogy Project\* (Patrick Mooney): base genealógica no exhaustiva, útil como contraste



\---



\## 3. Tabla resumen de licencias



Rellena `fuente\_dataset.licencia` con esto. Importa para saber qué puedes redistribuir.



| Fuente | Licencia | ¿Ingesta masiva? | Obligación |

|---|---|---|---|

| MANTO | CC-BY 4.0 | ✅ Sí | Atribuir |

| Pleiades | CC-BY 3.0 | ✅ Sí | Atribuir (AWMC + ISAW) |

| Wikidata | CC0 | ✅ Sí | Ninguna |

| ChronOntology (iDAI) | Abierta | ✅ Sí | Atribuir |

| Digital Marmor Parium | Proyecto académico abierto | ✅ Sí | Atribuir (M. Berti, Leipzig) |

| ToposText | Compartición con atribución | ✅ Datos sí | Atribuir; no redistribuir el corpus textual completo |

| Perseus (textos y Smith) | CC BY-SA | ⚠️ Con cuidado | Atribuir + \*\*ShareAlike vírico\*\* + conservar availability statement |

| Smith (escaneo IA) | Dominio público | ✅ Sí | Ninguna |

| Roscher | Dominio público | ✅ Sí | Ninguna |

| Higino (trad. Grant 1960) | Dominio público | ✅ Sí | Ninguna |

| Apolodoro (trad. Frazer 1921) | Dominio público | ✅ Sí | Ninguna |

| Attalus (crónicas) | Traducciones libres online | ✅ Sí | Atribuir |

| Digital LIMC | Dataset abierto vía DaSCH | ✅ Sí | Atribuir |

| DARE | CC (teselas) | ✅ Sí | Atribuir |

| \*\*Theoi\*\* | © sin licencia abierta | ❌ \*\*No\*\* | Solo consulta |

| \*\*Greek Mythology Link\*\* | © Maicar Förlag | ❌ \*\*No\*\* | Solo consulta |

| Smith \& Trzaskoma (Hackett) | Comercial | ❌ \*\*No\*\* | Solo consulta |



\---



\## 4. Esquema SQLite propuesto



Diseño en 5 bloques: \*\*entidades\*\*, \*\*relaciones\*\*, \*\*eventos\*\*, \*\*geografía\*\*, \*\*procedencia\*\*. SQLite con `PRAGMA foreign\_keys = ON`.



```sql

PRAGMA foreign\_keys = ON;

PRAGMA journal\_mode = WAL;



\-- =====================================================================

\-- BLOQUE 0: PROCEDENCIA  (crear primero: todo lo demás la referencia)

\-- =====================================================================



CREATE TABLE fuente\_dataset (

&#x20;   id                INTEGER PRIMARY KEY,

&#x20;   clave             TEXT NOT NULL UNIQUE,   -- 'manto','pleiades','topostext','wikidata','dmp','eusebio','smith'

&#x20;   nombre            TEXT NOT NULL,

&#x20;   version           TEXT,                   -- release o fecha del dump

&#x20;   url               TEXT,

&#x20;   licencia          TEXT NOT NULL,

&#x20;   doi               TEXT,

&#x20;   fecha\_descarga    TEXT NOT NULL,          -- ISO-8601

&#x20;   atribucion\_texto  TEXT NOT NULL,          -- cadena exacta a citar

&#x20;   notas             TEXT

);



\-- Autores y obras antiguas

CREATE TABLE autor\_antiguo (

&#x20;   id              INTEGER PRIMARY KEY,

&#x20;   nombre          TEXT NOT NULL,

&#x20;   nombre\_es       TEXT,

&#x20;   manto\_id        TEXT UNIQUE,

&#x20;   wikidata\_qid    TEXT,

&#x20;   floruit\_min\_ac  INTEGER,                  -- negativo = a.C.

&#x20;   floruit\_max\_ac  INTEGER,

&#x20;   notas           TEXT

);



CREATE TABLE obra (

&#x20;   id                  INTEGER PRIMARY KEY,

&#x20;   autor\_id            INTEGER REFERENCES autor\_antiguo(id),

&#x20;   titulo              TEXT NOT NULL,

&#x20;   titulo\_es           TEXT,

&#x20;   lengua              TEXT CHECK (lengua IN ('grc','lat','otro')),

&#x20;   genero              TEXT,                 -- epica, tragedia, mitografia, periegesis, cronica, lirica

&#x20;   cts\_urn             TEXT UNIQUE,          -- urn:cts:greekLit:tlg0012.tlg001

&#x20;   fecha\_comp\_min\_ac   INTEGER,

&#x20;   fecha\_comp\_max\_ac   INTEGER,

&#x20;   manto\_id            TEXT UNIQUE,

&#x20;   wikidata\_qid        TEXT,

&#x20;   fuente\_dataset\_id   INTEGER NOT NULL REFERENCES fuente\_dataset(id)

);



CREATE TABLE pasaje (

&#x20;   id                  INTEGER PRIMARY KEY,

&#x20;   obra\_id             INTEGER NOT NULL REFERENCES obra(id),

&#x20;   cita                TEXT NOT NULL,        -- '2.5.10', 'Il. 1.1-7'

&#x20;   cts\_urn             TEXT,

&#x20;   scaife\_url          TEXT,

&#x20;   topostext\_url       TEXT,

&#x20;   manto\_id            TEXT UNIQUE,

&#x20;   -- fecha de evento tal como la asigna ToposText a nivel de párrafo

&#x20;   tt\_fecha\_evento\_ac  INTEGER,

&#x20;   tt\_fecha\_precision  TEXT CHECK (tt\_fecha\_precision IN

&#x20;                         ('anio','decada','medio\_siglo','siglo','mitico\_indef','historico\_indef')),

&#x20;   fuente\_dataset\_id   INTEGER NOT NULL REFERENCES fuente\_dataset(id),

&#x20;   UNIQUE (obra\_id, cita)

);

CREATE INDEX ix\_pasaje\_obra ON pasaje(obra\_id);



\-- =====================================================================

\-- BLOQUE 1: ENTIDADES

\-- Modelo unificado (como MANTO) + tablas de detalle especializadas.

\-- Motivo: en mito griego un río ES un dios y una ciudad ES un epónimo.

\-- Separar "persona" de "lugar" desde la raíz rompe esos casos.

\-- =====================================================================



CREATE TABLE tipo\_entidad (

&#x20;   id       INTEGER PRIMARY KEY,

&#x20;   clave    TEXT NOT NULL UNIQUE,  -- dios, titan, primordial, daimon, heroe, mortal,

&#x20;                                   -- monstruo, ninfa, grupo, pueblo, lugar, rio, montana,

&#x20;                                   -- objeto, animal, personificacion, constelacion

&#x20;   nombre\_es TEXT NOT NULL,

&#x20;   es\_lugar  INTEGER NOT NULL DEFAULT 0,

&#x20;   es\_divino INTEGER NOT NULL DEFAULT 0

);



CREATE TABLE entidad (

&#x20;   id                  INTEGER PRIMARY KEY,

&#x20;   nombre              TEXT NOT NULL,        -- forma normalizada de trabajo

&#x20;   nombre\_grc          TEXT,                 -- griego Unicode politónico

&#x20;   nombre\_translit     TEXT,                 -- Kirke, Ouranos

&#x20;   nombre\_latino       TEXT,                 -- Circe, Uranus

&#x20;   nombre\_es           TEXT,                 -- Circe, Urano  <- de Wikidata

&#x20;   tipo\_entidad\_id     INTEGER REFERENCES tipo\_entidad(id),

&#x20;   genero              TEXT CHECK (genero IN ('m','f','otro','desconocido')),

&#x20;   es\_mortal           INTEGER,              -- NULL = indeterminado

&#x20;   generacion          INTEGER,              -- generación mítica relativa (ver 5.3)

&#x20;   descripcion         TEXT,                 -- prosa: Smith / Wikidata / MANTO commentary

&#x20;   -- desambiguación explícita de homónimos

&#x20;   desambiguador       TEXT,                 -- 'hijo de Egipto', 'rey de Argos'

&#x20;   homonimo\_grupo      TEXT,                 -- agrupa entidades que comparten nombre

&#x20;   fuente\_dataset\_id   INTEGER NOT NULL REFERENCES fuente\_dataset(id),

&#x20;   confianza           REAL DEFAULT 1.0,

&#x20;   revisado\_manual     INTEGER NOT NULL DEFAULT 0

);

CREATE INDEX ix\_entidad\_nombre ON entidad(nombre);

CREATE INDEX ix\_entidad\_tipo   ON entidad(tipo\_entidad\_id);

CREATE INDEX ix\_entidad\_homon  ON entidad(homonimo\_grupo);



\-- Nombres alternativos, epítetos, formas locales, equivalencias etruscas

CREATE TABLE entidad\_nombre (

&#x20;   id           INTEGER PRIMARY KEY,

&#x20;   entidad\_id   INTEGER NOT NULL REFERENCES entidad(id) ON DELETE CASCADE,

&#x20;   nombre       TEXT NOT NULL,

&#x20;   tipo         TEXT CHECK (tipo IN ('alternativo','epiteto','translit','latino','etrusco',

&#x20;                                     'moderno','local','patronimico','es')),

&#x20;   lengua\_tag   TEXT,                        -- BCP-47: grc, la, es, etr

&#x20;   pasaje\_id    INTEGER REFERENCES pasaje(id),

&#x20;   UNIQUE (entidad\_id, nombre, tipo)

);

CREATE INDEX ix\_ent\_nombre ON entidad\_nombre(nombre);



\-- ⭐ Reconciliación entre fuentes: SIEMPRE por aquí, nunca por nombre

CREATE TABLE entidad\_identificador (

&#x20;   id           INTEGER PRIMARY KEY,

&#x20;   entidad\_id   INTEGER NOT NULL REFERENCES entidad(id) ON DELETE CASCADE,

&#x20;   namespace    TEXT NOT NULL CHECK (namespace IN

&#x20;                  ('manto','wikidata','pleiades','topostext','trismegistos',

&#x20;                   'limc','digital\_limc','perseus\_smith','dbpedia','geonames','dare')),

&#x20;   valor        TEXT NOT NULL,

&#x20;   uri          TEXT,

&#x20;   confianza    REAL DEFAULT 1.0,            -- <1.0 para alineaciones automáticas (Pleiades+)

&#x20;   UNIQUE (namespace, valor)

);

CREATE INDEX ix\_entid\_ent ON entidad\_identificador(entidad\_id);



\-- Identidades disputadas: "posiblemente el mismo que", "a veces confundido con"

CREATE TABLE entidad\_equivalencia (

&#x20;   id           INTEGER PRIMARY KEY,

&#x20;   entidad\_a\_id INTEGER NOT NULL REFERENCES entidad(id),

&#x20;   entidad\_b\_id INTEGER NOT NULL REFERENCES entidad(id),

&#x20;   tipo         TEXT NOT NULL CHECK (tipo IN

&#x20;                  ('es\_el\_mismo','posiblemente\_el\_mismo','a\_veces\_confundido',

&#x20;                   'forma\_racionalizada','personificacion\_de','identificado\_con')),

&#x20;   pasaje\_id    INTEGER REFERENCES pasaje(id),

&#x20;   nota         TEXT,

&#x20;   CHECK (entidad\_a\_id <> entidad\_b\_id)

);



\-- =====================================================================

\-- BLOQUE 2: RELACIONES  (el corazón del modelo, ex MANTO `Tie`)

\-- =====================================================================



CREATE TABLE predicado (

&#x20;   id           INTEGER PRIMARY KEY,

&#x20;   clave        TEXT NOT NULL UNIQUE,   -- 'kills','father\_of','born\_at','founder\_of'

&#x20;   nombre\_es    TEXT NOT NULL,

&#x20;   categoria    TEXT NOT NULL CHECK (categoria IN

&#x20;                  ('genealogica','conyugal','belica','muerte','nacimiento','geografica',

&#x20;                   'cultual','politica','transformacion','creacion','fundacion',

&#x20;                   'profecia','oficio','competicion','objeto','otra')),

&#x20;   inverso\_id   INTEGER REFERENCES predicado(id),   -- father\_of <-> child\_of

&#x20;   simetrico    INTEGER NOT NULL DEFAULT 0,         -- twin\_of, has\_children\_with

&#x20;   manto\_id     TEXT UNIQUE

);



CREATE TABLE relacion (

&#x20;   id                  INTEGER PRIMARY KEY,

&#x20;   sujeto\_id           INTEGER NOT NULL REFERENCES entidad(id),

&#x20;   predicado\_id        INTEGER NOT NULL REFERENCES predicado(id),

&#x20;   objeto\_id           INTEGER REFERENCES entidad(id),   -- objeto directo

&#x20;   evento\_id           INTEGER REFERENCES evento(id),    -- si la relación pertenece a un evento

&#x20;   -- cronología relativa heredada de MANTO

&#x20;   timemark\_when       TEXT,

&#x20;   periodo\_id          INTEGER REFERENCES periodo(id),

&#x20;   -- flags de fiabilidad (ex MANTO)

&#x20;   dato\_incierto       INTEGER NOT NULL DEFAULT 0,

&#x20;   duda\_expresada      INTEGER NOT NULL DEFAULT 0,

&#x20;   alternativas\_dadas  INTEGER NOT NULL DEFAULT 0,

&#x20;   dato\_implicito      INTEGER NOT NULL DEFAULT 0,

&#x20;   comentario          TEXT,

&#x20;   manto\_id            TEXT UNIQUE,

&#x20;   fuente\_dataset\_id   INTEGER NOT NULL REFERENCES fuente\_dataset(id)

);

CREATE INDEX ix\_rel\_sujeto ON relacion(sujeto\_id);

CREATE INDEX ix\_rel\_objeto ON relacion(objeto\_id);

CREATE INDEX ix\_rel\_pred   ON relacion(predicado\_id);

CREATE INDEX ix\_rel\_evento ON relacion(evento\_id);



\-- ⭐ Los \~25 slots opcionales de MANTO, normalizados en vez de 25 columnas NULL

CREATE TABLE relacion\_rol (

&#x20;   id           INTEGER PRIMARY KEY,

&#x20;   relacion\_id  INTEGER NOT NULL REFERENCES relacion(id) ON DELETE CASCADE,

&#x20;   rol          TEXT NOT NULL CHECK (rol IN

&#x20;                  ('en','cerca\_de','desde','hacia','via','con\_intencion\_de\_ir\_a','usando',

&#x20;                   'de','para','en\_direccion\_a','contra','acerca\_de','con\_ayuda\_de',

&#x20;                   'por\_orden\_de','a\_instigacion\_de','con\_participacion\_de',

&#x20;                   'segun\_profecia\_de','segun\_profecia\_sobre','para\_vengar','para\_ayudar',

&#x20;                   'para\_obtener','para\_proteger','para\_honrar','para\_frustrar',

&#x20;                   'para\_castigar','y\_conciben','objeto\_indirecto')),

&#x20;   entidad\_id   INTEGER NOT NULL REFERENCES entidad(id),

&#x20;   UNIQUE (relacion\_id, rol, entidad\_id)

);

CREATE INDEX ix\_relrol\_rel ON relacion\_rol(relacion\_id);

CREATE INDEX ix\_relrol\_ent ON relacion\_rol(entidad\_id);



\-- Cada relación puede estar atestiguada por N pasajes / artefactos

CREATE TABLE relacion\_fuente (

&#x20;   id             INTEGER PRIMARY KEY,

&#x20;   relacion\_id    INTEGER NOT NULL REFERENCES relacion(id) ON DELETE CASCADE,

&#x20;   pasaje\_id      INTEGER REFERENCES pasaje(id),

&#x20;   artefacto\_id   INTEGER REFERENCES artefacto(id),

&#x20;   inscripcion\_id INTEGER REFERENCES inscripcion(id),

&#x20;   es\_indirecta   INTEGER NOT NULL DEFAULT 0,

&#x20;   CHECK (pasaje\_id IS NOT NULL OR artefacto\_id IS NOT NULL OR inscripcion\_id IS NOT NULL)

);

CREATE INDEX ix\_relfte\_rel ON relacion\_fuente(relacion\_id);



\-- ⭐ Contradicciones explícitas entre versiones del mito

CREATE TABLE contradiccion (

&#x20;   id             INTEGER PRIMARY KEY,

&#x20;   relacion\_a\_id  INTEGER NOT NULL REFERENCES relacion(id),

&#x20;   relacion\_b\_id  INTEGER NOT NULL REFERENCES relacion(id),

&#x20;   tipo           TEXT CHECK (tipo IN ('genealogia','autoria\_muerte','ubicacion','fecha','otra')),

&#x20;   descripcion    TEXT,

&#x20;   resuelta       INTEGER NOT NULL DEFAULT 0,

&#x20;   version\_preferida\_id INTEGER REFERENCES relacion(id),

&#x20;   criterio       TEXT   -- 'fuente mas antigua', 'consenso mayoritario', 'Hesiodo'

);



\-- =====================================================================

\-- BLOQUE 3: EVENTOS, GUERRAS, COMBATES

\-- =====================================================================



CREATE TABLE ciclo\_mitico (

&#x20;   id         INTEGER PRIMARY KEY,

&#x20;   clave      TEXT NOT NULL UNIQUE,

&#x20;   nombre\_es  TEXT NOT NULL,

&#x20;   orden      INTEGER,        -- secuencia canónica aproximada

&#x20;   descripcion TEXT

);

\-- Semilla: cosmogonia, titanomaquia, gigantomaquia, ciclo\_argivo, ciclo\_cretense,

\-- heracleia, argonautica, ciclo\_tebano, teseida, caceria\_calidonia,

\-- ciclo\_troyano, nostoi, orestiada, retorno\_heraclidas



CREATE TABLE periodo (

&#x20;   id                INTEGER PRIMARY KEY,

&#x20;   clave             TEXT NOT NULL UNIQUE,   -- 'LH\_IIIB', 'LH\_IIIC\_early'

&#x20;   nombre            TEXT NOT NULL,

&#x20;   anio\_inicio\_ac    INTEGER,

&#x20;   anio\_fin\_ac       INTEGER,

&#x20;   chronontology\_uri TEXT,                   -- iDAI ChronOntology

&#x20;   manto\_id          TEXT

);



CREATE TABLE evento (

&#x20;   id                INTEGER PRIMARY KEY,

&#x20;   nombre            TEXT NOT NULL,

&#x20;   nombre\_es         TEXT,

&#x20;   tipo              TEXT NOT NULL CHECK (tipo IN

&#x20;                       ('guerra','batalla','duelo','asedio','expedicion','viaje','trabajo',

&#x20;                        'caceria','certamen','juegos','fundacion','nacimiento','muerte',

&#x20;                        'boda','rapto','metamorfosis','juicio','profecia','sacrificio',

&#x20;                        'cataclismo','castigo','apoteosis','descenso\_hades','otro')),

&#x20;   ciclo\_id          INTEGER REFERENCES ciclo\_mitico(id),

&#x20;   lugar\_id          INTEGER REFERENCES entidad(id),   -- entidad de tipo lugar

&#x20;   padre\_evento\_id   INTEGER REFERENCES evento(id),    -- batalla dentro de guerra

&#x20;   descripcion       TEXT,

&#x20;   resultado         TEXT,

&#x20;   -- fecha "preferida" desnormalizada para consulta cómoda

&#x20;   fecha\_ac          INTEGER,

&#x20;   fecha\_min\_ac      INTEGER,

&#x20;   fecha\_max\_ac      INTEGER,

&#x20;   fecha\_metodo      TEXT CHECK (fecha\_metodo IN

&#x20;                       ('cronografo\_antiguo','generacional','arqueologico','moderno','sin\_fecha')),

&#x20;   fecha\_confianza   TEXT CHECK (fecha\_confianza IN ('alta','media','baja','nula')),

&#x20;   generacion        INTEGER,

&#x20;   periodo\_id        INTEGER REFERENCES periodo(id),

&#x20;   fuente\_dataset\_id INTEGER NOT NULL REFERENCES fuente\_dataset(id)

);

CREATE INDEX ix\_evento\_ciclo ON evento(ciclo\_id);

CREATE INDEX ix\_evento\_lugar ON evento(lugar\_id);

CREATE INDEX ix\_evento\_fecha ON evento(fecha\_ac);



\-- ⭐ ⭐ LA TABLA CLAVE PARA TU REQUISITO DE FECHAS

\-- Un evento tiene N dataciones según N autoridades. Ninguna es "la" fecha.

CREATE TABLE evento\_datacion (

&#x20;   id             INTEGER PRIMARY KEY,

&#x20;   evento\_id      INTEGER NOT NULL REFERENCES evento(id) ON DELETE CASCADE,

&#x20;   autoridad      TEXT NOT NULL,   -- 'Eratostenes','Marmol de Paros','Herodoto','Eusebio',

&#x20;                                   -- 'Duris de Samos','Timeo','Eforo','Dicearco','Sosibio',

&#x20;                                   -- 'arqueologia LH IIIB/C','derivado generacional'

&#x20;   sistema        TEXT NOT NULL CHECK (sistema IN

&#x20;                    ('cronografo\_antiguo','generacional','arqueologico','moderno')),

&#x20;   anio\_ac        INTEGER,         -- negativo. -1184 = 1184 a.C.

&#x20;   anio\_min\_ac    INTEGER,

&#x20;   anio\_max\_ac    INTEGER,

&#x20;   precision      TEXT CHECK (precision IN ('anio','lustro','decada','medio\_siglo','siglo','vago')),

&#x20;   es\_preferida   INTEGER NOT NULL DEFAULT 0,

&#x20;   pasaje\_id      INTEGER REFERENCES pasaje(id),

&#x20;   fuente\_dataset\_id INTEGER NOT NULL REFERENCES fuente\_dataset(id),

&#x20;   nota           TEXT

);

CREATE INDEX ix\_evdat\_evento ON evento\_datacion(evento\_id);

\-- una sola preferida por evento

CREATE UNIQUE INDEX ux\_evdat\_pref ON evento\_datacion(evento\_id) WHERE es\_preferida = 1;



CREATE TABLE bando (

&#x20;   id          INTEGER PRIMARY KEY,

&#x20;   evento\_id   INTEGER NOT NULL REFERENCES evento(id) ON DELETE CASCADE,

&#x20;   nombre      TEXT NOT NULL,     -- 'aqueos','troyanos','olimpicos','titanes','siete contra Tebas'

&#x20;   resultado   TEXT CHECK (resultado IN ('victoria','derrota','tablas','desconocido')),

&#x20;   UNIQUE (evento\_id, nombre)

);



CREATE TABLE evento\_participante (

&#x20;   id           INTEGER PRIMARY KEY,

&#x20;   evento\_id    INTEGER NOT NULL REFERENCES evento(id) ON DELETE CASCADE,

&#x20;   entidad\_id   INTEGER NOT NULL REFERENCES entidad(id),

&#x20;   bando\_id     INTEGER REFERENCES bando(id),

&#x20;   rol          TEXT CHECK (rol IN

&#x20;                  ('comandante','combatiente','victima','matador','instigador',

&#x20;                   'aliado\_divino','oponente\_divino','espectador','arbitro',

&#x20;                   'raptado','rescatador','tripulante','cazador','vencedor','vencido')),

&#x20;   resultado    TEXT CHECK (resultado IN ('sobrevive','muere','herido','capturado','desconocido')),

&#x20;   pasaje\_id    INTEGER REFERENCES pasaje(id),

&#x20;   UNIQUE (evento\_id, entidad\_id, rol)

);

CREATE INDEX ix\_evpart\_ent ON evento\_participante(entidad\_id);

CREATE INDEX ix\_evpart\_ev  ON evento\_participante(evento\_id);



\-- Causalidad y secuencia entre eventos

CREATE TABLE evento\_relacion (

&#x20;   id             INTEGER PRIMARY KEY,

&#x20;   evento\_a\_id    INTEGER NOT NULL REFERENCES evento(id),

&#x20;   evento\_b\_id    INTEGER NOT NULL REFERENCES evento(id),

&#x20;   tipo           TEXT NOT NULL CHECK (tipo IN

&#x20;                    ('causa\_de','consecuencia\_de','anterior\_a','simultaneo\_a','parte\_de','venganza\_de')),

&#x20;   CHECK (evento\_a\_id <> evento\_b\_id)

);



CREATE TABLE evento\_fuente (

&#x20;   id           INTEGER PRIMARY KEY,

&#x20;   evento\_id    INTEGER NOT NULL REFERENCES evento(id) ON DELETE CASCADE,

&#x20;   pasaje\_id    INTEGER NOT NULL REFERENCES pasaje(id),

&#x20;   es\_principal INTEGER NOT NULL DEFAULT 0,

&#x20;   UNIQUE (evento\_id, pasaje\_id)

);



\-- =====================================================================

\-- BLOQUE 4: GEOGRAFÍA

\-- =====================================================================



CREATE TABLE lugar\_detalle (

&#x20;   entidad\_id        INTEGER PRIMARY KEY REFERENCES entidad(id) ON DELETE CASCADE,

&#x20;   tipo\_lugar        TEXT,          -- settlement, sanctuary, mountain, river, island,

&#x20;                                    -- spring, tomb, cave, region, oracle, underworld

&#x20;   -- ⭐ COORDENADAS

&#x20;   latitud           REAL,          -- WGS-84 grados decimales con signo

&#x20;   longitud          REAL,

&#x20;   precision\_metros  INTEGER,       -- de Pleiades accuracy\_radius / max\_accuracy\_meters

&#x20;   location\_precision TEXT CHECK (location\_precision IN ('precise','rough')),

&#x20;   bbox\_wkt          TEXT,

&#x20;   geo\_tipo          TEXT NOT NULL CHECK (geo\_tipo IN

&#x20;                       ('real\_preciso',           -- Micenas, Delfos

&#x20;                        'real\_aproximado',        -- Aulide, Colcos

&#x20;                        'identificacion\_tradicional', -- Escila = estrecho de Mesina

&#x20;                        'legendario\_sin\_ubicacion',   -- Hades, Tartaro, Eliseo

&#x20;                        'sin\_datos')),

&#x20;   es\_ficticio       INTEGER NOT NULL DEFAULT 0,

&#x20;   geo\_fuente        TEXT CHECK (geo\_fuente IN

&#x20;                       ('pleiades','topostext','wikidata','geonames','dare','manual')),

&#x20;   -- vinculación con el mundo moderno

&#x20;   nombre\_moderno    TEXT,

&#x20;   pais\_iso2         TEXT,

&#x20;   geonames\_id       TEXT,

&#x20;   -- ventana temporal de atestación (de Pleiades)

&#x20;   anio\_desde\_ac     INTEGER,       -- year\_after\_which

&#x20;   anio\_hasta\_ac     INTEGER,       -- year\_before\_which

&#x20;   altitud\_m         INTEGER,

&#x20;   fuente\_dataset\_id INTEGER NOT NULL REFERENCES fuente\_dataset(id),

&#x20;   CHECK ( (latitud IS NULL AND longitud IS NULL)

&#x20;        OR (latitud BETWEEN -90 AND 90 AND longitud BETWEEN -180 AND 180) ),

&#x20;   CHECK ( geo\_tipo <> 'legendario\_sin\_ubicacion' OR latitud IS NULL )

);

CREATE INDEX ix\_lugar\_coord ON lugar\_detalle(latitud, longitud);

CREATE INDEX ix\_lugar\_tipo  ON lugar\_detalle(tipo\_lugar);



\-- Jerarquía territorial: Micenas -> Argólide -> Peloponeso -> Grecia

CREATE TABLE lugar\_jerarquia (

&#x20;   id            INTEGER PRIMARY KEY,

&#x20;   hijo\_id       INTEGER NOT NULL REFERENCES entidad(id),

&#x20;   padre\_id      INTEGER NOT NULL REFERENCES entidad(id),

&#x20;   tipo          TEXT CHECK (tipo IN ('parte\_de','cerca\_de','en','dentro\_de')),

&#x20;   certeza       TEXT CHECK (certeza IN ('certain','less-certain','uncertain')),

&#x20;   CHECK (hijo\_id <> padre\_id),

&#x20;   UNIQUE (hijo\_id, padre\_id, tipo)

);



\-- Geometrías múltiples cuando un lugar tiene varias localizaciones propuestas

CREATE TABLE lugar\_localizacion (

&#x20;   id                INTEGER PRIMARY KEY,

&#x20;   entidad\_id        INTEGER NOT NULL REFERENCES entidad(id) ON DELETE CASCADE,

&#x20;   titulo            TEXT,

&#x20;   geometria\_wkt     TEXT,

&#x20;   latitud           REAL,

&#x20;   longitud          REAL,

&#x20;   tipo\_localizacion TEXT,     -- representative, associated modern, relocated modern

&#x20;   precision         TEXT,

&#x20;   accuracy\_radius\_m INTEGER,

&#x20;   pleiades\_uri      TEXT,

&#x20;   es\_representativa INTEGER NOT NULL DEFAULT 0

);



\-- =====================================================================

\-- BLOQUE 5: MATERIAL COMPLEMENTARIO

\-- =====================================================================



CREATE TABLE artefacto (

&#x20;   id                INTEGER PRIMARY KEY,

&#x20;   nombre            TEXT,

&#x20;   tipo              TEXT,          -- vaso, escultura, moneda, sarcofago, mosaico

&#x20;   lugar\_creacion\_id INTEGER REFERENCES entidad(id),

&#x20;   lugar\_hallazgo\_id INTEGER REFERENCES entidad(id),

&#x20;   periodo\_id        INTEGER REFERENCES periodo(id),

&#x20;   coleccion         TEXT,

&#x20;   limc\_ref          TEXT,

&#x20;   digital\_limc\_url  TEXT,

&#x20;   bapd\_url          TEXT,

&#x20;   manto\_id          TEXT UNIQUE,

&#x20;   fuente\_dataset\_id INTEGER NOT NULL REFERENCES fuente\_dataset(id)

);



CREATE TABLE inscripcion (

&#x20;   id                INTEGER PRIMARY KEY,

&#x20;   nombre            TEXT,

&#x20;   ig\_ref            TEXT,

&#x20;   seg\_ref           TEXT,

&#x20;   lugar\_hallazgo\_id INTEGER REFERENCES entidad(id),

&#x20;   periodo\_id        INTEGER REFERENCES periodo(id),

&#x20;   trismegistos\_url  TEXT,

&#x20;   manto\_id          TEXT UNIQUE,

&#x20;   fuente\_dataset\_id INTEGER NOT NULL REFERENCES fuente\_dataset(id)

);



CREATE TABLE artefacto\_representa (

&#x20;   id           INTEGER PRIMARY KEY,

&#x20;   artefacto\_id INTEGER NOT NULL REFERENCES artefacto(id) ON DELETE CASCADE,

&#x20;   entidad\_id   INTEGER NOT NULL REFERENCES entidad(id),

&#x20;   es\_reportada INTEGER NOT NULL DEFAULT 0,   -- "se dice que representa"

&#x20;   UNIQUE (artefacto\_id, entidad\_id)

);

```



\### Vistas de conveniencia



```sql

\-- Genealogía plana, con la fuente y el nivel de duda a la vista

CREATE VIEW vw\_genealogia AS

SELECT r.id                AS relacion\_id,

&#x20;      p.clave             AS predicado,

&#x20;      hijo.id             AS hijo\_id,   hijo.nombre AS hijo,

&#x20;      prog.id             AS progenitor\_id, prog.nombre AS progenitor,

&#x20;      r.dato\_incierto, r.alternativas\_dadas,

&#x20;      o.titulo || ' ' || pa.cita AS fuente

FROM relacion r

JOIN predicado p  ON p.id = r.predicado\_id AND p.categoria = 'genealogica'

JOIN entidad prog ON prog.id = r.sujeto\_id

JOIN entidad hijo ON hijo.id = r.objeto\_id

LEFT JOIN relacion\_fuente rf ON rf.relacion\_id = r.id

LEFT JOIN pasaje pa ON pa.id = rf.pasaje\_id

LEFT JOIN obra o    ON o.id = pa.obra\_id;



\-- Enfrentamientos: quién mató a quién, dónde, con qué, en qué evento

CREATE VIEW vw\_muertes AS

SELECT r.id,

&#x20;      matador.nombre AS matador,

&#x20;      victima.nombre AS victima,

&#x20;      lug.nombre     AS lugar,

&#x20;      arma.nombre    AS arma,

&#x20;      e.nombre       AS evento,

&#x20;      e.fecha\_ac

FROM relacion r

JOIN predicado p     ON p.id = r.predicado\_id AND p.clave = 'kills'

JOIN entidad matador ON matador.id = r.sujeto\_id

JOIN entidad victima ON victima.id = r.objeto\_id

LEFT JOIN relacion\_rol rr\_l ON rr\_l.relacion\_id = r.id AND rr\_l.rol = 'en'

LEFT JOIN entidad lug       ON lug.id = rr\_l.entidad\_id

LEFT JOIN relacion\_rol rr\_a ON rr\_a.relacion\_id = r.id AND rr\_a.rol = 'usando'

LEFT JOIN entidad arma      ON arma.id = rr\_a.entidad\_id

LEFT JOIN evento e          ON e.id = r.evento\_id;



\-- Lugares listos para mapa (solo los que tienen coordenadas fiables)

CREATE VIEW vw\_lugares\_mapa AS

SELECT e.id, e.nombre, e.nombre\_es, ld.tipo\_lugar,

&#x20;      ld.latitud, ld.longitud, ld.precision\_metros, ld.geo\_tipo, ld.geo\_fuente

FROM entidad e

JOIN lugar\_detalle ld ON ld.entidad\_id = e.id

WHERE ld.latitud IS NOT NULL

&#x20; AND ld.geo\_tipo IN ('real\_preciso','real\_aproximado','identificacion\_tradicional');



\-- Auditoría: qué falta

CREATE VIEW vw\_huecos AS

SELECT 'lugar\_sin\_coordenadas' AS hueco, COUNT(\*) AS n

&#x20; FROM lugar\_detalle WHERE latitud IS NULL AND geo\_tipo <> 'legendario\_sin\_ubicacion'

UNION ALL SELECT 'evento\_sin\_fecha', COUNT(\*) FROM evento WHERE fecha\_ac IS NULL

UNION ALL SELECT 'evento\_sin\_lugar', COUNT(\*) FROM evento WHERE lugar\_id IS NULL

UNION ALL SELECT 'entidad\_sin\_tipo', COUNT(\*) FROM entidad WHERE tipo\_entidad\_id IS NULL

UNION ALL SELECT 'relacion\_sin\_fuente', COUNT(\*) FROM relacion r

&#x20; WHERE NOT EXISTS (SELECT 1 FROM relacion\_fuente rf WHERE rf.relacion\_id = r.id)

UNION ALL SELECT 'entidad\_sin\_id\_externo', COUNT(\*) FROM entidad e

&#x20; WHERE NOT EXISTS (SELECT 1 FROM entidad\_identificador i WHERE i.entidad\_id = e.id);

```



\---



\## 5. Estrategia de ingesta



\### 5.1 Orden de carga



```

0\. fuente\_dataset            <- una fila por dump descargado, con fecha y licencia

1\. Pleiades                  -> entidad(tipo=lugar) + lugar\_detalle + lugar\_localizacion

&#x20;                               + lugar\_jerarquia (de connections.csv)

&#x20;                               + entidad\_nombre (de names.csv)

&#x20;                               + entidad\_identificador(namespace='pleiades')

2\. ChronOntology             -> periodo

3\. MANTO Entity              -> entidad (match contra Pleiades por su campo `Pleiades`;

&#x20;                               los que no matcheen, se insertan nuevos)

&#x20;                               + entidad\_identificador (manto, wikidata, topostext,

&#x20;                                 trismegistos, limc)  <- el oro de MANTO

&#x20;                               + entidad\_equivalencia (de "possibly the same as", etc.)

4\. MANTO Author/Text/Passage -> autor\_antiguo, obra, pasaje

5\. MANTO Interaction         -> predicado (165 filas; asigna categoria a mano, es 1 tarde)

6\. MANTO Tie                 -> relacion + relacion\_rol + relacion\_fuente

7\. MANTO Artifact/Inscription-> artefacto, inscripcion, artefacto\_representa

8\. ToposText geojson+jsonld  -> completa coordenadas donde Pleiades no llega;

&#x20;                               pasaje.tt\_fecha\_evento\_ac

9\. Wikidata SPARQL           -> entidad.nombre\_es, descripcion, coordenadas de respaldo

10\. Digital Marmor Parium    -> evento + evento\_datacion (autoridad='Marmol de Paros')

11\. Eusebio / Attalus        -> evento\_datacion + reinados

12\. Tabla §2.6               -> evento\_datacion para el ciclo troyano

13\. Derivación generacional  -> evento.fecha\_\* para lo que quede sin fechar (§5.3)

14\. Smith / Roscher          -> entidad.descripcion donde siga vacía

15\. QA                       -> vw\_huecos + checks de §6

```



\*\*Idempotencia:\*\* cada carga debe ser re-ejecutable. Usa `INSERT ... ON CONFLICT DO UPDATE` sobre las claves `UNIQUE` de identificador externo (`entidad\_identificador(namespace, valor)`, `obra(cts\_urn)`, `relacion(manto\_id)`). Nunca `DELETE FROM` + recarga completa: perderías las correcciones manuales de `revisado\_manual`.



\*\*Reconciliación entre fuentes — algoritmo:\*\*

1\. `manto\_id` exacto → misma entidad

2\. `wikidata\_qid` exacto → misma entidad

3\. `pleiades\_id` exacto → mismo lugar

4\. Coincidencia de nombre normalizado \*\*+\*\* tipo de entidad \*\*+\*\* al menos una relación genealógica compartida → candidato, `confianza = 0.7`, a tabla de revisión

5\. Solo coincidencia de nombre → \*\*NO fusionar.\*\* Insertar como entidad separada con el mismo `homonimo\_grupo` y dejar que un humano decida.



\### 5.2 Cómo derivar eventos desde MANTO



MANTO no tiene tabla `Evento`. Tienes tres caminos, úsalos combinados:



1\. \*\*Agrupación por `Tie` co-localizados.\*\* Todas las relaciones con `predicado ∈ {kills, wounded\_by, competes\_in, conquered\_by}` que comparten el mismo valor en el rol `en` (`in/on/at`) y el mismo `periodo` son candidatas al mismo evento. Ej.: todas las muertes localizadas en Troya con predicado `kills` → agrúpalas bajo el evento "Guerra de Troya" y crea sub-eventos (`padre\_evento\_id`) por duelo.

2\. \*\*Semilla manual de eventos mayores.\*\* Son \~120–200 eventos los que de verdad importan. Créalos a mano (con ciclo, lugar, tipo) y luego engancha las relaciones por `relacion.evento\_id`. Es más rápido y da mucha mejor calidad que cualquier heurística. Lista mínima: Titanomaquia, Gigantomaquia, Diluvio de Deucalión, los 12 Trabajos de Heracles (12 eventos), Argonáutica (+ escalas como eventos hijos), Cacería de Calidón, Siete contra Tebas, Epígonos, Juicio de Paris, Rapto de Helena, Sacrificio de Ifigenia, los duelos de la Ilíada (Aquiles–Héctor, Áyax–Héctor, Menelao–Paris, Diomedes–Eneas...), Caballo de Troya, Saqueo de Ilión, cada Retorno (Nostoi) por héroe, Orestíada, Retorno de los Heráclidas, Minotauro, Perseo–Medusa, Belerofonte–Quimera.

3\. \*\*Los `Passage` de Apolodoro e Higino como delimitadores.\*\* La estructura de esas obras ya segmenta el mito en episodios. Un `Fabula` de Higino ≈ un evento. Úsalo como generador de candidatos.



\### 5.3 Cómo poner fecha a lo que no tiene fecha: derivación generacional



Para los eventos que ninguna fuente antigua fecha, deriva la fecha por desplazamiento de generaciones respecto al ancla troyana. Es el mismo método que usaron los cronógrafos antiguos, así que es defendible.



```

ANCLA:          Caída de Troya = -1184  (Eratóstenes)

GENERACIÓN:     33 años  (Hecateo vía Heródoto: 3 generaciones por siglo)

&#x20;               usa 40 años si estás encadenando reinados (convención regia antigua)



fecha\_ac = -1184 - (generacion\_troya - generacion\_evento) \* 33

```



Escala generacional de referencia (`entidad.generacion` / `evento.generacion`), con gen 0 = Heracles, que es el ancestro de las casas reales relevantes y el nodo que usaban los antiguos:



| Gen | Figuras / eventos | Fecha derivada aprox. |

|---|---|---|

| −6 y anteriores | Cosmogonía, Titanomaquia, Gigantomaquia | sin fecha real, `metodo='sin\_fecha'` |

| −5 | Ínaco, Cécrope, Deucalión, Diluvio | −1580 a −1520 (Mármol de Paros: datos directos) |

| −4 | Dánao, Europa, Cadmo, Ío | \~−1400 |

| −3 | Perseo, Minos, Belerofonte | \~−1330 |

| −2 | Pélope, Edipo, Layo | \~−1290 |

| −1 | Anfitrión, Atreo, Tiestes | \~−1255 |

| \*\*0\*\* | \*\*Heracles, Jasón, Teseo, Argonáutica, Siete contra Tebas, Cacería de Calidón\*\* | \*\*\~−1250\*\* |

| +1 | Agamenón, Menelao, Áyax, Odiseo, Epígonos | \~−1215 |

| +2 | \*\*Guerra de Troya (fin de gen 2), Aquiles, Héctor, Neoptólemo\*\* | \*\*−1184\*\* |

| +3 | Orestes, Telémaco, Nostoi, Orestíada | \~−1160 |

| +4 | Tisámeno, \*\*Retorno de los Heráclidas\*\* | \~−1120 |



Notas de rigor:

\- La caída de Troya cae \*\*al final\*\* de la generación 2, no en su centro. Los cronógrafos antiguos corregían por media generación. Documéntalo en `evento\_datacion.nota`.

\- El Retorno de los Heráclidas se sitúa dos generaciones después de Troya (80 años en el esquema griego estándar), lo que casa bien con el LH IIIC.

\- \*\*Marca siempre `sistema = 'generacional'` y `fecha\_confianza = 'baja'`\*\* para estas derivaciones. No las mezcles con las de cronógrafo antiguo sin distinguirlas.

\- Para la cosmogonía y las teomaquias, `fecha\_ac = NULL` y `fecha\_metodo = 'sin\_fecha'`. No inventes un número para "antes del tiempo".



\### 5.4 Cómo garantizar coordenadas para cada ubicación



Cadena de prioridad, primera que acierte gana, y \*\*registra siempre `geo\_fuente`\*\*:



```

1\. Pleiades places.csv → representative\_latitude/longitude

&#x20;  + places\_accuracy.csv → max\_accuracy\_meters

&#x20;  + location\_precision ('precise' o 'rough')

2\. Si falta o es 'rough': ToposText geojson (mejor granularidad en Grecia:

&#x20;  santuarios, tumbas heroicas, fuentes)

3\. Si falta: Wikidata P625 vía el QID que ya traes de MANTO

4\. Si falta: GeoNames vía Pleiades+ (confianza < 1.0, es alineación automática)

5\. Si falta: DARE

6\. Si sigue faltando:

&#x20;  - ¿es un lugar real? -> cola de resolución manual, geo\_tipo='sin\_datos'

&#x20;  - ¿es el Hades/Tártaro/Eliseo/Ogigia-como-utopía?

&#x20;       -> geo\_tipo='legendario\_sin\_ubicacion', latitud=NULL, es\_ficticio=1

&#x20;       (el CHECK del esquema fuerza esto: no se puede poner coordenada)

```



Objetivo realista de cobertura: \*\*>90 % de los lugares reales con coordenadas\*\*, y el resto explícitamente clasificado. Eso es mejor calidad que el 100 % con inventos.



\---



\## 6. Control de calidad



Ejecuta esto al final de cada carga.



```sql

\-- 1. Sin ciclos genealógicos (nadie es su propio antepasado)

WITH RECURSIVE asc\_(raiz, ancestro, prof) AS (

&#x20;   SELECT r.objeto\_id, r.sujeto\_id, 1

&#x20;     FROM relacion r JOIN predicado p ON p.id=r.predicado\_id

&#x20;    WHERE p.clave IN ('father\_of','mother\_of','parents\_of')

&#x20;   UNION ALL

&#x20;   SELECT a.raiz, r.sujeto\_id, a.prof+1

&#x20;     FROM asc\_ a JOIN relacion r ON r.objeto\_id = a.ancestro

&#x20;     JOIN predicado p ON p.id=r.predicado\_id

&#x20;    WHERE p.clave IN ('father\_of','mother\_of','parents\_of') AND a.prof < 40

)

SELECT \* FROM asc\_ WHERE raiz = ancestro;   -- debe devolver 0 filas



\-- 2. Coordenadas dentro del mundo griego conocido (Iberia -> Cáucaso -> India)

SELECT e.nombre, ld.latitud, ld.longitud

&#x20; FROM lugar\_detalle ld JOIN entidad e ON e.id=ld.entidad\_id

&#x20;WHERE ld.latitud IS NOT NULL

&#x20;  AND (ld.latitud NOT BETWEEN 20 AND 60 OR ld.longitud NOT BETWEEN -12 AND 80);



\-- 3. Fechas coherentes: min <= preferida <= max, y todas negativas o justificadas

SELECT \* FROM evento\_datacion

&#x20;WHERE (anio\_min\_ac IS NOT NULL AND anio\_ac IS NOT NULL AND anio\_ac < anio\_min\_ac)

&#x20;   OR (anio\_max\_ac IS NOT NULL AND anio\_ac IS NOT NULL AND anio\_ac > anio\_max\_ac)

&#x20;   OR anio\_ac > 0;



\-- 4. Causalidad temporalmente coherente

SELECT er.\*, a.nombre, a.fecha\_ac, b.nombre, b.fecha\_ac

&#x20; FROM evento\_relacion er

&#x20; JOIN evento a ON a.id=er.evento\_a\_id

&#x20; JOIN evento b ON b.id=er.evento\_b\_id

&#x20;WHERE er.tipo='causa\_de' AND a.fecha\_ac IS NOT NULL AND b.fecha\_ac IS NOT NULL

&#x20;  AND a.fecha\_ac < b.fecha\_ac;   -- a.C.: la causa debe tener año MAYOR en valor absoluto



\-- 5. Participantes vivos: nadie combate en dos eventos separados por >150 años

\-- 6. Todo lugar referenciado en evento.lugar\_id es de tipo lugar

SELECT e.id, e.nombre FROM evento ev

&#x20; JOIN entidad e ON e.id=ev.lugar\_id

&#x20; JOIN tipo\_entidad t ON t.id=e.tipo\_entidad\_id

&#x20;WHERE t.es\_lugar = 0;



\-- 7. Huecos generales

SELECT \* FROM vw\_huecos;

```



Métricas objetivo para llamarla "de calidad":



| Métrica | Objetivo |

|---|---|

| Entidades con ≥1 identificador externo | >95 % |

| Relaciones con ≥1 pasaje fuente | >90 % |

| Lugares reales con coordenadas | >90 % |

| Eventos mayores con ≥1 datación | 100 % |

| Eventos mayores con ≥2 dataciones alternativas | >40 % |

| Contradicciones detectadas y registradas | >200 (si sale 0, el modelo está aplanado — mal) |

| Homónimos con `desambiguador` relleno | 100 % de los grupos con >1 miembro |



\---



\## 7. Errores a evitar



1\. \*\*`padre\_id` y `madre\_id` como columnas de `entidad`.\*\* Fuerza a elegir una versión y descarta el resto del mito. Todo va por `relacion`.

2\. \*\*`JOIN` por nombre.\*\* Fusionará a los tres Yolaos, a las cinco Anaxibias y a Apolodoro-el-mitógrafo con Apolodoro-el-personaje.

3\. \*\*Una sola columna `fecha` en `evento`.\*\* La tienes en el esquema por comodidad, pero es un \*\*derivado\*\* de `evento\_datacion`, nunca el dato primario. Si solo guardas una fecha, estás afirmando algo que las fuentes antiguas no afirman.

4\. \*\*Coordenadas inventadas para lugares míticos.\*\* El `CHECK` del esquema lo impide a propósito. Un `NULL` documentado vale más que un punto falso.

5\. \*\*Confundir el Olimpo-monte (39.71 N, 22.36 E, real, mapeable) con el Olimpo-morada-divina\*\* (concepto, sin coordenadas). Son dos entidades, ligadas por `entidad\_equivalencia`.

6\. \*\*Mezclar formas griegas y latinas en `entidad.nombre`.\*\* Elige una convención (recomiendo latina en `nombre`, por ser la usada en español, y guarda las demás en `entidad\_nombre`). Theoi usa transliteración griega, Wikipedia usa latina: es el vector de duplicados número uno.

7\. \*\*Scrapear Theoi o Greek Mythology Link para poblar la base.\*\* No tienen licencia abierta. Además su contenido ya está en MANTO en forma estructurada y citada.

8\. \*\*Ignorar los flags de incertidumbre de MANTO.\*\* `data\_uncertain`, `doubt\_expressed`, `alternatives\_given`, `data\_implicit` son cuatro columnas que distinguen "Homero dice X" de "quizá se insinúa X". Perderlos degrada la base a nivel wiki.

9\. \*\*`DELETE` + recarga completa.\*\* Destruye el trabajo de revisión manual. Usa upsert.

10\. \*\*Tratar `location\_precision='rough'` como coordenada buena.\*\* Puede ser el centroide de una caja de 100 km.



\---



\## 8. Bibliografía de referencia (para resolver dudas, no para ingesta)



Obras comerciales de consulta, el estándar académico actual. Útiles cuando dos fuentes se contradicen y hay que decidir.



\- \*\*Timothy Gantz, \*Early Greek Myth: A Guide to Literary and Artistic Sources\*\*\* (Johns Hopkins, 1993). La referencia. Rastrea cada variante hasta su fuente. Si hay una sola obra que consultar para resolver una contradicción, es esta.

\- \*\*Pierre Grimal, \*Diccionario de mitología griega y romana\*\*\* (Paidós). En español, con tablas genealógicas. Muy práctico para nombres castellanos.

\- \*\*Smith \& Trzaskoma, \*Apollodorus' Library and Hyginus' Fabulae\*\*\* (Hackett, 2007). 19 tablas genealógicas + índice de pueblos y lugares + índice de autores citados.

\- \*\*LIMC\*\* (10 vols., 1981–2009) + \*\*ThesCRA\*\*. Estándar iconográfico. Colección buscable en HathiTrust.

\- \*\*Brill's New Pauly\*\*. Enciclopedia de referencia moderna.

\- \*\*Barrington Atlas of the Greek and Roman World\*\* (Talbert, 2000). El origen cartográfico de Pleiades y DARE.

\- \*\*Kokkinos, \*Ancient Chronography, Eratosthenes and the Dating of the Fall of Troy\*\*\*. PDF libre. Imprescindible si vas a modelar cronología en serio.

\- \*\*Digital Classicist Wiki\*\* (`https://wiki.digitalclassicist.org/`). Índice de proyectos digitales de clásicas: úsalo para descubrir fuentes nuevas.

\- \*\*AWOL – The Ancient World Online\*\* (`http://ancientworldonline.blogspot.com/`). Publica los nuevos releases de datasets; suscríbete si el proyecto va a vivir mucho tiempo.



\---



\## 9. Cadena de atribución para el README de la base



Texto listo para copiar:



```

Esta base de datos incorpora datos de:



\- MANTO (Mapping Ancient Narratives, Territories, Objects), Greta Hawes,

&#x20; R. Scott Smith et al. CC-BY 4.0. https://www.manto-myth.org

&#x20; DOI: 10.5281/zenodo.19446254

\- Pleiades: A community-built gazetteer and graph of ancient places.

&#x20; Ancient World Mapping Center \& Institute for the Study of the Ancient World.

&#x20; CC-BY 3.0. https://pleiades.stoa.org

\- ToposText, Aikaterini Laskaridis Foundation / Pavla S.A.

&#x20; https://topostext.org

\- Digital Marmor Parium, Monica Berti, Universität Leipzig.

&#x20; https://www.digitalmarmorparium.org

\- Wikidata contributors. CC0. https://www.wikidata.org

\- Perseus Digital Library, Tufts University. CC BY-SA.

&#x20; http://www.perseus.tufts.edu

\- iDAI ChronOntology, Deutsches Archäologisches Institut.

&#x20; https://chronontology.dainst.org

\- Digital LIMC, Universität Basel / DaSCH. https://weblimc.org

\- Eusebius' Chronicle, trads. A. Smith, R. Pearse et al.

&#x20; https://www.attalus.org

```



\---



\## 10. Primeros comandos



```bash

mkdir -p data/{manto,pleiades,topostext,wikidata,chrono} \&\& cd data



\# MANTO: dataset completo

\# (Zenodo record 19446255 — DOI 10.5281/zenodo.19446254)

\# descarga el ZIP desde https://zenodo.org/records/19446255



\# Pleiades: paquete GIS con lat/long ya limpio

curl -L -o pleiades/pleiades\_gis\_data.zip \\

&#x20; https://atlantides.org/downloads/pleiades/gis/pleiades\_gis\_data.zip

unzip -d pleiades/ pleiades/pleiades\_gis\_data.zip



\# ToposText: lugares y gazetteer con citas

curl -L -o topostext/places.geojson \\

&#x20; https://topostext.org/downloads/ToposText\_places\_2025-11-20.geojson

curl -L -o topostext/gazetteer.jsonld \\

&#x20; https://topostext.org/downloads/ToposTextGazetteer.jsonld

curl -L -o topostext/pelagios.ttl \\

&#x20; https://topostext.org/downloads/pelagios.ttl        # equivalencias Pleiades/DARE

curl -L -o topostext/works.ttl \\

&#x20; https://topostext.org/downloads/ToposTextWorkTurtles.ttl

```



Recordatorio para el parseo de Pleiades en Python: `encoding='utf-8-sig'` (los CSV llevan BOM), y los campos WKT pueden contener comas dentro de comillas.



Primer entregable sugerido: cargar solo Pleiades + MANTO `Entity` + MANTO `Tie`, con el esquema completo pero sin eventos. Con eso ya tienes \~9.000 personajes, \~32.000 relaciones citadas y miles de lugares geolocalizados. Los eventos y las fechas son la segunda iteración, y son donde hará falta el trabajo manual de las §5.2 y §5.3.

