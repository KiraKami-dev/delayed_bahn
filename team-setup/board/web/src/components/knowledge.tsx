import { useState, type FormEvent } from "react"
import {
  ArrowRight,
  Check,
  CheckCheck,
  FlaskConical,
  Lightbulb,
  MoreHorizontal,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Avatar,
  EmptyState,
  Field,
  FormError,
  PageHeading,
  Pick,
  SaveButton,
} from "./shared"
import { useWorkspace } from "@/lib/workspace"
import { cn } from "@/lib/utils"
import type { Decision, Idea, IdeaStatus, Research } from "@/lib/types"

export type EntryKind = "idea" | "decision" | "research"
export interface EntryRequest {
  kind: EntryKind
  promote?: Idea
  supersedes?: Decision
}
const ideaLabels: Record<IdeaStatus, string> = {
  raised: "Raised",
  exploring: "Exploring",
  adopted: "Adopted",
  discarded: "Set aside",
}

export function IdeasPage({
  onCreate,
}: {
  onCreate: (request: EntryRequest) => void
}) {
  const { state, mutate } = useWorkspace()
  const [filter, setFilter] = useState("all")
  const [query, setQuery] = useState("")
  if (!state) return null
  const ideas = state.ideas.filter(
    (i) =>
      (filter === "all" || i.status === filter) &&
      `${i.idea} ${i.who}`.toLowerCase().includes(query.toLowerCase()),
  )
  async function change(idea: Idea, status: IdeaStatus) {
    try {
      await mutate("/api/ideas/status", { id: idea.id, status })
    } catch {
      return
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="Room to think"
        title="Ideas"
        description="Capture possibilities without turning every thought into a commitment."
      >
        <Button onClick={() => onCreate({ kind: "idea" })}>
          <Plus />
          Capture an idea
        </Button>
      </PageHeading>
      <div className="board-toolbar">
        <Tabs value={filter} onValueChange={setFilter}>
          <TabsList>
            <TabsTrigger value="all">All ideas</TabsTrigger>
            <TabsTrigger value="raised">Raised</TabsTrigger>
            <TabsTrigger value="exploring">Exploring</TabsTrigger>
            <TabsTrigger value="adopted">Adopted</TabsTrigger>
            <TabsTrigger value="discarded">Set aside</TabsTrigger>
          </TabsList>
        </Tabs>
        <div className="search-field">
          <Search size={15} />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Find an idea…"
            aria-label="Search ideas"
          />
        </div>
      </div>
      {ideas.length ? (
        <div className="idea-grid">
          {ideas
            .slice()
            .reverse()
            .map((idea) => (
              <article className="idea-card" key={idea.id}>
                <div className="idea-card-top">
                  <span className={cn("idea-status", `idea-${idea.status}`)}>
                    <Lightbulb size={13} />
                    {ideaLabels[idea.status]}
                  </span>
                  {idea.status !== "adopted" && (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          size="icon-sm"
                          variant="ghost"
                          aria-label={`Actions for ${idea.idea}`}
                        >
                          <MoreHorizontal size={16} />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        {(["raised", "exploring", "discarded"] as const)
                          .filter((s) => s !== idea.status)
                          .map((status) => (
                            <DropdownMenuItem
                              key={status}
                              onSelect={() => void change(idea, status)}
                            >
                              Move to {ideaLabels[status].toLowerCase()}
                            </DropdownMenuItem>
                          ))}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                </div>
                <h2>{idea.idea}</h2>
                <div className="idea-owner">
                  <Avatar name={idea.who} small />
                  <span>{idea.who}</span>
                  <span>{idea.timestamp}</span>
                </div>
                {idea.status !== "adopted" && idea.status !== "discarded" && (
                  <Button
                    variant="ghost"
                    className="idea-promote"
                    onClick={() =>
                      onCreate({ kind: "decision", promote: idea })
                    }
                  >
                    Turn into a decision
                    <ArrowRight size={14} />
                  </Button>
                )}
                {idea.status === "adopted" && (
                  <p className="adopted-note">
                    <Check size={13} />
                    Linked to an accepted decision
                  </p>
                )}
              </article>
            ))}
        </div>
      ) : (
        <div className="workspace-card">
          <EmptyState
            icon={Lightbulb}
            title={
              query || filter !== "all"
                ? "No ideas match this view"
                : "Make space for the next good idea"
            }
            description="Raise it here, explore it together, and only turn it into a decision when the team agrees."
            action={
              <Button
                variant="outline"
                onClick={() => onCreate({ kind: "idea" })}
              >
                <Plus />
                Add an idea
              </Button>
            }
          />
        </div>
      )}
    </>
  )
}

export function DecisionsPage({
  onCreate,
}: {
  onCreate: (request: EntryRequest) => void
}) {
  const { state } = useWorkspace()
  const [history, setHistory] = useState(false)
  const [query, setQuery] = useState("")
  if (!state) return null
  const decisions = state.decisions.filter(
    (d) =>
      (history || !d.superseded_by) &&
      `${d.decision} ${d.reason}`.toLowerCase().includes(query.toLowerCase()),
  )
  return (
    <>
      <PageHeading
        eyebrow="A shared understanding"
        title="Decisions"
        description="What the team agreed, why it matters, and what changed."
      >
        <Button onClick={() => onCreate({ kind: "decision" })}>
          <Plus />
          Record a decision
        </Button>
      </PageHeading>
      <div className="board-toolbar">
        <label className="inline-checkbox">
          <Checkbox
            checked={history}
            onCheckedChange={(v) => setHistory(Boolean(v))}
          />
          Include replaced decisions
        </label>
        <div className="search-field">
          <Search size={15} />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search decisions…"
            aria-label="Search decisions"
          />
        </div>
      </div>
      {decisions.length ? (
        <div className="decision-timeline">
          {decisions
            .slice()
            .reverse()
            .map((decision) => (
              <article
                className={cn(
                  "decision-card",
                  decision.superseded_by && "decision-replaced",
                )}
                key={decision.id}
              >
                <span className="decision-marker">
                  <CheckCheck size={16} />
                </span>
                <div className="decision-topline">
                  <Badge variant="secondary">
                    {decision.superseded_by ? "Replaced" : "Current decision"}
                  </Badge>
                  <span>{decision.timestamp}</span>
                </div>
                <h2>{decision.decision}</h2>
                <p className="decision-reason">{decision.reason}</p>
                <div className="decision-bottom">
                  <span className="inline-person">
                    <Avatar name={decision.who} small />
                    Decided by {decision.who}
                  </span>
                  {!decision.superseded_by && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() =>
                        onCreate({ kind: "decision", supersedes: decision })
                      }
                    >
                      Change this decision
                      <ArrowRight size={13} />
                    </Button>
                  )}
                </div>
                {decision.promotes_idea && (
                  <p className="decision-link">
                    <Lightbulb size={13} />
                    Adopted from the ideas board
                  </p>
                )}
                {decision.supersedes && (
                  <p className="decision-link">
                    Replaces:{" "}
                    {state.decisions.find((d) => d.id === decision.supersedes)
                      ?.decision || decision.supersedes}
                  </p>
                )}
                {decision.superseded_by && (
                  <p className="decision-link">
                    Replaced by:{" "}
                    {state.decisions.find(
                      (d) => d.id === decision.superseded_by,
                    )?.decision || decision.superseded_by}
                  </p>
                )}
              </article>
            ))}
        </div>
      ) : (
        <div className="workspace-card">
          <EmptyState
            icon={CheckCheck}
            title="Good decisions deserve a home"
            description="Record an agreement once so nobody has to reconstruct the reasoning later."
            action={
              <Button
                variant="outline"
                onClick={() => onCreate({ kind: "decision" })}
              >
                <Plus />
                Record your first decision
              </Button>
            }
          />
        </div>
      )}
      <p className="page-footnote">
        <ShieldCheck size={14} />
        Decisions keep their history. Changing direction adds a replacement; it
        never rewrites an earlier agreement.
      </p>
    </>
  )
}

export function ResearchPage({
  onCreate,
}: {
  onCreate: (request: EntryRequest) => void
}) {
  const { state } = useWorkspace()
  const [filter, setFilter] = useState("all")
  const [editing, setEditing] = useState<Research | null>(null)
  if (!state) return null
  const research = state.research.filter(
    (r) => filter === "all" || r.viability === filter,
  )
  return (
    <>
      <PageHeading
        eyebrow="Evidence before assumptions"
        title="Research"
        description="Keep findings, open questions, and tested evidence in one place."
      >
        <Button onClick={() => onCreate({ kind: "research" })}>
          <Plus />
          Log a finding
        </Button>
      </PageHeading>
      <div className="board-toolbar">
        <Tabs value={filter} onValueChange={setFilter}>
          <TabsList>
            {["all", "untested", "feasible", "not-viable", "implemented"].map(
              (v) => (
                <TabsTrigger value={v} key={v}>
                  {v === "all"
                    ? "All findings"
                    : v === "not-viable"
                      ? "Not viable"
                      : v[0].toUpperCase() + v.slice(1)}
                </TabsTrigger>
              ),
            )}
          </TabsList>
        </Tabs>
      </div>
      {research.length ? (
        <div className="research-list">
          {research
            .slice()
            .reverse()
            .map((item) => (
              <article className="research-card" key={item.id}>
                <div className="research-icon">
                  <FlaskConical size={21} />
                </div>
                <div className="research-content">
                  <div className="research-topline">
                    <h2>{item.topic || "Research finding"}</h2>
                    <span
                      className={cn(
                        "research-status",
                        `viability-${item.viability}`,
                      )}
                    >
                      {item.viability.replace("-", " ")}
                    </span>
                  </div>
                  <p className="research-summary">{item.summary}</p>
                  {item.assessment && (
                    <div className="ai-assessment">
                      <Sparkles size={14} />
                      <p>
                        <strong>AI suggestion · not verified</strong>
                        {item.assessment.viability}:{" "}
                        {item.assessment.viability_reasoning}
                      </p>
                    </div>
                  )}
                  {item.evidence && (
                    <div className="research-evidence">
                      <ShieldCheck size={14} />
                      <span>
                        {item.evidence}
                        <small>Confirmed by {item.confirmed_by}</small>
                      </span>
                    </div>
                  )}
                  <div className="research-bottom">
                    <span className="inline-person">
                      <Avatar name={item.logged_by} small />
                      {item.logged_by}
                    </span>
                    {item.linked_mvp && (
                      <Badge variant="secondary">{item.linked_mvp}</Badge>
                    )}
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setEditing(item)}
                    >
                      {item.override
                        ? "Update assessment"
                        : "Record an assessment"}
                    </Button>
                  </div>
                </div>
              </article>
            ))}
        </div>
      ) : (
        <div className="workspace-card">
          <EmptyState
            icon={FlaskConical}
            title="Keep what you learn"
            description="A library you tested, an SDK constraint, a useful discovery. Start with a short summary; evidence can follow."
            action={
              <Button
                variant="outline"
                onClick={() => onCreate({ kind: "research" })}
              >
                <Plus />
                Add a finding
              </Button>
            }
          />
        </div>
      )}
      {editing && (
        <AssessmentDialog item={editing} onClose={() => setEditing(null)} />
      )}
    </>
  )
}

export function EntryDialog({
  request,
  onClose,
}: {
  request: EntryRequest
  onClose: () => void
}) {
  const { state, mutate, saving } = useWorkspace()
  const [text, setText] = useState(request.promote?.idea || "")
  const [who, setWho] = useState("")
  const [reason, setReason] = useState("")
  const [mvp, setMvp] = useState("")
  const [assess, setAssess] = useState(false)
  const [revision, setRevision] = useState(state?.revision)
  const [error, setError] = useState("")
  if (!state) return null
  const kind = request.kind
  const Icon =
    kind === "idea"
      ? Lightbulb
      : kind === "decision"
        ? CheckCheck
        : FlaskConical
  const title =
    kind === "idea"
      ? "Capture an idea"
      : kind === "research"
        ? "Log a research finding"
        : request.promote
          ? "Turn this idea into a decision"
          : request.supersedes
            ? "Change a decision"
            : "Record a decision"
  async function save(event: FormEvent) {
    event.preventDefault()
    if (kind !== "research" && !who) {
      setError("Choose the person who raised or decided this.")
      return
    }
    const path =
      kind === "idea"
        ? "/api/ideas"
        : kind === "decision"
          ? "/api/decision"
          : "/api/research"
    const data =
      kind === "idea"
        ? { idea: text, who }
        : kind === "decision"
          ? {
              decision: text,
              who,
              reason: reason.replace(/\s*\n\s*/g, " "),
              promotes_idea: request.promote?.id,
              supersedes: request.supersedes?.id,
            }
          : { summary: text, logged_by: who, linked_mvp: mvp || null, assess }
    try {
      await mutate(path, data, { revision })
      onClose()
    } catch (e) {
      setError((e as Error).message)
    }
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !saving) onClose()
      }}
    >
      <DialogContent className="entry-dialog sm:max-w-[540px]">
        <DialogHeader>
          <div className="dialog-icon">
            <Icon size={21} />
          </div>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {kind === "idea"
              ? "A possibility, not a promise. Give it a place to develop."
              : kind === "research"
                ? "Keep the original finding. Assessment and evidence stay separate."
                : "Make an accepted agreement clear to the whole team."}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={save} className="dialog-form">
          {request.supersedes && (
            <div className="previous-decision">
              <span>Replacing</span>
              <p>{request.supersedes.decision}</p>
            </div>
          )}
          <Field
            label={
              kind === "idea"
                ? "What's the idea?"
                : kind === "decision"
                  ? "What did the team decide?"
                  : "What did you learn?"
            }
          >
            {kind === "research" ? (
              <Textarea
                autoFocus
                aria-label="Research summary"
                rows={5}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Capture what you tested, observed, or still need to find out…"
                required
              />
            ) : (
              <Input
                autoFocus
                aria-label={kind === "idea" ? "Idea" : "Decision"}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder={
                  kind === "idea" ? "We could try…" : "We agreed to…"
                }
                required
                maxLength={800}
              />
            )}
          </Field>
          <Field
            label={
              kind === "idea"
                ? "Raised by"
                : kind === "decision"
                  ? "Decided by"
                  : "Logged by"
            }
          >
            <Pick
              label="Entry author"
              value={who}
              onChange={setWho}
              options={[
                {
                  value: "",
                  label:
                    kind === "research" ? "Unassigned" : "Choose a team member",
                },
                ...state.team.members.map((m) => ({
                  value: m.name,
                  label: m.name,
                })),
              ]}
            />
          </Field>
          {kind === "decision" && (
            <Field label="Why this direction?">
              <Textarea
                aria-label="Decision reasoning"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={3}
                placeholder="The short explanation everyone should remember."
                required
              />
            </Field>
          )}
          {kind === "research" && (
            <>
              <Field label="Milestone (optional)">
                <Input
                  aria-label="Research milestone"
                  value={mvp}
                  onChange={(e) => setMvp(e.target.value)}
                  placeholder="e.g. MVP 1"
                />
              </Field>
              <label className="ai-option">
                <Checkbox
                  checked={assess}
                  onCheckedChange={(v) => setAssess(Boolean(v))}
                  disabled={!state.ai.configured}
                />
                <div>
                  <strong>
                    <Sparkles size={14} />
                    Suggest an assessment with AI
                  </strong>
                  <span>
                    {state.ai.configured
                      ? "Sends this summary to OpenAI. Suggestions remain unverified."
                      : "Add your OpenAI key in Settings to enable this. Raw findings save without it."}
                  </span>
                </div>
              </label>
            </>
          )}
          <FormError
            message={error}
            current={
              kind === "decision"
                ? state.decisions.filter((d) => !d.superseded_by)
                : undefined
            }
            onReview={
              error.includes("changed")
                ? () => {
                    setRevision(state.revision)
                    setError("")
                  }
                : undefined
            }
          />
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={saving}
            >
              Cancel
            </Button>
            <SaveButton saving={saving}>
              {kind === "idea"
                ? "Save idea"
                : kind === "decision"
                  ? "Record decision"
                  : "Save finding"}
            </SaveButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function AssessmentDialog({
  item,
  onClose,
}: {
  item: Research
  onClose: () => void
}) {
  const { state, mutate, saving } = useWorkspace()
  const [viability, setViability] = useState(item.viability)
  const [who, setWho] = useState(item.confirmed_by || "")
  const [evidence, setEvidence] = useState(item.evidence || "")
  const [reason, setReason] = useState(
    item.override ? item.viability_reasoning : "",
  )
  const [linkedIdea, setLinkedIdea] = useState(item.linked_idea || "")
  const [revision, setRevision] = useState(state?.revision)
  const [error, setError] = useState("")
  if (!state) return null
  async function save(event: FormEvent) {
    event.preventDefault()
    try {
      await mutate(
        "/api/research/override",
        {
          id: item.id,
          viability,
          confirmed_by: who,
          evidence,
          viability_reasoning: reason,
          linked_idea: linkedIdea || null,
        },
        { revision },
      )
      onClose()
    } catch (e) {
      setError((e as Error).message)
    }
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !saving) onClose()
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Record a human assessment</DialogTitle>
          <DialogDescription>
            {item.topic}. This is separate from any AI suggestion.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={save} className="dialog-form">
          <Field label="Assessment">
            <Pick
              label="Research assessment"
              value={viability}
              onChange={(v) => setViability(v as Research["viability"])}
              options={[
                { value: "untested", label: "Untested" },
                { value: "feasible", label: "Feasible" },
                { value: "not-viable", label: "Not viable" },
                { value: "implemented", label: "Implemented" },
              ]}
            />
          </Field>
          <Field label="Confirmed by">
            <Pick
              label="Assessment author"
              value={who}
              onChange={setWho}
              options={[
                { value: "", label: "Choose a team member" },
                ...state.team.members.map((m) => ({
                  value: m.name,
                  label: m.name,
                })),
              ]}
            />
          </Field>
          <Field label="Why?">
            <Textarea
              aria-label="Assessment reasoning"
              rows={2}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="What supports this assessment?"
              required
            />
          </Field>
          <Field
            label="Evidence"
            hint="Required for implemented: a commit, measured result, or demo smoke."
          >
            <Textarea
              aria-label="Research evidence"
              rows={2}
              value={evidence}
              onChange={(e) => setEvidence(e.target.value)}
              required={viability === "implemented"}
            />
          </Field>
          <Field label="Related idea">
            <Pick
              label="Linked idea"
              value={linkedIdea}
              onChange={setLinkedIdea}
              options={[
                { value: "", label: "No linked idea" },
                ...state.ideas.map((i) => ({ value: i.id, label: i.idea })),
              ]}
            />
          </Field>
          <FormError
            message={error}
            current={state.research.find((r) => r.id === item.id)}
            onReview={
              error.includes("changed")
                ? () => {
                    setRevision(state.revision)
                    setError("")
                  }
                : undefined
            }
          />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <SaveButton saving={saving}>Save assessment</SaveButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
