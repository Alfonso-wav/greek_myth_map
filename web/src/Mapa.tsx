import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect, useRef, useState } from 'react'

import { pasoEscala, radio, type Indice, type Visible } from './datos'
import type { Contradiccion, Lugar } from './types'

/** Atribucion obligatoria: ODbL para OSM, CC BY-NC para MANTO. */
const ATRIBUCION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · ' +
  'datos <a href="https://www.manto-myth.org">MANTO</a> CC BY-NC · ' +
  '<a href="https://pleiades.stoa.org">Pleiades</a> CC BY'

function variable(nombre: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(nombre).trim()
}

/** Cambia cada vez que cambia el esquema de color (atributo data-theme o el del
 *  sistema). Los marcadores van en canvas y leen los colores de las variables CSS
 *  al pintarse: sin esto, al cambiar de tema conservaban la rampa del anterior. */
function useEsquema(): number {
  const [version, setVersion] = useState(0)
  useEffect(() => {
    const subir = () => setVersion((v) => v + 1)
    const mq = matchMedia('(prefers-color-scheme: dark)')
    mq.addEventListener('change', subir)
    const mo = new MutationObserver(subir)
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => {
      mq.removeEventListener('change', subir)
      mo.disconnect()
    }
  }, [])
  return version
}

interface Props {
  idx: Indice
  visible: Visible
  contradicciones: Contradiccion[]
  seleccion: number | null
  onSeleccion: (id: number | null) => void
}

export default function Mapa({ idx, visible, contradicciones, seleccion, onSeleccion }: Props) {
  const div = useRef<HTMLDivElement>(null)
  const mapa = useRef<L.Map | null>(null)
  const capaLugares = useRef<L.LayerGroup | null>(null)
  const capaDisputas = useRef<L.LayerGroup | null>(null)
  const esquema = useEsquema()

  useEffect(() => {
    if (!div.current || mapa.current) return
    // preferCanvas: con 1.100 marcadores el renderer SVG de Leaflet se arrastra
    const m = L.map(div.current, { preferCanvas: true, zoomControl: true }).setView(
      [38.5, 23.5],
      6,
    )
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18,
      attribution: ATRIBUCION,
    }).addTo(m)
    capaDisputas.current = L.layerGroup().addTo(m)
    capaLugares.current = L.layerGroup().addTo(m)
    m.on('click', () => onSeleccion(null))
    mapa.current = m
    return () => {
      m.remove()
      mapa.current = null
    }
    // onSeleccion es estable (useCallback en App); el mapa se crea una sola vez
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // --- lineas de contradiccion, debajo de los lugares
  useEffect(() => {
    const capa = capaDisputas.current
    if (!capa) return
    capa.clearLayers()
    const rubrica = variable('--rubrica')
    for (const c of contradicciones) {
      const a = idx.lugares.get(c.l[0])
      const b = idx.lugares.get(c.l[1])
      if (!a || !b) continue
      // Son cientos y cruzan el Mediterraneo de punta a punta: en reposo van
      // tenues para no tapar los lugares, y solo se destacan las del lugar
      // seleccionado. Asi la capa informa sin dominar el lienzo.
      const tocaSeleccion = seleccion != null && (a.id === seleccion || b.id === seleccion)
      L.polyline(
        [
          [a.lat, a.lng],
          [b.lat, b.lng],
        ],
        {
          color: rubrica,
          weight: tocaSeleccion ? 2.5 : 1.5,
          opacity: tocaSeleccion ? 0.95 : seleccion != null ? 0.2 : 0.5,
          dashArray: '5 4',
          interactive: true,
        },
      )
        .bindTooltip(
          `<b>Versiones incompatibles</b><i>${escapar(c.d)}</i><span>${escapar(a.n)} · ${escapar(b.n)}</span>`,
          { className: 'pista', sticky: true },
        )
        .addTo(capa)
    }
  }, [contradicciones, idx, seleccion, esquema])

  // --- lugares
  useEffect(() => {
    const capa = capaLugares.current
    if (!capa) return
    capa.clearLayers()
    const pasos = [1, 2, 3, 4].map((i) => variable(`--m${i}`))
    const superficie = variable('--superficie')

    for (const { lugar, n, divino } of visible.lugares) {
      const paso = pasoEscala(n)
      const elegido = lugar.id === seleccion
      L.circleMarker([lugar.lat, lugar.lng], {
        radius: radio(n) * (elegido ? 1.35 : 1),
        // anillo de 2px del color de la superficie: separa marcadores solapados
        color: elegido ? variable('--tinta') : superficie,
        weight: 2,
        fillColor: pasos[paso - 1],
        fillOpacity: divino ? 0.55 : 0.9,
        // 'rough' puede ser el centroide de una caja de 100 km: se dibuja
        // discontinuo para no vender precision que no hay
        dashArray: lugar.prec === 'rough' ? '3 3' : undefined,
      })
        .bindTooltip(pista(lugar, n), { className: 'pista', direction: 'top' })
        .on('click', (e) => {
          L.DomEvent.stopPropagation(e)
          onSeleccion(lugar.id)
        })
        .addTo(capa)
    }
  }, [visible, seleccion, onSeleccion, esquema])

  return <div ref={div} className="mapa" />
}

function escapar(s: string): string {
  return s.replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`)
}

function pista(l: Lugar, n: number): string {
  const detalle = [l.t, l.mod && l.mod !== l.n ? `hoy ${l.mod}` : null, l.pais]
    .filter(Boolean)
    .join(' · ')
  const nota = l.prec === 'rough' ? ' · ubicación aproximada' : ''
  return (
    `<b>${escapar(l.n)}</b>` +
    `<i>${escapar(detalle)}${nota}</i>` +
    `<span>${n} afirmaci${n === 1 ? 'ón' : 'ones'}</span>`
  )
}
