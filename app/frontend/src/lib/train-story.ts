import type { Journey, Leg, Prediction } from './contract'
export function trainDelay(journey: Journey, leg: Leg, index: number, prediction?: Prediction): number | undefined {
  const forecast = prediction?.journeyId === journey.id ? prediction.legs[index] : undefined
  const value = forecast?.trainId === leg.trainId ? forecast.expectedDelayMinutes.value : undefined
  return value != null && Number.isFinite(value) && value >= 0 ? value : undefined
}
/** A slow, illustrative trip with a pause, never a simulated live position. */
export function storyProgress(elapsedMs: number, delay = 0) {
  const travelMs = 90000, pauseMs = Math.min(30000, Math.max(0, delay) * 1000)
  const t = Math.max(0, elapsedMs) % (travelMs + pauseMs)
  const pauseAt = travelMs * .7
  return t <= pauseAt ? t / travelMs : t < pauseAt + pauseMs ? .7 : (t - pauseMs) / travelMs
}
export function trainScale(zoom: number, trackLength: number) {
  return Math.min(trackLength / 16, Math.max(35, 22000 / 2 ** (zoom - 6)))
}
export function disruptionKind(text: string): 'works' | 'weather' | 'technical' | 'reported' {
  if (/\b(baustelle|bauarbeiten|construction|engineering works|track works)\b/i.test(text)) return 'works'
  if (/\b(storm|snow|flood|weather|sturm|schnee|hochwasser|unwetter)\b/i.test(text)) return 'weather'
  if (/\b(signal failure|technical fault|technical failure|signalstörung|signalstoerung|technische störung)\b/i.test(text)) return 'technical'
  return 'reported'
}
