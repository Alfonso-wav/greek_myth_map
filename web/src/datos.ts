import type { Afirmacion, Agente, Autoridad, Datos, Lugar, Meta } from './types'

/** Indices derivados una sola vez. Sin esto, cada movimiento del slider
 *  recorreria las 9.937 afirmaciones. */
export interface Indice {
  meta: Meta
  autoridades: Autoridad[]
  lugares: Map<number, Lugar>
  agentes: Map<number, Agente>
  /** generacion -> afirmaciones de esa generacion */
  porGeneracion: Map<number, Afirmacion[]>
  /** afirmaciones cuyo agente es divino: no pertenecen a una generacion */
  divinas: Afirmacion[]
  /** generacion -> afirmaciones NO divinas, para el histograma.
   *  Las divinas quedan fuera a proposito: su `g` es teogonica (-9..-5) y el mapa
   *  las trata como atemporales, asi que contarlas por generacion hacia que el
   *  histograma y el mapa dijeran cosas distintas. */
  densidad: Map<number, number>
  /** total de afirmaciones de divinidades: no pertenecen a ninguna generacion */
  nDivinas: number
  porLugar: Map<number, Afirmacion[]>
  contradiccionesPorGen: Map<number, Datos['contradicciones']>
  contradiccionesSinGen: Datos['contradicciones']
  totalAfirmaciones: number
}

export function indexar(d: Datos): Indice {
  const lugares = new Map(d.lugares.map((l) => [l.id, l]))
  const agentes = new Map(d.agentes.map((a) => [a.id, a]))
  const porGeneracion = new Map<number, Afirmacion[]>()
  const porLugar = new Map<number, Afirmacion[]>()
  const densidad = new Map<number, number>()
  const divinas: Afirmacion[] = []

  for (const a of d.afirmaciones) {
    const ag = agentes.get(a.s)
    if (ag?.div) divinas.push(a)
    else {
      const lista = porGeneracion.get(a.g)
      if (lista) lista.push(a)
      else porGeneracion.set(a.g, [a])
      densidad.set(a.g, (densidad.get(a.g) ?? 0) + 1)
    }
    const enLugar = porLugar.get(a.l)
    if (enLugar) enLugar.push(a)
    else porLugar.set(a.l, [a])
  }

  const contradiccionesPorGen = new Map<number, Datos['contradicciones']>()
  const contradiccionesSinGen: Datos['contradicciones'] = []
  for (const c of d.contradicciones) {
    if (c.g == null) contradiccionesSinGen.push(c)
    else {
      const lista = contradiccionesPorGen.get(c.g)
      if (lista) lista.push(c)
      else contradiccionesPorGen.set(c.g, [c])
    }
  }

  return {
    meta: d.meta,
    // preferida primero, luego de la fecha mas antigua a la mas reciente
    autoridades: [...d.autoridades].sort(
      (a, b) => Number(b.preferida) - Number(a.preferida) || a.troya - b.troya,
    ),
    lugares,
    agentes,
    porGeneracion,
    divinas,
    densidad,
    nDivinas: divinas.length,
    porLugar,
    contradiccionesPorGen,
    contradiccionesSinGen,
    totalAfirmaciones: d.afirmaciones.length,
  }
}

export async function cargar(): Promise<Datos> {
  const r = await fetch(`${import.meta.env.BASE_URL}data/greek.json`)
  if (!r.ok) {
    throw new Error(
      `no se pudo cargar data/greek.json (HTTP ${r.status}). ` +
        'Genera el fichero con `uv run greek export-web` en la raiz del proyecto.',
    )
  }
  return (await r.json()) as Datos
}

/** Anio a.C. de una generacion segun la autoridad elegida. null = teogonia. */
export function anioDe(a: Autoridad, gen: number, sinFecha: number): number | null {
  if (gen <= sinFecha) return null
  const v = a.anios[String(gen)]
  return v ?? null
}

export function formatearAnio(anio: number | null): string {
  if (anio == null) return 'sin fecha'
  return `${Math.abs(anio)} a.C.`
}

/** Etiqueta de la generacion: numero, o su nombre si es un hito reconocible. */
export function etiquetaGeneracion(gen: number, sinFecha: number): string {
  if (gen <= sinFecha) return 'teogonia'
  const hitos: Record<number, string> = {
    [-5]: 'Diluvio de Deucalion',
    [-4]: 'Cadmo · Danao',
    [-3]: 'Perseo',
    [-1]: 'Teseo',
    0: 'Heracles · Argonautas',
    1: 'Epigonos · rapto de Helena',
    2: 'Guerra de Troya',
    3: 'los retornos',
    4: 'retorno de los Heraclidas',
  }
  return hitos[gen] ?? `generacion ${gen > 0 ? '+' : ''}${gen}`
}

/** Paso de la rampa ordinal sepia (1-4) para un recuento de afirmaciones.
 *  Cuatro y no cinco: el quinto paso era el mas claro y no despegaba de la
 *  superficie (1,30:1 frente al suelo de 2:1), asi que esos marcadores
 *  desaparecian contra el pergamino. */
export function pasoEscala(n: number): 1 | 2 | 3 | 4 {
  if (n >= 20) return 4
  if (n >= 7) return 3
  if (n >= 3) return 2
  return 1
}

/** Cortes de la escala, para rotular la leyenda sin repetirlos a mano. */
export const CORTES = ['1–2', '3–6', '7–19', '20+'] as const

export function radio(n: number): number {
  // area ~ recuento, con suelo de 8px de diametro (minimo de la guia de marcas)
  return Math.min(17, 4 + Math.sqrt(n) * 1.9)
}

export interface Visible {
  lugares: { lugar: Lugar; n: number; divino: boolean }[]
  afirmaciones: Afirmacion[]
  /** cuántas de las visibles son de divinidades. Se cuenta DESPUÉS de filtrar:
   *  usar el total del corpus prometía 2.026 con un filtro que dejaba 138. */
  nDivinas: number
  /** ids de lugar con algo visible, para que las disputas respeten los filtros */
  ids: Set<number>
}

export interface Filtros {
  gen: number
  acumulado: boolean
  conDivinidades: boolean
  /** papeles seleccionados; vacío = sin filtrar (no "ninguno") */
  papeles: Set<string>
  /** categorías de hecho seleccionadas; vacío = sin filtrar */
  categorias: Set<string>
  /** texto libre; casa contra figura O lugar */
  busqueda: string
}

/** Normaliza igual que `clave_busqueda` en export.py: minúsculas y sin
 *  diacríticos. El pajar ya trae todas las variantes atestiguadas y su
 *  transliteración, así que basta con subcadena — no hay que reimplementar aquí
 *  los pliegues griego→latín de normalize.py. */
export function normalizarBusqueda(s: string): string {
  return s
    .toLowerCase()
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .trim()
}

/** Lugares y afirmaciones activos con los filtros actuales. */
export function visibles(idx: Indice, f: Filtros): Visible {
  const { gen, acumulado, conDivinidades, papeles, categorias } = f
  const busca = normalizarBusqueda(f.busqueda)
  let afirmaciones: Afirmacion[] = []
  for (const [g, lista] of idx.porGeneracion) {
    if (acumulado ? g <= gen : g === gen) afirmaciones.push(...lista)
  }
  if (conDivinidades) afirmaciones.push(...idx.divinas)

  // Dos ejes independientes, y el conjunto vacío significa "sin filtrar", no
  // "ninguno": un chip apagado no debe vaciar el mapa.
  if (papeles.size) {
    afirmaciones = afirmaciones.filter((a) => {
      const ps = idx.agentes.get(a.s)?.p
      return ps ? ps.some((p) => papeles.has(p)) : false
    })
  }
  if (categorias.size) {
    afirmaciones = afirmaciones.filter((a) => categorias.has(a.cat ?? 'otra'))
  }
  // Casa contra la figura O contra el lugar: buscar "Ítaca" tiene que dejar el
  // lugar en el mapa aunque ningun agente se llame asi, y buscar "Odiseo" tiene
  // que dejar todos los sitios donde se le atestigua.
  if (busca) {
    afirmaciones = afirmaciones.filter(
      (a) =>
        idx.agentes.get(a.s)?.q.includes(busca) || idx.lugares.get(a.l)?.q.includes(busca),
    )
  }

  const cuenta = new Map<number, number>()
  const soloDivino = new Map<number, boolean>()
  let nDivinas = 0
  for (const a of afirmaciones) {
    cuenta.set(a.l, (cuenta.get(a.l) ?? 0) + 1)
    const ag = idx.agentes.get(a.s)
    if (ag?.div) nDivinas++
    const prev = soloDivino.get(a.l)
    soloDivino.set(a.l, prev === false ? false : Boolean(ag?.div))
  }

  const lugares: Visible['lugares'] = []
  for (const [id, n] of cuenta) {
    const lugar = idx.lugares.get(id)
    if (lugar) lugares.push({ lugar, n, divino: soloDivino.get(id) ?? false })
  }
  // los mas atestiguados se dibujan encima
  lugares.sort((a, b) => a.n - b.n)
  return { lugares, afirmaciones, nDivinas, ids: new Set(cuenta.keys()) }
}
