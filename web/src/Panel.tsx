import { useEffect } from 'react'

import { anioDe, formatearAnio, type Indice } from './datos'
import type { Afirmacion, Autoridad, Contradiccion } from './types'

interface Props {
  idx: Indice
  lugarId: number
  afirmaciones: Afirmacion[]
  contradicciones: Contradiccion[]
  autoridad: Autoridad
  onCerrar: () => void
}

export default function Panel({
  idx,
  lugarId,
  afirmaciones,
  contradicciones,
  autoridad,
  onCerrar,
}: Props) {
  // Escape cierra el panel, salvo que el cajón móvil esté abierto encima: ahí
  // Escape es del cajón
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !document.querySelector('.app.cajon-abierto')) onCerrar()
    }
    addEventListener('keydown', tecla)
    return () => removeEventListener('keydown', tecla)
  }, [onCerrar])

  const lugar = idx.lugares.get(lugarId)
  if (!lugar) return null

  const propias = afirmaciones.filter((a) => a.l === lugarId)

  // Deduplicado por (figura, predicado, el otro lugar): `contradiccion` guarda un
  // par de relaciones por CADA combinacion de fuentes que discrepan, asi que la
  // misma disputa aparecia siete veces seguidas en la tabla.
  const disputas = (() => {
    const vistas = new Set<string>()
    const out: { c: Contradiccion; otro: number | undefined }[] = []
    for (const c of contradicciones) {
      if (!c.l.includes(lugarId)) continue
      const otro = c.l.find((x) => x !== lugarId)
      const llave = `${c.sobre}|${c.pe}|${otro}`
      if (vistas.has(llave)) continue
      vistas.add(llave)
      out.push({ c, otro })
    }
    return out
  })()
  const detalle = [lugar.t, lugar.mod && lugar.mod !== lugar.n ? `hoy ${lugar.mod}` : null, lugar.pais]
    .filter(Boolean)
    .join(' · ')

  return (
    <aside className="panel" aria-label={`Detalle de ${lugar.n}`}>
      <header>
        <div>
          <h2>{lugar.n}</h2>
          <div className="sub">
            {detalle}
            {' · '}
            <span className="cifra">
              {lugar.lat.toFixed(3)}, {lugar.lng.toFixed(3)}
            </span>
          </div>
          {lugar.enl.length > 0 && (
            <div className="enlaces">
              {lugar.enl.map((e) => (
                <a key={e.u} href={e.u} target="_blank" rel="noopener noreferrer">
                  {e.k}
                </a>
              ))}
            </div>
          )}
        </div>
        <button className="cerrar" onClick={onCerrar} aria-label="Cerrar detalle">
          ×
        </button>
      </header>

      <div className="cuerpo">
        {lugar.prec === 'rough' && (
          <p className="aviso">
            Ubicación aproximada: Pleiades marca esta coordenada como <b>rough</b>, que puede
            ser el centroide de una caja de hasta 100 km.
            {lugar.pm ? ` Precisión declarada: ${lugar.pm.toLocaleString('es')} m.` : ''}
          </p>
        )}
        {lugar.fic === 1 && (
          <p className="aviso">
            Lugar legendario sin ubicación real. La coordenada es una identificación
            tradicional, no un hecho.
          </p>
        )}

        {disputas.length > 0 && (
          <>
            <p className="aviso disputa">
              <b>
                {disputas.length} {disputas.length === 1 ? 'hecho situado' : 'hechos situados'}{' '}
                también en otro lugar
              </b>{' '}

              según otra fuente. Ninguna versión es la correcta: se guardan todas.
            </p>
            <div className="tabla-envoltura">
              <table>
                <thead>
                  <tr>
                    <th>Hecho</th>
                    <th>La otra versión lo sitúa en</th>
                  </tr>
                </thead>
                <tbody>
                  {disputas.slice(0, 8).map(({ c, otro }) => (
                    <tr key={c.id}>
                      <td>
                        {c.sobre} · {c.pe}
                      </td>
                      <td>
                        {(otro != null && idx.lugares.get(otro)?.n) || '—'}
                      </td>
                    </tr>
                  ))}
                  {disputas.length > 8 && (
                    <tr>
                      <td colSpan={2} className="mas">
                        y {disputas.length - 8} más
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}

        {propias.length === 0 ? (
          <p className="aviso vacio">
            Nada atestiguado aquí con la generación y los filtros elegidos. Prueba a mover el eje o a
            activar «Acumular generaciones anteriores».
          </p>
        ) : (
          propias.map((a, i) => {
            const ag = idx.agentes.get(a.s)
            const anio = anioDe(autoridad, a.g, idx.meta.gen_sin_fecha)
            return (
              <article className="afirm" key={`${a.s}-${a.pk}-${i}`}>
                <div className="cabeza">
                  {ag?.enl?.length ? (
                    <a
                      className="quien"
                      href={ag.enl[0].u}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={`${ag.n} en ${ag.enl[0].k}${ag.d ? ` — ${ag.d}` : ''}`}
                    >
                      {ag.n}
                    </a>
                  ) : (
                    <span className="quien" title={ag?.d ?? undefined}>
                      {ag?.n ?? '—'}
                    </span>
                  )}
                  {ag?.grc && (
                    <span className="grc" lang="grc" translate="no">
                      {ag.grc}
                    </span>
                  )}
                  <span className="gen">
                    {ag?.div ? 'Divinidad' : `Gen. ${a.g > 0 ? '+' : ''}${a.g}`}
                    {ag?.div ? '' : ` · ${formatearAnio(anio)}`}
                  </span>
                </div>
                <div className="que">
                  {a.pe}
                  {a.obj ? <> · {a.obj}</> : null}
                  {a.rol ? <span className="rol"> ({a.rol} este lugar)</span> : null}
                </div>

                {a.inc || a.duda || a.impl || a.alt ? (
                  <div className="marcas">
                    {a.duda === 1 && <em>la fuente duda</em>}
                    {a.inc === 1 && <em>dato incierto</em>}
                    {a.impl === 1 && <em>implícito, no dicho</em>}
                    {a.alt === 1 && <em>la fuente da alternativas</em>}
                  </div>
                ) : null}

                {a.ci.length > 0 ? (
                  <ul className="citas">
                    {a.ci.map((c) => (
                      <li key={c.t}>
                        {/* el enlace lleva al pasaje exacto en Perseus/Scaife. La
                            mitad de las obras citadas (Estrabón, Plinio, Diodoro,
                            escolios) no tiene CTS URN y ahí no hay enlace posible:
                            se deja el texto, nunca una URL que no resuelve. */}
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
                    ))}
                    {a.nci > a.ci.length && (
                      <li className="mas">
                        y {a.nci - a.ci.length}{' '}
                        {a.nci - a.ci.length === 1 ? 'pasaje más' : 'pasajes más'}
                      </li>
                    )}
                  </ul>
                ) : (
                  <p className="sin-cita">Sin pasaje textual que lo atestigüe</p>
                )}
              </article>
            )
          })
        )}
      </div>
    </aside>
  )
}
