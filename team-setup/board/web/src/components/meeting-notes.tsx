import { useRef, useState } from "react"
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCheck,
  FileText,
  Lightbulb,
  Loader2,
  MessageSquareText,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  Upload,
} from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Checkbox } from "@/components/ui/checkbox"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { EmptyState, FormError, PageHeading } from "./shared"
import { formatDate } from "@/lib/format"
import { readAPI, useWorkspace } from "@/lib/workspace"
import type { Extraction, Meeting, NotesPreview, Page } from "@/lib/types"

export function MeetingNotesPage({
  navigate,
  onConfigure,
}: {
  navigate: (page: Page) => void
  onConfigure: () => void
}) {
  const { state, mutate, saving } = useWorkspace()
  const [tab, setTab] = useState("capture")
  const [text, setText] = useState("")
  const [query, setQuery] = useState("")
  const [error, setError] = useState("")
  const [preview, setPreview] = useState<NotesPreview | null>(null)
  const [selection, setSelection] = useState({
    decisions: [] as number[],
    ideas: [] as number[],
    tasks: [] as number[],
  })
  const [applied, setApplied] = useState<{
    decisions_written: number
    tasks_written: number
    ideas_written: number
  } | null>(null)
  const [viewing, setViewing] = useState<(Meeting & { text: string }) | null>(
    null,
  )
  const fileInput = useRef<HTMLInputElement>(null)
  if (!state) return null
  async function capture(structure: boolean) {
    if (!state) return
    if (state.event_is_blank) {
      onConfigure()
      return
    }
    setError("")
    try {
      const result = await mutate<NotesPreview>(
        "/api/notes",
        { text, structure },
        { quiet: true },
      )
      if (result.preview_id) {
        setPreview(result)
        setSelection({
          decisions: result.decisions.map((_, i) => i),
          ideas: result.ideas.map((_, i) => i),
          tasks: result.tasks.map((_, i) => i),
        })
      } else
        toast.message(result.warning || "Raw notes saved", {
          description:
            "Your original transcript is safely stored in the repository.",
        })
    } catch (e) {
      setError((e as Error).message)
    }
  }
  async function apply() {
    if (!preview) return
    try {
      const result = await mutate<{
        decisions_written: number
        tasks_written: number
        ideas_written: number
      }>(
        "/api/notes/confirm",
        { preview_id: preview.preview_id, selection },
        { revision: preview.revision, quiet: true },
      )
      setApplied(result)
      setPreview(null)
      setText("")
      setError("")
      toast.success("Your meeting is now actionable")
    } catch (e) {
      setError((e as Error).message)
    }
  }
  async function upload(file?: File) {
    if (!file) return
    if (!/\.(txt|md|srt|vtt)$/i.test(file.name) || file.size > 750000) {
      toast.error(
        "Choose a text transcript under 750 KB (.txt, .md, .srt or .vtt).",
      )
      return
    }
    if (text.trim()) {
      toast.error(
        "Save or clear the current draft before importing another transcript.",
      )
      return
    }
    setText(await file.text())
    setApplied(null)
    toast.success("Transcript loaded", {
      description: "Review it below before saving or requesting an AI preview.",
    })
  }
  async function openMeeting(meeting: Meeting) {
    try {
      setViewing(
        await readAPI<Meeting & { text: string }>(
          `/api/meetings/${encodeURIComponent(meeting.id)}`,
        ),
      )
    } catch (e) {
      toast.error((e as Error).message)
    }
  }
  const selectedCount = Object.values(selection).reduce(
    (sum, indexes) => sum + indexes.length,
    0,
  )
  const meetings = state.meetings.filter((m) =>
    `${m.title} ${m.excerpt}`.toLowerCase().includes(query.toLowerCase()),
  )
  return (
    <>
      <PageHeading
        eyebrow="Turn conversations into clarity"
        title="Meeting notes"
        description="Bring the transcript. Keep the context. Decide what becomes team action."
      />
      <div className="board-toolbar">
        <Tabs
          value={tab}
          onValueChange={(v) => {
            setTab(v)
            setError("")
          }}
        >
          <TabsList>
            <TabsTrigger value="capture">
              <MessageSquareText size={14} />
              Capture notes
            </TabsTrigger>
            <TabsTrigger value="library">
              <FileText size={14} />
              Saved notes
              <Badge variant="secondary">{state.meetings.length}</Badge>
            </TabsTrigger>
          </TabsList>
        </Tabs>
        {tab === "library" && (
          <div className="search-field">
            <Search size={15} />
            <Input
              aria-label="Search saved notes"
              placeholder="Find a conversation…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
        )}
      </div>
      {tab === "library" ? (
        <div className="meeting-library">
          {meetings.length ? (
            meetings.map((meeting) => (
              <button
                className="saved-meeting"
                key={meeting.id}
                onClick={() => void openMeeting(meeting)}
              >
                <span className="document-icon lavender">
                  <FileText size={22} />
                </span>
                <div>
                  <h2>{meeting.title}</h2>
                  <p>{meeting.excerpt}</p>
                  <small>
                    {formatDate(meeting.created_at, true)} · Original transcript
                  </small>
                </div>
                <ArrowRight size={17} />
              </button>
            ))
          ) : (
            <div className="workspace-card">
              <EmptyState
                icon={MessageSquareText}
                title="Your team's conversations, kept together"
                description="Saved transcripts will appear here. Original wording is preserved, even when AI is unavailable."
                action={
                  <Button variant="outline" onClick={() => setTab("capture")}>
                    <Plus />
                    Capture notes
                  </Button>
                }
              />
            </div>
          )}
        </div>
      ) : applied ? (
        <div className="workspace-card notes-success">
          <span className="success-symbol">
            <Check size={28} />
          </span>
          <h2>From discussion to direction.</h2>
          <p>
            Your selected updates are saved to the same files your team and
            agents use.
          </p>
          <div className="applied-counts">
            <button onClick={() => navigate("decisions")}>
              <CheckCheck />
              <strong>{applied.decisions_written}</strong>
              <span>decisions</span>
            </button>
            <button onClick={() => navigate("tasks")}>
              <CheckCheck />
              <strong>{applied.tasks_written}</strong>
              <span>tasks</span>
            </button>
            <button onClick={() => navigate("ideas")}>
              <Lightbulb />
              <strong>{applied.ideas_written}</strong>
              <span>ideas</span>
            </button>
          </div>
          <p className="field-hint">
            Saved locally. Publish accepted changes through Git to share them
            with other machines.
          </p>
          <Button variant="outline" onClick={() => setApplied(null)}>
            <Plus />
            Capture another meeting
          </Button>
        </div>
      ) : preview ? (
        <div className="notes-review">
          <div className="review-heading">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setPreview(null)
                setError("")
              }}
            >
              <ArrowLeft size={15} />
              Back to transcript
            </Button>
            <span>
              <ShieldCheck size={14} />
              Original notes already saved
            </span>
          </div>
          <div className="review-intro">
            <span className="dialog-icon">
              <Sparkles size={21} />
            </span>
            <h2>A first draft of your next steps.</h2>
            <p>
              Review the suggestions below. Uncheck anything that wasn't agreed
              or doesn't belong. Only selected items will be written.
            </p>
          </div>
          <FormError message={error} />
          {(["decisions", "tasks", "ideas"] as const).map((bucket) => (
            <section className="review-section workspace-card" key={bucket}>
              <div className="section-heading">
                <h2>
                  {bucket === "decisions"
                    ? "Decisions made"
                    : bucket === "tasks"
                      ? "Action items"
                      : "Ideas to explore"}
                  <Badge variant="secondary">{preview[bucket].length}</Badge>
                </h2>
              </div>
              {preview[bucket].length ? (
                preview[bucket].map((item, index) => (
                  <label className="review-item" key={index}>
                    <Checkbox
                      checked={selection[bucket].includes(index)}
                      onCheckedChange={(checked) =>
                        setSelection((s) => ({
                          ...s,
                          [bucket]: checked
                            ? [...s[bucket], index]
                            : s[bucket].filter((i) => i !== index),
                        }))
                      }
                    />
                    <div>
                      <strong>
                        {"title" in item ? item.title : item.text}
                      </strong>
                      <span>
                        {"title" in item
                          ? item.owner || "Unassigned owner"
                          : item.who || "Author not specified"}
                        {"target_time" in item && item.target_time
                          ? ` · ${item.target_time}`
                          : ""}
                      </span>
                    </div>
                    <Badge variant="outline">Suggested</Badge>
                  </label>
                ))
              ) : (
                <p className="field-hint">
                  No {bucket} extracted from this transcript.
                </p>
              )}
            </section>
          ))}
          {preview.flagged.length > 0 && (
            <section className="flagged-notes">
              <h3>Needs your team's judgment</h3>
              <ul>
                {preview.flagged.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
              <p>These points are not automatically written as decisions.</p>
            </section>
          )}
          <div className="review-footer">
            <span>
              {selectedCount} {selectedCount === 1 ? "update" : "updates"}{" "}
              selected
            </span>
            <Button onClick={apply} disabled={saving || !selectedCount}>
              {saving ? <Loader2 className="animate-spin" /> : <CheckCheck />}
              Apply selected updates
            </Button>
          </div>
        </div>
      ) : (
        <div className="notes-layout">
          <section className="workspace-card notes-composer">
            <div className="notes-composer-heading">
              <span>
                <MessageSquareText size={18} />
                The conversation
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => fileInput.current?.click()}
              >
                <Upload size={14} />
                Import transcript
              </Button>
              <input
                ref={fileInput}
                hidden
                type="file"
                accept=".txt,.md,.srt,.vtt"
                onChange={(e) => {
                  void upload(e.target.files?.[0])
                  e.target.value = ""
                }}
              />
            </div>
            <Textarea
              className="transcript-input"
              aria-label="Meeting transcript"
              placeholder={
                "Paste your meeting notes or transcript here.\n\nWhat did you discuss? What did the team agree on? Who is taking the next step?\n\nRough notes are welcome. The original text stays intact."
              }
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            <div className="transcript-meta">
              <span>
                {text.trim() ? text.trim().split(/\s+/).length : 0} words
              </span>
              <span>Text transcripts · .txt, .md, .srt, .vtt</span>
            </div>
            <FormError message={error} />
            <div className="notes-actions">
              <Button
                variant="outline"
                disabled={!text.trim() || saving}
                onClick={() => void capture(false)}
              >
                {saving && <Loader2 className="animate-spin" size={14} />}Save
                notes only
              </Button>
              <Button
                disabled={!text.trim() || saving || !state.ai.configured}
                onClick={() => void capture(true)}
              >
                {saving ? (
                  <Loader2 className="animate-spin" size={15} />
                ) : (
                  <Sparkles size={15} />
                )}
                Generate AI preview
                <ArrowRight size={14} />
              </Button>
            </div>
            <p className="notes-privacy">
              <ShieldCheck size={13} />
              AI preview sends this text to OpenAI. Nothing becomes a decision
              or task until you confirm.
            </p>
          </section>
          <aside className="notes-guide">
            <div className="guide-illustration" aria-hidden="true">
              <div>
                <MessageSquareText size={30} />
              </div>
              <ArrowRight size={19} />
              <div>
                <CheckCheck size={29} />
              </div>
            </div>
            <h2>
              A meeting is just
              <br />
              the beginning.
            </h2>
            <p>
              Keep the valuable parts from getting lost between conversations.
            </p>
            <div className="notes-flow">
              <div>
                <span>1</span>
                <section>
                  <strong>Bring your notes</strong>
                  <p>
                    Paste text or import a transcript. No special format needed.
                  </p>
                </section>
              </div>
              <div>
                <span>2</span>
                <section>
                  <strong>Review, don't assume</strong>
                  <p>
                    AI separates decisions, follow-ups and ideas for your
                    review.
                  </p>
                </section>
              </div>
              <div>
                <span>3</span>
                <section>
                  <strong>Make it shared context</strong>
                  <p>Apply approved items to the board and shared records.</p>
                </section>
              </div>
            </div>
            {!state.ai.configured && (
              <div className="key-callout">
                <Sparkles size={19} />
                <h3>Ready when your key is.</h3>
                <p>
                  Notes already save without AI. Add your own OpenAI key to
                  unlock structured previews.
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => navigate("settings")}
                >
                  Open settings
                  <ArrowRight size={13} />
                </Button>
              </div>
            )}
          </aside>
        </div>
      )}
      <Dialog
        open={Boolean(viewing)}
        onOpenChange={(open) => {
          if (!open) setViewing(null)
        }}
      >
        <DialogContent className="sm:max-w-[720px]">
          <DialogHeader>
            <DialogTitle>{viewing?.title}</DialogTitle>
            <DialogDescription>
              Original transcript · {formatDate(viewing?.created_at, true)}
            </DialogDescription>
          </DialogHeader>
          <pre className="saved-transcript">{viewing?.text}</pre>
          <Button
            variant="outline"
            onClick={() => {
              if (text.trim()) {
                toast.error(
                  "Save or clear your current draft before loading another transcript.",
                )
                return
              }
              setText(viewing?.text || "")
              setViewing(null)
              setPreview(null)
              setApplied(null)
              setTab("capture")
            }}
          >
            Use this transcript
            <ArrowRight size={14} />
          </Button>
        </DialogContent>
      </Dialog>
    </>
  )
}
