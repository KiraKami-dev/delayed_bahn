import { useEffect } from "react"
import type { CauseFamilies, Causes } from "@/lib/contract"
import { pct } from "@/lib/geo"
import { useStore } from "@/lib/store"

const FAMILY: { key: keyof CauseFamilies; label: string; colour: string }[] = [
  { key: "works", label: "Construction works", colour: "#f59e0b" },
  { key: "weather", label: "Weather", colour: "#60a5fa" },
  { key: "technical", label: "Technical faults", colour: "#f87171" },
  { key: "knock_on", label: "Knock-on from other trains", colour: "#c084fc" },
  { key: "staff", label: "Staff shortage", colour: "#fb7185" },
  { key: "external", label: "External (police, medical…)", colour: "#34d399" },
  { key: "unattributed", label: "No cause given", colour: "#3f3f4a" },
]

export function CauseStack({ families }: { families: CauseFamilies }) {
  let x = 0
  return (
    <div>
      <svg viewBox="0 0 100 14" className="h-5 w-full" role="img" aria-label="Share of delay by cause family" preserveAspectRatio="none">
        {FAMILY.map((f) => {
          const w = Math.max(0, families[f.key] * 100)
          const el = <rect key={f.key} x={x} y={0} width={w} height={14} fill={f.colour} />
          x += w
          return el
        })}
      </svg>
      <ul className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        {FAMILY.map((f) => (
          <li key={f.key} className="flex items-center gap-2">
            <i className="inline-block size-2.5 rounded-sm" style={{ background: f.colour }} />
            <span className="flex-1 truncate text-muted-foreground">{f.label}</span>
            <span className="font-mono">{pct(families[f.key])}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function DelaySparkline({ points }: { points: Causes["sparkline7d"] }) {
  if (!points?.length) return null
  const max = Math.max(...points.map((p) => p.meanDelayMin), 1)
  const w = 220, h = 48
  const step = w / Math.max(points.length - 1, 1)
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${i * step},${h - 6 - (p.meanDelayMin / max) * (h - 12)}`).join(" ")
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-12 w-full" role="img" aria-label="Mean delay over the last 7 days">
      <path d={path} fill="none" stroke="#8b8bff" strokeWidth={2} strokeLinejoin="round" />
      {points.map((p, i) => (
        <circle key={p.date} cx={i * step} cy={h - 6 - (p.meanDelayMin / max) * (h - 12)} r={2.5} fill="#c7c7ff" />
      ))}
    </svg>
  )
}

export function CausesPanel() {
  const s = useStore()
  const journey = s.journey
  const idx = Math.min(s.selectedLeg ?? 0, (journey?.legs.length ?? 1) - 1)
  const station = journey?.legs[idx]?.to
  useEffect(() => {
    if (station) void s.fetchCauses(station)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [station?.evaNumber, station?.name])
  if (!journey || !station) return null
  const c = s.causes
  return (
    <div className="space-y-3">
      <div>
        <h2 className="text-base font-semibold">Possible delay causes at {station.name}</h2>
        <p className="text-xs text-muted-foreground">Station-level patterns explain what can happen, not the confirmed cause of your train’s delay. Select a station below.</p>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {journey.legs.map((l, i) => (
          <button
            key={i}
            type="button"
            onClick={() => s.dispatch({ type: "selectLeg", index: i })}
            className={`rounded-full border px-3 py-1 text-xs ${i === idx ? "border-ring bg-secondary text-primary" : "border-border text-muted-foreground hover:bg-white/5"}`}
          >
            {l.to.name}
          </button>
        ))}
      </div>
      {!c ? (
        <div className="h-24 animate-pulse rounded-2xl bg-white/5" />
      ) : (
        <>
          <div className="rounded-2xl border border-border bg-white p-4">
            <div className="text-xs uppercase tracking-wide text-muted-foreground">Delay minutes by cause family</div>
            <div className="mt-2">
              <CauseStack families={c.families} />
            </div>
          </div>
          <div className="rounded-xl border border-border bg-white p-3">
            <div className="text-xs uppercase tracking-wide text-muted-foreground">Top named causes (DB IRIS text)</div>
            <ul className="mt-1.5 space-y-1 text-sm">
              {c.top.map((t) => (
                <li key={t.code} className="flex items-baseline gap-2">
                  <span className="font-mono text-xs text-muted-foreground">#{t.code}</span>
                  <span className="flex-1">{t.text}</span>
                  <span className="font-mono text-xs">{pct(t.share)}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-xl border border-border bg-white p-3">
            <div className="text-xs uppercase tracking-wide text-muted-foreground">Mean delay, last 7 days</div>
            <DelaySparkline points={c.sparkline7d} />
          </div>
          <p className="text-[11px] text-muted-foreground">
            Only {pct(c.attributionRate)} of stop events carry a cause code, so most delay is honestly “no cause given”. Source: {c.source}
          </p>
        </>
      )}
    </div>
  )
}
