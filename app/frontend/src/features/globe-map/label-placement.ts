import type * as maplibregl from "maplibre-gl"

// Station labels sit beside their dot on whichever side stays on screen, clear of the map
// controls and the trip sheet, off other labels and, where possible, off the route line.

type Rect = { left: number; top: number; right: number; bottom: number }
type Point = [number, number]
export type LabelTarget = { marker: maplibregl.Marker; tag: HTMLElement }

type Place = { name: string; align: "start" | "center" | "end"; x: (w: number) => number; y: (h: number) => number }
const GAP = 13
const DIAGONAL = 9
const SLIDE = 10
// In order of preference when several sides are equally clear.
const PLACES: Place[] = [
  { name: "right", align: "start", x: () => GAP, y: (h) => -h / 2 },
  { name: "left", align: "end", x: (w) => -GAP - w, y: (h) => -h / 2 },
  { name: "below", align: "center", x: (w) => -w / 2, y: () => GAP },
  { name: "above", align: "center", x: (w) => -w / 2, y: (h) => -GAP - h },
  { name: "below-right", align: "start", x: () => DIAGONAL, y: () => DIAGONAL },
  { name: "below-left", align: "end", x: (w) => -DIAGONAL - w, y: () => DIAGONAL },
  { name: "above-right", align: "start", x: () => DIAGONAL, y: (h) => -DIAGONAL - h },
  { name: "above-left", align: "end", x: (w) => -DIAGONAL - w, y: (h) => -DIAGONAL - h },
  // Slid along a side, so the label's top or bottom rather than its middle is level with the dot.
  { name: "right-up", align: "start", x: () => GAP, y: (h) => SLIDE - h },
  { name: "right-down", align: "start", x: () => GAP, y: () => -SLIDE },
  { name: "left-up", align: "end", x: (w) => -GAP - w, y: (h) => SLIDE - h },
  { name: "left-down", align: "end", x: (w) => -GAP - w, y: () => -SLIDE },
]
const OBSTACLES = [".map-controls", ".travel-sheet", ".map-sheet-toggle", ".map-warning"]
const MARGIN = 6
// Score weights, per square pixel for areas and per pixel of covered track: leaving the visible map
// or hiding under UI costs most, then covering another label or station, then covering the route.
// Switching sides must win by HYSTERESIS to happen.
const OFFSCREEN = 8, COVERED = 8, CROWDED = 5, DOT = 900, ROUTE = 20, PREFERENCE = 12, HYSTERESIS = 150

const overlap = (a: Rect, b: Rect) =>
  Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left)) * Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top))

/** Length of segment a-b inside the rectangle (Liang-Barsky clipping), so dense and sparse tracks weigh the same. */
function insideLength(a: Point, b: Point, r: Rect): number {
  let t0 = 0, t1 = 1
  const dx = b[0] - a[0], dy = b[1] - a[1]
  const edges: Point[] = [[-dx, a[0] - r.left], [dx, r.right - a[0]], [-dy, a[1] - r.top], [dy, r.bottom - a[1]]]
  for (const [p, q] of edges) {
    if (p === 0) { if (q < 0) return 0; continue }
    const t = q / p
    if (p < 0) { if (t > t1) return 0; t0 = Math.max(t0, t) }
    else { if (t < t0) return 0; t1 = Math.min(t1, t) }
  }
  return (t1 - t0) * Math.hypot(dx, dy)
}

export function placeLabels(map: maplibregl.Map, targets: LabelTarget[], lines: Point[][]) {
  const box = map.getContainer().getBoundingClientRect()
  if (!box.width || !box.height || !targets.length) return
  const visible: Rect = { left: MARGIN, top: MARGIN, right: box.width - MARGIN, bottom: box.height - MARGIN }
  const obstacles: Rect[] = []
  OBSTACLES.forEach((selector) => document.querySelectorAll<HTMLElement>(selector).forEach((el) => {
    const r = el.getBoundingClientRect()
    if (r.width && r.height) obstacles.push({ left: r.left - box.left - MARGIN, top: r.top - box.top - MARGIN, right: r.right - box.left + MARGIN, bottom: r.bottom - box.top + MARGIN })
  }))
  const route = lines.map((line) => line.map((p): Point => { const q = map.project(p); return [q.x, q.y] }))
  const dots = targets.map((t) => map.project(t.marker.getLngLat()))
  const items = targets.map((target, i) => ({ target, i, dot: dots[i], w: target.tag.offsetWidth, h: target.tag.offsetHeight }))
  type Item = (typeof items)[number]
  const rectAt = ({ dot, w, h }: Item, place: Place): Rect => {
    const left = dot.x + place.x(w), top = dot.y + place.y(h)
    return { left, top, right: left + w, bottom: top + h }
  }
  // A little air around each label, so neighbours do not end up touching.
  const padded = (r: Rect): Rect => ({ left: r.left - 4, top: r.top - 4, right: r.right + 4, bottom: r.bottom + 4 })
  const score = (item: Item, rank: number, others: Rect[]) => {
    const { dot, w, h, i } = item
    const r = rectAt(item, PLACES[rank])
    let total = rank * PREFERENCE
    if (dot.x >= 0 && dot.y >= 0 && dot.x <= box.width && dot.y <= box.height) {
      total += (w * h - overlap(r, visible)) * OFFSCREEN
      for (const o of obstacles) total += overlap(r, o) * COVERED
    }
    for (const o of others) total += overlap(r, o) * CROWDED
    const near = padded(r)
    dots.forEach((d, j) => { if (j !== i && d.x > near.left - 6 && d.x < near.right + 6 && d.y > near.top - 6 && d.y < near.bottom + 6) total += DOT })
    for (const line of route) for (let s = 1; s < line.length; s++) total += insideLength(line[s - 1], line[s], near) * ROUTE
    return total
  }

  // Biggest labels (the ones carrying a forecast) choose first. Later passes let every label
  // choose again with all the others in place, so an early pick cannot box a neighbour in.
  const order = [...items].sort((a, b) => b.w * b.h - a.w * a.h)
  const choice = new Map<number, number>()
  for (let pass = 0; pass < 3; pass++) {
    let changed = false
    for (const item of order) {
      const others = order.filter((o) => o !== item && choice.has(o.i)).map((o) => padded(rectAt(o, PLACES[choice.get(o.i)!])))
      const scores = PLACES.map((_, rank) => score(item, rank, others))
      let best = scores.indexOf(Math.min(...scores))
      const previous = choice.get(item.i) ?? PLACES.findIndex((place) => place.name === item.target.tag.dataset.place)
      if (previous >= 0 && scores[previous] - scores[best] < HYSTERESIS) best = previous
      if (choice.get(item.i) !== best) changed = true
      choice.set(item.i, best)
    }
    if (!changed) break
  }

  for (const item of items) {
    const place = PLACES[choice.get(item.i)!]
    item.target.tag.dataset.place = place.name
    item.target.tag.dataset.align = place.align
    item.target.tag.style.transform = `translate(${Math.round(place.x(item.w))}px, ${Math.round(place.y(item.h))}px)`
  }
}
