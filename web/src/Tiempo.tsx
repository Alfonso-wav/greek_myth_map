import { useEffect, useMemo, useRef, useState } from 'react'

import { anioDe, etiquetaGeneracion, formatearAnio, type Indice } from './datos'
import type { Autoridad } from './types'

const ALTO = 56
const PAD_ABAJO = 15
const HUECO = 2 // separacion de 2px entre barras: la exige la guia de marcas
const RADIO = 4 // extremo de dato redondeado 4px, anclado a la linea base

/** Rect con las dos esquinas de arriba redondeadas y la base plana. */
function barra(x: number, y: number, w: number, h: number): string {
  const r = Math.min(RADIO, w / 2, h)
  if (h <= 0) return ''
  return (
    `M${x},${y + h}V${y + r}` +
    `a${r},${r} 0 0 1 ${r},${-r}` +
    `h${w - 2 * r}` +
    `a${r},${r} 0 0 1 ${r},${r}` +
    `V${y + h}Z`
  )
}

interface Props {
  idx: Indice
  gen: number
  autoridad: Autoridad
  acumulado: boolean
  nLugares: number
  nAfirmaciones: number
  nDisputas: number
  /** divinidades entre las afirmaciones YA filtradas, no el total del corpus */
  nDivinas: number
  onGen: (g: number) => void
}

/** Ancho real en pixeles del contenedor.
 *  Necesario para dibujar 1:1: con `preserveAspectRatio="none"` el viewBox de
 *  1000 se estiraba ~1,65x en X y solo 1x en Y, lo que deformaba el redondeo de
 *  4px de los extremos y ensanchaba los huecos de 2px entre barras. */
function useAncho(ref: React.RefObject<HTMLElement>): number {
  const [ancho, setAncho] = useState(900)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setAncho(Math.round(e.contentRect.width)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [ref])
  return ancho
}

export default function Tiempo({
  idx,
  gen,
  autoridad,
  acumulado,
  nLugares,
  nAfirmaciones,
  nDisputas,
  nDivinas,
  onGen,
}: Props) {
  const [encima, setEncima] = useState<number | null>(null)
  const caja = useRef<HTMLElement>(null)
  const ancho = useAncho(caja)
  const { gen_min, gen_max, gen_sin_fecha } = idx.meta

  const barras = useMemo(() => {
    const out: { g: number; n: number }[] = []
    for (let g = gen_min; g <= gen_max; g++) out.push({ g, n: idx.densidad.get(g) ?? 0 })
    return out
  }, [idx, gen_min, gen_max])

  const max = Math.max(1, ...barras.map((b) => b.n))
  const paso = ancho / barras.length
  const wBarra = Math.max(2, paso - HUECO)
  const anio = anioDe(autoridad, gen, gen_sin_fecha)
  const activo = encima ?? gen
  const nEnBarra = idx.densidad.get(activo) ?? 0
  const iSinFecha = barras.findIndex((b) => b.g > gen_sin_fecha)

  return (
    <section className="tiempo" aria-label="Eje de generaciones" ref={caja}>
      <div className="encabezado">
        <div className="hito">
          <span className="rotulo">
            {encima != null && encima !== gen ? 'Al pasar' : 'Generación elegida'}
          </span>
          <p>
            {etiquetaGeneracion(activo, gen_sin_fecha)}{' '}
            <span className="cifra">
              · {nEnBarra.toLocaleString('es')} afirmaci{nEnBarra === 1 ? 'ón' : 'ones'}
            </span>
          </p>
        </div>
        <div className="anio">
          <b>{formatearAnio(anio)}</b>
          <span>
            {anio == null ? 'La teogonía no se data, a propósito' : `según ${autoridad.nombre}`}
          </span>
        </div>
      </div>

      <div className="histo-caja">
        <svg
          className="histo"
          width={ancho}
          height={ALTO}
          viewBox={`0 0 ${ancho} ${ALTO}`}
          aria-hidden="true"
        >
          {/* zona sin fecha: no es que falte el dato, es que no se data */}
          {iSinFecha > 0 && (
            <>
              <rect
                className="zona-sinfecha"
                x={0}
                y={0}
                width={iSinFecha * paso - HUECO / 2}
                height={ALTO - PAD_ABAJO}
              />
              <text className="tick" x={6} y={14}>
                Teogonía, sin fecha
              </text>
            </>
          )}
          {barras.map((b, i) => {
            const h = b.n === 0 ? 0 : Math.max(2, ((ALTO - PAD_ABAJO - 2) * b.n) / max)
            const x = i * paso + HUECO / 2
            const y = ALTO - PAD_ABAJO - h
            const sel = b.g === gen
            const enRango = acumulado ? b.g <= gen : sel
            const clase =
              sel || b.g === encima ? 'barra-sel' : enRango ? 'barra-act' : 'barra-fondo'
            return <path key={b.g} d={barra(x, y, wBarra, h)} className={clase} />
          })}
          <line className="eje" x1={0} y1={ALTO - PAD_ABAJO} x2={ancho} y2={ALTO - PAD_ABAJO} />
          {barras.map((b, i) =>
            b.g % 2 === 0 ? (
              <text
                key={`t${b.g}`}
                className="tick"
                x={i * paso + paso / 2}
                y={ALTO - 1}
                textAnchor="middle"
              >
                {b.g}
              </text>
            ) : null,
          )}
        </svg>
        {/* Dianas: una columna entera por generación, mayor que la barra (guía de
            interacción). Son botones reales pero fuera del tabulador: el slider de
            abajo ya da el mismo control por teclado. */}
        <div className="dianas">
          {barras.map((b) => (
            <button
              key={b.g}
              tabIndex={-1}
              aria-label={`${etiquetaGeneracion(b.g, gen_sin_fecha)}: ${b.n} afirmaciones`}
              onMouseEnter={() => setEncima(b.g)}
              onMouseLeave={() => setEncima(null)}
              onClick={() => onGen(b.g)}
            />
          ))}
        </div>
      </div>

      <input
        type="range"
        min={gen_min}
        max={gen_max}
        step={1}
        value={gen}
        onChange={(e) => onGen(Number(e.target.value))}
        aria-label="Generación mítica"
        aria-valuetext={`${etiquetaGeneracion(gen, gen_sin_fecha)}, ${formatearAnio(anio)}`}
      />

      <div className="pie">
        <span>
          <span className="cifra">{nLugares.toLocaleString('es')}</span> lugares
        </span>
        <span>
          <span className="cifra">{nAfirmaciones.toLocaleString('es')}</span> afirmaciones en el
          mapa
          {nDivinas > 0 ? (
            <>
              {' '}
              (<span className="cifra">{nDivinas.toLocaleString('es')}</span> de divinidades, que no
              tienen generación)
            </>
          ) : acumulado ? (
            ', acumuladas'
          ) : null}
        </span>
        <span>
          <span className="cifra">{nDisputas.toLocaleString('es')}</span> ubicaciones en disputa
        </span>
        <span className="fuente-anio">
          {autoridad.nombre} sitúa Troya en {Math.abs(autoridad.troya)} a.C. ·{' '}
          {idx.meta.anios_por_generacion} años por generación
        </span>
      </div>
      <p className="pie-movil">
        <span className="cifra">{nLugares.toLocaleString('es')}</span> lugares ·{' '}
        <span className="cifra">{nAfirmaciones.toLocaleString('es')}</span> afirmaciones ·{' '}
        <span className="cifra">{nDisputas.toLocaleString('es')}</span> en disputa
      </p>
    </section>
  )
}
