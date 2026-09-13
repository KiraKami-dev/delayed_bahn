// Types from team-setup/state/03-contract-freeze/contract.md, plus additive
// optional fields the app uses (lat/lon, distributions, leave-home time).

export type Station = {
  evaNumber: string
  name: string
  lat?: number
  lon?: number
}

export type Leg = {
  // Optional frontend map metadata from the timetable provider; never inferred.
  routeGeometry?: [number, number][]

  trainId: string // e.g. "RB 16"
  trainNumber?: string
  from: Station
  to: Station
  plannedDeparture: string // ISO 8601 with offset
  plannedArrival: string
  transferMinutes?: number // planned transfer to the next leg
}

export type Journey = {
  id: string
  legs: Leg[]
  source: "db-share" | "manual" | "seed"
}

export type Confidence = "low" | "medium" | "high"

export type Explained<T> = {
  value: T
  reasoning: string
  sources: string[]
  confidence: Confidence
}

export type DelayDistribution = {
  bins: string[] // e.g. ["≤5", "5–15", "15–30", ">30", "cancelled"]
  probs: number[]
}

export type LegDelay = {
  trainId: string
  expectedDelayMinutes: Explained<number>
  missProbability: Explained<number> // 0..1, chance this transfer breaks
  distribution?: DelayDistribution
  quantiles?: { p10: number; p50: number; p90: number }
  pCancel?: number
  // Full per-minute pmf when the backend provides it; used by the buffer slider.
  probs?: number[]
}

export type Prediction = {
  journeyId: string
  legs: LegDelay[]
  planFailProbability: Explained<number>
  modelId: string
}

export type Verdict = "good" | "add-buffer" | "take-alternative"

export type Recommendation = {
  verdict: Verdict
  advice: Explained<string>
  bufferMinutes?: number
  alternative?: Journey
  leaveHomeBy?: string
  chosenDeparture?: string
}

export type RerouteOption = {
  journey: Journey
  planFailProbability: Explained<number>
  arrivalDelayMinutes: number
  label: string
}

export type Reroute = {
  station: Station
  options: RerouteOption[]
}

export type CauseFamilies = {
  works: number
  weather: number
  technical: number
  knock_on: number
  staff: number
  external: number
  unattributed: number
}

export type Causes = {
  station: Station
  attributionRate: number
  families: CauseFamilies
  top: { code: number; text: string; share: number }[]
  sparkline7d: { date: string; meanDelayMin: number }[]
  source: string
}

export type Proof = {
  metric: string
  label: string
  lowerIsBetter: boolean
  n: number
  split: string
  models: { name: string; value: number; highlight?: boolean }[]
}
