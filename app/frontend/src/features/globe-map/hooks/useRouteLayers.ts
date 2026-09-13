import * as maplibregl from "maplibre-gl"
import type { Journey } from "@/lib/contract"
import { legLine, RISK_MAP_COLOUR } from "@/lib/geo"
import { DUR, motionOff } from "@/lib/motion"

export type RouteKind = "main" | "alt"

type Handles = {
  markers: maplibregl.Marker[]
  layerIds: string[]
  sourceIds: string[]
  anim: number
  flow: number
}

const registry = new WeakMap<maplibregl.Map, Record<RouteKind, Handles>>()

function handles(map: maplibregl.Map, kind: RouteKind): Handles {
  let r = registry.get(map)
  if (!r) {
    r = { main: { markers: [], layerIds: [], sourceIds: [], anim: 0, flow: 0 }, alt: { markers: [], layerIds: [], sourceIds: [], anim: 0, flow: 0 } }
    registry.set(map, r)
  }
  return r[kind]
}

export function clearRoute(map: maplibregl.Map, kind: RouteKind) {
  const h = handles(map, kind)
  cancelAnimationFrame(h.anim)
  window.clearInterval(h.flow)
  h.flow = 0
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
  const position = Math.max(0.002, t) * (line.length - 1)
  const index = Math.min(line.length - 2, Math.floor(position))
  return [...line.slice(0, index + 1), lerp(line[index], line[index + 1], position - index)]
}

/** Thicker when zoomed out (globe view), slimmer at street level. */
function lineWidth(base: number): maplibregl.ExpressionSpecification {
  return ["interpolate", ["linear"], ["zoom"], 1, base * 1.6, 5, base * 1.25, 9, base, 13, base * 0.8]
}

export type DrawOptions = {
  colours?: (string | undefined)[] // per leg
  dashed?: boolean
  animate?: boolean
  onStationClick?: (legIndex: number, end: "from" | "to") => void
  labels?: boolean
  width?: number
  satellite?: boolean
}

/** Draw a journey's legs as glowing lines plus station markers. Idempotent per kind. */
export function drawRoute(map: maplibregl.Map, kind: RouteKind, journey: Journey, opts: DrawOptions = {}) {
  clearRoute(map, kind)
  const h = handles(map, kind)
  const base = kind === "main" ? RISK_MAP_COLOUR.none : "#b9ffe0"
  const width = opts.width ?? (kind === "main" ? 4.5 : 3.5)
  const animate = (opts.animate ?? true) && !motionOff()
  const beforeLabels = map.getStyle().layers?.find(layer => layer.type === "symbol")?.id

  journey.legs.forEach((leg, i) => {
    const line = legLine(leg)
    if (!line) return
    const colour = opts.colours?.[i] ?? base
    const sourceId = `route-${kind}-${i}`
    map.addSource(sourceId, {
      type: "geojson",
      ...(leg.routeGeometrySource === "osm" || leg.routeGeometrySource === "router" ? { attribution: 'Track routes © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a> (ODbL)' } : {}),
      data: { type: "Feature", properties: { leg: i }, geometry: { type: "LineString", coordinates: animate ? partial(line, 0) : line } },
    })
    h.sourceIds.push(sourceId)
    const glowId = `${sourceId}-glow`
    const lineId = `${sourceId}-line`
    const casingId = `${sourceId}-casing`
    const sheenId = `${sourceId}-sheen`
    const tiesId = `${sourceId}-ties`
    const dashed = opts.dashed || (leg.routeGeometry?.length ?? 0) < 2
    const satellite = opts.satellite ?? false
    map.addLayer({
      id: glowId,
      type: "line",
      source: sourceId,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": colour, "line-width": lineWidth(width * (satellite ? 3.6 : 3.2)), "line-opacity": satellite ? 0.3 : 0.35, "line-blur": satellite ? 10 : 8 },
    }, beforeLabels)
    // Dark casing under the coloured line so it reads on satellite imagery, sea and snow alike.
    map.addLayer({
      id: casingId,
      type: "line",
      source: sourceId,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": satellite ? "#06131f" : "#0b1020", "line-width": lineWidth(width * (satellite ? 2.15 : 1.9)), "line-opacity": satellite ? 0.92 : 0.85 },
    }, beforeLabels)
    map.addLayer({
      id: lineId,
      type: "line",
      source: sourceId,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": colour,
        "line-width": lineWidth(width),
        "line-opacity": 1,
        ...(dashed ? { "line-dasharray": [1.5, 1.5] } : {}),
      },
    }, beforeLabels)
    h.layerIds.push(glowId, casingId, lineId)
    if (!dashed) {
      // Glossy centre line plus sleeper ticks: reads as a railway on photographic ground.
      map.addLayer({
        id: sheenId,
        type: "line",
        source: sourceId,
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#ffffff", "line-width": lineWidth(width * 0.32), "line-opacity": satellite ? 0.55 : 0.45 },
      }, beforeLabels)
      map.addLayer({
        id: tiesId,
        type: "line",
        source: sourceId,
        minzoom: 7,
        layout: { "line-cap": "butt", "line-join": "round" },
        paint: { "line-color": satellite ? "#f6fbff" : "#10203a", "line-width": lineWidth(width * 1.35), "line-opacity": satellite ? 0.42 : 0.28, "line-dasharray": TIE_PHASES[0] },
      }, beforeLabels)
      h.layerIds.push(sheenId, tiesId)
    }
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
      const dot = document.createElement("span")
      dot.className = "dot"
      dot.style.setProperty("--c", colour)
      el.append(dot)
      if (opts.labels !== false) {
        const label = document.createElement("span")
        label.className = "label"
        label.textContent = st.name
        el.append(label)
      }
      el.addEventListener("click", (e) => {
        e.stopPropagation()
        opts.onStationClick?.(i, end)
      })
      const m = new maplibregl.Marker({ element: el, anchor: "left", offset: [-10, 0] }).setLngLat([st.lon, st.lat]).addTo(map)
      h.markers.push(m)
    }
  })

  if (animate) animateDraw(map, kind, journey)
  if (!motionOff()) {
    // Sleeper ticks drift along the line in the direction of travel.
    let phase = 0
    h.flow = window.setInterval(() => {
      if (document.hidden) return
      phase = (phase + 1) % TIE_PHASES.length
      for (const id of h.layerIds) if (id.endsWith("-ties") && map.getLayer(id)) map.setPaintProperty(id, "line-dasharray", TIE_PHASES[phase])
    }, 140)
  }
}

// Dash patterns are [dash, gap, ...] starting with a dash, so a phase shift is a zero dash plus an offset gap.
const TIE_DASH = 0.35, TIE_GAP = 1.95
const TIE_PHASES: number[][] = [0, 1, 2, 3, 4, 5].map(step => {
  const offset = (TIE_GAP + TIE_DASH) * (1 - step / 6)
  return step === 0 ? [TIE_DASH, TIE_GAP] : [0, offset, TIE_DASH, TIE_GAP + TIE_DASH - offset - TIE_DASH]
})

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
  journey.legs.forEach((leg, i) => {
    const line = legLine(leg)
    const source = map.getSource(`route-${kind}-${i}`) as maplibregl.GeoJSONSource | undefined
    if (line && source) source.setData({ type: "Feature", properties: { leg: i }, geometry: { type: "LineString", coordinates: line } })
    const colour = colours[i] ?? RISK_MAP_COLOUR.none
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
    if (idx >= 0) dot.style.setProperty("--c", colours[idx] ?? RISK_MAP_COLOUR.none)
  })
}
