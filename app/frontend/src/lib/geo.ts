import type { Journey, Leg } from "./contract"

export type LngLat = [number, number]

export function legLine(leg: Leg): LngLat[] | null {
  if (leg.from.lon == null || leg.from.lat == null || leg.to.lon == null || leg.to.lat == null) return null
  return [
    [leg.from.lon, leg.from.lat],
    [leg.to.lon, leg.to.lat],
  ]
}

export function journeyBounds(journey: Journey): [LngLat, LngLat] | null {
  let minLon = Infinity, minLat = Infinity, maxLon = -Infinity, maxLat = -Infinity
  for (const leg of journey.legs) {
    for (const s of [leg.from, leg.to]) {
      if (s.lon == null || s.lat == null) continue
      minLon = Math.min(minLon, s.lon); maxLon = Math.max(maxLon, s.lon)
      minLat = Math.min(minLat, s.lat); maxLat = Math.max(maxLat, s.lat)
    }
  }
  if (!isFinite(minLon)) return null
  return [[minLon, minLat], [maxLon, maxLat]]
}

export function riskLevel(p: number): "low" | "mid" | "high" {
  if (p < 0.15) return "low"
  if (p < 0.4) return "mid"
  return "high"
}

export const RISK_COLOUR = { low: "#34d399", mid: "#fbbf24", high: "#f87171", none: "#8b8bff" } as const

export function riskColour(p: number | undefined): string {
  if (p == null) return RISK_COLOUR.none
  return RISK_COLOUR[riskLevel(p)]
}

export function fmtTime(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return "--:--"
  return d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Berlin" })
}

export function fmtDate(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ""
  return d.toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "2-digit", year: "numeric", timeZone: "Europe/Berlin" })
}

export function pct(p: number): string {
  return `${Math.round(p * 100)}%`
}
