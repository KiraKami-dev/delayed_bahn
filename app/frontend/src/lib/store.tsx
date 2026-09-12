import { createContext, useCallback, useContext, useMemo, useReducer, type ReactNode } from "react"
import { api, loadFixture } from "./api"
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
  tab: "plan",
  stage: "idle",
  offline: false,
  selectedLeg: null,
  bufferExtra: 0,
  doorToStationMin: 20,
  acceptableRisk: 0.15,
  overlay: "none",
  rerouteChoice: 0,
  stageMode: false,
  stageStep: 0,
  busy: false,
}

function reducer(s: State, a: Action): State {
  switch (a.type) {
    case "tab": return { ...s, tab: a.tab }
    case "stage": return { ...s, stage: a.stage }
    case "share": return { ...s, sharedText: a.text, stage: "parsing", error: undefined }
    case "journey": return { ...s, journey: a.journey, prediction: undefined, recommendation: undefined, reroute: undefined, missedLeg: undefined, overlay: "none", bufferExtra: 0, selectedLeg: null, stage: "journey", error: undefined }
    case "prediction": return { ...s, prediction: a.prediction, stage: "predicted" }
    case "recommendation": return { ...s, recommendation: a.recommendation, stage: "done" }
    case "reroute": return { ...s, reroute: a.reroute, missedLeg: a.missedLeg, overlay: "reroute", rerouteChoice: 0 }
    case "causes": return { ...s, causes: a.causes, causesFor: a.causesFor }
    case "error": return { ...s, error: a.error, stage: "error", busy: false }
    case "offline": return { ...s, offline: a.offline }
    case "selectLeg": return { ...s, selectedLeg: a.index }
    case "buffer": return { ...s, bufferExtra: a.minutes }
    case "door": return { ...s, doorToStationMin: a.minutes }
    case "risk": return { ...s, acceptableRisk: a.risk }
    case "overlay": return { ...s, overlay: a.overlay }
    case "rerouteChoice": return { ...s, rerouteChoice: a.index }
    case "stageMode": return { ...s, stageMode: a.on, stageStep: a.on ? s.stageStep : 0 }
    case "stageStep": return { ...s, stageStep: a.step }
    case "busy": return { ...s, busy: a.busy }
    case "reset": return { ...initial, offline: s.offline, stageMode: s.stageMode }
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

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initial)

  const pipeline = useCallback(
    async (journey: Journey, opts?: { door?: number; risk?: number }) => {
      const j = hydrateCoords(journey)
      dispatch({ type: "journey", journey: j })
      dispatch({ type: "busy", busy: true })
      let offline = false
      let prediction: Prediction
      dispatch({ type: "stage", stage: "predicting" })
      try {
        prediction = await api.predict(j)
      } catch {
        offline = true
        prediction = await loadFixture<Prediction>("prediction")
        prediction = { ...prediction, journeyId: j.id }
      }
      await sleep(250)
      dispatch({ type: "prediction", prediction })
      dispatch({ type: "stage", stage: "recommending" })
      let recommendation: Recommendation
      try {
        if (offline) throw new Error("offline")
        recommendation = await api.recommend(j, prediction, opts?.door, opts?.risk)
      } catch {
        offline = true
        recommendation = await loadFixture<Recommendation>("recommendation")
      }
      if (recommendation.alternative) recommendation = { ...recommendation, alternative: hydrateCoords(recommendation.alternative) }
      dispatch({ type: "offline", offline })
      dispatch({ type: "recommendation", recommendation })
      dispatch({ type: "busy", busy: false })
    },
    [],
  )

  const runJourney = useCallback((journey: Journey) => pipeline(journey), [pipeline])

  const runFromText = useCallback(
    async (text: string) => {
      dispatch({ type: "share", text })
      dispatch({ type: "busy", busy: true })
      try {
        const journey = await api.parseJourney(text)
        await pipeline(journey)
      } catch (e) {
        const err = e as { status?: number; message?: string }
        if (err.status === 400 || err.status === 422) {
          dispatch({ type: "error", error: err.message || "Could not find a connection in that text." })
          return
        }
        // Backend unreachable: fall back to the seed so the app still works.
        dispatch({ type: "offline", offline: true })
        try {
          const journey = await loadFixture<Journey>("journey")
          await pipeline(journey)
        } catch {
          dispatch({ type: "error", error: "The forecast service is unreachable and no offline seed is bundled." })
        }
      }
    },
    [pipeline],
  )

  const runFromSeed = useCallback(async () => {
    dispatch({ type: "busy", busy: true })
    let journey: Journey
    try {
      journey = await api.seedDemo()
    } catch {
      dispatch({ type: "offline", offline: true })
      journey = await loadFixture<Journey>("journey")
    }
    await pipeline(journey)
  }, [pipeline])

  const refreshRecommendation = useCallback(
    async (door?: number, risk?: number) => {
      if (!state.journey || !state.prediction) return
      if (door != null) dispatch({ type: "door", minutes: door })
      if (risk != null) dispatch({ type: "risk", risk })
      try {
        let rec = await api.recommend(state.journey, state.prediction, door ?? state.doorToStationMin, risk ?? state.acceptableRisk)
        if (rec.alternative) rec = { ...rec, alternative: hydrateCoords(rec.alternative) }
        dispatch({ type: "recommendation", recommendation: rec })
      } catch {
        /* keep the current recommendation; LeaveHomeBy computes locally */
      }
    },
    [state.journey, state.prediction, state.doorToStationMin, state.acceptableRisk],
  )

  const fetchReroute = useCallback(
    async (missedLeg: number) => {
      if (!state.journey) return
      let reroute: Reroute
      try {
        reroute = await api.reroute(state.journey, missedLeg)
      } catch {
        reroute = await loadFixture<Reroute>("reroute")
      }
      reroute = { ...reroute, options: reroute.options.map((o) => ({ ...o, journey: hydrateCoords(o.journey) })) }
      dispatch({ type: "reroute", reroute, missedLeg })
    },
    [state.journey],
  )

  const fetchCauses = useCallback(
    async (station: Station) => {
      const key = station.evaNumber || station.name
      if (state.causesFor === key && state.causes) return
      let causes: Causes
      try {
        causes = await api.causes(station.evaNumber, station.name)
      } catch {
        causes = await loadFixture<Causes>("causes")
        causes = { ...causes, station }
      }
      dispatch({ type: "causes", causes, causesFor: key })
    },
    [state.causesFor, state.causes],
  )

  const value = useMemo(
    () => ({ ...state, dispatch, runFromText, runFromSeed, runJourney, refreshRecommendation, fetchReroute, fetchCauses }),
    [state, runFromText, runFromSeed, runJourney, refreshRecommendation, fetchReroute, fetchCauses],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useStore() {
  const v = useContext(Ctx)
  if (!v) throw new Error("useStore outside StoreProvider")
  return v
}
