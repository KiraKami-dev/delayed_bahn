import { Database, FlaskConical, ShieldAlert } from "lucide-react"
import { useEffect, useState } from "react"
import type { Proof } from "@/lib/contract"
import { InstallButton } from "@/features/pwa-shell/components/StatusPills"

export function ResultsChart({ proof }: { proof: Proof }) {
  const max = Math.max(...proof.models.map((m) => m.value), 0.01)
  const rowH = 26
  const w = 300
  const labelW = 150
  return (
    <svg viewBox={`0 0 ${w} ${proof.models.length * rowH + 8}`} className="w-full" role="img" aria-label={proof.label}>
      {proof.models.map((m, i) => {
        const bw = ((w - labelW - 44) * m.value) / max
        const y = i * rowH + 4
        const colour = m.highlight ? "#5c8451" : "#acb7a3"
        return (
          <g key={m.name}>
            <text x={0} y={y + 15} fontSize="11" fill={m.highlight ? "#285b43" : "#66736c"} fontWeight={m.highlight ? 600 : 400}>
              {m.name}
            </text>
            <rect x={labelW} y={y + 4} width={bw} height={14} rx={3} fill={colour} />
            <text x={labelW + bw + 6} y={y + 15} fontSize="11" fill="#44543e" fontFamily="ui-monospace, monospace">
              {m.value.toFixed(3)}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

export function EvidencePanel() {
  const [proof, setProof] = useState<Proof | null>(null)
  const [png, setPng] = useState(false)
  useEffect(() => {
    fetch("/proof.json")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((p: Proof) => setProof(p))
      .catch(() => setPng(true))
  }, [])
  return (
    <div className="space-y-3">
      <section className="rounded-2xl border border-border bg-white p-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <Database className="size-4 text-sky-800" /> Where the data comes from
        </h3>
        <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
          <li>
            <b className="text-foreground/90">piebro/deutsche-bahn-data</b> (CC BY 4.0): every DB stop event from the Timetables/IRIS feed, monthly parquet files, all stations since Nov 2025.
          </li>
          <li>
            <b className="text-foreground/90">All of Germany</b> as training universe: 2,539 stations and 722 services, S-Bahn and regional trains one hop out from the hubs along local operators; the forecast names the recorded service and stop it used.
          </li>
          <li>
            <b className="text-foreground/90">Cause codes</b> parsed from the raw IRIS XML into six families; only ~30% of stops carry one, and the app says so instead of inventing a reason.
          </li>
          <li>
            <b className="text-foreground/90">Alternative times</b> currently include synthetic timing scenarios, not verified live departures. Use DB Navigator to confirm the actual timetable.
          </li>
        </ul>
      </section>

      <section className="rounded-2xl border border-border bg-white p-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <FlaskConical className="size-4 text-primary" /> Evaluation · held-out trains and weeks
        </h3>
        {proof ? (
          <>
            <p className="mt-1 text-xs text-muted-foreground">
              {proof.label} · {proof.split} · n = {proof.n.toLocaleString()}
            </p>
            <div className="mt-2">
              <ResultsChart proof={proof} />
            </div>
            {"note" in proof && <p className="mt-1 text-[11px] text-muted-foreground">{String((proof as Proof & { note?: string }).note)}</p>}
          </>
        ) : png ? (
          <p className="mt-3 text-sm text-muted-foreground">Evaluation data is unavailable. No accuracy claims can be made from this screen.</p>
        ) : (
          <div className="mt-2 h-24 animate-pulse rounded-xl bg-white/5" />
        )}
        <p className="mt-2 text-sm text-muted-foreground">
          Numbers from the bake-off on all-Germany data (quarter profile, 2,000 steps, one H100): the fine-tuned model ties a gradient-boosting baseline on the same inputs and both beat the naive train-median by about 30%. A tie is not a win; the chart says what was measured, not more.
        </p>
      </section>

      <section className="rounded-2xl border border-border bg-white p-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <ShieldAlert className="size-4 text-amber-800" /> Where it can fail, what it can't do yet
        </h3>
        <ul className="mt-2 list-disc space-y-1 pl-4 text-sm text-muted-foreground">
          <li>Transfers are chained as if trains were independent — optimistic when one disruption hits both, and DB holding a connecting train is not modelled.</li>
          <li>The model forecasts a service's next-week departure delay at a recorded stop; a train it never saw gets the closest recorded service on the same corridor, its recorded history, or a class prior, and the “why” text says which.</li>
          <li>When the model server is offline the app shows a prior (badge “mock-prior”), not the fine-tuned forecast.</li>
          <li>Confidence dots are advisory, not calibrated probabilities; the “why” text quotes inputs, not causes.</li>
          <li>Causes are known for only ~30% of stop events; the rest is honestly unattributed.</li>
          <li>Share-sheet entry needs the app installed from HTTPS on Android; iOS uses paste.</li>
        </ul>
      </section>

      <section className="rounded-2xl border border-border bg-white p-4 text-center">
        <p className="text-lg font-medium">Not “it will rain” — “take an umbrella”.</p>
        <p className="mt-1 text-sm text-muted-foreground">Install error404 and it shows up in the DB app's share sheet.</p>
        <div className="mt-3">
          <InstallButton big />
        </div>
      </section>
    </div>
  )
}
