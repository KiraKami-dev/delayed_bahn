import { ClipboardPaste, Loader2, Share2, Sparkles, Wrench } from "lucide-react"
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
  const [text, setText] = useState("")
  const drop = useDropText((t) => {
    setText(t)
    void s.runFromText(t)
  })

  return (
    <div className="space-y-4" {...drop.handlers}>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Will my plan hold?</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Share a connection from the DB app, paste it, or build one. You get the chance your plan fails and what to do about it.
        </p>
      </div>

      <div className="flex gap-1 rounded-lg bg-black/30 p-1 text-sm">
        {(
          [
            ["paste", "Paste or drop", ClipboardPaste],
            ["build", "Build", Wrench],
          ] as const
        ).map(([id, label, Icon]) => (
          <button
            key={id}
            type="button"
            onClick={() => setMode(id)}
            className={cn("flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5", mode === id ? "bg-white/10 text-white" : "text-muted-foreground")}
          >
            <Icon className="size-4" /> {label}
          </button>
        ))}
      </div>

      {mode === "paste" ? (
        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (text.trim()) void s.runFromText(text)
          }}
        >
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={6}
            placeholder={"Paste what the DB app shared, e.g.\n" + SAMPLE_SHARE.split("\n").slice(0, 4).join("\n") + "\n…"}
            className={cn(
              "w-full resize-none rounded-xl border border-input bg-black/30 p-3 font-mono text-[13px] leading-snug outline-none placeholder:text-muted-foreground/60 focus:border-ring",
              drop.over && "border-ring bg-primary/10",
            )}
          />
          <div className="flex flex-wrap gap-2">
            <button
              type="submit"
              disabled={!text.trim() || s.busy}
              className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 font-medium text-white disabled:opacity-50"
            >
              {s.busy ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />} Check my plan
            </button>
            <button
              type="button"
              disabled={s.busy}
              onClick={() => {
                setText(SAMPLE_SHARE)
                void s.runFromText(SAMPLE_SHARE)
              }}
              className="rounded-xl border border-border px-4 py-2.5 text-sm hover:bg-white/5"
            >
              Use a real share text
            </button>
            <button
              type="button"
              disabled={s.busy}
              onClick={() => void s.runFromSeed()}
              className="rounded-xl border border-border px-4 py-2.5 text-sm hover:bg-white/5"
            >
              Demo journey
            </button>
          </div>
        </form>
      ) : (
        <JourneyBuilder />
      )}

      {s.error && <p className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-red-200">{s.error}</p>}

      <p className="flex items-start gap-2 text-xs text-muted-foreground">
        <Share2 className="mt-0.5 size-3.5 shrink-0" />
        In the DB app, open a connection, press <b className="text-foreground/80">Share</b> and pick <b className="text-foreground/80">error404</b>. The journey lands here with no typing.
      </p>
    </div>
  )
}
