import type * as maplibregl from "maplibre-gl"
import type { Journey, Leg, Station } from "@/lib/contract"
import { journeyBounds, type LngLat } from "@/lib/geo"
import { DUR, motionOff } from "@/lib/motion"

export const HOME = { center: [10.5, 51] as LngLat, zoom: 4.8, pitch: 0, bearing: 0 }

/** Padding that keeps the route clear of the overlay panel. */
export function panelPadding(): { top: number; bottom: number; left: number; right: number } {
  const app = document.querySelector<HTMLElement>('.travel-app')
  const sheet = app?.querySelector<HTMLElement>('.travel-sheet')
  const visible = sheet && !sheet.hidden
  if (app) {
    if (window.innerWidth < 768 && window.innerWidth < window.innerHeight) {
      const occupied = visible ? window.innerHeight - sheet.getBoundingClientRect().top : 66
      return { top: 55, bottom: Math.min(window.innerHeight - 160, occupied + 15), left: 24, right: 62 }
    }
    return { top: 95, bottom: 75, left: visible ? Math.round(sheet.getBoundingClientRect().right + 25) : 50, right: 70 }
  }
  return { top: 50, bottom: 60, left: 50, right: 60 }
}

const dur = (ms: number) => (motionOff() ? 0 : ms)

export function goHome(map: maplibregl.Map) {
  const portrait = window.innerWidth < 768 && window.innerWidth < window.innerHeight
  const padding = panelPadding()
  const zoom = portrait ? 4.2 : window.innerHeight < 520 ? 4.2 : HOME.zoom
  map.flyTo({ ...HOME, zoom, padding, duration: dur(DUR.fly), essential: true })
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
  map.setPadding({ top: 0, bottom: 0, left: 0, right: 0 })
  map.fitBounds(
    [
      [minLon - padDeg, minLat - padDeg],
      [maxLon + padDeg, maxLat + padDeg],
    ],
    { padding: panelPadding(), duration: opts.duration ?? dur(DUR.fly), maxZoom: opts.maxZoom ?? 10.5, pitch: motionOff() ? 0 : 48, bearing: 0, essential: true },
  )
}

export function flyToLeg(map: maplibregl.Map, leg: Leg) {
  const bounds = journeyBounds({ id: "leg-focus", source: "manual", legs: [leg] })
  if (!bounds) return
  const padDeg = 0.03
  map.setPadding({ top: 0, bottom: 0, left: 0, right: 0 })
  map.fitBounds(
    [
      [bounds[0][0] - padDeg, bounds[0][1] - padDeg],
      [bounds[1][0] + padDeg, bounds[1][1] + padDeg],
    ],
    { padding: panelPadding(), duration: dur(1600), maxZoom: 11.5, pitch: motionOff() ? 0 : 35, essential: true },
  )
}

export function flyToStation(map: maplibregl.Map, station: Station, zoom = 11) {
  if (station.lon == null || station.lat == null) return
  const pad = panelPadding()
  map.flyTo({
    center: [station.lon, station.lat],
    zoom,
    pitch: motionOff() ? 0 : 50,
    bearing: -15,
    duration: dur(1800),
    essential: true,
    padding: pad,
  })
}

