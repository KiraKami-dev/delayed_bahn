import { Component, type ReactNode } from "react"
import { createRoot } from "react-dom/client"
import { Toaster } from "sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { WorkspaceProvider } from "@/lib/workspace"
import App from "./App"
import "./index.css"

class ErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    if (this.state.failed)
      return (
        <main className="connection-empty">
          <h1>The workspace needs a refresh.</h1>
          <p>
            Your saved repository files are untouched. Reload the page to
            reconnect.
          </p>
          <button onClick={() => location.reload()}>Reload workspace</button>
        </main>
      )
    return this.props.children
  }
}

createRoot(document.getElementById("root")!).render(
  <ErrorBoundary>
    <TooltipProvider delayDuration={200}>
      <WorkspaceProvider>
        <App />
        <Toaster position="bottom-right" richColors closeButton />
      </WorkspaceProvider>
    </TooltipProvider>
  </ErrorBoundary>,
)
