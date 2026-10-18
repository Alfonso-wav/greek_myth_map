import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'

import { mayuscula } from './datos'
import {
  buscarFiguras,
  CORTES_FUENTES,
  GRUPOS,
  pasoFuentes,
  vecinosDe,
  type Grupo,
  type IndiceRed,
  type Vecino,
} from './datosRed'
import type { AristaRed } from './types'

interface Props {
  ir: IndiceRed
  centro: number
  onCentro: (id: number) => void
  /** abre el mapa filtrado por esta figura; null si no aparece en el mapa */
  onVerMapa: ((nombre: string) => void) | null
  enMapa: (id: number) => boolean
}

/** Espacio que se reserva fuera del anillo para los nombres, que van en radial. */
const MARGEN_ETIQUETA = 128
/** Separación mínima entre nodos sobre el anillo, en px de arco: por debajo los
 *  nombres radiales se pisan. Lo que no cabe queda en la lista de la derecha. */
const ARCO_MIN = 15
const MAX_ETIQUETA = 22
/** Por debajo de este radio los rótulos de grupo se pisan en el centro. */
const R_ROTULOS = 150
const FAMILIA = new Set<Grupo>(['padres', 'hijos', 'pareja', 'familia'])

const ETIQUETA_GRUPO = Object.fromEntries(GRUPOS.map((g) => [g.k, g.et])) as Record<Grupo, string>

function recortar(s: string): string {
  return s.length > MAX_ETIQUETA ? `${s.slice(0, MAX_ETIQUETA - 1)}…` : s
}

function radioNodo(grado: number): number {
  return Math.min(9, 3 + Math.sqrt(grado) * 0.35)
}

/** Tamaño real del contenedor: el SVG se dibuja a píxeles reales, igual que el
 *  histograma, para que trazos y textos no se deformen con el viewBox. */
function useTamano<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [tam, setTam] = useState({ w: 0, h: 0 })
  useLayoutEffect(() => {
    if (!ref.current) return
    const ro = new ResizeObserver(([e]) => {
      const { width, height } = e.contentRect
      setTam({ w: Math.round(width), h: Math.round(height) })
    })
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])
  return [ref, tam] as const
}

interface Colocado {
  v: Vecino
  x: number
  y: number
  ang: number
}

function colocar(vecinos: Vecino[], cx: number, cy: number, R: number) {
  // un hueco de un puesto entre grupos, para que se lean como bloques
  const grupos = GRUPOS.map((g) => ({ k: g.k, vs: vecinos.filter((v) => v.grupo === g.k) })).filter(
    (g) => g.vs.length,
  )
  const puestos = vecinos.length + grupos.length
  const paso = (2 * Math.PI) / Math.max(puestos, 1)

  let i = 0
  const crudos: { v: Vecino; a: number }[] = []
  const centros: { k: Grupo; a: number; n: number }[] = []
  for (const g of grupos) {
    const desde = i
    for (const v of g.vs) crudos.push({ v, a: i++ * paso })
    centros.push({ k: g.k, a: ((desde + i - 1) / 2) * paso, n: g.vs.length })
    i++
  }
  // progenitores arriba; si no hay, descendencia abajo
  const ref = centros.find((c) => c.k === 'padres') ?? centros.find((c) => c.k === 'hijos')
  const giro = ref ? (ref.k === 'padres' ? -Math.PI / 2 : Math.PI / 2) - ref.a : -Math.PI / 2

  const nodos: Colocado[] = crudos.map(({ v, a }) => {
    const ang = a + giro
    return { v, ang, x: cx + R * Math.cos(ang), y: cy + R * Math.sin(ang) }
  })
  const rotulos = centros.map((c) => {
    const ang = c.a + giro
    return { ...c, x: cx + R * 0.6 * Math.cos(ang), y: cy + R * 0.6 * Math.sin(ang) }
  })
  return { nodos, rotulos }
}

export default function Red({ ir, centro, onCentro, onVerMapa, enMapa }: Props) {
  const [caja, { w, h }] = useTamano<HTMLDivElement>()
  const [foco, setFoco] = useState<number | null>(null)
  const [texto, setTexto] = useState('')
  const lista = useRef<HTMLDivElement>(null)

  const nodo = ir.nodos.get(centro)
  const vecinos = useMemo(() => vecinosDe(ir, centro), [ir, centro])

  useEffect(() => {
    setFoco(null)
    lista.current?.scrollTo({ top: 0 })
  }, [centro])

  const cx = w / 2
  const cy = h / 2
  const R = Math.max(70, Math.min(w, h) / 2 - MARGEN_ETIQUETA)
  const cupo = Math.max(8, Math.floor((2 * Math.PI * R) / ARCO_MIN))
  // Si no caben todas, la familia entra siempre y el resto por fuentes (`vecinos`
  // ya llega ordenado así): recortar por fuentes a secas dejaba fuera a dos de
  // los cinco progenitores de Heracles, citados una sola vez.
  const dibujados = useMemo(() => {
    if (vecinos.length <= cupo) return vecinos
    const familia = vecinos.filter((v) => FAMILIA.has(v.grupo))
    const resto = vecinos.filter((v) => !FAMILIA.has(v.grupo))
    return [...familia, ...resto].slice(0, cupo)
  }, [vecinos, cupo])
  const { nodos, rotulos } = useMemo(
    () => colocar(dibujados, cx, cy, R),
    [dibujados, cx, cy, R],
  )
  const totalGrupo = useMemo(() => {
    const t = new Map<Grupo, number>()
    for (const v of vecinos) t.set(v.grupo, (t.get(v.grupo) ?? 0) + 1)
    return t
  }, [vecinos])

  const resultados = useMemo(() => buscarFiguras(ir, texto), [ir, texto])

  if (!nodo) {
    return (
      <div className="red vacia">
        <p>Esta figura no tiene relaciones con otras figuras en MANTO.</p>
      </div>
    )
  }

  const focoV = foco != null ? vecinos.find((v) => v.nodo.id === foco) : undefined
  const porGrupo = GRUPOS.map((g) => ({
    ...g,
    vs: vecinos.filter((v) => v.grupo === g.k),
  })).filter((g) => g.vs.length)

  function elegir(id: number) {
    setTexto('')
    onCentro(id)
  }

  function frase(a: AristaRed) {
    const pred = ir.red.predicados[a.p]
    const nombre = (id: number) => {
      const n = ir.nodos.get(id)
      if (id === centro || !n) return <b>{n?.n ?? '—'}</b>
      return (
        <button className="nombre" onClick={() => elegir(id)} title={n.d ?? undefined}>
          {n.n}
        </button>
      )
    }
    return (
      <>
        {nombre(a.s)} {pred.e} {nombre(a.o)}
        {a.rol ? <span className="rol"> ({a.rol.replace(/_/g, ' ')})</span> : null}
      </>
    )
  }

  const detalle = [
    nodo.d,
    nodo.p?.length ? nodo.p.map(mayuscula).join(', ') : null,
    nodo.div ? 'Divinidad' : nodo.g != null ? `Gen. ${nodo.g > 0 ? '+' : ''}${nodo.g}` : null,
  ].filter(Boolean)

  return (
    <div className="red">
      <div className="red-lienzo" ref={caja}>
        <div className="red-buscar">
          <label htmlFor="buscar-figura" className="solo-lector">
            Buscar figura
          </label>
          <input
            id="buscar-figura"
            type="search"
            autoComplete="off"
            spellCheck={false}
            placeholder="Buscar figura: Heracles, Kirke, Ἀχιλλεύς…"
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && resultados[0]) elegir(resultados[0].id)
              if (e.key === 'Escape') setTexto('')
            }}
          />
          {texto.trim() && (
            <ul className="red-resultados" aria-live="polite">
              {resultados.length === 0 && <li className="nada">Ninguna figura coincide</li>}
              {resultados.map((r) => (
                <li key={r.id}>
                  <button onClick={() => elegir(r.id)}>
                    {r.n}
                    <span className="cifra">{r.gr.toLocaleString('es')}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {w > 0 && (
          <svg
            width={w}
            height={h}
            className={foco != null ? 'con-foco' : undefined}
            role="img"
            aria-label={`${nodo.n} y ${dibujados.length} figuras relacionadas`}
          >
            <g className="aristas">
              {nodos.map(({ v, x, y }) => (
                <line
                  key={v.nodo.id}
                  x1={cx}
                  y1={cy}
                  x2={x}
                  y2={y}
                  className={`arista f${pasoFuentes(v.n)}${v.dis ? ' dis' : ''}${
                    v.debil ? ' debil' : ''
                  }${foco === v.nodo.id ? ' activa' : ''}`}
                />
              ))}
            </g>

            {R >= R_ROTULOS &&
              rotulos.map((r) => {
                const total = totalGrupo.get(r.k) ?? r.n
                return (
                  <text key={r.k} x={r.x} y={r.y} className="rotulo-grupo" textAnchor="middle">
                    {ETIQUETA_GRUPO[r.k]} · {r.n === total ? r.n : `${r.n} de ${total}`}
                  </text>
                )
              })}

            {nodos.map(({ v, x, y, ang }) => {
              const r = radioNodo(v.nodo.gr)
              const izquierda = Math.cos(ang) < 0
              const grados = (ang * 180) / Math.PI + (izquierda ? 180 : 0)
              return (
                <g
                  key={v.nodo.id}
                  className={`vecino${foco === v.nodo.id ? ' activa' : ''}`}
                  transform={`translate(${x},${y})`}
                  tabIndex={0}
                  role="button"
                  aria-label={`${v.nodo.n}: ${ETIQUETA_GRUPO[v.grupo]}, ${v.n} ${
                    v.n === 1 ? 'fuente' : 'fuentes'
                  }. Centrar.`}
                  onMouseEnter={() => setFoco(v.nodo.id)}
                  onMouseLeave={() => setFoco(null)}
                  onFocus={() => setFoco(v.nodo.id)}
                  onBlur={() => setFoco(null)}
                  onClick={() => elegir(v.nodo.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      elegir(v.nodo.id)
                    }
                  }}
                >
                  {/* área de toque generosa, invisible */}
                  <circle r={Math.max(r + 6, 11)} className="toque" />
                  <circle r={r} className="punto" />
                  <text
                    transform={`rotate(${grados})`}
                    x={izquierda ? -(r + 5) : r + 5}
                    dy="0.32em"
                    textAnchor={izquierda ? 'end' : 'start'}
                  >
                    {recortar(v.nodo.n)}
                  </text>
                </g>
              )
            })}

            <g className="centro" transform={`translate(${cx},${cy})`}>
              <circle r={12} />
              <text y={30} textAnchor="middle">
                {nodo.n}
              </text>
            </g>
          </svg>
        )}

        {focoV && (
          <div className="red-pista" role="status">
            {focoV.aristas.slice(0, 4).map((a, i) => {
              const pred = ir.red.predicados[a.p]
              const s = ir.nodos.get(a.s)?.n
              const o = ir.nodos.get(a.o)?.n
              return (
                <p key={i}>
                  {s} <i>{pred.e}</i> {o}
                  {a.dis ? <span className="dis"> · en disputa</span> : null}
                </p>
              )
            })}
            {focoV.aristas.length > 4 && <p className="mas">y {focoV.aristas.length - 4} más</p>}
          </div>
        )}

        <div className="leyenda red-leyenda">
          <h2>Fuentes que lo afirman</h2>
          <div className="escala">
            {CORTES_FUENTES.map((c, i) => (
              <span key={c}>
                <i className={`f${i + 1}`} aria-hidden="true" />
                {c}
              </span>
            ))}
          </div>
          <div className="fila">
            <i className="marca-linea solida" aria-hidden="true" />
            <span>Las fuentes discrepan</span>
          </div>
          <div className="fila">
            <i className="marca-linea debil" aria-hidden="true" />
            <span>Dudoso o implícito</span>
          </div>
        </div>
      </div>

      <aside className="ficha" aria-label={`Relaciones de ${nodo.n}`} ref={lista}>
        <header>
          <h2>{nodo.n}</h2>
          {nodo.grc && (
            <div className="grc" lang="grc" translate="no">
              {nodo.grc}
            </div>
          )}
          {detalle.length > 0 && <p className="sub">{detalle.join(' · ')}</p>}
          <div className="enlaces">
            {nodo.enl?.map((e) => (
              <a key={e.u} href={e.u} target="_blank" rel="noopener noreferrer">
                {e.k}
              </a>
            ))}
            {onVerMapa && enMapa(nodo.id) && (
              <button className="enlace" onClick={() => onVerMapa(nodo.n)}>
                Ver en el mapa
              </button>
            )}
          </div>
          <p className="resumen">
            <span className="cifra">{vecinos.length.toLocaleString('es')}</span>{' '}
            {vecinos.length === 1 ? 'figura relacionada' : 'figuras relacionadas'}
            {vecinos.length > dibujados.length && (
              <>
                {' '}
                · se dibujan <span className="cifra">{dibujados.length}</span>: la familia y
                las mejor atestiguadas. La lista las trae todas
              </>
            )}
          </p>
        </header>

        {porGrupo.map((g) => (
          <section key={g.k} className="grupo-red">
            <h3>
              {g.et} <span className="cifra">{g.vs.length}</span>
            </h3>
            {g.vs.flatMap((v) =>
              v.aristas.map((a, i) => (
                <article className="afirm" key={`${v.nodo.id}-${a.p}-${a.rol ?? ''}-${a.s}-${i}`}>
                  <div className="que">{frase(a)}</div>
                  {a.dis || a.inc || a.duda || a.impl || a.alt ? (
                    <div className="marcas">
                      {a.dis === 1 && <em className="dis">otra fuente lo cuenta distinto</em>}
                      {a.duda === 1 && <em>la fuente duda</em>}
                      {a.inc === 1 && <em>dato incierto</em>}
                      {a.impl === 1 && <em>implícito, no dicho</em>}
                      {a.alt === 1 && <em>la fuente da alternativas</em>}
                    </div>
                  ) : null}
                  {a.ci?.length ? (
                    <ul className="citas">
                      {a.ci.map((ci) => {
                        const c = ir.red.citas[ci]
                        return (
                          <li key={ci}>
                            {c.u ? (
                              <a
                                href={c.u}
                                target="_blank"
                                rel="noopener noreferrer"
                                title="Leer el pasaje en Perseus / Scaife"
                              >
                                {c.t}
                              </a>
                            ) : (
                              c.t
                            )}
                          </li>
                        )
                      })}
                      {a.n > a.ci.length && (
                        <li className="mas">
                          y {a.n - a.ci.length} {a.n - a.ci.length === 1 ? 'fuente más' : 'fuentes más'}
                        </li>
                      )}
                    </ul>
                  ) : (
                    <p className="sin-cita">Sin pasaje textual que lo atestigüe</p>
                  )}
                </article>
              )),
            )}
          </section>
        ))}
      </aside>
    </div>
  )
}
