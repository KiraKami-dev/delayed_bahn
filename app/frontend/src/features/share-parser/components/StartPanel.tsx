import { ArrowRight, Check, ClipboardPaste, Loader2, PenLine, Share2, TrainFront } from "lucide-react"
import { useState } from "react"
import { useStore } from "@/lib/store"
import { cn } from "@/lib/utils"
import { useDropText } from "@/features/pwa-shell/hooks/useDropText"
import { JourneyBuilder } from "./JourneyBuilder"

export const SAMPLE_SHARE = `Nürnberg Hbf → München Hbf
Sun 13.09.2026
RB16 (59143)
To München Hbf
From 04:34 Nürnberg Hbf, Platform 5 C-F
To 07:25 München Hbf, Platform 21
View journey: https://int.bahn.de/en/buchung/start?vbid=e6285f4d-26a0-45db-a595-f36ddbb4ff20`

type Mode = "paste" | "build"

export function StartPanel() {
  const s = useStore()
  const [mode, setMode] = useState<Mode>("paste")
  const text = s.sharedText ?? ""
  const setText = (text: string) => s.dispatch({ type: "draft", text })
  const drop = useDropText((t) => { if (!s.busy) setText(t) })

  return (
    <section className="start-card" id="trip-form" aria-labelledby="trip-form-title" {...drop.handlers}>
      <div className="form-heading">
        <span className="icon-tile"><TrainFront size={21} /></span>
        <div><h2 id="trip-form-title">Let’s check your journey.</h2><p>No account. Just your travel plans.</p></div>
      </div>
      <div className="input-modes" aria-label="How to enter your trip">
        <button type="button" aria-pressed={mode === "paste"} onClick={() => setMode("paste")} disabled={s.busy}><ClipboardPaste size={16} /> Paste DB journey</button>
        <button type="button" aria-pressed={mode === "build"} onClick={() => setMode("build")} disabled={s.busy}><PenLine size={16} /> Enter train details</button>
      </div>
      {mode === "paste" ? (
        <form onSubmit={(e) => { e.preventDefault(); if (text.trim() && !s.busy) void s.runFromText(text) }}>
          <label className="field-label" htmlFor="journey-text">Your journey from DB Navigator</label>
          <textarea
            id="journey-text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={s.busy}
            rows={5}
            maxLength={20000}
            aria-describedby="paste-hint"
            placeholder={"Paste the shared journey text here…\n\nNürnberg Hbf → München Hbf\nRB 16 · 04:34 – 07:25"}
            className={cn("journey-input", drop.over && "is-dragging")}
          />
          <p id="paste-hint" className="field-hint"><Share2 size={14} /> In DB Navigator: open your journey → Share → Copy.</p>
          <button type="submit" disabled={!text.trim() || s.busy} className="primary-button check-button">
            {s.busy ? <><Loader2 size={18} className="animate-spin" /> Checking your journey…</> : <>Check my trip <ArrowRight size={18} /></>}
          </button>
        </form>
      ) : <JourneyBuilder />}
      <div className="example-row"><span>Just having a look?</span><button type="button" disabled={s.busy} onClick={() => void s.runFromSeed()}>Try an example trip <ArrowRight size={14} /></button></div>
      <div className="form-reassurance"><Check size={13} /> Your journey stays in this session. No sign-up needed.</div>
    </section>
  )
}
