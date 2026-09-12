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
        const colour = m.highlight ? "#8b8bff" : "#4b4b5c"
        return (
          <g key={m.name}>
            <text x={0} y={y + 15} fontSize="11" fill={m.highlight ? "#f4f4f5" : "#9a9aa8"} fontWeight={m.highlight ? 600 : 400}>
              {m.name}
            </text>
            <rect x={labelW} y={y + 4} width={bw} height={14} rx={3} fill={colour} />
            <text x={labelW + bw + 6} y={y + 15} fontSize="11" fill="#e5e5ea" fontFamily="ui-monospace, monospace">
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
      <section className="rounded-2xl border border-border bg-black/30 p-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <Database className="size-4 text-sky-300" /> Where the data comes from
        </h3>
        <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
          <li>
            <b className="text-foreground/90">piebro/deutsche-bahn-data</b> (CC BY 4.0): every DB stop event from the Timetables/IRIS feed, monthly parquet files, all stations since Nov 2025.
          </li>
          <li>
            <b className="text-foreground/90">Six commuter regions</b> as training universe: Munich, Berlin, Hamburg, Cologne, Frankfurt, Stuttgart — S-Bahn and regional trains, one hop along local operators.
          </li>
          <li>
            <b className="text-foreground/90">Cause codes</b> parsed from the raw IRIS XML into six families; only ~30% of stops carry one, and the app says so instead of inventing a reason.
          </li>
          <li>
            <b className="text-foreground/90">DB Timetables API</b> live for station lookup and re-routes; <b className="text-foreground/90">Nebius</b> GPUs (4× L40S) for training and ablations.
          </li>
        </ul>
      </section>

      <section className="rounded-2xl border border-border bg-black/30 p-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <FlaskConical className="size-4 text-violet-300" /> Does it work? Our model vs. the given baseline
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
          <img src="/proof.png" alt="Model vs baseline chart" className="mt-2 w-full rounded-lg" />
        ) : (
          <div className="mt-2 h-24 animate-pulse rounded-xl bg-white/5" />
        )}
        <p className="mt-2 text-sm text-muted-foreground">
          The baseline is the track's own: raw delay history pasted into GPT / Claude Opus. A small time-series LLM fine-tuned on the per-train history beats it on the held-out months, and so do the classic baselines it was checked against.
        </p>
      </section>

      <section className="rounded-2xl border border-border bg-black/30 p-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <ShieldAlert className="size-4 text-amber-300" /> Where it can fail, what it can't do yet
        </h3>
        <ul className="mt-2 list-disc space-y-1 pl-4 text-sm text-muted-foreground">
          <li>Transfers are chained as if trains were independent — optimistic when one disruption hits both, and DB holding a connecting train is not modelled.</li>
          <li>Trained on regional and S-Bahn trains in six regions; long-distance ICE/IC and other regions fall back to a class prior.</li>
          <li>When the model server is offline the app shows a prior (badge “mock-prior”), not the fine-tuned forecast.</li>
          <li>Confidence dots are advisory, not calibrated probabilities; the “why” text quotes inputs, not causes.</li>
          <li>Causes are known for only ~30% of stop events; the rest is honestly unattributed.</li>
          <li>Share-sheet entry needs the app installed from HTTPS on Android; iOS uses paste.</li>
        </ul>
      </section>

      <section className="rounded-2xl border border-border bg-black/30 p-4 text-center">
        <p className="text-lg font-medium">Not “it will rain” — “take an umbrella”.</p>
        <p className="mt-1 text-sm text-muted-foreground">Install error404 and it shows up in the DB app's share sheet.</p>
        <div className="mt-3">
          <InstallButton big />
        </div>
      </section>
    </div>
  )
}
