import { useCallback, useEffect } from "react"
import { useStore, type Tab } from "@/lib/store"
import { toggleMotion } from "@/lib/motion"
import { SAMPLE_SHARE } from "@/features/share-parser/components/StartPanel"

/**
 * Stage mode: the real app, bigger type, and arrow keys that walk the real flow.
 *   0 Plan (empty)  1 share arrives  2 journey cards  3 forecast
 *   4 advice        5 missed connection → re-route  6 causes  7 evidence
 */
export const STAGE_STEPS: { tab: Tab; label: string }[] = [
  { tab: "plan", label: "Plan" },
  { tab: "plan", label: "Share from the DB app" },
  { tab: "plan", label: "Journey" },
  { tab: "forecast", label: "Forecast" },
  { tab: "advice", label: "Advice" },
  { tab: "advice", label: "Missed connection" },
  { tab: "causes", label: "Causes" },
  { tab: "evidence", label: "Evidence" },
]

export function useStageKeys() {
  const s = useStore()

  const apply = useCallback(
    async (step: number) => {
      const st = STAGE_STEPS[step]
      if (!st) return
      s.dispatch({ type: "stageStep", step })
      if (step === 0) {
        s.dispatch({ type: "reset" })
        s.dispatch({ type: "tab", tab: "plan" })
        return
      }
      if (!s.journey) {
        s.dispatch({ type: "tab", tab: "plan" })
        await s.runFromText(SAMPLE_SHARE)
      }
      if (step === 1) {
        s.dispatch({ type: "tab", tab: "plan" })
        s.dispatch({ type: "overlay", overlay: "none" })
        return
      }
      if (step === 5) {
        s.dispatch({ type: "tab", tab: "advice" })
        await s.fetchReroute(0)
        return
      }
      if (step === 4) s.dispatch({ type: "overlay", overlay: "none" })
      s.dispatch({ type: "tab", tab: st.tab })
    },
    [s],
  )

  useEffect(() => {
    const q = new URLSearchParams(location.search)
    if (q.get("stage") === "1" && !s.stageMode) s.dispatch({ type: "stageMode", on: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (s.stageMode) document.documentElement.dataset.stage = "1"
    else delete document.documentElement.dataset.stage
  }, [s.stageMode])

  // Keep the progress dots honest when the tab changes by tap or deep link.
  useEffect(() => {
    if (!s.stageMode) return
    if (STAGE_STEPS[s.stageStep]?.tab === s.tab) return
    const idx = STAGE_STEPS.findIndex((st, i) => st.tab === s.tab && (s.tab !== "plan" || (s.journey ? i === 2 : i === 0)))
    if (idx >= 0) s.dispatch({ type: "stageStep", step: idx })
  }, [s.tab, s.stageMode, s.stageStep, s.journey, s])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      const typing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)
      if (typing) return
      if (e.key === "s" || e.key === "S") {
        s.dispatch({ type: "stageMode", on: !s.stageMode })
        return
      }
      if (e.key === "m" || e.key === "M") {
        toggleMotion()
        return
      }
      if (e.key === "f" || e.key === "F") {
        if (document.fullscreenElement) void document.exitFullscreen()
        else void document.documentElement.requestFullscreen?.()
        return
      }
      if (!s.stageMode) return
      if (e.key === "ArrowRight" || e.key === " " || e.key === "PageDown") {
        e.preventDefault()
        void apply(Math.min(STAGE_STEPS.length - 1, s.stageStep + 1))
      } else if (e.key === "ArrowLeft" || e.key === "PageUp") {
        e.preventDefault()
        void apply(Math.max(0, s.stageStep - 1))
      } else if (e.key === "Home") {
        void apply(0)
      } else if (e.key === "Escape") {
        s.dispatch({ type: "stageMode", on: false })
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [s, apply])
}
