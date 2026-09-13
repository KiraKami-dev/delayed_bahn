import { parseRouteGeometry, routeMatches } from './route-geometry'
import { applyMappedRoute, fetchMappedRoute, matchesMappedRoute, type MappedRoute } from './osm-route'
import { validTrack } from './track-path'
import type { Journey, Station } from './contract'

type Stop = { id?: string; name?: string; location?: { latitude?: number; longitude?: number } }
type TimetableLeg = { remarks?: { type?: string; text?: string; summary?: string }[]; polyline?: unknown; walking?: boolean; cancelled?: boolean; line?: { name?: string; mode?: string; productName?: string; product?: string; operator?: { name?: string } }; origin?: Stop; destination?: Stop; plannedDeparture?: string; plannedArrival?: string }
const station = (s: Stop): Station => ({ evaNumber: s.id!, name: s.name!, lat: s.location?.latitude, lon: s.location?.longitude })

export async function searchJourneys(from: Station, to: Station, signal: AbortSignal, departure = new Date().toISOString()): Promise<Journey[]> {
  const query = new URLSearchParams({ from: from.evaNumber, to: to.evaNumber, results: '5', departure, polylines: 'true', stopovers: 'true', startWithWalking: 'false', bus: 'false', ferry: 'false', tram: 'false', taxi: 'false', subway: 'false', language: 'en', remarks: 'true' })
  const response = await fetch(`https://v6.db.transport.rest/journeys?${query}`, { signal })
  if (!response.ok) throw new Error(response.status === 429 ? 'The timetable service is busy. Please wait a moment and retry, or open DB Navigator below.' : `The timetable service is unavailable (HTTP ${response.status}). Your stations are saved. Open DB Navigator below, then share the chosen journey back here.`)
  const data = await response.json() as { journeys?: { legs?: TimetableLeg[] }[] }
  if (!Array.isArray(data.journeys)) throw new Error('The timetable returned an incomplete response. Please try again.')
  return data.journeys.flatMap(item => {
    // Never silently drop walking legs or fabricate train times.
    if (!item.legs?.length || item.legs.some(l => l.walking || l.cancelled || l.line?.mode !== 'train' || !l.line?.name || !l.origin?.id || !l.origin.name || !l.destination?.id || !l.destination.name || !l.plannedDeparture || !l.plannedArrival || !Number.isFinite(Date.parse(l.plannedDeparture)) || !Number.isFinite(Date.parse(l.plannedArrival)) || Date.parse(l.plannedArrival) <= Date.parse(l.plannedDeparture))) return []
    const legs = item.legs.map(l => ({ trainId: l.line!.name!, serviceCategory: l.line!.productName, serviceProduct: l.line!.product, operatorName: l.line!.operator?.name, disruptions: l.remarks?.filter(r => r.type === 'warning' && (r.text || r.summary)).map(r => ({ text: (r.text || r.summary)!.replace(/<[^>]*>/g, ''), source: 'Timetable service notice' })), routeGeometry: parseRouteGeometry(l.polyline), from: station(l.origin!), to: station(l.destination!), plannedDeparture: l.plannedDeparture!, plannedArrival: l.plannedArrival!, transferMinutes: undefined as number | undefined }))
    if (legs[0].from.evaNumber !== from.evaNumber || legs.at(-1)!.to.evaNumber !== to.evaNumber) return []
    if (legs.some((l, i) => i > 0 && (legs[i - 1].to.evaNumber !== l.from.evaNumber || Date.parse(l.plannedDeparture) < Date.parse(legs[i - 1].plannedArrival)))) return []
    legs.forEach((l, i) => { if (legs[i + 1]) l.transferMinutes = (Date.parse(legs[i + 1].plannedDeparture) - Date.parse(l.plannedArrival)) / 60000 })
    return [{ id: `search-${crypto.randomUUID()}`, source: 'manual' as const, legs }]
  })
}

export async function resolveJourneyGeometry(journey: Journey, signal: AbortSignal): Promise<Journey> {
  let cached: MappedRoute[] = []
  try {
    const response = await fetch('/seed/mapped-routes.json', { signal: AbortSignal.any([signal, AbortSignal.timeout(3000)]) })
    if (response.ok) {
      const data = await response.json() as { routes?: MappedRoute[] }
      if (Array.isArray(data.routes)) cached = data.routes
    }
  } catch {}
  const legs = await Promise.all(journey.legs.map(async leg => {
    if (validTrack(leg.routeGeometry) || signal.aborted) return leg
    const saved = cached.find(route => matchesMappedRoute(leg, route))
    if (journey.source === 'seed' && saved) return applyMappedRoute(leg, saved)
    if (journey.source !== 'seed') {
      try {
        const options = await searchJourneys(leg.from, leg.to, AbortSignal.any([signal, AbortSignal.timeout(6000)]), leg.plannedDeparture)
        const match = options.flatMap(option => option.legs).find(candidate => routeMatches(candidate, leg) && validTrack(candidate.routeGeometry))
        if (match) return { ...leg, routeGeometry: match.routeGeometry, routeGeometrySource: 'timetable' as const, serviceCategory: match.serviceCategory ?? leg.serviceCategory, serviceProduct: match.serviceProduct ?? leg.serviceProduct, operatorName: match.operatorName ?? leg.operatorName }
      } catch {}
    }
    if (signal.aborted) return leg
    if (saved) return applyMappedRoute(leg, saved)
    try {
      const route = await fetchMappedRoute(leg, AbortSignal.any([signal, AbortSignal.timeout(20000)]))
      if (route && !signal.aborted) return applyMappedRoute(leg, route)
    } catch {}
    return leg
  }))
  return { ...journey, legs }
}
