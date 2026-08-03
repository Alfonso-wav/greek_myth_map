import { useCallback, useEffect, useMemo, useState } from 'react'

import Mapa from './Mapa'
import Panel from './Panel'
import Tiempo from './Tiempo'
import { cargar, CORTES, indexar, visibles, type Indice } from './datos'

type Tema = 'auto' | 'light' | 'dark'

/** Estado en el hash, para que una vista concreta sea un enlace compartible:
 *  #g=2&l=43391&a=Eratostenes&acum=1 */
function leerHash(): URLSearchParams {
  return new URLSearchParams(location.hash.replace(/^#/, ''))
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
    if (tema === 'auto') document.documentElement.removeAttribute('data-theme')
    else document.documentElement.setAttribute('data-theme', tema)
  }, [tema])

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

  if (error) {
    return (
      <div className="cargando">
        <b>no hay datos</b>
        <p style={{ maxWidth: 460, fontSize: 13 }}>{error}</p>
      </div>
    )
  }
  if (!idx || !visible || !autoridad) return <div className="cargando">cargando el mito…</div>

  return (
    <div className="app">
      <header className="barra">
        <div className="marca">
          <b>greek</b>
          <span>el mito griego sobre el mapa, generación a generación</span>
        </div>

        <label className="campo">
          <span>cronología según</span>
          <select
            value={autoridad.nombre}
            onChange={(e) => setAutoridad(e.target.value)}
            title="Las 11 autoridades no discrepan en el orden de los hechos, solo en dónde cae el ancla troyana"
          >
            {idx.autoridades.map((a) => (
              <option key={a.nombre} value={a.nombre}>
                {a.nombre} — Troya {Math.abs(a.troya)} a.C.
                {a.preferida ? ' ★' : ''}
              </option>
            ))}
          </select>
        </label>

        <div className="conmutadores">
          <button
            className="conmutador"
            aria-pressed={acumulado}
            onClick={() => setAcumulado((v) => !v)}
            title="Mostrar todo lo anterior a la generación elegida, en vez de solo esa"
          >
            acumulado
          </button>
          <button
            className="conmutador"
            aria-pressed={conDivinidades}
            onClick={() => setConDivinidades((v) => !v)}
            title="Las divinidades no pertenecen a una generación: la paternidad divina no fecha nada"
          >
            <i className="punto" aria-hidden="true" />
            divinidades
          </button>
          <button
            className="conmutador"
            aria-pressed={conDisputas}
            onClick={() => setConDisputas((v) => !v)}
            title="Hechos que dos fuentes sitúan en lugares distintos"
          >
            <i className="punto verde" aria-hidden="true" />
            en disputa
          </button>
          <button
            className="conmutador"
            onClick={() => setTema(tema === 'dark' ? 'light' : 'dark')}
            aria-label="cambiar tema"
            title="claro / oscuro"
          >
            {tema === 'dark' ? '☾' : '☀'}
          </button>
        </div>
      </header>

      {/* Dos ejes, etiquetados: 'quien' se deriva de las fuentes y 'que' sale de
          predicado.categoria. Un chip apagado no filtra; el conjunto vacio
          significa "todo", no "nada". */}
      <div className="filtros">
        <fieldset className="buscador">
          <legend>nombre</legend>
          <input
            type="search"
            value={busqueda}
            placeholder="Circe, Kirke, Κίρκη, Ítaca…"
            onChange={(e) => setBusqueda(e.target.value)}
            aria-label="buscar por nombre de figura o de lugar"
          />
          {busqueda.trim() && (
            <span className="resultado">
              {visible.lugares.length} lugares · {visible.afirmaciones.length} afirmaciones
            </span>
          )}
        </fieldset>

        <fieldset>
          <legend>quién</legend>
          {idx.meta.papeles.map((f) => (
            <button
              key={f.clave}
              className="chip"
              aria-pressed={papeles.has(f.clave)}
              onClick={() => alternar(papeles, setPapeles)(f.clave)}
              title={`${f.n} figuras con este papel entre las visibles del corpus`}
            >
              {f.etiqueta} <b>{f.n}</b>
            </button>
          ))}
          {papeles.size > 0 && (
            <button className="chip limpiar" onClick={() => setPapeles(new Set())}>
              quitar
            </button>
          )}
        </fieldset>

        <fieldset>
          <legend>qué</legend>
          {idx.meta.categorias.map((f) => (
            <button
              key={f.clave}
              className="chip"
              aria-pressed={categorias.has(f.clave)}
              onClick={() => alternar(categorias, setCategorias)(f.clave)}
              title={`${f.n} afirmaciones de este tipo`}
            >
              {f.etiqueta} <b>{f.n}</b>
            </button>
          ))}
          {categorias.size > 0 && (
            <button className="chip limpiar" onClick={() => setCategorias(new Set())}>
              quitar
            </button>
          )}
        </fieldset>
      </div>

      <div className="lienzo">
        <Mapa
          idx={idx}
          visible={visible}
          contradicciones={disputas}
          seleccion={seleccion}
          onSeleccion={onSeleccion}
        />

        <div className="leyenda">
          <h4>afirmaciones por lugar</h4>
          <div className="escala">
            {CORTES.map((corte, i) => (
              <i
                key={corte}
                style={{ background: `var(--m${i + 1})` }}
                title={`${corte} afirmaciones`}
              />
            ))}
          </div>
          <div className="escala-rotulos">
            {CORTES.map((corte) => (
              <span key={corte}>{corte}</span>
            ))}
          </div>
          <div className="fila">
            <i className="marca-linea" aria-hidden="true" />
            <span>mismo hecho, dos lugares</span>
          </div>
          <div className="fila">
            <i className="marca-hueca" aria-hidden="true" />
            <span>coordenada aproximada</span>
          </div>
        </div>

        {seleccion != null && (
          <Panel
            idx={idx}
            lugarId={seleccion}
            afirmaciones={visible.afirmaciones}
            contradicciones={disputas}
            autoridad={autoridad}
            onCerrar={() => setSeleccion(null)}
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
    </div>
  )
}
