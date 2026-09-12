import { Component, type ReactNode } from "react"
import { createRoot } from "react-dom/client"
import { registerSW } from "virtual:pwa-register"
import { StoreProvider } from "@/lib/store"
import App from "./App"
import "./index.css"

class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    if (this.state.failed)
      return (
        <main className="flex h-full flex-col items-center justify-center gap-4 p-8 text-center">
          <h1 className="text-2xl font-semibold">Something broke on this screen.</h1>
          <p className="text-muted-foreground">Reload to start again. Nothing was saved.</p>
          <button className="rounded-md bg-primary px-4 py-2 text-white" onClick={() => location.reload()}>
            Reload
          </button>
        </main>
      )
    return this.props.children
  }
}

registerSW({ immediate: true })

createRoot(document.getElementById("root")!).render(
  <ErrorBoundary>
    <StoreProvider>
      <App />
    </StoreProvider>
  </ErrorBoundary>,
)
