import { useEffect, useMemo, useRef, useState } from 'react'

import { anioDe, etiquetaGeneracion, formatearAnio, type Indice } from './datos'
import type { Autoridad } from './types'

const ALTO = 54
const PAD_ABAJO = 13
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
    <section className="tiempo" aria-label="eje temporal" ref={caja}>
      <div className="encabezado">
        <span className="titulo">afirmaciones por generacion</span>
        <span style={{ fontSize: 12.5, color: 'var(--tinta-2)' }}>
          {etiquetaGeneracion(activo, gen_sin_fecha)}
          {encima != null && encima !== gen ? ' (al pasar)' : ''} ·{' '}
          <span className="cifra">{nEnBarra.toLocaleString('es')}</span>
        </span>
        <span className="anio">
          <b>{formatearAnio(anio)}</b>
          <span>
            {anio == null
              ? 'la teogonia no se datea, a proposito'
              : `segun ${autoridad.nombre}`}
          </span>
        </span>
      </div>

      <svg
        className="histo"
        width={ancho}
        height={ALTO}
        viewBox={`0 0 ${ancho} ${ALTO}`}
        role="img"
        aria-label={`densidad de afirmaciones por generacion, de ${gen_min} a ${gen_max}`}
      >
        {/* zona sin fecha: no es que falte el dato, es que no se datea */}
        {iSinFecha > 0 && (
          <>
            <rect
              className="zona-sinfecha"
              x={0}
              y={0}
              width={iSinFecha * paso - HUECO / 2}
              height={ALTO - PAD_ABAJO}
            />
            <text className="tick" x={5} y={11}>
              teogonía · no se datea
            </text>
          </>
        )}
        {barras.map((b, i) => {
          const h = b.n === 0 ? 0 : Math.max(2, ((ALTO - PAD_ABAJO - 2) * b.n) / max)
          const x = i * paso + HUECO / 2
          const y = ALTO - PAD_ABAJO - h
          const sel = b.g === gen
          const enRango = acumulado ? b.g <= gen : sel
          return (
            <g key={b.g}>
              <path
                d={barra(x, y, wBarra, h)}
                className={sel ? 'barra-sel' : enRango ? 'barra-act' : 'barra-fondo'}
              />
              {/* diana mas grande que la marca, como pide la guia de interaccion */}
              <rect
                className="diana"
                x={i * paso}
                y={0}
                width={paso}
                height={ALTO}
                onMouseEnter={() => setEncima(b.g)}
                onMouseLeave={() => setEncima(null)}
                onClick={() => onGen(b.g)}
              />
            </g>
          )
        })}
        <line className="eje" x1={0} y1={ALTO - PAD_ABAJO} x2={ancho} y2={ALTO - PAD_ABAJO} />
        {barras.map((b, i) =>
          b.g % 2 === 0 ? (
            <text
              key={`t${b.g}`}
              className="tick"
              x={i * paso + paso / 2}
              y={ALTO - 3}
              textAnchor="middle"
            >
              {b.g}
            </text>
          ) : null,
        )}
      </svg>

      <input
        type="range"
        min={gen_min}
        max={gen_max}
        step={1}
        value={gen}
        onChange={(e) => onGen(Number(e.target.value))}
        aria-label="generacion mitica"
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
              (con <span className="cifra">{nDivinas.toLocaleString('es')}</span> de divinidades,
              que no están en ninguna generación)
            </>
          ) : acumulado ? (
            ', acumuladas'
          ) : null}
        </span>
        <span>
          <span className="cifra">{nDisputas.toLocaleString('es')}</span> ubicaciones en disputa
        </span>
        <span style={{ marginLeft: 'auto' }}>
          {autoridad.nombre} sitúa Troya en {Math.abs(autoridad.troya)} a.C. ·{' '}
          {idx.meta.anios_por_generacion} años por generación
        </span>
      </div>
    </section>
  )
}
