import { parseRouteGeometry, routeMatches } from './route-geometry'
import { applyMappedRoute, fetchMappedRoute, matchesMappedRoute, type MappedRoute } from './osm-route'
import { validTrack } from './track-path'
import { fetchRailRoute } from './rail-router'
import type { Journey, Leg, Station } from './contract'

type Stop = { id?: string; name?: string; location?: { latitude?: number; longitude?: number } }
type TimetableLeg = { remarks?: { type?: string; text?: string; summary?: string }[]; polyline?: unknown; walking?: boolean; cancelled?: boolean; line?: { name?: string; mode?: string; productName?: string; product?: string; operator?: { name?: string } }; origin?: Stop; destination?: Stop; plannedDeparture?: string; plannedArrival?: string }
const station = (s: Stop): Station => ({ evaNumber: s.id!, name: s.name!, lat: s.location?.latitude, lon: s.location?.longitude })

export async function searchTransportRest(from: Station, to: Station, signal: AbortSignal, departure = new Date().toISOString()): Promise<Journey[]> {
  const query = new URLSearchParams({ from: from.evaNumber, to: to.evaNumber, results: '5', departure, polylines: 'true', stopovers: 'true', startWithWalking: 'false', bus: 'false', ferry: 'false', tram: 'false', taxi: 'false', subway: 'false', language: 'en', remarks: 'true' })
  let response: Response
  try {
    response = await fetch(`https://v6.db.transport.rest/journeys?${query}`, { signal })
  } catch (cause) {
    // Browsers hide an upstream error without CORS headers as a network failure.
    // Preserve cancellation so stale requests never become visible errors.
    if (signal.aborted) throw cause
    throw new Error('We couldn’t reach the timetable service. Your stations are saved. Retry shortly, or open DB and paste the shared journey here.', { cause })
  }
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

/** Track geometry per leg. `onProgress` receives the journey whenever a leg's route improves, so the map can show tracks before every source has answered. */
export async function resolveJourneyGeometry(journey: Journey, signal: AbortSignal, onProgress?: (journey: Journey) => void): Promise<Journey> {
  let cached: MappedRoute[] = []
  try {
    const response = await fetch('/seed/mapped-routes.json', { signal: AbortSignal.any([signal, AbortSignal.timeout(3000)]) })
    if (response.ok) {
      const data = await response.json() as { routes?: MappedRoute[] }
      if (Array.isArray(data.routes)) cached = data.routes
    }
  } catch {}
  const legs = [...journey.legs]
  // Legs that answer together become one update, so the map redraws once rather than per leg.
  let pending = 0
  const snapshot = () => ({ ...journey, legs: [...legs] })
  const publish = () => {
    if (!onProgress || pending) return
    pending = window.setTimeout(() => { pending = 0; if (!signal.aborted) onProgress(snapshot()) }, 150)
  }
  await Promise.all(journey.legs.map(async (leg, i) => {
    if (validTrack(leg.routeGeometry) || signal.aborted) return
    // The best route so far is shown as soon as it answers: timetable polyline (the real service
    // path) over a mapped OSM route over the rail-network router. A slow or failing timetable
    // service therefore no longer keeps straight lines on the map while the router already knows the track.
    let rank = 0
    const offer = (next: Leg, nextRank: number) => {
      if (nextRank <= rank || signal.aborted) return
      rank = nextRank
      legs[i] = next
      publish()
    }
    const saved = cached.find(route => matchesMappedRoute(leg, route))
    if (saved) offer(applyMappedRoute(leg, saved), 2)
    if (journey.source === 'seed' && saved) return
    const timetable = journey.source === 'seed' ? Promise.resolve(undefined) : searchTransportRest(leg.from, leg.to, AbortSignal.any([signal, AbortSignal.timeout(6000)]), leg.plannedDeparture)
      .then(options => options.flatMap(option => option.legs).find(candidate => routeMatches(candidate, leg) && validTrack(candidate.routeGeometry)))
      .catch(() => undefined)
    const routed = fetchRailRoute(leg, AbortSignal.any([signal, AbortSignal.timeout(15000)])).catch(() => undefined)
    void routed.then(track => { if (track) offer({ ...leg, routeGeometry: track, routeGeometrySource: 'router' }, 1) })
    const match = await timetable
    if (match) offer({ ...leg, routeGeometry: match.routeGeometry, routeGeometrySource: 'timetable', serviceCategory: match.serviceCategory ?? leg.serviceCategory, serviceProduct: match.serviceProduct ?? leg.serviceProduct, operatorName: match.operatorName ?? leg.operatorName }, 3)
    await routed
    if (rank || signal.aborted) return
    try {
      const route = await fetchMappedRoute(leg, AbortSignal.any([signal, AbortSignal.timeout(20000)]))
      if (route) offer(applyMappedRoute(leg, route), 2)
    } catch {}
  }))
  if (pending) {
    window.clearTimeout(pending)
    if (!signal.aborted) onProgress?.(snapshot())
  }
  return snapshot()
}
