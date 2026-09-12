import type { Journey, Station } from "./contract"
import raw from "./stations.json"

export type StationEntry = { name: string; evaNumber: string; lat: number; lon: number; aliases: string[] }

export const STATIONS: StationEntry[] = raw as StationEntry[]

export function normaliseName(s: string): string {
  return s
    .toLowerCase()
    .replace(/ä/g, "ae")
    .replace(/ö/g, "oe")
    .replace(/ü/g, "ue")
    .replace(/ß/g, "ss")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/hauptbahnhof/g, "hbf")
    .replace(/[()\-.,/]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
}

const byEva = new Map<string, StationEntry>()
const byName = new Map<string, StationEntry>()
for (const st of STATIONS) {
  byEva.set(st.evaNumber, st)
  byName.set(normaliseName(st.name), st)
  for (const a of st.aliases) byName.set(normaliseName(a), st)
}

export function lookupStation(q: { evaNumber?: string; name?: string }): StationEntry | undefined {
  if (q.evaNumber && byEva.has(q.evaNumber)) return byEva.get(q.evaNumber)
  if (!q.name) return undefined
  const n = normaliseName(q.name)
  if (byName.has(n)) return byName.get(n)
  const stripped = n.replace(/\b(hbf|hb)\b/g, "").trim()
  for (const [k, v] of byName) if (k.replace(/\b(hbf|hb)\b/g, "").trim() === stripped) return v
  for (const [k, v] of byName) if (k.startsWith(n) || n.startsWith(k)) return v
  return undefined
}

export function searchStations(q: string, limit = 8): StationEntry[] {
  const n = normaliseName(q)
  if (!n) return []
  const seen = new Set<string>()
  const out: StationEntry[] = []
  for (const st of STATIONS) {
    const hay = [st.name, ...st.aliases].map(normaliseName)
    if (hay.some((h) => h.includes(n)) && !seen.has(st.evaNumber)) {
      seen.add(st.evaNumber)
      out.push(st)
      if (out.length >= limit) break
    }
  }
  return out
}

export function withCoords(station: Station): Station {
  if (station.lat != null && station.lon != null) return station
  const hit = lookupStation(station)
  return hit ? { ...station, evaNumber: station.evaNumber || hit.evaNumber, lat: hit.lat, lon: hit.lon } : station
}

export function hydrateCoords(journey: Journey): Journey {
  return { ...journey, legs: journey.legs.map((l) => ({ ...l, from: withCoords(l.from), to: withCoords(l.to) })) }
}
