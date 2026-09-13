import { createContext, useCallback, useContext, useMemo, useReducer, useRef, type ReactNode } from "react"
import { api, loadFixture, type ApiError } from "./api"
import type { Causes, Journey, Prediction, Recommendation, Reroute, Station } from "./contract"
import { hydrateCoords } from "./stations"

export type Tab = "plan" | "forecast" | "advice" | "causes" | "evidence"
export type Stage = "idle" | "parsing" | "journey" | "predicting" | "predicted" | "recommending" | "done" | "error"

export type State = {
  tab: Tab
  stage: Stage
  sharedText?: string
  journey?: Journey
  prediction?: Prediction
  recommendation?: Recommendation
  reroute?: Reroute
  missedLeg?: number
  causes?: Causes
  causesFor?: string
  error?: string
  offline: boolean
  selectedLeg: number | null
  bufferExtra: number
  doorToStationMin: number
  acceptableRisk: number
  overlay: "none" | "alternative" | "reroute"
  rerouteChoice: number
  stageMode: boolean
  stageStep: number
  busy: boolean
}

type Action =
  | { type: "tab"; tab: Tab }
  | { type: "stage"; stage: Stage }
  | { type: "draft"; text: string }
  | { type: "share"; text: string }
  | { type: "journey"; journey: Journey }
  | { type: "prediction"; prediction: Prediction }
  | { type: "recommendation"; recommendation: Recommendation }
  | { type: "reroute"; reroute: Reroute; missedLeg: number }
  | { type: "causes"; causes: Causes; causesFor: string }
  | { type: "error"; error: string }
  | { type: "offline"; offline: boolean }
  | { type: "selectLeg"; index: number | null }
  | { type: "buffer"; minutes: number }
  | { type: "door"; minutes: number }
  | { type: "risk"; risk: number }
  | { type: "overlay"; overlay: State["overlay"] }
  | { type: "rerouteChoice"; index: number }
  | { type: "stageMode"; on: boolean }
  | { type: "stageStep"; step: number }
  | { type: "busy"; busy: boolean }
  | { type: "reset" }

const initial: State = {
  tab: "plan", stage: "idle", offline: false, selectedLeg: null,
  bufferExtra: 0, doorToStationMin: 20, acceptableRisk: 0.15,
  overlay: "none", rerouteChoice: 0, stageMode: false, stageStep: 0, busy: false,
}

function reducer(s: State, a: Action): State {
  switch (a.type) {
    case "tab": return { ...s, tab: a.tab }
    case "stage": return { ...s, stage: a.stage }
    case "draft": return { ...s, sharedText: a.text }
    case "share": return { ...initial, stageMode: s.stageMode, sharedText: a.text, stage: "parsing", busy: true }
    case "journey": return { ...s, tab: "plan", journey: a.journey, prediction: undefined, recommendation: undefined, reroute: undefined, missedLeg: undefined, causes: undefined, causesFor: undefined, overlay: "none", bufferExtra: 0, selectedLeg: null, stage: "journey", error: undefined }
    case "prediction": return { ...s, prediction: a.prediction, stage: "predicted" }
    case "recommendation": return { ...s, recommendation: a.recommendation, stage: "done", error: undefined }
    case "reroute": return { ...s, reroute: a.reroute, missedLeg: a.missedLeg, overlay: "reroute", rerouteChoice: 0, error: undefined }
    case "causes": return { ...s, causes: a.causes, causesFor: a.causesFor }
    case "error": return { ...s, error: a.error, stage: "error", busy: false }
    case "offline": return { ...s, offline: a.offline }
    case "selectLeg": return { ...s, selectedLeg: a.index, causes: undefined, causesFor: undefined }
    case "buffer": return { ...s, bufferExtra: a.minutes }
    case "door": return { ...s, doorToStationMin: a.minutes }
    case "risk": return { ...s, acceptableRisk: a.risk }
    case "overlay": return { ...s, overlay: a.overlay }
    case "rerouteChoice": return { ...s, rerouteChoice: a.index }
    case "stageMode": return { ...s, stageMode: a.on, stageStep: a.on ? s.stageStep : 0 }
    case "stageStep": return { ...s, stageStep: a.step }
    case "busy": return { ...s, busy: a.busy }
    case "reset": return { ...initial, stageMode: s.stageMode }
  }
}

type Actions = {
  dispatch: (a: Action) => void
  runFromText: (text: string) => Promise<void>
  runFromSeed: () => Promise<void>
  runJourney: (journey: Journey) => Promise<void>
  refreshRecommendation: (doorToStationMin?: number, acceptableRisk?: number) => Promise<void>
  fetchReroute: (missedLeg: number) => Promise<void>
  fetchCauses: (station: Station) => Promise<void>
}

const Ctx = createContext<(State & Actions) | null>(null)
const validProbability = (p: number) => Number.isFinite(p) && p >= 0 && p <= 1

/**
 * Call the real service. The bundled sample answers only for the example trip
 * and only when the service is unreachable (status 0: offline, timeout, HTML
 * captive portal), never on a real error, so a live trip never shows sample data.
 */
async function withSeedFallback<T>(journey: Journey, call: () => Promise<T>, fixture: "prediction" | "recommendation" | "reroute" | "journey"): Promise<T> {
  try {
    return await call()
  } catch (e) {
    const status = (e as ApiError).status
    if (journey.source !== "seed" || status !== 0) throw e
    return loadFixture<T>(fixture)
  }
}

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, rawDispatch] = useReducer(reducer, initial)
  const generation = useRef(0)
  const causesRequest = useRef(0)
  const rerouteRequest = useRef(0)
  const dispatch = useCallback((action: Action) => {
    if (action.type === "reset") generation.current++
    if (action.type === "selectLeg") causesRequest.current++
    rawDispatch(action)
  }, [])

  const pipeline = useCallback(async (journey: Journey, requestId: number) => {
    if (!journey?.legs?.length || !journey.legs.every(l => l.trainId && l.from?.name && l.to?.name && Number.isFinite(Date.parse(l.plannedDeparture)) && Date.parse(l.plannedArrival) > Date.parse(l.plannedDeparture))) throw new Error("The journey has incomplete train details. Please check its stations and times.")
    if (requestId !== generation.current) return
    const j = hydrateCoords(journey)
    dispatch({ type: "journey", journey: j })
    dispatch({ type: "busy", busy: true })
    dispatch({ type: "stage", stage: "predicting" })
    // Every journey, the example trip included, is forecast by the real service.
    // Only when the service cannot be reached at all (offline PWA) does the
    // example trip fall back to its bundled sample, which the UI labels as such.
    const prediction = await withSeedFallback(j, () => api.predict(j), "prediction")
    if (requestId !== generation.current) return
    if (prediction.journeyId !== j.id || prediction.legs?.length !== j.legs.length || !validProbability(prediction.planFailProbability?.value) || !prediction.legs.every((l, i) => l.trainId === j.legs[i].trainId && Number.isFinite(l.expectedDelayMinutes?.value) && validProbability(l.missProbability?.value))) throw new Error("The forecast did not match your journey. Please try again.")
    dispatch({ type: "prediction", prediction })
    dispatch({ type: "stage", stage: "recommending" })
    try {
      let recommendation = await withSeedFallback(j, () => api.recommend(j, prediction), "recommendation")
      if (requestId !== generation.current) return
      if (recommendation.alternative) recommendation = { ...recommendation, alternative: hydrateCoords(recommendation.alternative) }
      dispatch({ type: "recommendation", recommendation })
    } catch {
      if (requestId === generation.current) dispatch({ type: "error", error: "Your forecast is available, but travel advice could not be loaded. Please retry, or check alternatives in DB Navigator." })
    } finally {
      if (requestId === generation.current) dispatch({ type: "busy", busy: false })
    }
  }, [dispatch])

  const runJourney = useCallback(async (journey: Journey) => {
    const id = ++generation.current
    try { await pipeline(journey, id) }
    catch { if (id === generation.current) dispatch({ type: "error", error: "We couldn’t get a forecast for this trip. No example forecast has been substituted. Please try again." }) }
  }, [pipeline, dispatch])

  const runFromText = useCallback(async (text: string) => {
    const id = ++generation.current
    dispatch({ type: "share", text })
    try {
      const journey = await api.parseJourney(text)
      if (id === generation.current) await pipeline({ ...journey, source: "db-share" }, id)
    } catch (e) {
      if (id !== generation.current) return
      const err = e as { status?: number; message?: string }
      dispatch({ type: "error", error: err.status === 400 || err.status === 422 ? err.message || "Paste the full journey text, including train names, stations and times." : `The trip-checking service is unavailable (${err.message || "no response"}). Your text is still here. Try again, or explore the clearly labelled example trip.` })
    }
  }, [pipeline, dispatch])

  const runFromSeed = useCallback(async () => {
    const id = ++generation.current
    dispatch({ type: "busy", busy: true })
    try {
      // The example trip comes from the service too; the bundled copy only answers offline.
      const seed: Journey = { id: "seed", legs: [], source: "seed" }
      const journey = await withSeedFallback(seed, () => api.seedDemo(), "journey")
      if (id === generation.current) await pipeline({ ...journey, source: "seed" }, id)
    } catch {
      if (id === generation.current) dispatch({ type: "error", error: "The example trip could not be loaded. Check your connection and try again." })
    }
  }, [pipeline, dispatch])

  const refreshRecommendation = useCallback(async (door?: number, risk?: number) => {
    if (!state.journey || !state.prediction) return
    const id = generation.current
    if (door != null) dispatch({ type: "door", minutes: door })
    if (risk != null) dispatch({ type: "risk", risk })
    try {
      let rec = await api.recommend(state.journey, state.prediction, door ?? state.doorToStationMin, risk ?? state.acceptableRisk)
      if (id !== generation.current) return
      if (rec.alternative) rec = { ...rec, alternative: hydrateCoords(rec.alternative) }
      dispatch({ type: "recommendation", recommendation: rec })
    } catch {
      /* keep the current recommendation; LeaveHomeBy computes locally */
    }
  }, [state.journey, state.prediction, state.doorToStationMin, state.acceptableRisk, dispatch])

  const fetchReroute = useCallback(async (missedLeg: number) => {
    if (!state.journey || state.busy) return
    const id = generation.current
    const attempt = ++rerouteRequest.current
    try {
      const journey = state.journey
      let reroute = await withSeedFallback(journey, () => api.reroute(journey, missedLeg), "reroute")
      if (id !== generation.current || attempt !== rerouteRequest.current) return
      reroute = { ...reroute, options: reroute.options.map(o => ({ ...o, journey: hydrateCoords(o.journey) })) }
      dispatch({ type: "reroute", reroute, missedLeg })
    } catch {
      if (id === generation.current && attempt === rerouteRequest.current) dispatch({ type: "error", error: "Alternatives are unavailable. Check the next departures in DB Navigator; we have not substituted sample trains." })
    }
  }, [state.journey, state.busy, dispatch])

  const fetchCauses = useCallback(async (station: Station) => {
    const key = station.evaNumber || station.name
    if (state.causesFor === key && state.causes) return
    const id = generation.current
    const attempt = ++causesRequest.current
    try {
      const causes = await api.causes(station.evaNumber, station.name)
      if (id === generation.current && attempt === causesRequest.current) dispatch({ type: "causes", causes, causesFor: key })
    } catch {
      if (id === generation.current && attempt === causesRequest.current) dispatch({ type: "error", error: "Station background data is unavailable. Your journey forecast has not changed." })
    }
  }, [state.causesFor, state.causes, dispatch])

  const value = useMemo(() => ({ ...state, dispatch, runFromText, runFromSeed, runJourney, refreshRecommendation, fetchReroute, fetchCauses }), [state, dispatch, runFromText, runFromSeed, runJourney, refreshRecommendation, fetchReroute, fetchCauses])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useStore() {
  const v = useContext(Ctx)
  if (!v) throw new Error("useStore outside StoreProvider")
  return v
}
