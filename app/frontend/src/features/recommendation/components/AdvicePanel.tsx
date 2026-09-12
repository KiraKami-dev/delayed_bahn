import { AlertTriangle, CheckCircle2, CloudLightning, Home, Route, Share2, Umbrella } from "lucide-react"
import { useMemo } from "react"
import type { Recommendation, Verdict } from "@/lib/contract"
import { fmtTime, pct, riskColour } from "@/lib/geo"
import { useStore } from "@/lib/store"
import { cn } from "@/lib/utils"
import { WhyDisclosure } from "@/features/delay-prediction/components/WhyDisclosure"

const VERDICT: Record<Verdict, { label: string; Icon: typeof Umbrella; colour: string }> = {
  good: { label: "Clear skies — keep your plan", Icon: CheckCircle2, colour: "#34d399" },
  "add-buffer": { label: "Showers likely — add buffer", Icon: Umbrella, colour: "#fbbf24" },
  "take-alternative": { label: "Storm warning — take the earlier train", Icon: CloudLightning, colour: "#f87171" },
}

function minus(iso: string, minutes: number): string {
  return new Date(new Date(iso).getTime() - minutes * 60000).toISOString()
}

/* ---------- leave home by ---------- */
export function LeaveHomeBy({ rec }: { rec: Recommendation }) {
  const s = useStore()
  const journey = s.journey
  if (!journey) return null
  const chosen = rec.chosenDeparture ?? (rec.verdict === "take-alternative" && rec.alternative ? rec.alternative.legs[0].plannedDeparture : journey.legs[0].plannedDeparture)
  const leaveBy = useMemo(() => minus(chosen, s.doorToStationMin + 5), [chosen, s.doorToStationMin])
  return (
    <div className="rounded-xl border border-border bg-black/30 p-3">
      <div className="flex items-center gap-2 text-sm font-medium">
        <Home className="size-4 text-muted-foreground" /> Leave home by <span className="ml-auto font-mono text-lg">{fmtTime(leaveBy)}</span>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        {s.doorToStationMin} min door to {journey.legs[0].from.name}, 5 min to find the platform, {rec.verdict === "take-alternative" ? "the earlier" : "your"} train at {fmtTime(chosen)}.
      </p>
      <label className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
        Door → station
        <input
          type="range"
          min={5}
          max={90}
          step={5}
          value={s.doorToStationMin}
          onChange={(e) => s.dispatch({ type: "door", minutes: Number(e.target.value) })}
          className="flex-1 accent-[#8b8bff]"
          aria-label="Minutes from door to the first station"
        />
        <span className="w-12 text-right font-mono">{s.doorToStationMin} min</span>
      </label>
    </div>
  )
}

/* ---------- missed connection / re-route ---------- */
export function MissedConnection() {
  const s = useStore()
  const journey = s.journey
  if (!journey || journey.legs.length < 2) return null
  const transfers = journey.legs.slice(0, -1)
  return (
    <div className="rounded-xl border border-border bg-black/30 p-3">
      <div className="flex items-center gap-2 text-sm font-medium">
        <AlertTriangle className="size-4 text-amber-300" /> I missed my connection at…
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        {transfers.map((leg, i) => (
          <button
            key={i}
            type="button"
            onClick={() => void s.fetchReroute(i)}
            className={cn("rounded-full border border-border px-3 py-1 text-xs hover:bg-white/5", s.missedLeg === i && s.overlay === "reroute" && "border-ring bg-primary/20 text-white")}
          >
            {leg.to.name}
          </button>
        ))}
      </div>
      {s.reroute && s.overlay === "reroute" && (
        <ul className="mt-3 space-y-1.5">
          {s.reroute.options.map((o, i) => {
            const best = i === 0
            return (
              <li key={i}>
                <button
                  type="button"
                  onClick={() => s.dispatch({ type: "rerouteChoice", index: i })}
                  className={cn("flex w-full items-center gap-3 rounded-lg border border-border px-3 py-2 text-left text-sm hover:bg-white/5", s.rerouteChoice === i && "border-ring bg-white/5")}
                >
                  <Route className="size-4 shrink-0 text-muted-foreground" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">{o.label}</span>
                    <span className="block text-xs text-muted-foreground">
                      {o.journey.legs.map((l) => `${l.trainId} ${fmtTime(l.plannedDeparture)}`).join(" · ")} → arrive {fmtTime(o.journey.legs[o.journey.legs.length - 1].plannedArrival)}
                    </span>
                  </span>
                  <span className="text-right text-xs">
                    <span className="block font-mono" style={{ color: riskColour(o.planFailProbability.value) }}>
                      {pct(o.planFailProbability.value)} risk
                    </span>
                    <span className="block text-muted-foreground">+{o.arrivalDelayMinutes} min</span>
                  </span>
                  {best && <span className="rounded-full bg-emerald-400/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">best</span>}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

/* ---------- panel ---------- */
export function AdvicePanel() {
  const s = useStore()
  const journey = s.journey
  const rec = s.recommendation
  if (!journey) return null
  if (!rec)
    return (
      <div className="space-y-3">
        <div className="h-20 animate-pulse rounded-2xl bg-white/5" />
        <p className="text-sm text-muted-foreground">Working out what to do…</p>
      </div>
    )
  const v = VERDICT[rec.verdict]
  const share = async () => {
    const text = `${journey.legs[0].from.name} → ${journey.legs[journey.legs.length - 1].to.name}: ${pct(s.prediction?.planFailProbability.value ?? 0)} chance my plan fails. ${rec.advice.value}`
    try {
      if (navigator.share) await navigator.share({ title: "error404 forecast", text })
      else await navigator.clipboard.writeText(text)
    } catch {
      /* dismissed */
    }
  }
  return (
    <div className="space-y-3">
      <div className="rounded-2xl border border-border bg-black/30 p-4">
        <div className="flex items-center gap-2 text-sm font-semibold" style={{ color: v.colour }}>
          <v.Icon className="size-5" /> {v.label}
        </div>
        <p className="mt-2 text-lg leading-snug">{rec.advice.value}</p>
        {rec.bufferMinutes != null && rec.verdict === "add-buffer" && (
          <p className="mt-1 text-sm text-muted-foreground">Take the next connection: +{rec.bufferMinutes} min at the tight change.</p>
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          {rec.alternative && (
            <button
              type="button"
              onClick={() => s.dispatch({ type: "overlay", overlay: s.overlay === "alternative" ? "none" : "alternative" })}
              className={cn("rounded-xl border border-border px-3 py-2 text-sm hover:bg-white/5", s.overlay === "alternative" && "border-emerald-300/60 bg-emerald-400/10 text-emerald-200")}
            >
              {s.overlay === "alternative" ? "Hide alternative" : "Show alternative on the map"}
            </button>
          )}
          <button type="button" onClick={() => void share()} className="inline-flex items-center gap-1.5 rounded-xl border border-border px-3 py-2 text-sm hover:bg-white/5">
            <Share2 className="size-4" /> Share result
          </button>
        </div>
        <div className="mt-3">
          <WhyDisclosure item={rec.advice} label="Why this advice?" />
        </div>
      </div>
      {rec.alternative && s.overlay === "alternative" && (
        <div className="rounded-xl border border-emerald-300/30 bg-emerald-400/5 p-3 text-sm">
          <div className="font-medium text-emerald-200">Alternative (dashed on the map)</div>
          <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
            {rec.alternative.legs.map((l, i) => (
              <li key={i}>
                <span className="font-mono text-foreground">{l.trainId}</span> {fmtTime(l.plannedDeparture)} {l.from.name} → {fmtTime(l.plannedArrival)} {l.to.name}
                {l.transferMinutes != null && ` · ${l.transferMinutes} min change`}
              </li>
            ))}
          </ul>
        </div>
      )}
      <LeaveHomeBy rec={rec} />
      <MissedConnection />
    </div>
  )
}
