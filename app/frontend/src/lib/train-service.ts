import type { Leg } from './contract'
export type TrainKind = 'ice' | 'intercity' | 're' | 'rb' | 'sbahn' | 'unknown'
export type TrainVisual = { kind: TrainKind; label: string; color: string; nose: number; doors: number }
const styles: Record<TrainKind, Omit<TrainVisual, 'kind'>> = {
  ice: { label: 'ICE', color: '#f4f5ef', nose: 1.15, doors: 1 },
  intercity: { label: 'IC / EC', color: '#e9ece8', nose: .55, doors: 1 },
  re: { label: 'Regional Express', color: '#c63e35', nose: .4, doors: 2 },
  rb: { label: 'Regionalbahn', color: '#b9443c', nose: .35, doors: 2 },
  sbahn: { label: 'S-Bahn', color: '#ba453a', nose: .18, doors: 3 },
  unknown: { label: 'Train', color: '#788b87', nose: .2, doors: 2 },
}
function namedKind(name: string): TrainKind {
  if (/^ICE(?=\s|\d|$)/i.test(name)) return 'ice'
  if (/^(IC|EC)(?=\s|\d|$)/i.test(name)) return 'intercity'
  if (/^RE(?=\s|\d|$)/i.test(name)) return 're'
  if (/^RB(?=\s|\d|$)/i.test(name)) return 'rb'
  if (/^S(?:-Bahn)?(?=\s|\d|$)/i.test(name)) return 'sbahn'
  return 'unknown'
}
/** Category artwork only: neither carriage count, vehicle class nor livery is supplied. */
export function trainVisual(leg: Pick<Leg, 'trainId' | 'serviceCategory' | 'serviceProduct'>): TrainVisual {
  const named = namedKind(leg.trainId.trim())
  const category = namedKind(leg.serviceCategory?.trim() ?? '')
  const kind = named !== 'unknown' && category !== 'unknown' && named !== category ? 'unknown'
    : named !== 'unknown' ? named : category !== 'unknown' ? category
    : leg.serviceProduct === 'suburban' ? 'sbahn' : 'unknown'
  return { kind, ...styles[kind] }
}
