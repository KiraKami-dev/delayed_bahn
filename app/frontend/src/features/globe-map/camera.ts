import type * as maplibregl from "maplibre-gl"
import type { Journey, Leg, Station } from "@/lib/contract"
import { journeyBounds, type LngLat } from "@/lib/geo"
import { DUR, motionOff } from "@/lib/motion"

export const HOME = { center: [10.5, 48] as LngLat, zoom: 1.35, pitch: 0, bearing: 0 }

/** Padding that keeps the route clear of the overlay panel. */
export function panelPadding(): { top: number; bottom: number; left: number; right: number } {
  const w = window.innerWidth
  const h = window.innerHeight
  if (w >= 1024) {
    const panel = Math.min(w * 0.36, Math.max(380, Math.min(520, w * 0.32)))
    return { top: 90, bottom: 60, left: 60, right: panel + 48 }
  }
  return { top: 80, bottom: Math.round(h * 0.55), left: 36, right: 36 }
}

const dur = (ms: number) => (motionOff() ? 0 : ms)

export function goHome(map: maplibregl.Map) {
  map.flyTo({ ...HOME, duration: dur(DUR.fly), essential: true })
}

export function fitJourney(map: maplibregl.Map, journeys: Journey[], opts: { maxZoom?: number; duration?: number } = {}) {
  let minLon = Infinity, minLat = Infinity, maxLon = -Infinity, maxLat = -Infinity
  for (const j of journeys) {
    const b = journeyBounds(j)
    if (!b) continue
    minLon = Math.min(minLon, b[0][0]); minLat = Math.min(minLat, b[0][1])
    maxLon = Math.max(maxLon, b[1][0]); maxLat = Math.max(maxLat, b[1][1])
  }
  if (!isFinite(minLon)) return
  // Give very short routes some air so the fit does not zoom to street level.
  const padDeg = 0.02
  map.fitBounds(
    [
      [minLon - padDeg, minLat - padDeg],
      [maxLon + padDeg, maxLat + padDeg],
    ],
    { padding: panelPadding(), duration: opts.duration ?? dur(DUR.fly), maxZoom: opts.maxZoom ?? 10.5, pitch: 0, bearing: 0, essential: true },
  )
}

export function flyToLeg(map: maplibregl.Map, leg: Leg) {
  if (leg.from.lon == null || leg.to.lon == null || leg.from.lat == null || leg.to.lat == null) return
  const padDeg = 0.03
  map.fitBounds(
    [
      [Math.min(leg.from.lon, leg.to.lon) - padDeg, Math.min(leg.from.lat, leg.to.lat) - padDeg],
      [Math.max(leg.from.lon, leg.to.lon) + padDeg, Math.max(leg.from.lat, leg.to.lat) + padDeg],
    ],
    { padding: panelPadding(), duration: dur(1600), maxZoom: 11.5, pitch: 35, essential: true },
  )
}

export function flyToStation(map: maplibregl.Map, station: Station, zoom = 11) {
  if (station.lon == null || station.lat == null) return
  const pad = panelPadding()
  map.flyTo({
    center: [station.lon, station.lat],
    zoom,
    pitch: 50,
    bearing: -15,
    duration: dur(1800),
    essential: true,
    padding: pad,
  })
}

/** Slow idle rotation of the globe until the user touches it. */
export function startIdleSpin(map: maplibregl.Map): () => void {
  if (motionOff()) return () => {}
  let raf = 0
  let stopped = false
  const stop = () => {
    stopped = true
    cancelAnimationFrame(raf)
  }
  const tick = () => {
    if (stopped) return
    if (!map.isMoving()) {
      const c = map.getCenter()
      map.jumpTo({ center: [c.lng + 0.035, c.lat] })
    }
    raf = requestAnimationFrame(tick)
  }
  raf = requestAnimationFrame(tick)
  const onInteract = () => stop()
  map.on("mousedown", onInteract)
  map.on("touchstart", onInteract)
  map.on("wheel", onInteract)
  return () => {
    stop()
    map.off("mousedown", onInteract)
    map.off("touchstart", onInteract)
    map.off("wheel", onInteract)
  }
}
