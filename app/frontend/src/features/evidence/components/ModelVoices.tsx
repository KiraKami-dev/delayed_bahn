import { MessageSquareQuote } from "lucide-react"
import { useEffect, useState } from "react"
import { api } from "@/lib/api"
import type { Generation, Generations } from "@/lib/contract"

const KIND: Record<Generation["kind"], string> = {
  ScalarPredictionTask: "Minutes late next week",
  ClassificationTask: "Late or on time? Which cause?",
  AnswerTask: "Advice in one sentence",
}

function trim(text: string | undefined, max = 220): string {
  if (!text) return ""
  const t = text.replace(/\s+/g, " ").trim()
  return t.length > max ? t.slice(0, max - 1) + "…" : t
}

/**
 * What the fine-tuned model actually generated, verbatim, for random held-out rows:
 * the question it was asked, its answer, and the recorded truth. Nothing here is
 * templated by the app; the text is the model's own output from the GPU job log.
 */
export function ModelVoices({ compact = false }: { compact?: boolean }) {
  const [data, setData] = useState<Generations | null>(null)
  const [failed, setFailed] = useState(false)
  const [i, setI] = useState(0)
  useEffect(() => {
    api.generations().then(setData).catch(() => setFailed(true))
  }, [])
  if (failed) return <p className="text-xs text-muted-foreground">The model's generated answers are not available from this backend.</p>
  if (!data) return <p className="text-xs text-muted-foreground">Loading the model's own answers…</p>
  if (!data.samples.length) return <p className="text-xs text-muted-foreground">{data.note || "No generated answers were saved for this model."}</p>
  const g = data.samples[i % data.samples.length]
  const agree = g.truth && g.model.trim().toLowerCase() === g.truth.trim().toLowerCase()
  return (
    <div className={compact ? "space-y-2" : "rounded-2xl border border-border bg-white p-4 space-y-2"}>
      <h3 className="flex items-center gap-2 text-sm font-semibold"><MessageSquareQuote className="size-4 text-primary" /> In the model's own words</h3>
      <p className="text-[11px] text-muted-foreground">{KIND[g.kind]}{g.service ? ` · ${g.service} at ${g.station}` : ""}{g.travelDate ? ` · ${g.travelDate}` : ""}</p>
      {g.question && <p className="text-xs text-muted-foreground">Asked: {trim(g.question)}</p>}
      {g.options && <p className="text-[11px] text-muted-foreground">Options: {g.options.join(", ")}</p>}
      <blockquote className="rounded-xl border-l-4 border-primary bg-secondary/60 px-3 py-2 text-sm">“{g.model}”</blockquote>
      <p className="text-xs">
        <span className="text-muted-foreground">What actually happened: </span>
        <span className={agree ? "text-risk-low font-medium" : "font-medium"}>{g.truth}</span>
        {g.actualMinutes != null && <span className="text-muted-foreground"> ({g.actualMinutes} min)</span>}
        {g.quantiles && <span className="text-muted-foreground"> · distribution median {g.quantiles.p50}, range {g.quantiles.p10}–{g.quantiles.p90} min</span>}
      </p>
      <div className="flex items-center justify-between text-[11px] text-muted-foreground">
        <button type="button" className="rounded-lg border border-border px-2 py-1" onClick={() => setI((i - 1 + data.samples.length) % data.samples.length)} aria-label="Previous sample">‹</button>
        <span>sample {(i % data.samples.length) + 1} / {data.samples.length} · verbatim from the GPU job{data.job ? ` ${data.job}` : ""}</span>
        <button type="button" className="rounded-lg border border-border px-2 py-1" onClick={() => setI((i + 1) % data.samples.length)} aria-label="Next sample">›</button>
      </div>
    </div>
  )
}
