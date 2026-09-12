import { Presentation, RotateCcw } from "lucide-react"
import { useStore } from "@/lib/store"
import { GlobeMap } from "@/features/globe-map/components/GlobeMap"
import { StartPanel } from "@/features/share-parser/components/StartPanel"
import { JourneyCards } from "@/features/share-parser/components/JourneyCards"
import { ForecastPanel } from "@/features/delay-prediction/components/ForecastPanel"
import { AdvicePanel } from "@/features/recommendation/components/AdvicePanel"
import { CausesPanel } from "@/features/causes/components/CausesPanel"
import { EvidencePanel } from "@/features/evidence/components/EvidencePanel"
import { TabBar } from "./TabBar"
import { InstallButton, OfflinePill } from "./StatusPills"
import { STAGE_STEPS } from "../hooks/useStageKeys"

function PanelBody() {
  const s = useStore()
  switch (s.tab) {
    case "plan":
      return s.journey ? <JourneyCards journey={s.journey} /> : <StartPanel />
    case "forecast":
      return <ForecastPanel />
    case "advice":
      return <AdvicePanel />
    case "causes":
      return <CausesPanel />
    case "evidence":
      return <EvidencePanel />
  }
}

export function AppShell() {
  const s = useStore()
  return (
    <div className="shell">
      <GlobeMap />

      <div className="brand">
        <span className="rounded-full bg-black/50 px-3 py-1 text-sm font-semibold tracking-tight backdrop-blur">
          <span style={{ color: "#ec0016" }}>error</span>404
        </span>
        <OfflinePill />
        <InstallButton />
      </div>

      <div className="absolute right-4 top-3 z-20 hidden gap-2 lg:right-[calc(var(--panel-w)+32px)] lg:flex">
        {s.journey && (
          <button
            type="button"
            onClick={() => s.dispatch({ type: "reset" })}
            className="inline-flex items-center gap-1.5 rounded-full border border-border bg-black/40 px-3 py-1 text-xs backdrop-blur hover:bg-white/10"
          >
            <RotateCcw className="size-3.5" /> New plan
          </button>
        )}
        <button
          type="button"
          onClick={() => s.dispatch({ type: "stageMode", on: !s.stageMode })}
          className="inline-flex items-center gap-1.5 rounded-full border border-border bg-black/40 px-3 py-1 text-xs backdrop-blur hover:bg-white/10"
          title="Stage mode (S). Arrow keys walk the flow, F fullscreen, M motion."
        >
          <Presentation className="size-3.5" /> {s.stageMode ? "Exit stage" : "Stage"}
        </button>
      </div>

      <aside className="panel glass">
        {s.journey && s.tab === "plan" && (
          <div className="flex justify-end px-4 pt-3 lg:hidden">
            <button type="button" onClick={() => s.dispatch({ type: "reset" })} className="text-xs text-muted-foreground">
              New plan
            </button>
          </div>
        )}
        <div className="panel-scroll flex-1 p-4 pt-4">
          <PanelBody />
        </div>
        <TabBar />
      </aside>

      {s.stageMode && (
        <div className="stage-dots" aria-label={`Step ${s.stageStep + 1} of ${STAGE_STEPS.length}: ${STAGE_STEPS[s.stageStep]?.label}`}>
          {STAGE_STEPS.map((st, i) => (
            <i key={st.label + i} data-on={i === s.stageStep} />
          ))}
        </div>
      )}
    </div>
  )
}
