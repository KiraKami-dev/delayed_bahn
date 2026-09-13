import { AlertTriangle, ArrowRight, CheckCircle2, Clock3, Home, Route, Share2, Umbrella } from "lucide-react"
import { useState } from "react"
import type { Recommendation, Verdict } from "@/lib/contract"
import { fmtDate, fmtTime, journeyOutlook, pct } from "@/lib/geo"
import { useStore } from "@/lib/store"
import { cn } from "@/lib/utils"
import { WhyDisclosure } from "@/features/delay-prediction/components/WhyDisclosure"

const VERDICT: Record<Verdict, { label: string; Icon: typeof Umbrella; colour: string }> = {
  good: { label: "Your connection looks manageable", Icon: CheckCircle2, colour: "#26704c" },
  "add-buffer": { label: "A little more transfer time would help", Icon: Clock3, colour: "#916019" },
  "take-alternative": { label: "Consider a less rushed connection", Icon: Route, colour: "#b54534" },
}

export function travelerAdvice(rec: Recommendation): string {
  if (rec.verdict === "good") return "Your connections look manageable in this estimate. Keep an eye on live departures and allow enough time to reach your platform."
  if (rec.verdict === "add-buffer") return `Look for a connection with ${rec.bufferMinutes ?? "a few"} extra minutes to change trains. The comparison shows a timing scenario, not a verified service.`
  return "Consider an earlier departure or a longer change. Compare the timing scenario, then find an actual connection in DB Navigator before changing your plans."
}

function minus(iso: string, minutes: number): string {
  return new Date(new Date(iso).getTime() - minutes * 60000).toISOString()
}

/* ---------- leave home by ---------- */
export function LeaveHomeBy({ rec }: { rec: Recommendation }) {
  const s = useStore()
  const journey = s.journey
  if (!journey) return null
  const chosen = journey.legs[0].plannedDeparture
  const leaveBy = minus(chosen, s.doorToStationMin + 5)
  return <section className="rounded-xl border border-border bg-white p-4" aria-label="Departure preparation">
    <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="flex items-center gap-2 text-sm font-medium"><Home size={16} className="text-muted-foreground" /> Aim to leave by</h3><span className="text-2xl font-semibold tracking-tight">{fmtTime(leaveBy)}</span></div>
    <p className="mt-1 text-[10px] text-muted-foreground">{fmtDate(leaveBy)} · {s.doorToStationMin} min to {journey.legs[0].from.name} + 5 min to find your platform.</p>
    <label className="mt-5 flex items-center justify-between gap-2 text-xs" htmlFor="station-travel-time">Time to the first station<span className="font-semibold text-primary">{s.doorToStationMin} min</span></label>
    <input id="station-travel-time" type="range" min={5} max={90} step={5} value={s.doorToStationMin} onChange={e => s.dispatch({ type: "door", minutes: Number(e.target.value) })} className="mt-3 w-full" aria-valuetext={`${s.doorToStationMin} minutes`} />
    <p className="mt-2 text-[10px] text-muted-foreground">Based on a scheduled {fmtTime(chosen)} departure{rec.verdict !== "good" ? " on your original journey, not the suggested scenario" : " on your original journey"}. Allow more time if you need help boarding. Confirm the train is running before leaving.</p>
  </section>
}

/* ---------- missed connection / re-route ---------- */
export function MissedConnection() {
  const s = useStore()
  const [loading, setLoading] = useState(false)
  const journey = s.journey
  if (!journey || journey.legs.length < 2) return null
  return <section className="rounded-xl border border-border bg-white p-4">
    <h3 className="flex items-center gap-2 text-sm font-medium"><AlertTriangle size={16} className="text-risk-mid" /> Missed a connection?</h3>
    <p className="mt-1 text-xs text-muted-foreground">Choose where you’re changing trains to check next steps.</p>
    <div className="mt-3 flex flex-wrap gap-2">{journey.legs.slice(0, -1).map((leg, i) => <button key={i} type="button" disabled={loading || s.busy} onClick={async () => { setLoading(true); try { await s.fetchReroute(i) } finally { setLoading(false) } }} className={cn("min-h-10 rounded-lg border border-border px-3 py-2 text-xs hover:bg-secondary", s.missedLeg === i && s.overlay === "reroute" && "border-primary bg-secondary text-primary")}>{leg.to.name}<ArrowRight size={12} className="ml-2 inline" /></button>)}</div>
    {loading && <p className="mt-3 text-xs text-muted-foreground" role="status">Checking the next connections…</p>}
    {s.reroute && s.overlay === "reroute" && <><p className="mt-3 text-[10px] text-muted-foreground">Timing scenarios, not verified departures or ticket bookings. These trains may not run at the times shown. Check actual services in DB Navigator.</p><ul className="mt-3 space-y-2">{s.reroute.options.length === 0 && <li className="text-xs text-muted-foreground">No alternatives returned. Please check the station departure board.</li>}{s.reroute.options.map((o, i) => <li key={i}><button type="button" aria-pressed={s.rerouteChoice === i} onClick={() => s.dispatch({ type: "rerouteChoice", index: i })} className={cn("flex w-full items-start gap-3 rounded-lg border border-border p-3 text-left text-xs hover:bg-secondary", s.rerouteChoice === i && "border-primary bg-secondary")}><Route size={16} /><span className="min-w-0 flex-1"><strong className="block font-medium">{o.label}</strong><span className="mt-1 block text-[10px] leading-relaxed text-muted-foreground">{o.journey.legs.map(l => `${l.trainId} ${fmtTime(l.plannedDeparture)}`).join(" · ")}<br />Arrive {fmtTime(o.journey.legs.at(-1)!.plannedArrival)}</span></span><span className="shrink-0 text-right" style={{ color: journeyOutlook(o.planFailProbability.value).colour }}>{journeyOutlook(o.planFailProbability.value).percent}% {journeyOutlook(o.planFailProbability.value).short}<br /><span className="text-[10px] text-muted-foreground">+{o.arrivalDelayMinutes} min</span></span></button></li>)}</ul></>}
  </section>
}

/* ---------- panel ---------- */
export function AdvicePanel() {
  const s = useStore()
  const [shareStatus, setShareStatus] = useState("")
  const [copyText, setCopyText] = useState("")
  const journey = s.journey
  const rec = s.recommendation
  if (!journey) return null
  if (!rec) return <p className="rounded-xl border border-border bg-white p-4 text-sm text-muted-foreground">{s.error ? "Travel advice isn’t available yet. Retry your check above, or confirm your options in DB Navigator." : "Working out useful next steps…"}</p>
  const v = VERDICT[rec.verdict]
  const share = async () => {
    const kind = journey.source === "seed" ? "EXAMPLE TRIP — not live travel advice. " : s.prediction?.modelId.includes("mock") ? "Illustrative prior — no live delay data. " : "Advisory estimate, not a guarantee. "
    const text = `${kind}${fmtDate(journey.legs[0].plannedDeparture)}: ${journey.legs[0].from.name} → ${journey.legs.at(-1)!.to.name}. Estimated plan-failure risk: ${pct(s.prediction?.planFailProbability.value ?? 0)}. ${travelerAdvice(rec)} Confirm current trains in DB Navigator.`
    setShareStatus("")
    try {
      if (navigator.share) { await navigator.share({ title: "delayedBahn journey outlook", text }); setShareStatus("Result shared.") }
      else { await navigator.clipboard.writeText(text); setShareStatus("Result copied to clipboard.") }
    } catch (error) {
      /* dismissed */
      if ((error as Error).name !== "AbortError") { setCopyText(text); setShareStatus("Automatic sharing isn’t available. Select and copy the result below.") }
    }
  }
  return <div className="space-y-4">
    <section className="rounded-xl border border-border bg-white p-4">
      <h2 className="flex items-center gap-2 text-sm font-semibold" style={{ color: v.colour }}><v.Icon size={19} />{v.label}</h2>
      <p className="mt-3 text-sm leading-relaxed">{travelerAdvice(rec)}</p>
      {rec.bufferMinutes != null && rec.verdict === "add-buffer" && <p className="mt-2 text-xs text-muted-foreground">Look for a connection with {rec.bufferMinutes} more minutes to change trains. This does not change your booked journey.</p>}
      <div className="mt-4 flex flex-wrap gap-2">{rec.alternative && <button type="button" aria-pressed={s.overlay === "alternative"} onClick={() => s.dispatch({ type: "overlay", overlay: s.overlay === "alternative" ? "none" : "alternative" })} className="min-h-10 rounded-lg border border-border px-3 py-2 text-xs font-medium text-primary hover:bg-secondary">{s.overlay === "alternative" ? "Hide alternative" : "Compare alternative"}</button>}<button type="button" onClick={() => void share()} className="inline-flex min-h-10 items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-xs hover:bg-secondary"><Share2 size={14} /> Share result</button></div>
      {shareStatus && <p role="status" className="mt-3 text-xs text-primary">{shareStatus}</p>}
      {copyText && <textarea aria-label="Result to copy" readOnly value={copyText} onFocus={e => e.target.select()} className="journey-input mt-3" rows={5} />}
      <div className="mt-4"><WhyDisclosure item={rec.advice} label="Why this advice?" /></div>
    </section>
    {rec.alternative && s.overlay === "alternative" && <section className="rounded-xl border border-[#cedfc6] bg-[#f0f5eb] p-4"><h3 className="text-sm font-medium">Timing scenario · not a verified train</h3><p className="mt-1 text-[10px] text-muted-foreground">Dashed on the route map. These times illustrate extra buffer and may not match any running service. Find an actual departure in DB Navigator.</p><ul className="mt-3 space-y-3">{rec.alternative.legs.map((l, i) => <li key={i} className="text-xs"><strong className="font-medium">{l.trainId}</strong> · {fmtDate(l.plannedDeparture)}<span className="mt-1 block text-muted-foreground">{fmtTime(l.plannedDeparture)} {l.from.name} → {fmtTime(l.plannedArrival)} {l.to.name}</span>{l.transferMinutes != null && <span className="text-[10px] text-muted-foreground">{l.transferMinutes} min to change</span>}</li>)}</ul></section>}
    <LeaveHomeBy rec={rec} /><MissedConnection />
  </div>
}
