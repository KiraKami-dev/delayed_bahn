import { AppShell } from "@/features/pwa-shell/components/AppShell"
import { useShareTarget } from "@/features/pwa-shell/hooks/useShareTarget"
import { useStageKeys } from "@/features/pwa-shell/hooks/useStageKeys"

export default function App() {
  useShareTarget()
  useStageKeys()
  return <AppShell />
}
