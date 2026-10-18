import type { AristaRed, NodoRed, Red } from './types'
import { normalizarBusqueda } from './datos'
import type { Forma } from './formas'

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

/** Clase de vínculo que dibuja la línea. Color = familia (parentesco, violencia,
 *  lo sagrado, otros tratos en gris), forma = subtipo (`formas.ts`). El color solo
 *  no basta: las líneas salen todas juntas del centro y con más de tres tonos el
 *  validador no encuentra paleta que se distinga con daltonismo. La pareja
 *  (familia, forma) es única para cada clase. */
export const FAMILIAS = [
  { k: 'familia', et: 'Parentesco' },
  { k: 'violencia', et: 'Violencia' },
  { k: 'sagrado', et: 'Lo sagrado' },
  { k: 'otra', et: 'Otros tratos' },
] as const
export type Familia = (typeof FAMILIAS)[number]['k']

export const TIPOS = [
  { k: 'filiacion', et: 'Filiación y crianza', fam: 'familia', forma: 'recta' },
  { k: 'pareja', et: 'Pareja o unión', fam: 'familia', forma: 'onda' },
  { k: 'linaje', et: 'Hermanos y linaje', fam: 'familia', forma: 'doble' },
  { k: 'muerte', et: 'Muerte', fam: 'violencia', forma: 'zigzag' },
  { k: 'combate', et: 'Combate y derrota', fam: 'violencia', forma: 'cuadrada' },
  { k: 'agravio', et: 'Castigo, rapto, engaño', fam: 'violencia', forma: 'raya' },
  { k: 'creacion', et: 'Creación y metamorfosis', fam: 'sagrado', forma: 'bucles' },
  { k: 'culto', et: 'Culto, profecía, patronazgo', fam: 'sagrado', forma: 'rayapunto' },
  { k: 'ayuda', et: 'Ayuda, protección, hospitalidad', fam: 'otra', forma: 'punto' },
  { k: 'trato', et: 'Viajes, envíos y dones', fam: 'otra', forma: 'chevrones' },
  { k: 'poder', et: 'Mando, sucesión, servidumbre', fam: 'otra', forma: 'espina' },
  { k: 'identidad', et: 'Pertenencia e identidad', fam: 'otra', forma: 'raya' },
  { k: 'otro', et: 'Otras relaciones', fam: 'otra', forma: 'recta' },
] as const satisfies readonly { k: string; et: string; fam: Familia; forma: Forma }[]
export type Tipo = (typeof TIPOS)[number]['k']
export const TIPO = Object.fromEntries(TIPOS.map((t) => [t.k, t])) as Record<
  Tipo,
  (typeof TIPOS)[number]
>

const FILIACION = new Set(['is_child_of', 'is_a_descendant_of'])
/** Predicados de categoría `otra` (o sin una precisa) repartidos a mano entre las
 *  clases. Las claves son las de MANTO, con sus ranuras entre corchetes. */
const POR_CLAVE: Record<string, Tipo> = Object.fromEntries(
  (
    [
      [
        'agravio',
        [
          'punishes',
          'expels_[from]_[to]',
          'imprisons',
          'abducts_[from]_[to]',
          'deceives',
          'offends',
          'quarrels_with',
          'plots_against',
          'threatens',
          'curses',
          'insults',
          'mistreats',
          'hinders',
          'drives_insane',
          'captures_[not_place]',
          'pursues_[from]_[to]',
          'hunts',
          'destroys',
          'damages',
          'abandons',
          'exposes',
          'shipwrecks_[in/on/at]',
        ],
      ],
      [
        'creacion',
        [
          'takes_form_of',
          'resurrects',
          'grants_superhuman_power_[ind._obj.]',
          'changes_name_of_[dir._obj.]_[ind._obj]',
        ],
      ],
      ['culto', ['purifies', 'appears_in_an_epiphany_[ind._obj.]']],
      [
        'ayuda',
        [
          'helps',
          'rescues_[from]',
          'protects_[from]',
          'hosts',
          'requests_help_[from]',
          'pledges_oath_with_[against]',
          'heals',
          'recovers_the_body_of_[from]_[to]',
          'releases_[from]_[to]',
          'ransoms_[from]_[to]',
          'teaches',
          'mourns',
          'bathes',
        ],
      ],
      [
        'trato',
        [
          'gives_[dir._obj.]_[ind._obj.]',
          'gives_something_[ind._obj]',
          'takes_[dir._obj.]_[from]_[to]_[via]',
          'sends_[against]_[from]_[to]_[via]',
          'flees_[from]_[to]_[via]',
          'visits',
          'travels_[from]_[to]_[via]',
          'encounters',
          'migrates_[from]_[to]',
          'searches_for_[in/on/at]_[from]_[to]_[via]',
          'offers_[ind._obj.]',
          'performs_[for]',
          'goes_past',
          'hides_[from]',
          'consumes',
          'discards',
        ],
      ],
      [
        'poder',
        [
          'succeeds_[in/on/at]',
          'leads',
          'possesses',
          'is_slave_[of]_[in/on/at]',
          'guards',
          'puts_on_trial',
          'sells_as_slave_[ind._obj]',
          'speaks_in_assembly_[of]_[in/on/at]',
          'assembles',
          'tests',
        ],
      ],
      [
        'identidad',
        [
          'is_member_of',
          'is_associated_with',
          'is_compared_to',
          'is_contemporary_of',
          'is_conflated_with',
          'is_alternative_name_for',
          'derives_etymology_[from]',
          'is_identified_as',
          '[non-greek_entity]_is_identified_as_[greek_entity]',
          'names',
          'changes_name_to',
        ],
      ],
    ] as [Tipo, string[]][]
  ).flatMap(([t, ks]) => ks.map((k) => [k, t])),
)

export function tipoDe(red: Red, a: AristaRed): Tipo {
  const { k, cat } = red.predicados[a.p]
  if (FILIACION.has(k) || cat === 'nacimiento') return 'filiacion'
  if (cat === 'conyugal' || UNIONES.has(k)) return 'pareja'
  if (cat === 'genealogica') return 'linaje'
  if (cat === 'muerte') return 'muerte'
  if (cat === 'belica' || cat === 'competicion' || k === 'wins_in_competition_[against]')
    return 'combate'
  if (POR_CLAVE[k]) return POR_CLAVE[k]
  if (cat === 'creacion' || cat === 'transformacion' || cat === 'fundacion') return 'creacion'
  if (cat === 'cultual' || cat === 'profecia' || cat === 'oficio') return 'culto'
  if (cat === 'politica') return 'poder'
  return 'otro'
}

export interface Vecino {
  nodo: NodoRed
  grupo: Grupo
  /** el tipo de la línea: el primero de TIPOS entre sus aristas, igual que el
   *  grupo manda por precedencia (Hera es hermana y esposa: sale pareja) */
  tipo: Tipo
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
    const tipos = new Set(aristas.map((a) => tipoDe(ir.red, a)))
    out.push({
      nodo,
      grupo: PRECEDENCIA.find((g) => grupos.has(g)) ?? 'otras',
      tipo: TIPOS.find((t) => tipos.has(t.k))?.k ?? 'otro',
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
