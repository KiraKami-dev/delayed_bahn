import { Activity, BookOpenCheck, CloudRain, ListChecks, Map as MapIcon } from "lucide-react"
import { useStore, type Tab } from "@/lib/store"
import { cn } from "@/lib/utils"

const TABS: { id: Tab; label: string; Icon: typeof MapIcon; needsJourney: boolean }[] = [
  { id: "plan", label: "Plan", Icon: MapIcon, needsJourney: false },
  { id: "forecast", label: "Forecast", Icon: Activity, needsJourney: true },
  { id: "advice", label: "Advice", Icon: ListChecks, needsJourney: true },
  { id: "causes", label: "Causes", Icon: CloudRain, needsJourney: true },
  { id: "evidence", label: "Evidence", Icon: BookOpenCheck, needsJourney: false },
]

export function TabBar() {
  const s = useStore()
  return (
    <nav className="tabbar flex gap-1 border-t border-border p-2" aria-label="Sections">
      {TABS.map(({ id, label, Icon, needsJourney }) => {
        const disabled = needsJourney && !s.journey
        return (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={s.tab === id}
            disabled={disabled}
            onClick={() => s.dispatch({ type: "tab", tab: id })}
            className={cn(
              "flex min-w-0 flex-1 flex-col items-center gap-1 rounded-lg px-0.5 py-1.5 text-[10px] font-medium text-muted-foreground transition-colors lg:px-2 lg:text-[11px]",
              "hover:bg-white/5 disabled:opacity-35",
            )}
          >
            <Icon className="size-4" />
            {label}
          </button>
        )
      })}
    </nav>
  )
}
