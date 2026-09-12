import { Download, WifiOff } from "lucide-react"
import { useEffect, useState } from "react"
import { useStore } from "@/lib/store"

type BeforeInstallPromptEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> }

export function InstallButton({ big = false }: { big?: boolean }) {
  const [evt, setEvt] = useState<BeforeInstallPromptEvent | null>(null)
  const [installed, setInstalled] = useState(false)
  useEffect(() => {
    const onPrompt = (e: Event) => {
      e.preventDefault()
      setEvt(e as BeforeInstallPromptEvent)
    }
    const onInstalled = () => setInstalled(true)
    window.addEventListener("beforeinstallprompt", onPrompt)
    window.addEventListener("appinstalled", onInstalled)
    if (window.matchMedia("(display-mode: standalone)").matches) setInstalled(true)
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt)
      window.removeEventListener("appinstalled", onInstalled)
    }
  }, [])
  if (installed) return big ? <span className="text-sm text-muted-foreground">Installed — find error404 in your share sheet.</span> : null
  if (!evt) return big ? <span className="text-sm text-muted-foreground">Open in Chrome on Android and choose “Install app” to get error404 into the share sheet.</span> : null
  return (
    <button
      type="button"
      onClick={() => void evt.prompt()}
      className={
        big
          ? "inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 font-medium text-white"
          : "inline-flex items-center gap-1.5 rounded-full border border-border bg-black/40 px-3 py-1 text-xs text-foreground backdrop-blur"
      }
    >
      <Download className="size-4" /> Install app
    </button>
  )
}

export function OfflinePill() {
  const s = useStore()
  if (!s.offline) return null
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-400/40 bg-amber-400/10 px-3 py-1 text-xs text-amber-200">
      <WifiOff className="size-3.5" /> offline · seed data
    </span>
  )
}
