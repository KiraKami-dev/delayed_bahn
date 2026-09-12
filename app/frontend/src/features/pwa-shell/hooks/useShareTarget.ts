import { useEffect, useRef } from "react"
import { useStore, type Tab } from "@/lib/store"
import { replaceUrl, useRoute } from "./useRoute"

const TABS: Tab[] = ["plan", "forecast", "advice", "causes", "evidence"]

/**
 * Entry links:
 *  - Web Share Target: the manifest routes shares to GET /share?title=&text=&url=.
 *    Read the shared text, clean the URL, and run the pipeline once.
 *  - ?demo=1[&tab=forecast]: load the seed journey and open a tab (deep link for
 *    presenting and for screenshots).
 */
export function useShareTarget() {
  const route = useRoute()
  const s = useStore()
  const handled = useRef(false)
  useEffect(() => {
    if (handled.current) return
    const isShare = route.path === "/share" || route.params.has("text")
    const isDemo = route.params.get("demo") === "1"
    if (!isShare && !isDemo) return
    handled.current = true
    const tab = route.params.get("tab") as Tab | null
    const keep = new URLSearchParams()
    if (route.params.get("stage") === "1") keep.set("stage", "1")
    if (route.params.get("motion") === "0") keep.set("motion", "0")
    replaceUrl("/" + (keep.size ? `?${keep}` : ""))

    const run = async () => {
      if (isShare) {
        const text = [route.params.get("title"), route.params.get("text"), route.params.get("url")].filter(Boolean).join("\n").trim()
        if (!text) return
        s.dispatch({ type: "tab", tab: "plan" })
        await s.runFromText(text)
      } else {
        await s.runFromSeed()
      }
      if (tab && TABS.includes(tab)) s.dispatch({ type: "tab", tab })
    }
    void run()
  }, [route, s])
}
