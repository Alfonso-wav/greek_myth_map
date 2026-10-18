import type { AristaRed, NodoRed, Red } from './types'
import { normalizarBusqueda } from './datos'

export interface IndiceRed {
  red: Red
  nodos: Map<number, NodoRed>
  /** id -> aristas en las que participa, como sujeto o como objeto */
  vecinas: Map<number, AristaRed[]>
}

export async function cargarRed(): Promise<IndiceRed> {
  const r = await fetch(`${import.meta.env.BASE_URL}data/red.json`)
  if (!r.ok) {
    throw new Error(
      `El servidor respondió HTTP ${r.status} al pedir data/red.json. En local, ` +
        'genéralo con «uv run greek export-web» desde la raíz del proyecto y recarga.',
    )
  }
  const red = (await r.json()) as Red
  const vecinas = new Map<number, AristaRed[]>()
  const poner = (id: number, a: AristaRed) => {
    const lista = vecinas.get(id)
    if (lista) lista.push(a)
    else vecinas.set(id, [a])
  }
  for (const a of red.aristas) {
    poner(a.s, a)
    poner(a.o, a)
  }
  return { red, nodos: new Map(red.nodos.map((n) => [n.id, n])), vecinas }
}

/** Grupos de la vista, en el orden en que se reparten alrededor de la figura
 *  (en el sentido de las agujas del reloj desde arriba): los progenitores arriba
 *  y la descendencia abajo, como en cualquier árbol genealógico. */
export const GRUPOS = [
  { k: 'padres', et: 'Progenitores' },
  { k: 'conflicto', et: 'Muerte y guerra' },
  { k: 'otras', et: 'Otras relaciones' },
  { k: 'hijos', et: 'Descendencia' },
  { k: 'familia', et: 'Hermanos y linaje' },
  { k: 'pareja', et: 'Parejas y uniones' },
] as const
export type Grupo = (typeof GRUPOS)[number]['k']

/** Si una figura cae en varios grupos (Hera es hermana Y esposa de Zeus), manda
 *  el primero de esta lista. */
const PRECEDENCIA: Grupo[] = ['padres', 'hijos', 'pareja', 'familia', 'conflicto', 'otras']

const UNIONES = new Set(['has_sex_with', 'desires', 'rapes', 'attempts_to_rape'])

export function grupoDe(red: Red, a: AristaRed, centro: number): Grupo {
  const { k, cat } = red.predicados[a.p]
  const sale = a.s === centro
  // «es hijo de» con sujeto = hijo: si el centro es el sujeto, el otro es su padre
  if (k === 'is_child_of' || k === 'is_a_descendant_of') return sale ? 'padres' : 'hijos'
  if (cat === 'conyugal' || UNIONES.has(k)) return 'pareja'
  if (cat === 'genealogica') return 'familia'
  if (cat === 'muerte' || cat === 'belica') return 'conflicto'
  return 'otras'
}

export interface Vecino {
  nodo: NodoRed
  grupo: Grupo
  aristas: AristaRed[]
  /** fuentes sumadas de todas sus aristas con el centro */
  n: number
  /** alguna arista en disputa entre fuentes */
  dis: boolean
  /** todas sus aristas son dudosas, inciertas o implícitas */
  debil: boolean
}

export function vecinosDe(ir: IndiceRed, centro: number): Vecino[] {
  const porId = new Map<number, AristaRed[]>()
  for (const a of ir.vecinas.get(centro) ?? []) {
    const otro = a.s === centro ? a.o : a.s
    const lista = porId.get(otro)
    if (lista) lista.push(a)
    else porId.set(otro, [a])
  }
  const out: Vecino[] = []
  for (const [id, aristas] of porId) {
    const nodo = ir.nodos.get(id)
    if (!nodo) continue
    const grupos = new Set(aristas.map((a) => grupoDe(ir.red, a, centro)))
    out.push({
      nodo,
      grupo: PRECEDENCIA.find((g) => grupos.has(g)) ?? 'otras',
      aristas,
      n: aristas.reduce((t, a) => t + a.n, 0),
      dis: aristas.some((a) => a.dis),
      debil: aristas.every((a) => a.inc || a.duda || a.impl),
    })
  }
  return out.sort((a, b) => b.n - a.n || a.nodo.n.localeCompare(b.nodo.n, 'es'))
}

/** Paso de la rampa de tinta (1-4) por número de fuentes que afirman la relación. */
export function pasoFuentes(n: number): 1 | 2 | 3 | 4 {
  if (n >= 6) return 4
  if (n >= 3) return 3
  if (n >= 2) return 2
  return 1
}
export const CORTES_FUENTES = ['1', '2', '3–5', '6+'] as const

/** Figuras cuyo pajar contiene el texto, las mejor conectadas primero. */
export function buscarFiguras(ir: IndiceRed, texto: string, max = 8): NodoRed[] {
  const busca = normalizarBusqueda(texto)
  if (!busca) return []
  const out: NodoRed[] = []
  // `nodos` ya llega ordenado por grado descendente desde el export
  for (const n of ir.red.nodos) {
    if (n.q.includes(busca)) {
      out.push(n)
      if (out.length >= max) break
    }
  }
  return out
}
