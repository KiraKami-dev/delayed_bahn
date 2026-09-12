import { useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import {
  ArrowRight,
  Braces,
  Check,
  Copy,
  FileText,
  LockKeyhole,
  Network,
  Pencil,
  Save,
  X,
} from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Textarea } from "@/components/ui/textarea"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { EmptyState, FormError, PageHeading } from "./shared"
import { docLabels } from "@/lib/format"
import { useWorkspace } from "@/lib/workspace"
import { cn } from "@/lib/utils"
import type { DocKey } from "@/lib/types"

const descriptions: Record<DocKey, string> = {
  challenge:
    "The problem, the people it affects, and the outcome you're working toward.",
  demo_script:
    "The story your demo tells, shot by shot. Keep it focused on the outcome.",
  not_building: "A clear boundary around what this version will not include.",
  contract: "The shared interfaces your team agrees to build against.",
  architecture:
    "The system diagram generated from your agreed technical contract.",
  partner_notes:
    "Useful details about tools, datasets, partner requirements, and constraints.",
}

export function DocumentsPage({ onConfigure }: { onConfigure: () => void }) {
  const { state, docs, mutate, saving } = useWorkspace()
  const [selected, setSelected] = useState<DocKey>("challenge")
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState("")
  const [mode, setMode] = useState("write")
  const [revision, setRevision] = useState<string>()
  const [error, setError] = useState("")
  const [pending, setPending] = useState<DocKey | "close" | null>(null)
  if (!state || !docs) return null
  const document = docs[selected]
  const dirty = editing && draft !== document.content
  function begin() {
    if (state!.event_is_blank) {
      onConfigure()
      return
    }
    setDraft(document.content)
    setRevision(state!.revision)
    setEditing(true)
    setMode("write")
    setError("")
  }
  function choose(key: DocKey | "close") {
    if (dirty) {
      setPending(key)
      return
    }
    setEditing(false)
    setError("")
    if (key !== "close") setSelected(key)
  }
  async function save() {
    try {
      await mutate("/api/docs", { key: selected, content: draft }, { revision })
      setEditing(false)
      setError("")
    } catch (e) {
      setError((e as Error).message)
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="The team's shared memory"
        title="Documents"
        description="The brief, the boundaries, and the plan. Written once, understood together."
      />
      <div className="documents-layout">
        <aside className="document-index">
          <div className="document-index-label">Workspace documents</div>
          {(Object.keys(docLabels) as DocKey[]).map((key) => {
            const Icon =
              key === "architecture"
                ? Network
                : key === "contract"
                  ? Braces
                  : FileText
            return (
              <button
                key={key}
                className={cn(selected === key && "selected")}
                onClick={() => choose(key)}
              >
                <Icon size={16} />
                <span>{docLabels[key]}</span>
                {!docs[key].editable ? (
                  <LockKeyhole size={12} />
                ) : !docs[key].not_written_yet ? (
                  <Check size={13} />
                ) : (
                  <span className="document-empty-dot" />
                )}
              </button>
            )
          })}
          <p>
            Documents live in the same repository files your agents read. Frozen
            agreements stay protected.
          </p>
        </aside>
        <section className="document-canvas">
          <div className="document-toolbar">
            <span className="document-location">
              <FileText size={14} />
              {docLabels[selected]}
            </span>
            <div>
              {editing ? (
                <>
                  <Tabs value={mode} onValueChange={setMode}>
                    <TabsList>
                      <TabsTrigger value="write">Write</TabsTrigger>
                      <TabsTrigger value="preview">Preview</TabsTrigger>
                    </TabsList>
                  </Tabs>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => choose("close")}
                    disabled={saving}
                  >
                    Cancel
                  </Button>
                  <Button size="sm" onClick={save} disabled={saving}>
                    <Save size={14} />
                    {saving ? "Saving…" : "Save"}
                  </Button>
                </>
              ) : (
                <>
                  {!document.not_written_yet && (
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label="Copy document"
                      onClick={() =>
                        void navigator.clipboard
                          .writeText(document.content)
                          .then(() => toast.success("Document copied"))
                          .catch(() =>
                            toast.error("Clipboard access unavailable"),
                          )
                      }
                    >
                      <Copy size={14} />
                    </Button>
                  )}
                  {document.editable && (
                    <Button variant="outline" size="sm" onClick={begin}>
                      <Pencil size={14} />
                      {document.not_written_yet
                        ? "Start writing"
                        : "Edit document"}
                    </Button>
                  )}
                </>
              )}
            </div>
          </div>
          <div className="document-page">
            <div className="large-document-icon">
              {selected === "architecture" ? (
                <Network size={31} strokeWidth={1.4} />
              ) : (
                <FileText size={31} strokeWidth={1.4} />
              )}
            </div>
            <h2>{docLabels[selected]}</h2>
            <p className="document-description">{descriptions[selected]}</p>
            {!document.editable && (
              <div className="locked-note">
                <LockKeyhole size={14} />
                {document.locked_reason}
              </div>
            )}
            {editing ? (
              <>
                <FormError
                  message={error}
                  current={document.content}
                  onReview={
                    error.includes("changed")
                      ? () => {
                          setRevision(state.revision)
                          setError("")
                        }
                      : undefined
                  }
                />
                {mode === "write" ? (
                  <Textarea
                    autoFocus
                    className="document-editor"
                    aria-label="Document content"
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    placeholder="Start with a heading, then write what the team needs to know. Markdown is supported."
                  />
                ) : (
                  <Markdown
                    content={draft || "_Your preview will appear here._"}
                  />
                )}
                <p className="editor-hint">
                  Markdown supported · Your draft is not shared until you save.
                </p>
              </>
            ) : document.not_written_yet ? (
              <EmptyState
                compact
                icon={FileText}
                title="A blank page, a clear starting point"
                description={
                  document.editable
                    ? "Add the information your team needs. No sample project is filled in for you."
                    : "Ask the owning agent to generate this from the real contract."
                }
                action={
                  document.editable ? (
                    <Button variant="outline" onClick={begin}>
                      <Pencil size={14} />
                      Start writing
                    </Button>
                  ) : undefined
                }
              />
            ) : selected === "architecture" ? (
              <Architecture content={document.content} />
            ) : (
              <Markdown content={document.content} />
            )}
          </div>
        </section>
      </div>
      <Dialog
        open={pending !== null}
        onOpenChange={(open) => {
          if (!open) setPending(null)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Leave this draft?</DialogTitle>
            <DialogDescription>
              Your changes have not been saved. The existing document will stay
              unchanged.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPending(null)}>
              Keep editing
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                setEditing(false)
                setError("")
                if (pending && pending !== "close") setSelected(pending)
                setPending(null)
              }}
            >
              Discard draft
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

export function Markdown({ content }: { content: string }) {
  return (
    <div className="document-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          a: ({ children, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
          img: ({ alt }) => (
            <span className="muted">[Image: {alt || "embedded image"}]</span>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

function Architecture({ content }: { content: string }) {
  const edges = content.split("\n").flatMap((line) => {
    const match = line.match(
      /^\s*([\w]+)(?:\[([^\]]+)\])?\s*-->(?:\|([^|]+)\|)?\s*([\w]+)(?:\[([^\]]+)\])?/,
    )
    return match
      ? [
          {
            from: match[2] || match[1],
            to: match[5] || match[4],
            label: match[3] || "",
          },
        ]
      : []
  })
  return (
    <>
      {edges.length > 0 && (
        <div className="architecture-diagram">
          {edges.map((edge, index) => (
            <div className="architecture-edge" key={index}>
              <span>
                <Braces size={16} />
                {edge.from}
              </span>
              <div>
                <small>{edge.label}</small>
                <ArrowRight size={20} />
              </div>
              <span>
                <Braces size={16} />
                {edge.to}
              </span>
            </div>
          ))}
        </div>
      )}
      <details className="diagram-source" open={!edges.length}>
        <summary>
          Mermaid source
          {edges.length
            ? " · supported connections shown above"
            : " · complex diagrams can be rendered by your agent"}
        </summary>
        <pre>{content}</pre>
      </details>
    </>
  )
}
