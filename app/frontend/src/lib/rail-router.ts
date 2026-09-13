import type { Leg } from './contract'
import { trackDistance, validTrack, type TrackPoint } from './track-path'

// Rail-network routing between two stations via BRouter's public "rail"
// profile (OpenStreetMap railway ways). It is a shortest rail path, not the
// timetabled service path, so timetable polylines win when they exist.
const cache = new Map<string, Promise<TrackPoint[] | undefined>>()

export async function fetchRailRoute(leg: Leg, signal: AbortSignal): Promise<TrackPoint[] | undefined> {
  const { from, to } = leg
  if (from.lon == null || from.lat == null || to.lon == null || to.lat == null) return undefined
  const key = `${from.lon},${from.lat}|${to.lon},${to.lat}`
  if (!cache.has(key)) {
    const url = new URL('https://brouter.de/brouter')
    url.searchParams.set('lonlats', key)
    url.searchParams.set('profile', 'rail')
    url.searchParams.set('alternativeidx', '0')
    url.searchParams.set('format', 'geojson')
    const request = (async () => {
      const response = await fetch(url, { signal })
      if (!response.ok) throw new Error(`Rail router replied ${response.status}`)
      const data = await response.json() as { features?: { geometry?: { coordinates?: number[][] } }[] }
      const raw = data.features?.[0]?.geometry?.coordinates
      if (!Array.isArray(raw)) return undefined
      const points = raw.map(([lon, lat]) => [lon, lat] as TrackPoint)
      if (!validTrack(points)) return undefined
      // The path must actually start and end at the stations, not at the nearest track kilometres away.
      if (trackDistance(points[0], [from.lon!, from.lat!]) > 2500 || trackDistance(points.at(-1)!, [to.lon!, to.lat!]) > 2500) return undefined
      return points
    })()
    cache.set(key, request)
    request.catch(() => cache.delete(key))
  }
  return cache.get(key)!
}
