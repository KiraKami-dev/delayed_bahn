export type TrackPoint = [number, number]
const radians = Math.PI / 180
export function validTrack(points: unknown): points is TrackPoint[] {
  return Array.isArray(points) && points.length >= 2 && points.every(p => Array.isArray(p) && p.length === 2 && Number.isFinite(p[0]) && Number.isFinite(p[1]) && Math.abs(p[0]) <= 180 && Math.abs(p[1]) <= 90) && points.some(p => p[0] !== points[0][0] || p[1] !== points[0][1])
}
export function trackDistance(a: TrackPoint, b: TrackPoint): number {
  const dlat = (b[1] - a[1]) * radians, dlon = (b[0] - a[0]) * radians
  const h = Math.sin(dlat / 2) ** 2 + Math.cos(a[1] * radians) * Math.cos(b[1] * radians) * Math.sin(dlon / 2) ** 2
  return 6371008.8 * 2 * Math.asin(Math.sqrt(Math.min(1, h)))
}
export function buildTrack(points: TrackPoint[]) {
  points = points.filter((p, i) => i === 0 || p[0] !== points[i - 1][0] || p[1] !== points[i - 1][1])
  const cumulative = [0]
  for (let i = 1; i < points.length; i++) cumulative.push(cumulative[i - 1] + trackDistance(points[i - 1], points[i]))
  return { points, cumulative, length: cumulative.at(-1)! }
}
export function sampleTrack(track: ReturnType<typeof buildTrack>, distance: number) {
  const target = Math.max(0, Math.min(distance, track.length))
  let low = 0, high = track.points.length - 1
  while (low + 1 < high) { const mid = Math.floor((low + high) / 2); if (track.cumulative[mid] <= target) low = mid; else high = mid }
  const a = track.points[low], b = track.points[high]
  const span = track.cumulative[high] - track.cumulative[low]
  const fraction = span > 0 ? (target - track.cumulative[low]) / span : 0
  return { point: [a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction] as TrackPoint,
    heading: Math.atan2((b[0] - a[0]) * Math.cos(a[1] * radians), b[1] - a[1]) }
}
