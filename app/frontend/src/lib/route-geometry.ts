import type { Leg } from './contract'
export type RoutePoint = [number, number]
export function parseRouteGeometry(value: unknown): RoutePoint[] | undefined {
  if (!value || typeof value !== 'object') return undefined
  const g = value as { type?: string; coordinates?: unknown; geometry?: unknown; features?: unknown[] }
  if (g.type === 'Feature') return parseRouteGeometry(g.geometry)
  if (g.type === 'FeatureCollection' && Array.isArray(g.features)) {
    const points = g.features.flatMap(f => {
      const geometry = (f as { geometry?: { type?: string; coordinates?: unknown } })?.geometry
      if (geometry?.type === 'Point' && validPoint(geometry.coordinates)) return [geometry.coordinates as RoutePoint]
      return parseRouteGeometry(f) ?? []
    })
    return points.length > 1 ? points : undefined
  }
  if (g.type === 'LineString' && Array.isArray(g.coordinates) && g.coordinates.length > 1 && g.coordinates.every(validPoint)) return g.coordinates as RoutePoint[]
  return undefined
}
function validPoint(p: unknown): p is RoutePoint {
  return Array.isArray(p) && p.length >= 2 && Number.isFinite(p[0]) && Number.isFinite(p[1]) && Math.abs(p[0]) <= 180 && Math.abs(p[1]) <= 90
}
export function routeMatches(a: Leg, b: Leg): boolean {
  return a.trainId.replace(/\s/g, '').toLowerCase() === b.trainId.replace(/\s/g, '').toLowerCase() && a.from.evaNumber === b.from.evaNumber && a.to.evaNumber === b.to.evaNumber && Date.parse(a.plannedDeparture) === Date.parse(b.plannedDeparture) && Date.parse(a.plannedArrival) === Date.parse(b.plannedArrival)
}
