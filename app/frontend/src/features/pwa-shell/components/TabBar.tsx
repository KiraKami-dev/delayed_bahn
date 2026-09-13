import { Activity, ListChecks, Route } from "lucide-react"
import { useStore, type Tab } from "@/lib/store"

const TABS: { id: Tab; label: string; Icon: typeof Route }[] = [
  { id: "plan", label: "Your journey", Icon: Route },
  { id: "forecast", label: "Train details", Icon: Activity },
  { id: "advice", label: "Travel advice", Icon: ListChecks },
]

export function TabBar() {
  const s = useStore()
  return <nav className="tabbar" aria-label="Journey sections">{TABS.map(({ id, label, Icon }) => <button key={id} type="button" aria-current={s.tab === id ? "page" : undefined} onClick={() => s.dispatch({ type: "tab", tab: id })}><Icon size={16} />{label}</button>)}</nav>
}
