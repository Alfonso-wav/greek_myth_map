/** Geometría de los trazos de la vista de relaciones. Cada clase de vínculo tiene
 *  una forma propia además del tono: el color solo distingue tres familias (más
 *  no pasan el validador de daltonismo con todas las líneas juntas), la forma
 *  distingue el subtipo y se lee igual en gris, impreso o con daltonismo.
 *
 *  Raya, punto y raya-punto son la misma recta con `stroke-dasharray` (CSS); el
 *  resto se dibuja aquí como trazado SVG en coordenadas locales de la línea —x a
 *  lo largo, y perpendicular— y se gira al final. */

export type Forma =
  | 'recta'
  | 'raya'
  | 'punto'
  | 'rayapunto'
  | 'onda'
  | 'zigzag'
  | 'cuadrada'
  | 'bucles'
  | 'doble'
  | 'chevrones'
  | 'espina'

/** Longitud de un ciclo del motivo y su semiamplitud, en px. */
const PERIODO = 12
const AMP = 3

type P = [number, number]

/** Motivo entre x = 0 y x = L, como lista de subtrazados (la mayoría, uno). */
function motivo(forma: Forma, L: number): P[][] {
  switch (forma) {
    case 'onda': {
      const pts: P[] = []
      for (let x = 0; x <= L; x += 1) pts.push([x, AMP * Math.sin((2 * Math.PI * x) / PERIODO)])
      return [pts]
    }
    case 'zigzag': {
      // onda triangular: cuartos de periodo alternando 0, +A, 0, −A
      const pts: P[] = []
      const ys = [0, AMP, 0, -AMP]
      for (let i = 0, x = 0; x <= L; i++, x = (i * PERIODO) / 4) pts.push([x, ys[i % 4]])
      return [pts]
    }
    case 'cuadrada': {
      const pts: P[] = [[0, AMP]]
      let y = AMP
      for (let x = PERIODO / 2; x <= L; x += PERIODO / 2) {
        pts.push([x, y])
        y = -y
        pts.push([x, y])
      }
      pts.push([L, y])
      return [pts]
    }
    case 'bucles': {
      // trocoide prolata: con b > a la curva se cruza y hace un rizo por ciclo
      const a = PERIODO / (2 * Math.PI)
      const b = 2.2 * a
      // arranca en t = π/2, donde y = 0, para empalmar con el tramo recto
      const x0 = (a * Math.PI) / 2 - b
      const pts: P[] = []
      for (let t = Math.PI / 2; ; t += 0.15) {
        const x = a * t - b * Math.sin(t) - x0
        if (x > L) break
        pts.push([x, b * Math.cos(t)])
      }
      return [pts]
    }
    case 'doble':
      return [
        [
          [0, -1.8],
          [L, -1.8],
        ],
        [
          [0, 1.8],
          [L, 1.8],
        ],
      ]
    case 'chevrones': {
      // «>» abiertos que apuntan hacia fuera, sobre la recta
      const subs: P[][] = [
        [
          [0, 0],
          [L, 0],
        ],
      ]
      for (let x = PERIODO; x <= L; x += PERIODO)
        subs.push([
          [x - 4, -AMP],
          [x, 0],
          [x - 4, AMP],
        ])
      return subs
    }
    case 'espina': {
      // puntadas perpendiculares, como una vía o una costura
      const subs: P[][] = [
        [
          [0, 0],
          [L, 0],
        ],
      ]
      for (let x = PERIODO / 2; x <= L; x += PERIODO / 1.5)
        subs.push([
          [x, -AMP],
          [x, AMP],
        ])
      return subs
    }
    default:
      return [
        [
          [0, 0],
          [L, 0],
        ],
      ]
  }
}

const r1 = (n: number) => Math.round(n * 10) / 10

/** Trazado `d` de (x1,y1) a (x2,y2). El motivo empieza a `desde` px del origen y
 *  acaba a `hasta` px del final: junto al centro todas las líneas convergen y una
 *  onda allí es un borrón, así que ese tramo va recto. */
export function trazado(
  forma: Forma,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  desde = 0,
  hasta = 0,
): string {
  const dx = x2 - x1
  const dy = y2 - y1
  const largo = Math.hypot(dx, dy)
  if (largo < 1) return ''
  const c = dx / largo
  const s = dy / largo
  const fuera = (x: number, y: number) => `${r1(x1 + x * c - y * s)},${r1(y1 + x * s + y * c)}`

  const ini = Math.min(desde, largo)
  const fin = Math.max(ini, largo - hasta)
  const partes: string[] = []
  // tramos rectos de entrada y salida, solo si el motivo no es ya una recta
  const recto = forma === 'recta' || forma === 'raya' || forma === 'punto' || forma === 'rayapunto'
  if (recto) return `M${fuera(0, 0)}L${fuera(largo, 0)}`
  if (ini > 0) partes.push(`M${fuera(0, 0)}L${fuera(ini, 0)}`)
  for (const sub of motivo(forma, fin - ini)) {
    partes.push(sub.map(([x, y], i) => `${i ? 'L' : 'M'}${fuera(ini + x, y)}`).join(''))
  }
  if (fin < largo) partes.push(`M${fuera(fin, 0)}L${fuera(largo, 0)}`)
  return partes.join('')
}
