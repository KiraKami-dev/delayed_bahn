import { parseRouteGeometry } from './route-geometry'
import type { Journey, Station } from './contract'

type Stop = { id?: string; name?: string; location?: { latitude?: number; longitude?: number } }
type TimetableLeg = { polyline?: unknown; walking?: boolean; cancelled?: boolean; line?: { name?: string; mode?: string }; origin?: Stop; destination?: Stop; plannedDeparture?: string; plannedArrival?: string }
const station = (s: Stop): Station => ({ evaNumber: s.id!, name: s.name!, lat: s.location?.latitude, lon: s.location?.longitude })

export async function searchJourneys(from: Station, to: Station, signal: AbortSignal, departure = new Date().toISOString()): Promise<Journey[]> {
  const query = new URLSearchParams({ from: from.evaNumber, to: to.evaNumber, results: '5', departure, polylines: 'true', stopovers: 'true', startWithWalking: 'false', bus: 'false', ferry: 'false', tram: 'false', taxi: 'false', subway: 'false', language: 'en' })
  const response = await fetch(`https://v6.db.transport.rest/journeys?${query}`, { signal })
  if (!response.ok) throw new Error('Timetable lookup is unavailable. Please try again or paste a connection from DB Navigator.')
  const data = await response.json() as { journeys?: { legs?: TimetableLeg[] }[] }
  if (!Array.isArray(data.journeys)) throw new Error('The timetable returned an incomplete response. Please try again.')
  return data.journeys.flatMap(item => {
    // Never silently drop walking legs or fabricate train times.
    if (!item.legs?.length || item.legs.some(l => l.walking || l.cancelled || l.line?.mode !== 'train' || !l.line?.name || !l.origin?.id || !l.origin.name || !l.destination?.id || !l.destination.name || !l.plannedDeparture || !l.plannedArrival || !Number.isFinite(Date.parse(l.plannedDeparture)) || Date.parse(l.plannedArrival) <= Date.parse(l.plannedDeparture))) return []
    const legs = item.legs.map(l => ({ trainId: l.line!.name!, routeGeometry: parseRouteGeometry(l.polyline), from: station(l.origin!), to: station(l.destination!), plannedDeparture: l.plannedDeparture!, plannedArrival: l.plannedArrival!, transferMinutes: undefined as number | undefined }))
    if (legs[0].from.evaNumber !== from.evaNumber || legs.at(-1)!.to.evaNumber !== to.evaNumber) return []
    if (legs.some((l, i) => i > 0 && (legs[i - 1].to.evaNumber !== l.from.evaNumber || Date.parse(l.plannedDeparture) < Date.parse(legs[i - 1].plannedArrival)))) return []
    legs.forEach((l, i) => { if (legs[i + 1]) l.transferMinutes = (Date.parse(legs[i + 1].plannedDeparture) - Date.parse(l.plannedArrival)) / 60000 })
    return [{ id: `search-${crypto.randomUUID()}`, source: 'manual' as const, legs }]
  })
}
