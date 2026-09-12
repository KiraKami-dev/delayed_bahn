import { lazy, Suspense, useEffect, useState } from "react"
import {
  ArrowRight,
  BookOpen,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  CloudOff,
  FileText,
  FlaskConical,
  FolderKanban,
  LayoutDashboard,
  Lightbulb,
  Loader2,
  Menu,
  MessageSquareText,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  Sparkles,
  X,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { Overview } from "@/components/overview"
import { TaskBoard, TaskEditor } from "@/components/task-board"
import {
  DecisionsPage,
  EntryDialog,
  IdeasPage,
  ResearchPage,
  type EntryRequest,
} from "@/components/knowledge"
import { EventEditor, SettingsPage } from "@/components/settings"
import { Avatar } from "@/components/shared"
import { useWorkspace } from "@/lib/workspace"
import { docLabels } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { Page, Task, TaskStatus } from "@/lib/types"

const DocumentsPage = lazy(() =>
  import("@/components/documents").then((module) => ({
    default: module.DocumentsPage,
  })),
)

const MeetingNotesPage = lazy(() =>
  import("@/components/meeting-notes").then((module) => ({
    default: module.MeetingNotesPage,
  })),
)

const GuidePage = lazy(() =>
  import("@/components/guide").then((module) => ({
    default: module.GuidePage,
  })),
)

const navigation = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "tasks", label: "Task board", icon: FolderKanban },
  { id: "ideas", label: "Ideas", icon: Lightbulb },
  { id: "decisions", label: "Decisions", icon: CheckCheck },
  { id: "documents", label: "Documents", icon: FileText },
  { id: "research", label: "Research", icon: FlaskConical },
  { id: "notes", label: "Meeting notes", icon: MessageSquareText },
  { id: "settings", label: "Team & settings", icon: Settings2 },
  { id: "guide", label: "How to use", icon: BookOpen },
] as const

function currentPage(): Page {
  const hash = location.hash.slice(1)
  return navigation.some((item) => item.id === hash)
    ? (hash as Page)
    : "overview"
}

export default function App() {
  const { state, docs, loading, offline, saving, refresh } = useWorkspace()
  const [page, setPage] = useState<Page>(currentPage)
  const [sidebar, setSidebar] = useState(false)
  const [mobile, setMobile] = useState(
    () => window.matchMedia("(max-width: 960px)").matches,
  )
  const [searchOpen, setSearchOpen] = useState(false)
  const [search, setSearch] = useState("")
  const [eventEditor, setEventEditor] = useState(false)
  const [taskEditor, setTaskEditor] = useState<{
    task?: Task
    status?: TaskStatus
  } | null>(null)
  const [entry, setEntry] = useState<EntryRequest | null>(null)
  useEffect(() => {
    const media = window.matchMedia("(max-width: 960px)")
    const onResize = () => {
      setMobile(media.matches)
      if (!media.matches) setSidebar(false)
    }
    media.addEventListener("change", onResize)
    const onHash = () => {
      setPage(currentPage())
      setSidebar(false)
      window.scrollTo({ top: 0, behavior: "instant" })
    }
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault()
        setSidebar(false)
        setSearchOpen((v) => !v)
      }
    }
    window.addEventListener("hashchange", onHash)
    window.addEventListener("keydown", onKey)
    return () => {
      media.removeEventListener("change", onResize)
      window.removeEventListener("hashchange", onHash)
      window.removeEventListener("keydown", onKey)
    }
  }, [])
  useEffect(() => {
    document.title = `${state?.event.event_name || "hack-os"} · ${navigation.find((n) => n.id === page)?.label}`
  }, [state?.event.event_name, page])
  function navigate(next: Page) {
    location.hash = next
    setPage(next)
    setSidebar(false)
  }
  function newTask(status?: TaskStatus) {
    if (state?.event_is_blank) setEventEditor(true)
    else setTaskEditor({ status })
  }
  function newEntry(request: EntryRequest) {
    if (state?.event_is_blank) setEventEditor(true)
    else setEntry(request)
  }
  const results = state
    ? [
        {
          id: "guide",
          title: "How to use hack-os",
          subtitle: "Step-by-step guide",
          icon: BookOpen,
          action: () => navigate("guide"),
        },
        ...state.tasks.map((task) => ({
          id: task.id,
          title: task.title,
          subtitle: "Task",
          icon: FolderKanban,
          action: () => setTaskEditor({ task }),
        })),
        ...state.ideas.map((idea) => ({
          id: idea.id,
          title: idea.idea,
          subtitle: "Idea",
          icon: Lightbulb,
          action: () => navigate("ideas"),
        })),
        ...state.decisions
          .filter((d) => !d.superseded_by)
          .map((d) => ({
            id: d.id,
            title: d.decision,
            subtitle: "Decision",
            icon: CheckCheck,
            action: () => navigate("decisions"),
          })),
        ...Object.entries(docLabels).map(([id, title]) => ({
          id,
          title,
          subtitle: "Document",
          icon: FileText,
          action: () => navigate("documents"),
        })),
      ]
        .filter(
          (item) =>
            !search || item.title.toLowerCase().includes(search.toLowerCase()),
        )
        .slice(0, 12)
    : []
  const sidebarContent = (
    <>
      <div className="brand">
        <span className="brand-icon">
          <span />
          <span />
          <span />
        </span>
        <span>
          hack<span className="brand-dash">—</span>os
        </span>
        <SheetClose asChild>
          <button className="mobile-close" aria-label="Close navigation">
            <X size={19} />
          </button>
        </SheetClose>
      </div>
      <button
        className="workspace-switcher"
        onClick={() => {
          setSidebar(false)
          setEventEditor(true)
        }}
        disabled={!state}
      >
        <span className="workspace-letter">
          {(state?.team.team_name || "W").slice(0, 1).toUpperCase()}
        </span>
        <span>
          <strong>{state?.team.team_name || "Team workspace"}</strong>
          <small>{state?.event.event_name || "Your next project"}</small>
        </span>
        <ChevronDown size={14} />
      </button>
      <button
        className="sidebar-search"
        onClick={() => {
          setSidebar(false)
          setSearchOpen(true)
        }}
      >
        <Search size={15} />
        <span>Find anything</span>
        <kbd>⌘ K</kbd>
      </button>
      <div className="nav-caption">WORKSPACE</div>
      <nav aria-label="Main navigation">
        {navigation.slice(0, 4).map((item) => (
          <button
            key={item.id}
            className={cn("nav-item", page === item.id && "nav-active")}
            onClick={() => navigate(item.id)}
            aria-current={page === item.id ? "page" : undefined}
          >
            <item.icon size={18} strokeWidth={1.7} />
            <span>{item.label}</span>
            {item.id === "tasks" && Boolean(state?.tasks.length) && (
              <span className="nav-count">
                {state?.tasks.filter((t) => t.status !== "demo-ready").length}
              </span>
            )}
            {item.id === "ideas" &&
              Boolean(
                state?.ideas.filter((i) => i.status === "raised").length,
              ) && (
                <span className="nav-count">
                  {state?.ideas.filter((i) => i.status === "raised").length}
                </span>
              )}
          </button>
        ))}
        <div className="nav-caption nav-caption-second">KNOWLEDGE</div>
        {navigation.slice(4, 7).map((item) => (
          <button
            key={item.id}
            className={cn("nav-item", page === item.id && "nav-active")}
            onClick={() => navigate(item.id)}
            aria-current={page === item.id ? "page" : undefined}
          >
            <item.icon size={18} strokeWidth={1.7} />
            <span>{item.label}</span>
            {item.id === "notes" && (
              <span className="nav-spark">
                <Sparkles size={12} />
              </span>
            )}
          </button>
        ))}
      </nav>
      <button className="sidebar-note" onClick={() => navigate("notes")}>
        <span className="note-mini-icon">
          <MessageSquareText size={17} />
        </span>
        <strong>Don't lose the good bits.</strong>
        <p>Turn a conversation into clear next steps.</p>
        <span>
          Capture meeting notes
          <ArrowRight size={13} />
        </span>
      </button>
      <div className="sidebar-bottom">
        <button
          className={cn("nav-item", page === "settings" && "nav-active")}
          onClick={() => navigate("settings")}
        >
          <Settings2 size={17} />
          <span>Team & settings</span>
        </button>
        <button
          className={cn("nav-item", page === "guide" && "nav-active")}
          onClick={() => navigate("guide")}
          aria-current={page === "guide" ? "page" : undefined}
        >
          <BookOpen size={17} />
          <span>How to use</span>
          <ArrowRight size={13} />
        </button>
        <div className="sidebar-team">
          <div className="avatar-stack">
            {state?.team.members.slice(0, 4).map((member) => (
              <Avatar name={member.name} small key={member.name} />
            ))}
          </div>
          <span>
            {state?.team.members.length || "Your"} teammates
            <br />
            <small>One shared direction</small>
          </span>
        </div>
      </div>
    </>
  )
  const title = navigation.find((item) => item.id === page)?.label
  return (
    <Sheet open={sidebar && mobile} onOpenChange={setSidebar}>
      <div className="workspace-app">
        <a
          className="skip-link"
          href="#workspace-main"
          onClick={(event) => {
            event.preventDefault()
            document.getElementById("workspace-main")?.focus()
          }}
        >
          Skip to workspace
        </a>
        <aside className="workspace-sidebar">{sidebarContent}</aside>
        <SheetContent
          side="left"
          className="mobile-sidebar"
          showCloseButton={false}
        >
          <SheetTitle className="sr-only">Workspace navigation</SheetTitle>
          <SheetDescription className="sr-only">
            Switch pages, search your workspace, or open the step-by-step guide.
          </SheetDescription>
          {sidebarContent}
        </SheetContent>
        <div className="workspace-shell">
          <header className="workspace-topbar">
            <div className="breadcrumbs">
              <SheetTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="mobile-menu"
                  aria-label="Open navigation"
                >
                  <Menu size={19} />
                </Button>
              </SheetTrigger>
              <span className="breadcrumb-workspace">Workspace</span>
              <ChevronRight size={13} />
              <strong>{title}</strong>
            </div>
            <div className="topbar-actions">
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    className={cn(
                      "connection-pill",
                      offline && "connection-offline",
                    )}
                    onClick={() => navigate("settings")}
                  >
                    {offline ? (
                      <CloudOff size={13} />
                    ) : saving ? (
                      <Loader2 className="animate-spin" size={13} />
                    ) : (
                      <span />
                    )}
                    {offline
                      ? "Disconnected"
                      : saving
                        ? "Saving"
                        : "Local workspace"}
                  </button>
                </TooltipTrigger>
                <TooltipContent>
                  Connected to local files. Sharing with other machines still
                  uses Git.
                </TooltipContent>
              </Tooltip>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="Refresh workspace"
                onClick={() => void refresh()}
              >
                <RefreshCw size={15} />
              </Button>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    className="quick-create"
                    size="sm"
                    disabled={!state || offline}
                  >
                    <Plus size={15} />
                    New
                    <ChevronDown size={13} />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-52">
                  <DropdownMenuLabel>Add to your workspace</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onSelect={() => newTask()}>
                    <FolderKanban />
                    Task
                  </DropdownMenuItem>
                  <DropdownMenuItem onSelect={() => newEntry({ kind: "idea" })}>
                    <Lightbulb />
                    Idea
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onSelect={() => newEntry({ kind: "decision" })}
                  >
                    <CheckCheck />
                    Decision
                  </DropdownMenuItem>
                  <DropdownMenuItem onSelect={() => navigate("notes")}>
                    <MessageSquareText />
                    Meeting notes
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onSelect={() => newEntry({ kind: "research" })}
                  >
                    <FlaskConical />
                    Research finding
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </header>
          <main id="workspace-main" className="workspace-main" tabIndex={-1}>
            {offline && state && (
              <div className="offline-banner" role="alert">
                <CloudOff size={17} />
                <span>
                  This is your last loaded view. Reconnect before saving or
                  relying on its freshness.
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => void refresh()}
                >
                  Retry
                </Button>
              </div>
            )}
            {page === "guide" ? (
              <Suspense
                fallback={
                  <div className="workspace-card" role="status">
                    Opening the guide…
                  </div>
                }
              >
                <GuidePage
                  navigate={navigate}
                  onConfigure={() => setEventEditor(true)}
                />
              </Suspense>
            ) : loading ? (
              <div className="workspace-loading" aria-label="Loading workspace">
                <div />
                <div className="skeleton-metrics">
                  <span />
                  <span />
                  <span />
                  <span />
                </div>
                <section />
                <section />
              </div>
            ) : !state || !docs ? (
              <div className="connection-empty">
                <span className="dialog-icon">
                  <CloudOff size={25} />
                </span>
                <h1>Let's connect your workspace.</h1>
                <p>
                  The local API isn't responding yet, or a state file needs
                  attention. Your repository files have not been changed.
                </p>
                <code>npm --prefix team-setup/board/web run dev</code>
                <Button onClick={() => void refresh()}>
                  <RefreshCw size={15} />
                  Try again
                </Button>
                <Button variant="outline" onClick={() => navigate("guide")}>
                  <BookOpen size={15} />
                  Open setup guide
                </Button>
              </div>
            ) : (
              <>
                {state.event_is_blank &&
                  page !== "overview" &&
                  page !== "settings" && (
                    <div className="setup-reminder">
                      <Sparkles size={17} />
                      <span>
                        A blank canvas. Name your workspace to start saving your
                        team's work.
                      </span>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setEventEditor(true)}
                      >
                        Set up workspace
                      </Button>
                    </div>
                  )}
                {page === "overview" && (
                  <Overview
                    navigate={navigate}
                    onNewTask={() => newTask()}
                    onEditTask={(task) => setTaskEditor({ task })}
                    onConfigure={() => setEventEditor(true)}
                  />
                )}
                {page === "tasks" && (
                  <TaskBoard
                    onNew={newTask}
                    onEdit={(task) => setTaskEditor({ task })}
                  />
                )}
                {page === "ideas" && <IdeasPage onCreate={newEntry} />}
                {page === "decisions" && <DecisionsPage onCreate={newEntry} />}
                {page === "documents" && (
                  <Suspense
                    fallback={
                      <div className="document-canvas p-8" role="status">
                        Opening documents…
                      </div>
                    }
                  >
                    <DocumentsPage onConfigure={() => setEventEditor(true)} />
                  </Suspense>
                )}
                {page === "research" && <ResearchPage onCreate={newEntry} />}
                {page === "notes" && (
                  <Suspense
                    fallback={
                      <div className="workspace-card p-8" role="status">
                        Opening meeting notes…
                      </div>
                    }
                  >
                    <MeetingNotesPage
                      navigate={navigate}
                      onConfigure={() => setEventEditor(true)}
                    />
                  </Suspense>
                )}
                {page === "settings" && (
                  <SettingsPage onConfigure={() => setEventEditor(true)} />
                )}
              </>
            )}
          </main>
          <footer className="workspace-footer">
            <span>Made for the work that matters.</span>
            <span>
              {state?.freshness.local_changes.length
                ? `${state.freshness.local_changes.length} local coordination changes · not yet shared`
                : "Your repository is the source of truth"}
            </span>
          </footer>
        </div>
        {eventEditor && state && (
          <EventEditor onClose={() => setEventEditor(false)} />
        )}
        {taskEditor && state && (
          <TaskEditor
            task={taskEditor.task}
            initialStatus={taskEditor.status}
            onClose={() => setTaskEditor(null)}
          />
        )}
        {entry && state && (
          <EntryDialog request={entry} onClose={() => setEntry(null)} />
        )}
        <Dialog open={searchOpen} onOpenChange={setSearchOpen}>
          <DialogContent className="search-dialog sm:max-w-[600px]">
            <DialogHeader>
              <DialogTitle>Find anything</DialogTitle>
              <DialogDescription>
                Search tasks, ideas, current decisions and document titles.
              </DialogDescription>
            </DialogHeader>
            <div className="global-search-input">
              <Search size={19} />
              <Input
                autoFocus
                aria-label="Search workspace"
                placeholder="What are you looking for?"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <div className="global-search-results">
              {results.map((result) => (
                <button
                  key={result.id}
                  onClick={() => {
                    result.action()
                    setSearchOpen(false)
                    setSearch("")
                  }}
                >
                  <result.icon size={17} />
                  <span>
                    <strong>{result.title}</strong>
                    <small>{result.subtitle}</small>
                  </span>
                  <ArrowRight size={14} />
                </button>
              ))}
              {!results.length && (
                <p>No matching items. Try a different word.</p>
              )}
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </Sheet>
  )
}
