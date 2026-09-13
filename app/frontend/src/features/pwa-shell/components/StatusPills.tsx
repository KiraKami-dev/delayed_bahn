import { Download, WifiOff, X } from "lucide-react"
import { useEffect, useState } from "react"

type BeforeInstallPromptEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> }

// The install event is captured once, app-wide, so any button rendered later
// (header, help dialog) can still trigger the native prompt.
let captured: BeforeInstallPromptEvent | null = null
const listeners = new Set<() => void>()
if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault()
    captured = e as BeforeInstallPromptEvent
    listeners.forEach((l) => l())
  })
  window.addEventListener("appinstalled", () => {
    captured = null
    listeners.forEach((l) => l())
  })
}

function platformHint(): string {
  const ua = navigator.userAgent
  const ios = /iPhone|iPad|iPod/.test(ua)
  const android = /Android/.test(ua)
  if (ios) return "On iPhone: tap the Share button in Safari, then “Add to Home Screen”. iOS has no share-sheet target, so paste the DB text into the app instead."
  if (android) return "On Android Chrome: open the ⋮ menu and choose “Install app” (or “Add to Home screen”). After that, delayedBahn appears in the DB app’s Share list."
  return "On desktop Chrome or Edge: click the install icon at the right end of the address bar, or open the ⋮ menu → “Cast, save and share” → “Install page as app”."
}

export function InstallButton({ big = false, icon = false }: { big?: boolean; icon?: boolean }) {
  const [, force] = useState(0)
  const [hint, setHint] = useState(false)
  const [installed, setInstalled] = useState(() => window.matchMedia("(display-mode: standalone)").matches)
  useEffect(() => {
    const l = () => force((n) => n + 1)
    listeners.add(l)
    const onInstalled = () => setInstalled(true)
    window.addEventListener("appinstalled", onInstalled)
    return () => {
      listeners.delete(l)
      window.removeEventListener("appinstalled", onInstalled)
    }
  }, [])
  if (installed) return big ? <span className="text-sm text-muted-foreground">Installed — delayedBahn is in your share sheet.</span> : null

  const onClick = async () => {
    if (captured) {
      try {
        await captured.prompt()
        const choice = await captured.userChoice
        if (choice.outcome === "accepted") setInstalled(true)
        captured = null
        force((n) => n + 1)
        return
      } catch {
        /* fall through to the hint */
      }
    }
    setHint((h) => !h)
  }

  return (
    <span className="relative inline-flex">
      <button
        type="button"
        onClick={() => void onClick()}
        aria-label={icon ? "Install app" : undefined}
        title={icon ? "Install app" : undefined}
        className={
          icon
            ? "install-icon"
            : big
              ? "inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 font-medium text-white"
              : "install-btn inline-flex items-center gap-1.5 rounded-full border border-border bg-white px-3 py-1 text-xs text-foreground"
        }
      >
        <Download className="size-4" />{!icon && " Install app"}
      </button>
      {hint && (
        <span
          role="dialog"
          className="absolute right-0 top-full z-50 mt-2 w-72 rounded-xl border border-border bg-white p-3 text-left text-xs leading-relaxed text-foreground shadow-xl"
        >
          <button type="button" aria-label="Close" onClick={() => setHint(false)} className="absolute right-2 top-2 text-muted-foreground">
            <X className="size-3.5" />
          </button>
          {platformHint()}
        </span>
      )}
    </span>
  )
}

export function OfflinePill() {
  const [offline, setOffline] = useState(!navigator.onLine)
  useEffect(() => {
    const update = () => setOffline(!navigator.onLine)
    window.addEventListener("online", update)
    window.addEventListener("offline", update)
    return () => {
      window.removeEventListener("online", update)
      window.removeEventListener("offline", update)
    }
  }, [])
  if (!offline) return null
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-400/40 bg-amber-400/10 px-3 py-1 text-xs text-amber-800">
      <WifiOff className="size-3.5" /> You’re offline
    </span>
  )
}
