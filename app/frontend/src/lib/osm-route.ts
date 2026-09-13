import type { Journey, Leg } from './contract'
import { trackDistance, validTrack, type TrackPoint } from './track-path'

export type OsmMember = { type: string; role: string; ref?: number; lat?: number; lon?: number; geometry?: { lat: number; lon: number }[] }
export type OsmRoute = { id: number; tags?: Record<string, string>; members?: OsmMember[] }
type OsmElement = OsmRoute & { type: string; lat?: number; lon?: number; nodes?: number[] }

export function expandOsmRelation(elements: OsmElement[], id: number): OsmRoute | undefined {
  const relation = elements.find(element => element.type === 'relation' && element.id === id)
  if (!relation?.members) return undefined
  const nodes = new Map(elements.filter(element => element.type === 'node').map(node => [node.id, node]))
  const ways = new Map(elements.filter(element => element.type === 'way').map(way => [way.id, way]))
  return { ...relation, members: relation.members.map(member => {
    if (member.type === 'node') {
      const node = nodes.get(member.ref!)
      return { ...member, lat: member.lat ?? node?.lat, lon: member.lon ?? node?.lon }
    }
    if (member.type !== 'way' || member.geometry) return member
    const way = ways.get(member.ref!)
    const geometry = way?.nodes?.map(ref => ({ lat: nodes.get(ref)?.lat ?? NaN, lon: nodes.get(ref)?.lon ?? NaN }))
    return { ...member, geometry }
  }) }
}
export type MappedRoute = {
  trainId: string
  fromEva: string
  toEva: string
  relationId: number
  name: string
  dataTimestamp: string
  coordinates: TrackPoint[]
}

const normalized = (name: string) => name.replace(/\s/g, '').toUpperCase()
const near = (a: TrackPoint, b: TrackPoint) => trackDistance(a, b) < 1

export function joinRouteWays(members: OsmMember[]): TrackPoint[] | undefined {
  const ways = members.filter(member => member.type === 'way' && ['', 'forward', 'backward'].includes(member.role))
  if (!ways.length || ways.some(way => !way.geometry || !validTrack(way.geometry.map(point => [point.lon, point.lat])))) return undefined
  const segments = ways.map(way => {
    const points: TrackPoint[] = way.geometry!.map(point => [point.lon, point.lat])
    return way.role === 'backward' ? points.reverse() : points
  })
  for (const reverseFirst of [false, true]) {
    if (reverseFirst && ways[0].role) continue
    const path = reverseFirst ? [...segments[0]].reverse() : [...segments[0]]
    let connected = true
    for (let i = 1; i < segments.length; i++) {
      const segment = segments[i]
      if (near(path.at(-1)!, segment[0])) path.push(...segment.slice(1))
      else if (!ways[i].role && near(path.at(-1)!, segment.at(-1)!)) path.push(...[...segment].reverse().slice(1))
      else { connected = false; break }
    }
    if (connected && validTrack(path)) return path
  }
  return undefined
}

function nearest(points: TrackPoint[], target: TrackPoint, start = 0) {
  let index = -1, distance = Infinity
  for (let i = start; i < points.length; i++) {
    const d = trackDistance(points[i], target)
    if (d < distance) { index = i; distance = d }
  }
  return { index, distance }
}

export function mappedRouteForLeg(route: OsmRoute, leg: Leg, dataTimestamp: string): MappedRoute | undefined {
  if (!Number.isSafeInteger(route.id) || !route.tags?.ref || normalized(route.tags.ref) !== normalized(leg.trainId) || !['train', 'light_rail', 'subway'].includes(route.tags.route) || !route.members) return undefined
  const { from, to } = leg
  if (from.lon == null || from.lat == null || to.lon == null || to.lat == null) return undefined
  const stops: TrackPoint[] = route.members.filter(member => member.type === 'node' && /^stop(?:_|$)/.test(member.role) && Number.isFinite(member.lon) && Number.isFinite(member.lat)).map(stop => [stop.lon!, stop.lat!])
  const startStop = nearest(stops, [from.lon, from.lat])
  const endStop = nearest(stops, [to.lon, to.lat], startStop.index + 1)
  if (startStop.distance > 800 || endStop.distance > 800 || startStop.index < 0 || endStop.index <= startStop.index) return undefined
  const path = joinRouteWays(route.members)
  if (!path) return undefined
  const start = nearest(path, stops[startStop.index])
  const end = nearest(path, stops[endStop.index], start.index + 1)
  if (start.distance > 20 || end.distance > 20 || end.index <= start.index) return undefined
  const coordinates = path.slice(start.index, end.index + 1)
  if (!validTrack(coordinates)) return undefined
  return { trainId: leg.trainId, fromEva: from.evaNumber, toEva: to.evaNumber, relationId: route.id, name: route.tags.name ?? route.tags.ref, dataTimestamp, coordinates }
}

export function applyMappedRoute(leg: Leg, route: MappedRoute): Leg {
  return { ...leg, routeGeometry: route.coordinates, routeGeometrySource: 'osm', routeRelationId: route.relationId, routeDataTimestamp: route.dataTimestamp }
}

export function matchesMappedRoute(leg: Leg, route: MappedRoute): boolean {
  return typeof route?.trainId === 'string' && normalized(leg.trainId) === normalized(route.trainId) && leg.from.evaNumber === route.fromEva && leg.to.evaNumber === route.toEva && validTrack(route.coordinates) && Number.isSafeInteger(route.relationId) && route.relationId > 0
}

export function reuseMappedServiceGeometry(journey: Journey, known: Journey): Journey {
  return { ...journey, legs: journey.legs.map(leg => {
    if (validTrack(leg.routeGeometry)) return leg
    const match = known.legs.find(candidate => candidate.routeGeometrySource === 'osm' && validTrack(candidate.routeGeometry) && normalized(candidate.trainId) === normalized(leg.trainId) && candidate.from.evaNumber === leg.from.evaNumber && candidate.to.evaNumber === leg.to.evaNumber)
    return match ? { ...leg, routeGeometry: match.routeGeometry, routeGeometrySource: 'osm', routeRelationId: match.routeRelationId, routeDataTimestamp: match.routeDataTimestamp } : leg
  }) }
}

export async function fetchMappedRoute(leg: Leg, signal: AbortSignal): Promise<MappedRoute | undefined> {
  const { lat, lon } = leg.from
  if (!/^(?:RB|RE|S|IC|ICE|EC)\s?\d{1,5}$/i.test(leg.trainId) || typeof lat !== 'number' || typeof lon !== 'number' || !Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return undefined
  const ref = normalized(leg.trainId).replace(/(\D+)(\d+)/, '$1 ?$2')
  const query = `[out:json][timeout:15];relation["type"="route"]["route"~"^(train|light_rail|subway)$"]["ref"~"^${ref}$"](around:1500,${lat},${lon});out geom;`
  const url = new URL('https://overpass.private.coffee/api/interpreter')
  url.searchParams.set('data', query)
  const response = await fetch(url, { signal })
  if (!response.ok) throw new Error('Mapped service routes are temporarily unavailable.')
  const data = await response.json() as { osm3s?: { timestamp_osm_base?: string }; elements?: OsmRoute[]; remark?: string }
  if (data.remark || !Array.isArray(data.elements)) return undefined
  const matches = data.elements.map(route => mappedRouteForLeg(route, leg, data.osm3s?.timestamp_osm_base ?? '')).filter((route): route is MappedRoute => Boolean(route))
  if (!matches.length) return undefined
  const first = JSON.stringify(matches[0].coordinates)
  return matches.every(route => JSON.stringify(route.coordinates) === first) ? matches[0] : undefined
}
