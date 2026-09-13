import type { Journey, Leg } from "./contract"

export type LngLat = [number, number]

export function legLine(leg: Leg): LngLat[] | null {
  if (leg.routeGeometry && leg.routeGeometry.length > 1) return leg.routeGeometry
  if (leg.from.lon == null || leg.from.lat == null || leg.to.lon == null || leg.to.lat == null) return null
  return [
    [leg.from.lon, leg.from.lat],
    [leg.to.lon, leg.to.lat],
  ]
}

export function journeyBounds(journey: Journey): [LngLat, LngLat] | null {
  let minLon = Infinity, minLat = Infinity, maxLon = -Infinity, maxLat = -Infinity
  for (const leg of journey.legs) {
    for (const [lon, lat] of legLine(leg) ?? []) {
      const s = { lon, lat }
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

/**
 * How a plan-fail probability is shown to a traveller: always as the chance of
 * making every change, 100% green down to red for a plan that is likely to break.
 * The colour and heading follow the risk level.
 */
export type Outlook = { level: "low" | "mid" | "high"; colour: string; percent: number; short: string; unit: string; heading: string }
const HEADING = { low: "This connection looks good.", mid: "Give your day a backup plan.", high: "Plan for a missed connection." } as const
export function journeyOutlook(p: number): Outlook {
  const level = riskLevel(p)
  return { level, colour: RISK_COLOUR[level], percent: Math.round((1 - p) * 100), short: "you will make it", unit: "chance you will make it", heading: HEADING[level] }
}

/** A direct journey has no change to miss: colour its arrival delay instead. */
export function delayColour(minutes: number): string {
  if (minutes <= 5) return RISK_COLOUR.low
  if (minutes <= 15) return RISK_COLOUR.mid
  return RISK_COLOUR.high
}

// Muted tones for text and cards on the light UI.
export const RISK_COLOUR = { low: "#26704c", mid: "#916019", high: "#b54534", none: "#52794a" } as const
// Saturated, luminous tones for lines and pins on the satellite globe.
export const RISK_MAP_COLOUR = { low: "#4dffb4", mid: "#ffc83d", high: "#ff5d5d", none: "#6ee7ff" } as const

export function riskColour(p: number | undefined): string {
  if (p == null) return RISK_COLOUR.none
  return RISK_COLOUR[riskLevel(p)]
}

export function riskMapColour(p: number | undefined): string {
  if (p == null) return RISK_MAP_COLOUR.none
  return RISK_MAP_COLOUR[riskLevel(p)]
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
