import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react"
import { toast } from "sonner"
import type { BoardState, Documents, MutationResult } from "./types"

interface Workspace {
  state: BoardState | null
  docs: Documents | null
  loading: boolean
  offline: boolean
  saving: boolean
  refresh: () => Promise<void>
  mutate: <T = MutationResult>(
    path: string,
    data: unknown,
    options?: { revision?: string; quiet?: boolean },
  ) => Promise<T>
}
const Context = createContext<Workspace | null>(null)

export async function readAPI<T>(path: string): Promise<T> {
  const response = await fetch(path, { signal: AbortSignal.timeout(12000) })
  const data = await response.json()
  if (!response.ok || data.ok === false)
    throw new Error(data.error || "The workspace could not be loaded")
  return data
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<BoardState | null>(null)
  const [docs, setDocs] = useState<Documents | null>(null)
  const [loading, setLoading] = useState(true)
  const [offline, setOffline] = useState(false)
  const [saving, setSaving] = useState(false)
  const current = useRef<BoardState | null>(null)
  const busy = useRef(false)
  const refreshing = useRef(false)
  const refresh = useCallback(async () => {
    if (refreshing.current) return
    refreshing.current = true
    try {
      const [next, documents] = await Promise.all([
        readAPI<BoardState>("/api/state"),
        readAPI<Documents>("/api/docs"),
      ])
      if (next.revision !== documents.revision) return
      current.current = next
      setState(next)
      setDocs(documents)
      setOffline(false)
    } catch {
      setOffline(true)
    } finally {
      setLoading(false)
      refreshing.current = false
    }
  }, [])

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => {
      if (!busy.current) void refresh()
    }, 6000)
    return () => clearInterval(timer)
  }, [refresh])

  const mutate = useCallback(
    async <T,>(
      path: string,
      data: unknown,
      options?: { revision?: string; quiet?: boolean },
    ): Promise<T> => {
      if (!current.current)
        throw new Error("Connect to the workspace before saving")
      if (busy.current)
        throw new Error(
          "Another update is saving. Your draft is safe; try again in a moment.",
        )
      busy.current = true
      setSaving(true)
      try {
        const response = await fetch(path, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Hackos-Token": current.current.csrf_token,
            "If-Match": options?.revision || current.current.revision,
          },
          body: JSON.stringify(data),
          signal: AbortSignal.timeout(45000),
        })
        const result = await response.json()
        if (!response.ok || !result.ok) {
          if (response.status === 409 || response.status === 403)
            await refresh()
          throw new Error(result.error || "This update could not be saved")
        }
        if (!options?.quiet) {
          if (result.warning) toast.message(result.warning)
          else
            toast.success("Saved to your workspace", {
              description:
                "Local files updated. Share accepted changes through Git.",
            })
        }
        await refresh()
        return result as T
      } catch (error) {
        const message =
          error instanceof Error
            ? error.message
            : "Save failed. Your input has been kept."
        if (!options?.quiet) toast.error(message)
        throw new Error(message)
      } finally {
        busy.current = false
        setSaving(false)
      }
    },
    [refresh],
  )

  return (
    <Context.Provider
      value={{ state, docs, loading, offline, saving, refresh, mutate }}
    >
      {children}
    </Context.Provider>
  )
}

export function useWorkspace() {
  const context = useContext(Context)
  if (!context) throw new Error("WorkspaceProvider is required")
  return context
}
