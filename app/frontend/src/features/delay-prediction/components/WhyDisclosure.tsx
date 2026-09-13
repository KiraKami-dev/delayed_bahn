import { ChevronDown } from "lucide-react"
import { useState } from "react"
import type { Explained } from "@/lib/contract"
import { cn } from "@/lib/utils"

const DOTS: Record<Explained<unknown>["confidence"], number> = { low: 1, medium: 2, high: 3 }

export function ConfidenceDots({ level }: { level: Explained<unknown>["confidence"] }) {
  return (
    <span className="inline-flex items-center gap-0.5" title={`confidence: ${level} (advisory, not calibrated)`}>
      {[1, 2, 3].map((i) => (
        <i key={i} className={cn("inline-block size-1.5 rounded-full", i <= DOTS[level] ? "bg-foreground/80" : "bg-foreground/20")} />
      ))}
    </span>
  )
}

export function WhyDisclosure({ item, label = "Why?" }: { item: Explained<unknown>; label?: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="text-xs">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
      >
        {label} <ConfidenceDots level={item.confidence} />
        <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="mt-2 space-y-1.5 rounded-lg border border-border bg-white p-3 text-muted-foreground">
          <p className="text-foreground/90">{item.reasoning}</p>
          <p>
            <span className="text-foreground/60">Sources:</span> {item.sources.join(" · ")}
          </p>
          <p className="text-[11px] italic">Confidence is advisory, not a calibrated probability.</p>
        </div>
      )}
    </div>
  )
}
