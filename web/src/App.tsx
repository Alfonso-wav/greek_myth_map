import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import Mapa from './Mapa'
import Panel from './Panel'
import Tiempo from './Tiempo'
import { cargar, CORTES, indexar, mayuscula, visibles, type Indice } from './datos'

type Tema = 'auto' | 'light' | 'dark'
const SIGUIENTE_TEMA: Record<Tema, Tema> = { auto: 'light', light: 'dark', dark: 'auto' }
const NOMBRE_TEMA: Record<Tema, string> = { auto: 'el del sistema', light: 'claro', dark: 'oscuro' }
// mismos valores que colors.canvas / colors.dark-canvas de DESIGN.md
const COLOR_BARRA: Record<'light' | 'dark', string> = { light: '#f3f3f0', dark: '#15171c' }

/** Estado en el hash, para que una vista concreta sea un enlace compartible:
 *  #g=2&l=43391&a=Eratostenes&acum=1 */
function leerHash(): URLSearchParams {
  return new URLSearchParams(location.hash.replace(/^#/, ''))
}

/** Por debajo de 900 px el lateral es un cajón. Coincide con el breakpoint de styles.css. */
function useEstrecho(): boolean {
  const consulta = '(max-width: 900px)'
  const [estrecho, setEstrecho] = useState(() => matchMedia(consulta).matches)
  useEffect(() => {
    const mq = matchMedia(consulta)
    const cambio = () => setEstrecho(mq.matches)
    mq.addEventListener('change', cambio)
    return () => mq.removeEventListener('change', cambio)
  }, [])
  return estrecho
}

export default function App() {
  const inicial = leerHash()
  const [idx, setIdx] = useState<Indice | null>(null)
  const [error, setError] = useState<string | null>(null)
  // por defecto arranca en la Guerra de Troya, que es donde hay mas que ver
  const [gen, setGen] = useState(Number(inicial.get('g') ?? 2))
  const [autoridadNombre, setAutoridad] = useState<string | null>(inicial.get('a'))
  const [acumulado, setAcumulado] = useState(inicial.get('acum') === '1')
  const [conDivinidades, setConDivinidades] = useState(inicial.get('div') !== '0')
  const [conDisputas, setConDisputas] = useState(inicial.get('dis') !== '0')
  const [seleccion, setSeleccion] = useState<number | null>(
    inicial.get('l') ? Number(inicial.get('l')) : null,
  )
  const [tema, setTema] = useState<Tema>('auto')
  const [papeles, setPapeles] = useState<Set<string>>(
    () => new Set((inicial.get('p') ?? '').split(',').filter(Boolean)),
  )
  const [categorias, setCategorias] = useState<Set<string>>(
    () => new Set((inicial.get('c') ?? '').split(',').filter(Boolean)),
  )
  const [busqueda, setBusqueda] = useState(inicial.get('q') ?? '')

  const estrecho = useEstrecho()
  const [cajon, setCajon] = useState(false)
  const lateral = useRef<HTMLElement>(null)
  const botonCajon = useRef<HTMLButtonElement>(null)

  const alternar = useCallback(
    (set: Set<string>, poner: (s: Set<string>) => void) => (clave: string) => {
      const copia = new Set(set)
      if (copia.has(clave)) copia.delete(clave)
      else copia.add(clave)
      poner(copia)
    },
    [],
  )

  useEffect(() => {
    cargar()
      .then((d) => setIdx(indexar(d)))
      .catch((e) => setError(String(e.message ?? e)))
  }, [])

  useEffect(() => {
    const raiz = document.documentElement
    if (tema === 'auto') raiz.removeAttribute('data-theme')
    else raiz.setAttribute('data-theme', tema)
    // las <meta theme-color> van por media query: con el tema forzado hay que
    // pisarlas, o la barra del navegador queda del color del otro esquema
    for (const meta of document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')) {
      const propio = meta.media.includes('dark') ? 'dark' : 'light'
      meta.content = COLOR_BARRA[tema === 'auto' ? propio : tema]
    }
  }, [tema])

  // Cajón cerrado = fuera del árbol de foco y de accesibilidad (`inert`), no solo
  // apartado con transform: un cajón fuera de pantalla con controles tabulables es
  // una trampa para el teclado.
  useEffect(() => {
    lateral.current?.toggleAttribute('inert', estrecho && !cajon)
  }, [estrecho, cajon])

  useEffect(() => {
    if (!cajon) return
    lateral.current?.querySelector<HTMLElement>('input, button, select')?.focus()
    const tecla = (e: KeyboardEvent) => {
      if (e.key === 'Escape') cerrarCajon()
    }
    addEventListener('keydown', tecla)
    return () => removeEventListener('keydown', tecla)
  }, [cajon])

  function cerrarCajon() {
    setCajon(false)
    botonCajon.current?.focus()
  }

  // replaceState y no location.hash: asi no llena el historial con cada paso
  // del slider
  useEffect(() => {
    const p = new URLSearchParams({ g: String(gen) })
    if (seleccion != null) p.set('l', String(seleccion))
    if (autoridadNombre) p.set('a', autoridadNombre)
    if (acumulado) p.set('acum', '1')
    if (!conDivinidades) p.set('div', '0')
    if (!conDisputas) p.set('dis', '0')
    if (papeles.size) p.set('p', [...papeles].join(','))
    if (categorias.size) p.set('c', [...categorias].join(','))
    if (busqueda.trim()) p.set('q', busqueda.trim())
    history.replaceState(null, '', `#${p}`)
  }, [
    gen,
    seleccion,
    autoridadNombre,
    acumulado,
    conDivinidades,
    conDisputas,
    papeles,
    categorias,
    busqueda,
  ])

  const autoridad = useMemo(() => {
    if (!idx) return null
    return (
      idx.autoridades.find((a) => a.nombre === autoridadNombre) ??
      idx.autoridades.find((a) => a.preferida) ??
      idx.autoridades[0]
    )
  }, [idx, autoridadNombre])

  const visible = useMemo(
    () =>
      idx
        ? visibles(idx, { gen, acumulado, conDivinidades, papeles, categorias, busqueda })
        : null,
    [idx, gen, acumulado, conDivinidades, papeles, categorias, busqueda],
  )

  const disputas = useMemo(() => {
    if (!idx || !conDisputas || !visible) return []
    const out = []
    for (const [g, lista] of idx.contradiccionesPorGen) {
      if (acumulado ? g <= gen : g === gen) out.push(...lista)
    }
    // La disputa solo se dibuja si toca un lugar visible: con "héroes + guerra"
    // el mapa bajaba a 61 lugares y seguían pintándose las 286 líneas, que
    // tapaban justo lo que el filtro acababa de aislar.
    return out.filter((c) => visible.ids.has(c.l[0]) || visible.ids.has(c.l[1]))
  }, [idx, gen, acumulado, conDisputas, visible])

  const onSeleccion = useCallback((id: number | null) => setSeleccion(id), [])
  const cerrarPanel = useCallback(() => setSeleccion(null), [])

  // lo que difiere de la vista por defecto, para el botón «Filtros» del móvil
  const nActivos =
    papeles.size +
    categorias.size +
    (busqueda.trim() ? 1 : 0) +
    (acumulado ? 1 : 0) +
    (conDivinidades ? 0 : 1) +
    (conDisputas ? 0 : 1)

  if (error) {
    return (
      <div className="cargando" role="alert">
        <h1>No se pudieron cargar los datos</h1>
        <p>{error}</p>
      </div>
    )
  }
  if (!idx || !visible || !autoridad) {
    return (
      <div className="cargando" aria-busy="true">
        <h1 translate="no">Periégesis</h1>
        <p>Cargando el mito…</p>
      </div>
    )
  }

  return (
    <div className={`app${cajon ? ' cajon-abierto' : ''}`}>
      <header className="barra-movil">
        <span className="nombre" translate="no">
          Periégesis
        </span>
        <button
          ref={botonCajon}
          className="boton"
          aria-expanded={cajon}
          aria-controls="lateral"
          onClick={() => setCajon(true)}
        >
          Filtros
          {nActivos > 0 && (
            <b>
              {' · '}
              {nActivos}
              <span className="solo-lector"> activos</span>
            </b>
          )}
        </button>
      </header>

      <aside id="lateral" className="lateral" ref={lateral} aria-label="Búsqueda y filtros">
        <div className="marca">
          <div>
            <h1 translate="no">Periégesis</h1>
            <p>El mito griego lugar por lugar: dónde sitúa cada fuente antigua cada hecho.</p>
          </div>
          <button className="boton cajon-cerrar" onClick={cerrarCajon}>
            Ver mapa
          </button>
        </div>

        <div className="campo">
          <label htmlFor="busqueda">
            <span className="rotulo">Buscar figura o lugar</span>
          </label>
          <input
            id="busqueda"
            type="search"
            name="q"
            autoComplete="off"
            spellCheck={false}
            value={busqueda}
            placeholder="Circe, Kirke, Κίρκη, Ítaca…"
            onChange={(e) => setBusqueda(e.target.value)}
          />
          {busqueda.trim() && (
            <span className="resultado" aria-live="polite">
              <span className="cifra">{visible.lugares.length.toLocaleString('es')}</span> lugares
              · <span className="cifra">{visible.afirmaciones.length.toLocaleString('es')}</span>{' '}
              afirmaciones
            </span>
          )}
        </div>

        <label className="campo">
          <span>Cronología según</span>
          <select value={autoridad.nombre} onChange={(e) => setAutoridad(e.target.value)}>
            {idx.autoridades.map((a) => (
              <option key={a.nombre} value={a.nombre}>
                {a.nombre} · {Math.abs(a.troya)} a.C.{a.preferida ? ' · por defecto' : ''}
              </option>
            ))}
          </select>
          <span className="ayuda">
            El año es el de la caída de Troya. Las once autoridades coinciden en el orden de los
            hechos; solo discrepan en dónde cae Troya.
          </span>
        </label>

        <div className="grupo" role="group" aria-labelledby="rotulo-vista">
          <span className="rotulo" id="rotulo-vista">
            Vista
          </span>
          <div className="conmutadores">
            <button
              className="conmutador"
              aria-pressed={acumulado}
              onClick={() => setAcumulado((v) => !v)}
            >
              Acumular generaciones anteriores
            </button>
            <button
              className="conmutador"
              aria-pressed={conDivinidades}
              onClick={() => setConDivinidades((v) => !v)}
            >
              <i className="muestra" aria-hidden="true" />
              Divinidades, sin generación
            </button>
            <button
              className="conmutador"
              aria-pressed={conDisputas}
              onClick={() => setConDisputas((v) => !v)}
            >
              <i className="muestra rubrica" aria-hidden="true" />
              Hechos en disputa
            </button>
          </div>
        </div>

        {/* Dos ejes, etiquetados: 'quién' se deriva de las fuentes y 'qué' sale de
            predicado.categoria. Un chip apagado no filtra; el conjunto vacío
            significa "todo", no "nada". */}
        <fieldset className="grupo">
          <legend>Quién protagoniza</legend>
          <div className="chips">
            {idx.meta.papeles.map((f) => (
              <button
                key={f.clave}
                className="chip"
                aria-pressed={papeles.has(f.clave)}
                onClick={() => alternar(papeles, setPapeles)(f.clave)}
              >
                {mayuscula(f.etiqueta)} <b>{f.n.toLocaleString('es')}</b>
              </button>
            ))}
            {papeles.size > 0 && (
              <button className="chip limpiar" onClick={() => setPapeles(new Set())}>
                Quitar
              </button>
            )}
          </div>
        </fieldset>

        <fieldset className="grupo">
          <legend>Qué clase de hecho</legend>
          <div className="chips">
            {idx.meta.categorias.map((f) => (
              <button
                key={f.clave}
                className="chip"
                aria-pressed={categorias.has(f.clave)}
                onClick={() => alternar(categorias, setCategorias)(f.clave)}
              >
                {mayuscula(f.etiqueta)} <b>{f.n.toLocaleString('es')}</b>
              </button>
            ))}
            {categorias.size > 0 && (
              <button className="chip limpiar" onClick={() => setCategorias(new Set())}>
                Quitar
              </button>
            )}
          </div>
        </fieldset>

        <footer className="pie-lateral">
          <button className="boton" onClick={() => setTema(SIGUIENTE_TEMA[tema])}>
            Tema: {NOMBRE_TEMA[tema]}
          </button>
          <span>
            Datos de MANTO (CC BY-NC), Pleiades (CC BY) y ToposText. Mapa © OpenStreetMap.
          </span>
        </footer>
      </aside>

      <main className="lienzo-col">
        <div className="lienzo">
          <Mapa
            idx={idx}
            visible={visible}
            contradicciones={disputas}
            seleccion={seleccion}
            onSeleccion={onSeleccion}
          />

          <div className="leyenda">
            <h2>Afirmaciones por lugar</h2>
            <div className="escala">
              {CORTES.map((corte, i) => (
                <span key={corte}>
                  <i style={{ background: `var(--m${i + 1})` }} aria-hidden="true" />
                  {corte}
                </span>
              ))}
            </div>
            {conDisputas && (
              <div className="fila">
                <i className="marca-linea" aria-hidden="true" />
                <span>Mismo hecho, dos lugares</span>
              </div>
            )}
            <div className="fila aprox">
              <i className="marca-hueca" aria-hidden="true" />
              <span>Coordenada aproximada</span>
            </div>
          </div>

          {visible.lugares.length === 0 && (
            <div className="sin-resultados" role="status">
              <p>
                {busqueda.trim()
                  ? `Nada coincide con «${busqueda.trim()}» en esta generación.`
                  : 'Ningún lugar cumple a la vez todos los filtros en esta generación.'}
              </p>
              {busqueda.trim() ? (
                <button className="boton" onClick={() => setBusqueda('')}>
                  Quitar la búsqueda
                </button>
              ) : (
                <button
                  className="boton"
                  onClick={() => {
                    setPapeles(new Set())
                    setCategorias(new Set())
                  }}
                >
                  Quitar los filtros
                </button>
              )}
            </div>
          )}

          {seleccion != null && (
            <Panel
              idx={idx}
              lugarId={seleccion}
              afirmaciones={visible.afirmaciones}
              contradicciones={disputas}
              autoridad={autoridad}
              onCerrar={cerrarPanel}
            />
          )}
        </div>

        <Tiempo
          idx={idx}
          gen={gen}
          autoridad={autoridad}
          acumulado={acumulado}
          nLugares={visible.lugares.length}
          nAfirmaciones={visible.afirmaciones.length}
          nDisputas={disputas.length}
          nDivinas={visible.nDivinas}
          onGen={setGen}
        />
      </main>
    </div>
  )
}
