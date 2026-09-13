import { animate } from "motion"
import { useEffect, useMemo, useRef, useState } from "react"
import type { Journey, LegDelay, Prediction } from "@/lib/contract"
import { rechain, transferBuffer } from "@/lib/chain"
import { pct, riskColour } from "@/lib/geo"
import { useReducedMotion } from "@/lib/motion"
import { useStore } from "@/lib/store"
import { LegCard } from "@/features/share-parser/components/LegCard"
import { WhyDisclosure } from "./WhyDisclosure"

/* ---------- headline count-up ---------- */
export function FailHeadline({ value, label = "Probability your plan fails" }: { value: number; label?: string }) {
  const still = useReducedMotion()
  const [shown, setShown] = useState(still ? value : 0)
  const prev = useRef(0)
  useEffect(() => {
    if (still) {
      setShown(value)
      return
    }
    const controls = animate(prev.current, value, { duration: 1.2, ease: "easeOut", onUpdate: (v) => setShown(v) })
    prev.current = value
    return () => controls.stop()
  }, [value, still])
  const colour = riskColour(value)
  return (
    <div className="rounded-2xl border border-border bg-white p-4">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="headline-number mt-1 text-6xl font-semibold" style={{ color: colour }}>
        {Math.round(shown * 100)}
        <span className="text-3xl">%</span>
      </div>
    </div>
  )
}

/* ---------- per-leg delay bars ---------- */
export function DelayBars({ leg }: { leg: LegDelay }) {
  const d = leg.distribution
  if (!d) return null
  const max = Math.max(...d.probs, 0.01)
  const colours = ["#34d399", "#a3e635", "#fbbf24", "#f87171", "#9ca3af"]
  return (
    <svg viewBox="0 0 220 64" className="mt-2 h-16 w-full" role="img" aria-label={`Delay probability: ${d.bins.map((bin, i) => `${bin} minutes: ${pct(d.probs[i] ?? 0)}`).join(", ")}`}>
      {d.bins.map((bin, i) => {
        const p = d.probs[i] ?? 0
        const h = Math.max(2, (p / max) * 40)
        const x = 4 + i * 44
        return (
          <g key={bin}>
            <rect x={x} y={44 - h} width={36} height={h} rx={3} fill={colours[i] ?? "#999"} opacity={0.9} />
            <text x={x + 18} y={44 - h - 3} textAnchor="middle" fontSize="9" fill="#44543e">
              {Math.round(p * 100)}%
            </text>
            <text x={x + 18} y={58} textAnchor="middle" fontSize="9" fill="#9a9aa8">
              {bin}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

/* ---------- chain strip ---------- */
export function ChainStrip({ journey, prediction, missOverride }: { journey: Journey; prediction: Prediction; missOverride?: number[] }) {
  return (
    <div className="flex items-stretch gap-1 overflow-x-auto py-1">
      {journey.legs.map((leg, i) => {
        const last = i === journey.legs.length - 1
        const miss = missOverride?.[i] ?? prediction.legs[i]?.missProbability.value ?? 0
        const delay = prediction.legs[i]?.expectedDelayMinutes.value ?? 0
        const buffer = transferBuffer(journey, i)
        const left = Math.max(0, buffer - delay)
        return (
          <div key={i} className="flex items-center gap-1">
            <div className="rounded-lg border border-border bg-white px-2 py-1.5 text-center">
              <div className="font-mono text-[11px] font-semibold">{leg.trainId}</div>
              <div className="text-[10px] text-muted-foreground">+{delay} min</div>
            </div>
            {!last && (
              <div className="flex flex-col items-center px-1 text-[10px]" title={`${buffer} min planned change`}>
                <div className="relative h-2.5 rounded-full bg-white/10" style={{ width: Math.min(96, 8 + buffer * 3) }}>
                  <div
                    className="absolute inset-y-0 left-0 rounded-full"
                    style={{ width: `${Math.round((left / Math.max(buffer, 1)) * 100)}%`, background: riskColour(miss) }}
                  />
                </div>
                <span style={{ color: riskColour(miss) }}>{miss >= 0.4 ? "missed?" : `${pct(miss)} miss`}</span>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

/* ---------- buffer slider ---------- */
export function BufferSlider({ journey, prediction }: { journey: Journey; prediction: Prediction }) {
  const s = useStore()
  const result = useMemo(() => rechain(journey, prediction, s.bufferExtra), [journey, prediction, s.bufferExtra])
  if (journey.legs.length < 2) return null
  return (
    <div className="rounded-xl border border-border bg-white p-3">
      <div className="flex items-center justify-between text-sm">
        <span>
          What if I had <b>+{s.bufferExtra} min</b> at every change?
        </span>
        <span className="font-mono" style={{ color: riskColour(result.planFail) }}>
          {pct(result.planFail)}
        </span>
      </div>
      <input
        type="range"
        min={0}
        max={60}
        step={5}
        value={s.bufferExtra}
        onChange={(e) => s.dispatch({ type: "buffer", minutes: Number(e.target.value) })}
        className="mt-2 w-full accent-primary"
        aria-label="Extra minutes at each change"
      />
      <p className="mt-1 text-[11px] text-muted-foreground">A what-if estimate, not a confirmed alternative. Extra buffer does not change your booked trains.</p>
    </div>
  )
}

/* ---------- the panel ---------- */
export function ForecastPanel() {
  const s = useStore()
  const journey = s.journey
  const prediction = s.prediction
  if (!journey) return null
  if (!prediction)
    return (
      <div className="space-y-3">
        <div className="h-24 animate-pulse rounded-2xl bg-secondary" />
        <p className="text-sm text-muted-foreground">{s.error ? "Your forecast is unavailable. Retry your check above; we won’t substitute an example result." : "Forecasting each train…"}</p>
      </div>
    )
  const live = s.bufferExtra > 0 ? rechain(journey, prediction, s.bufferExtra) : null
  return (
    <div className="space-y-3">
      {journey.legs.length > 1 && <><FailHeadline value={live ? live.planFail : prediction.planFailProbability.value} /><WhyDisclosure item={prediction.planFailProbability} label="Why this number?" /></>}
      <ChainStrip journey={journey} prediction={prediction} missOverride={live?.legs} />
      <div className="space-y-2">
        {journey.legs.map((leg, i) => {
          const d = prediction.legs[i]
          if (!d) return null
          const q = d.quantiles
          return (
            <LegCard key={i} leg={leg} index={i} active={s.selectedLeg === i} delay={d} onSelect={(j) => s.dispatch({ type: "selectLeg", index: s.selectedLeg === j ? null : j })}>
              <div className="mt-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-sm">
                <span>
                  <b>+{d.expectedDelayMinutes.value} min</b>
                  {q && <span className="text-muted-foreground"> · likely {q.p10}–{q.p90}</span>}
                </span>
                {i < journey.legs.length - 1 && (
                  <span className="text-xs" style={{ color: riskColour(live?.legs[i] ?? d.missProbability.value) }}>
                    {pct(live?.legs[i] ?? d.missProbability.value)} chance to miss the change
                  </span>
                )}
              </div>
              <DelayBars leg={d} />
              <div className="mt-1 flex flex-wrap gap-3">
                <WhyDisclosure item={d.expectedDelayMinutes} label="Why this delay?" />
                {i < journey.legs.length - 1 && <WhyDisclosure item={d.missProbability} label="Why this change?" />}
              </div>
            </LegCard>
          )
        })}
      </div>
      <BufferSlider journey={journey} prediction={prediction} />
      <p className="text-[11px] text-muted-foreground">
        Model: <span className="font-mono">{prediction.modelId}</span>
        {prediction.modelId.startsWith("mock") && " · prior only, the fine-tuned model server is offline"}
      </p>
    </div>
  )
}
