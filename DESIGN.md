---
version: 1
name: Periégesis
description: "Herramienta de exploración del mito griego sobre el mapa. Papel neutro #f3f3f0, tinta azul-negra #16181d, magnitud en una rampa ordinal de tinta ferrogálica y un solo color que significa algo más: la rúbrica #b3301d, reservada a los hechos que dos fuentes sitúan en lugares distintos. Alegreya para nombres y citas, Alegreya Sans para la interfaz; esquinas rectas, superficies separadas por escalón de tono y filete de 1 px en paneles. Nunca crema con terracota, nunca versalitas espaciadas como etiqueta, nunca un color decorativo."
surface: herramienta

colors:
  canvas: "#f3f3f0"
  surface-1: "#fbfbf9"
  surface-2: "#e8e8e3"
  ink: "#16181d"
  ink-2: "#3d424b"
  ink-muted: "#5c616b"
  hairline: "#d4d4cd"
  link: "#2f5288"
  rubrica: "#b3301d"
  primary: "#16181d"
  on-primary: "#fbfbf9"
  tinta-1: "#8fa6c4"
  tinta-2: "#5b7aa6"
  tinta-3: "#2f5288"
  tinta-4: "#13305e"
  lazo-familia: "#2a78d6"
  lazo-violencia: "#c98a00"
  lazo-sagrado: "#159a6c"

  dark-canvas: "#15171c"
  dark-surface-1: "#1c1f25"
  dark-surface-2: "#272b33"
  dark-ink: "#ecebe6"
  dark-ink-2: "#c4c6cc"
  dark-ink-muted: "#9ca1ab"
  dark-hairline: "#343944"
  dark-link: "#8eacd6"
  dark-rubrica: "#ec6b54"
  dark-primary: "#c4c6cc"
  dark-on-primary: "#15171c"
  dark-tinta-1: "#3f5f8f"
  dark-tinta-2: "#5f82b4"
  dark-tinta-3: "#8eacd6"
  dark-tinta-4: "#c3d4ec"
  dark-lazo-familia: "#3987e5"
  dark-lazo-violencia: "#c98500"
  dark-lazo-sagrado: "#199e70"

typography:
  brand:
    fontFamily: Alegreya
    fontSize: 22px
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: -0.01em
  heading:
    fontFamily: Alegreya
    fontSize: 18px
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: 0
  body:
    fontFamily: Alegreya Sans
    fontSize: 15px
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: 0
  small:
    fontFamily: Alegreya Sans
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: 0
  label:
    fontFamily: Alegreya Sans
    fontSize: 12px
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: 0

spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px

rounded:
  none: 0px
  pill: 9999px

components:
  chip:
    backgroundColor: "{colors.surface-1}"
    textColor: "{colors.ink-2}"
    typography: "{typography.small}"
    rounded: "{rounded.none}"
    padding: 4px 8px
  chip-pressed:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
  input:
    backgroundColor: "{colors.surface-1}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    padding: 8px 10px
  panel:
    backgroundColor: "{colors.surface-1}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: 16px
---

# Periégesis — sistema de diseño

> Generado con la skill `design-md`. Manda sobre el manifiesto en todo lo visual (precedencia §0).

## Overview

Periégesis es el explorador web de la base `greek`: 1.104 lugares, 816 figuras, 9.937 afirmaciones
citadas y 3.409 disputas de ubicación, sobre un mapa y un eje de generaciones míticas. El nombre es
el de la obra de Pausanias, que describe Grecia lugar por lugar y, en cada sitio, recoge lo que
cuentan los de allí aunque contradiga a los del pueblo vecino. Eso es exactamente lo que hace la
herramienta: no da una versión canónica del mito, enseña dónde lo sitúa cada fuente.

**La idea:** en esta interfaz, *la rúbrica de los manuscritos —el minio rojo con que el copista
señalaba lo que había que notar— se convierte en la marca de la disputa*: lo único rojo en toda la
pantalla son los hechos que dos fuentes sitúan en lugares distintos. La magnitud va en la tinta
ferrogálica azul-negra con la que esos mismos manuscritos están escritos. Una página de códice:
papel, tinta y rúbrica.

**Superficie: herramienta.** Se usa mil veces, rápido. Densidad compacta, cifras tabulares, estados
claros, nada decorativo. Las líneas de 1 px se permiten para separar paneles y filas de tabla.

## Colors

Solo dos cosas tienen color propio, y las dos codifican dato:

- **tinta-1…4** — rampa ordinal de un solo tono (afirmaciones por lugar: 1–2, 3–6, 7–19, 20+).
  Validada con `validate_palette.js --ordinal`: monótona, saltos ≥ 0,06 L, el paso claro a 2,24:1
  contra el papel (suelo 2:1).
- **rubrica** `#b3301d` — disputa de ubicación: líneas en el mapa, aviso en el panel, conmutador
  «en disputa». Validada contra los cuatro pasos de la rampa porque conviven en el mismo lienzo:
  peor par CVD ΔE 16,6 (claro) y 14,7 (oscuro), objetivo ≥ 8.

- **lazo-familia / lazo-violencia / lazo-sagrado** — solo en la vista de relaciones: la
  familia del vínculo (parentesco; violencia; lo sagrado; los demás tratos en ink-muted). La
  clase va en la forma de la línea (onda, zigzag, onda cuadrada, bucles, doble, chevrones,
  espina, raya, punto), no en un cuarto tono: con siete tonos ninguna
  paleta pasa todos los pares con daltonismo, porque las líneas salen juntas del centro. Los
  tres validados `--pairs all` con la rúbrica en claro (peor CVD ΔE 8,1, normal 19,8) y entre
  sí en oscuro (CVD 8,4). En oscuro la rúbrica cae cerca del ámbar (CVD 4,3): por eso la
  disputa en esa vista es un rombo a media línea, forma propia, nunca el color de la línea.
  El grosor dice cuántas fuentes lo afirman; «otras relaciones» va en ink-muted.

### Brand & Accent
- **primary** es la tinta: el estado «activado» de un chip o conmutador se dibuja en negativo
  (fondo tinta, texto papel). En oscuro el negativo usa ink-2 (`#c4c6cc`), no la tinta plena:
  con `#ecebe6` los conmutadores activos eran bloques blancos que dominaban el lateral. No hay un color de marca aparte: la marca es el papel y la tinta.
- **link** `#2f5288` (= tinta-3) — enlaces a pasajes y fichas externas.

### Surface
- **canvas** → **surface-1** → **surface-2**: el lateral y el panel van en surface-1 sobre el canvas;
  hover y fondos de aviso en surface-2.
- El mapa raster de OSM se lleva a gris (`grayscale`) y se aclara: es el papel sobre el que va la
  tinta, no compite en color.

### Text
- **ink** para todo texto corrido y nombres. **ink-2** para descripciones. **ink-muted** solo para
  notas, rótulos de eje y metadatos. Contraste medido: ink-muted 5,59:1 sobre canvas, 5,06:1 sobre
  surface-2; en oscuro 6,92 y 5,47.
- El texto nunca lleva el color de la serie: la cifra de un chip va en tinta, no en azul.

### Semantic
- No hay success/warning/danger: la herramienta no tiene estados de operación. La rúbrica es dato,
  no alarma.

### Dark mode
Diseñado, no invertido. Tokens `dark-*` del frontmatter, aplicados bajo
`@media (prefers-color-scheme: dark)` (si no hay `data-theme='light'`) y bajo
`[data-theme='dark']`. La rampa se invierte **por rol**: sobre fondo oscuro «más» es más claro,
validada aparte contra `#15171c`. El raster se invierte y se pasa a gris
(`invert grayscale brightness`). `color-scheme: dark` y `<meta name="theme-color">` por esquema.

## Typography

### Font Family
**Alegreya** (nombres, títulos, citas) y **Alegreya Sans** (interfaz, cifras): una superfamilia
literaria con griego politónico (`greek-ext`), imprescindible porque los nombres llegan como
`Κίρκη` o `Ἀχιλλεύς`. Google Fonts, `display=swap`, fallback `Georgia, serif` / `system-ui`.
Cifras siempre `lining-nums tabular-nums` (Alegreya usa elzevirianas por defecto).

### Hierarchy
| Rol | Tamaño | Peso | Interlineado | Tracking | Uso |
| --- | --- | --- | --- | --- | --- |
| brand | 22px | 700 | 1.1 | −0.01em | Marca y el año del eje |
| heading | 18px | 600 | 1.25 | 0 | Nombre del lugar en el panel |
| body | 15px | 400 | 1.45 | 0 | Afirmaciones, controles |
| small | 13px | 400 | 1.4 | 0 | Chips, citas, descripciones |
| label | 12px | 500 | 1.3 | 0 | Rótulos de grupo, ejes, metadatos |

### Principles
- Cinco tamaños, ninguno por debajo de 12 px.
- Sentence case en todo, también en los rótulos de grupo («Quién», «Qué»). Sin versalitas espaciadas.
- `tabular-nums` en cifras comparables: recuentos de chips, años, generaciones, pie del eje.

## Layout

### Spacing System
4 / 8 / 16 / 24 / 32. Dentro de un control 4–8; entre controles 8; entre grupos del lateral 24;
margen de los paneles 16.

### Grid & Container
Escritorio: dos columnas a toda altura — **lateral** de 300 px (marca, búsqueda, cronología,
vista, quién, qué) y **lienzo** (mapa arriba, eje de tiempo abajo). El panel de detalle flota sobre
el borde derecho del mapa. Un eje de texto a 16 px en el lateral y en el eje de tiempo.

### Whitespace Philosophy
El mapa es el contenido: todo lo demás cede espacio. Ninguna barra horizontal sobre el mapa.

## Elevation & Depth
Plano. Solo flotan de verdad el panel de detalle, la leyenda, el tooltip y el cajón móvil; llevan
filete de 1 px y una sombra corta tintada de tinta (`--sombra`).

## Shapes
Radio **0** en todo lo rectangular: chips, botones, campos, paneles. Es la página impresa. Los
marcadores del mapa son círculos (son datos, no forma de interfaz); el pulgar del slider también.

## Imagery
Ninguna. La única imagen es el raster de OpenStreetMap (ODbL), con atribución obligatoria en el
mapa junto a MANTO (CC BY-NC) y Pleiades (CC BY).

## Motion
120–180 ms, ease-out, solo `transform`/`opacity`/color: apertura del cajón móvil y del panel,
hover de chips. Todo desactivado con `prefers-reduced-motion: reduce`.

## Components

### Buttons
- **Chip** (filtro): papel con filete; activado en negativo (tinta/papel). Cifra en tabular.
- **Conmutador** (acumulado, divinidades, en disputa): mismo patrón que el chip, con la muestra de
  color del dato que activa (tinta-3 para divinidades, rúbrica para disputas).
- Estados: hover sube a surface-2; focus-visible anillo de 2 px en tinta con offset 2; pressed en
  negativo; activo `translateY(1px)`.
- Área mínima 32 px en escritorio, 44 px en táctil.

### Inputs & Forms
Búsqueda y select con `<label>` visible, filete, radio 0, foco con el mismo anillo.

### Navigation
No hay navegación: es una sola vista. La URL (hash) guarda todo el estado y es compartible.

### Panel de detalle
Nombre en Alegreya 18, metadatos en label, enlaces externos como texto subrayado (no pastillas).
Cada afirmación: figura (Alegreya 600), predicado, flags de incertidumbre **siempre con texto**,
citas con `§` en ink-muted.

### Eje de tiempo
Histograma de barras en la rampa (fondo tinta-1, rango tinta-3, seleccionada tinta-4), 2 px de
hueco, extremo redondeado 4 px anclado a la base. Año en el rol brand. Slider debajo.

## Do's and Don'ts

### Do
- Un solo color con significado además de la rampa: la rúbrica, y solo para disputas. La
  excepción son los tres tonos de lazo, confinados a las líneas de la vista de relaciones.
- Validar con `validate_palette.js` cualquier cambio de rampa o de rúbrica, en claro y en oscuro.
- Texto junto a todo color: leyenda con rótulos, flags con palabras.
- Recuentos calculados sobre lo exportado, no sobre la base.

### Don't
- Fondo crema con marrón/terracota (la paleta sepia anterior caía ahí).
- Versalitas o mayúsculas con tracking como rótulo de grupo.
- Pastillas redondeadas, radios suaves de 9–16 px.
- Emoji o pictogramas de sol/luna como icono de tema: el botón dice «claro»/«oscuro».
- Un segundo acento decorativo. Si algo no codifica dato, va en tinta.
- Texto por debajo de 12 px.

## Responsive Behavior

### Breakpoints
| Nombre | Ancho | Qué cambia |
| --- | --- | --- |
| phone | ≤ 900 | Lateral → cajón a pantalla completa tras el botón «Filtros»; barra superior de 56 px con marca y botón; panel como hoja inferior |
| tablet | 768 | Igual que phone (el lateral de 300 px dejaba el mapa en 468 px) |
| desktop | > 900 | Lateral fijo de 300 px + lienzo |

### Touch Targets
44 × 44 px en táctil (`pointer: coarse`): chips, conmutadores, cerrar, enlaces del panel.

### Collapsing Strategy
El móvil no apila el escritorio: el mapa ocupa todo lo que hay entre la barra y el eje de tiempo, y
los filtros viven en un cajón que se abre encima. El botón «Filtros» dice cuántos hay activos.

## Iteration Guide
- ¿Nuevo control? Reutiliza `.chip`/`.conmutador`; nunca un color literal: `drift` lo detecta.
- ¿Cambiar la marca? `colors.primary` y `typography.brand`.
- ¿Cambiar un color de dato? Rampa y rúbrica, y vuelve a pasar el validador en los dos modos.
- Regenera `web/src/tokens.css` con `design.mjs tokens DESIGN.md --out web/src/tokens.css`.

## Known Gaps
- **Los lugares solo se eligen con puntero.** Los marcadores van en canvas (`preferCanvas`, por
  rendimiento con 1.100 puntos) y no son focusables. Por teclado se llega a todo menos a abrir el
  detalle de un lugar; la alternativa sería una lista de lugares visibles en el lateral.
- Las teselas de OSM son raster con rótulos en varias escrituras; el filtro gris las calma pero no
  las controla. Un estilo vectorial propio queda fuera de alcance (exige servidor de teselas).
- Leaflet inyecta `<img>` sin `width`/`height`: el WARN de CLS de `visual-qa` sobre las teselas no
  es corregible desde la app (van posicionadas en absoluto y no desplazan el layout).
