import * as maplibregl from "maplibre-gl"
import type { Journey } from "@/lib/contract"
import { legLine, RISK_COLOUR } from "@/lib/geo"
import { DUR, motionOff } from "@/lib/motion"

export type RouteKind = "main" | "alt"

type Handles = {
  markers: maplibregl.Marker[]
  layerIds: string[]
  sourceIds: string[]
  anim: number
}

const registry = new WeakMap<maplibregl.Map, Record<RouteKind, Handles>>()

function handles(map: maplibregl.Map, kind: RouteKind): Handles {
  let r = registry.get(map)
  if (!r) {
    r = { main: { markers: [], layerIds: [], sourceIds: [], anim: 0 }, alt: { markers: [], layerIds: [], sourceIds: [], anim: 0 } }
    registry.set(map, r)
  }
  return r[kind]
}

export function clearRoute(map: maplibregl.Map, kind: RouteKind) {
  const h = handles(map, kind)
  cancelAnimationFrame(h.anim)
  for (const id of h.layerIds) if (map.getLayer(id)) map.removeLayer(id)
  for (const id of h.sourceIds) if (map.getSource(id)) map.removeSource(id)
  for (const m of h.markers) m.remove()
  h.layerIds = []
  h.sourceIds = []
  h.markers = []
}

/** Point a fraction `t` along the straight segment from a to b. */
function lerp(a: [number, number], b: [number, number], t: number): [number, number] {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
}

function partial(line: [number, number][], t: number): [number, number][] {
  if (t >= 0.999) return line
  const [a, b] = [line[0], line[line.length - 1]]
  return [a, lerp(a, b, Math.max(t, 0.002))]
}

export type DrawOptions = {
  colours?: (string | undefined)[] // per leg
  dashed?: boolean
  animate?: boolean
  onStationClick?: (legIndex: number, end: "from" | "to") => void
  labels?: boolean
  width?: number
}

/** Draw a journey's legs as glowing lines plus station markers. Idempotent per kind. */
export function drawRoute(map: maplibregl.Map, kind: RouteKind, journey: Journey, opts: DrawOptions = {}) {
  clearRoute(map, kind)
  const h = handles(map, kind)
  const base = kind === "main" ? RISK_COLOUR.none : "#a7f3d0"
  const width = opts.width ?? (kind === "main" ? 4.5 : 3.5)
  const animate = (opts.animate ?? true) && !motionOff()

  journey.legs.forEach((leg, i) => {
    const line = legLine(leg)
    if (!line) return
    const colour = opts.colours?.[i] ?? base
    const sourceId = `route-${kind}-${i}`
    map.addSource(sourceId, {
      type: "geojson",
      data: { type: "Feature", properties: { leg: i }, geometry: { type: "LineString", coordinates: animate ? partial(line, 0) : line } },
    })
    h.sourceIds.push(sourceId)
    const glowId = `${sourceId}-glow`
    const lineId = `${sourceId}-line`
    map.addLayer({
      id: glowId,
      type: "line",
      source: sourceId,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": colour, "line-width": width * 3, "line-opacity": 0.22, "line-blur": 6 },
    })
    map.addLayer({
      id: lineId,
      type: "line",
      source: sourceId,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": colour,
        "line-width": width,
        "line-opacity": 0.95,
        ...(opts.dashed ? { "line-dasharray": [1.5, 1.5] } : {}),
      },
    })
    h.layerIds.push(glowId, lineId)
  })

  // Station markers: HTML so they work without glyph fonts and offline.
  const seen = new Set<string>()
  journey.legs.forEach((leg, i) => {
    const ends: ["from" | "to", typeof leg.from][] = [["from", leg.from], ["to", leg.to]]
    for (const [end, st] of ends) {
      if (st.lon == null || st.lat == null) continue
      const key = `${st.evaNumber || st.name}`
      if (seen.has(key)) continue
      seen.add(key)
      const el = document.createElement("button")
      el.type = "button"
      el.className = "station-marker"
      el.setAttribute("aria-label", st.name)
      const colour = end === "to" ? (opts.colours?.[i] ?? base) : (opts.colours?.[i - 1] ?? base)
      el.innerHTML = `<span class="dot" style="--c:${colour}"></span>${opts.labels === false ? "" : `<span class="label">${st.name}</span>`}`
      el.addEventListener("click", (e) => {
        e.stopPropagation()
        opts.onStationClick?.(i, end)
      })
      const m = new maplibregl.Marker({ element: el, anchor: "left", offset: [10, 0] }).setLngLat([st.lon, st.lat]).addTo(map)
      h.markers.push(m)
    }
  })

  if (animate) animateDraw(map, kind, journey)
}

function animateDraw(map: maplibregl.Map, kind: RouteKind, journey: Journey) {
  const h = handles(map, kind)
  const legs = journey.legs.map((_, i) => i).filter((i) => legLine(journey.legs[i]))
  const per = DUR.leg
  const start = performance.now()
  const step = (now: number) => {
    const elapsed = now - start
    legs.forEach((i, order) => {
      const t = Math.max(0, Math.min(1, (elapsed - order * per) / per))
      const line = legLine(journey.legs[i])
      const src = map.getSource(`route-${kind}-${i}`) as maplibregl.GeoJSONSource | undefined
      if (line && src) src.setData({ type: "Feature", properties: { leg: i }, geometry: { type: "LineString", coordinates: partial(line, t) } })
    })
    if (elapsed < legs.length * per) h.anim = requestAnimationFrame(step)
  }
  h.anim = requestAnimationFrame(step)
}

/** Recolour an existing route (e.g. once the forecast arrives) without redrawing. */
export function recolourRoute(map: maplibregl.Map, kind: RouteKind, journey: Journey, colours: (string | undefined)[]) {
  const h = handles(map, kind)
  cancelAnimationFrame(h.anim)
  journey.legs.forEach((_, i) => {
    const colour = colours[i] ?? RISK_COLOUR.none
    for (const suffix of ["glow", "line"]) {
      const id = `route-${kind}-${i}-${suffix}`
      if (map.getLayer(id)) map.setPaintProperty(id, "line-color", colour)
    }
  })
  h.markers.forEach((m) => {
    const el = m.getElement()
    const dot = el.querySelector<HTMLElement>(".dot")
    if (!dot) return
    // Marker order mirrors leg iteration: recompute colour by matching label to the leg ends.
    const name = el.getAttribute("aria-label")
    const idx = journey.legs.findIndex((l) => l.to.name === name)
    if (idx >= 0) dot.style.setProperty("--c", colours[idx] ?? RISK_COLOUR.none)
  })
}
