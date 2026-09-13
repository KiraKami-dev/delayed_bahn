import type { Leg } from './contract'
export type RoutePoint = [number, number]
export function parseRouteGeometry(value: unknown): RoutePoint[] | undefined {
  if (!value || typeof value !== 'object') return undefined
  const g = value as { type?: string; coordinates?: unknown; geometry?: unknown; features?: unknown[] }
  if (g.type === 'Feature') return parseRouteGeometry(g.geometry)
  if (g.type === 'FeatureCollection' && Array.isArray(g.features)) {
    const points: RoutePoint[] = []
    for (const f of g.features) {
      const geometry = (f as { geometry?: { type?: string; coordinates?: unknown } })?.geometry
      if (geometry?.type === 'Point' && validPoint(geometry.coordinates)) {
        points.push([geometry.coordinates[0], geometry.coordinates[1]])
      } else {
        const part = parseRouteGeometry(f)
        if (!part) return undefined // Never bridge a missing or malformed track segment.
        points.push(...part)
      }
    }
    return points.length > 1 ? points : undefined
  }
  if (g.type === 'LineString' && Array.isArray(g.coordinates) && g.coordinates.length > 1 && g.coordinates.every(validPoint)) return g.coordinates.map(p => [p[0], p[1]])

  return undefined
}
function validPoint(p: unknown): p is RoutePoint {
  return Array.isArray(p) && p.length >= 2 && Number.isFinite(p[0]) && Number.isFinite(p[1]) && Math.abs(p[0]) <= 180 && Math.abs(p[1]) <= 90
}
export function routeMatches(a: Leg, b: Leg): boolean {
  return a.trainId.replace(/\s/g, '').toLowerCase() === b.trainId.replace(/\s/g, '').toLowerCase() && a.from.evaNumber === b.from.evaNumber && a.to.evaNumber === b.to.evaNumber && Date.parse(a.plannedDeparture) === Date.parse(b.plannedDeparture) && Date.parse(a.plannedArrival) === Date.parse(b.plannedArrival)
}
