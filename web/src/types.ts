/** Contrato con `greek export-web` (src/greek/export.py). Claves cortas a proposito. */

/** Una opción de filtro con su recuento real de lo exportado. */
export interface Faceta {
  clave: string
  etiqueta: string
  n: number
}

export interface Meta {
  generado: string
  gen_min: number
  gen_max: number
  gen_troya: number
  /** generaciones <= este valor son teogonia: no se datan, a proposito */
  gen_sin_fecha: number
  anios_por_generacion: number
  atribucion: string[]
  /** quién protagoniza: dios, heroe, gobernante, monstruo... (multi-etiqueta) */
  papeles: Faceta[]
  /** de qué trata el hecho: guerra, muerte, culto... (predicado.categoria) */
  categorias: Faceta[]
}

export interface Autoridad {
  nombre: string
  sistema: string
  /** el anio que esa autoridad da a la caida de Troya */
  troya: number
  preferida: boolean
  /** generacion (como string) -> anio a.C. negativo */
  anios: Record<string, number>
}

/** Enlace externo ya montado en el export (plantillas comprobadas con HTTP 200). */
export interface Enlace {
  /** etiqueta visible: Pleiades, ToposText, Wikidata */
  k: string
  u: string
}

/** Cita textual; `u` solo si el pasaje es resoluble en Perseus/Scaife. */
export interface Cita {
  t: string
  u?: string
}

export interface Lugar {
  id: number
  n: string
  t: string | null
  lat: number
  lng: number
  /** 'precise' | 'rough' | ... — 'rough' puede ser el centroide de 100 km */
  prec: string | null
  pm: number | null
  /** 1 = legendario sin ubicacion real (Hades) */
  fic: number
  mod: string | null
  pais: string | null
  gt: string | null
  /** generaciones en las que pasa algo aqui */
  gens: number[]
  /** pajar de busqueda: nombre, moderno y variantes, transliterado y crudo */
  q: string
  enl: Enlace[]
}

export interface Agente {
  id: number
  n: string
  grc: string | null
  g: number
  gmin: number | null
  gmax: number | null
  conf: 'alta' | 'media' | 'baja'
  m: string
  /** 1 = divinidad: no transmite cronologia, existe en todas las generaciones */
  div: number
  t: string | null
  d: string | null
  /** papeles derivados; multi-etiqueta, puede venir vacío */
  p: string[]
  /** pajar de busqueda: nombre, griego y variantes, transliterado y crudo */
  q: string
  enl: Enlace[]
}

export interface Afirmacion {
  /** id de lugar */
  l: number
  /** id de agente */
  s: number
  g: number
  pk: string
  pe: string
  cat: string | null
  rol: string | null
  obj: string | null
  inc: number
  duda: number
  impl: number
  alt: number
  ci: Cita[]
  au: string[]
  nci: number
}

export interface Contradiccion {
  id: number
  sobre: string
  pe: string
  g: number | null
  d: string
  /** los dos lugares en disputa */
  l: [number, number]
}

export interface Datos {
  meta: Meta
  autoridades: Autoridad[]
  lugares: Lugar[]
  agentes: Agente[]
  afirmaciones: Afirmacion[]
  contradicciones: Contradiccion[]
}

/* ---------------------------------------------- red.json (vista de relaciones) */

export interface PredicadoRed {
  k: string
  /** etiqueta castellana, verbo en tercera persona: «es hijo de», «mata a» */
  e: string
  cat: string
}

export interface NodoRed {
  id: number
  n: string
  /** agente | colectivo | objeto | constelacion | evento_mitico */
  t: string
  /** número de relaciones agregadas: escala el nodo */
  gr: number
  grc?: string
  d?: string
  p?: string[]
  g?: number
  div?: number
  enl?: Enlace[]
  q: string
}

/** Una arista por (sujeto, predicado, objeto, rol): las N filas de `relacion` que
 *  afirman lo mismo desde fuentes distintas llegan agregadas. */
export interface AristaRed {
  s: number
  o: number
  /** índice en `predicados` */
  p: number
  /** cuántas fuentes lo afirman */
  n: number
  rol?: string
  /** flags agregados con AND: solo si TODAS las fuentes lo marcan */
  inc?: 1
  duda?: 1
  impl?: 1
  alt?: 1
  /** alguna de sus relaciones está en una `contradiccion` */
  dis?: 1
  /** índices en `citas` */
  ci?: number[]
}

export interface Red {
  predicados: PredicadoRed[]
  citas: Cita[]
  nodos: NodoRed[]
  aristas: AristaRed[]
}
