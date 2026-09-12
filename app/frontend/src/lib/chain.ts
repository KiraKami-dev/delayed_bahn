// Port of app/agents/src/features/db_delay/trip/connection.py.
// A change works when both trains run and
//   arrival delay - departure delay <= planned buffer - minimum transfer.
// Trains are treated as independent (optimistic when one disruption hits both).

import type { Journey, LegDelay, Prediction } from "./contract"

export type TrainForecast = { probs: number[]; pCancel?: number }

export const LATE_MINUTES = 6
export const MIN_TRANSFER_MINUTES = 5

export function normalise(probs: number[]): Float64Array {
  let total = 0
  for (const p of probs) total += p
  if (!(total > 0)) throw new Error("delay distribution has no mass")
  return Float64Array.from(probs, (p) => p / total)
}

/** P(both run and A - D <= floor(buffer - minTransfer)). */
export function changeProbability(
  arriving: TrainForecast,
  departing: TrainForecast,
  plannedBuffer: number,
  minTransfer: number,
): number {
  const a = normalise(arriving.probs)
  const d = normalise(departing.probs)
  const slack = Math.floor(plannedBuffer - minTransfer)
  // tail[k] = P(D >= k)
  const tail = new Float64Array(d.length + 1)
  for (let k = d.length - 1; k >= 0; k--) tail[k] = tail[k + 1] + d[k]
  let made = 0
  for (let i = 0; i < a.length; i++) {
    const k = i - slack // need D >= i - slack
    made += a[i] * (k <= 0 ? 1 : k >= d.length ? 0 : tail[k])
  }
  return (1 - (arriving.pCancel ?? 0)) * (1 - (departing.pCancel ?? 0)) * made
}

export function journeyProbability(
  changes: [TrainForecast, TrainForecast, number, number][],
  finalArrival?: TrainForecast,
  arrivalSlack?: number,
) {
  const perChange = changes.map(([a, d, b, m]) => changeProbability(a, d, b, m))
  let success = perChange.reduce((p, x) => p * x, 1)
  if (finalArrival && arrivalSlack != null) {
    const pmf = normalise(finalArrival.probs)
    let onTime = 0
    for (let k = 0; k <= Math.floor(arrivalSlack) && k < pmf.length; k++) onTime += pmf[k]
    success *= (1 - (finalArrival.pCancel ?? 0)) * onTime
  }
  return { changeProbabilities: perChange, planSuccess: success, planFail: 1 - success }
}

export function point(minutes: number, size = 240, pCancel = 0): TrainForecast {
  const probs = new Array<number>(size).fill(0)
  probs[Math.min(minutes, size - 1)] = 1
  return { probs, pCancel }
}

export function quantile(probs: number[], q: number): number {
  const p = normalise(probs)
  let c = 0
  for (let k = 0; k < p.length; k++) {
    c += p[k]
    if (c >= q) return k
  }
  return p.length - 1
}

/** Geometric pmf whose median lands on `median` minutes (mirrors the backend mock). */
export function geometricPmf(median: number, size = 240): number[] {
  const q = Math.pow(0.5, 1 / (Math.max(median, 0) + 1))
  const probs = new Array<number>(size)
  for (let k = 0; k < size; k++) probs[k] = (1 - q) * Math.pow(q, k)
  return probs
}

function forecastOf(leg: LegDelay): TrainForecast {
  const probs = leg.probs && leg.probs.length ? leg.probs : geometricPmf(leg.expectedDelayMinutes.value)
  return { probs, pCancel: leg.pCancel ?? 0 }
}

function minutesBetween(a: string, b: string): number {
  return Math.round((new Date(b).getTime() - new Date(a).getTime()) / 60000)
}

export function transferBuffer(journey: Journey, i: number): number {
  const leg = journey.legs[i]
  const next = journey.legs[i + 1]
  if (!next) return 0
  return leg.transferMinutes ?? minutesBetween(leg.plannedArrival, next.plannedDeparture)
}

/**
 * Re-chain a prediction in the browser with extra minutes added at one transfer
 * (or every transfer when index is -1). Used by the buffer slider.
 */
export function rechain(
  journey: Journey,
  prediction: Prediction,
  extraMinutes: number,
  atTransfer = -1,
  minTransfer = MIN_TRANSFER_MINUTES,
): { legs: number[]; planFail: number } {
  const changes: [TrainForecast, TrainForecast, number, number][] = []
  for (let i = 0; i < journey.legs.length - 1; i++) {
    const arr = forecastOf(prediction.legs[i])
    const depLeg = prediction.legs[i + 1]
    const dep: TrainForecast = { probs: geometricPmf(depLeg.expectedDelayMinutes.value * 0.4), pCancel: depLeg.pCancel ?? 0 }
    const extra = atTransfer === -1 || atTransfer === i ? extraMinutes : 0
    changes.push([arr, dep, transferBuffer(journey, i) + extra, minTransfer])
  }
  const r = journeyProbability(changes)
  const legs = r.changeProbabilities.map((p) => 1 - p)
  legs.push(0)
  return { legs, planFail: r.planFail }
}
