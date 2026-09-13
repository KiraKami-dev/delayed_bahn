import type { Journey, Leg, Prediction } from './contract'
export function trainDelay(journey: Journey, leg: Leg, index: number, prediction?: Prediction): number | undefined {
  const forecast = prediction?.journeyId === journey.id ? prediction.legs[index] : undefined
  const value = forecast?.trainId === leg.trainId ? forecast.expectedDelayMinutes.value : undefined
  return value != null && Number.isFinite(value) && value >= 0 ? value : undefined
}

/**
 * A slow, illustrative replay of the whole journey, never a simulated live
 * position: each train waits at its platform, runs its leg with gentle
 * acceleration, holds once for the forecast delay, and parks at its
 * destination while the connecting train sets off. Then the story loops.
 */
export type StoryLeg = { dwellStart: number; travelStart: number; travelMs: number; pauseAt: number; pauseMs: number; travelEnd: number }
export type Story = { legs: StoryLeg[]; cycle: number }
export type LegPhase = 'waiting' | 'moving' | 'held' | 'arrived'
export type LegState = { progress: number; phase: LegPhase }

export const DWELL_MS = 5000
export const FINAL_HOLD_MS = 7000

export function buildStory(journey: Journey, prediction?: Prediction, lengths: number[] = []): Story {
  let clock = 0
  const legs = journey.legs.map((leg, index) => {
    const km = (lengths[index] ?? 0) / 1000
    const travelMs = Math.min(110000, Math.max(55000, 55000 + km * 250))
    const delay = trainDelay(journey, leg, index, prediction) ?? 0
    const pauseMs = Math.min(20000, Math.max(0, delay) * 1000)
    const dwellStart = clock
    const travelStart = dwellStart + (index === 0 ? 3000 : DWELL_MS)
    const travelEnd = travelStart + travelMs + pauseMs
    clock = travelEnd
    return { dwellStart, travelStart, travelMs, pauseAt: .65, pauseMs, travelEnd }
  })
  return { legs, cycle: clock + FINAL_HOLD_MS }
}

/** Trapezoid speed profile: 12% of the leg accelerating, 12% braking. */
export function easeTravel(u: number) {
  const r = .12, v = 1 / (1 - r)
  if (u <= 0) return 0
  if (u >= 1) return 1
  if (u < r) return v * u * u / (2 * r)
  if (u < 1 - r) return v * (r / 2 + (u - r))
  return 1 - v * (1 - u) ** 2 / (2 * r)
}

export function storyState(story: Story, elapsedMs: number): { legs: LegState[]; active: number } {
  const t = story.cycle > 0 ? Math.max(0, elapsedMs) % story.cycle : 0
  let active = story.legs.length - 1
  const legs = story.legs.map((leg, index) => {
    if (t < leg.travelEnd && t >= leg.dwellStart && index < active) active = index
    if (t < leg.travelStart) return { progress: 0, phase: 'waiting' as const }
    if (t >= leg.travelEnd) return { progress: 1, phase: 'arrived' as const }
    const local = t - leg.travelStart
    const pauseStart = leg.pauseAt * leg.travelMs
    if (leg.pauseMs > 0 && local >= pauseStart && local < pauseStart + leg.pauseMs) return { progress: easeTravel(leg.pauseAt), phase: 'held' as const }
    const u = (local >= pauseStart ? local - leg.pauseMs : local) / leg.travelMs
    return { progress: easeTravel(u), phase: 'moving' as const }
  })
  return { legs, active }
}

/** Miniature scale in metres per model unit: legible at any zoom, never longer than a slice of its own track. */
export function trainScale(zoom: number, trackLength: number) {
  return Math.min(trackLength / 22, Math.max(30, 14000 / 2 ** (zoom - 6)))
}
export function disruptionKind(text: string): 'works' | 'weather' | 'technical' | 'reported' {
  if (/\b(baustelle|bauarbeiten|construction|engineering works|track works)\b/i.test(text)) return 'works'
  if (/\b(storm|snow|flood|weather|sturm|schnee|hochwasser|unwetter)\b/i.test(text)) return 'weather'
  if (/\b(signal failure|technical fault|technical failure|signalstörung|signalstoerung|technische störung)\b/i.test(text)) return 'technical'
  return 'reported'
}
