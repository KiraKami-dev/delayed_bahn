import { useState, type FormEvent } from "react"
import {
  ArrowUpRight,
  CalendarDays,
  Check,
  Copy,
  Eye,
  EyeOff,
  FolderKanban,
  GitBranch,
  KeyRound,
  LockKeyhole,
  Pencil,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Checkbox } from "@/components/ui/checkbox"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Avatar,
  Field,
  FormError,
  PageHeading,
  Pick,
  SaveButton,
  SectionHeading,
} from "./shared"
import { formatDate, localDateInput, splitNames } from "@/lib/format"
import { useWorkspace } from "@/lib/workspace"
import type { EventConfig } from "@/lib/types"

export function EventEditor({ onClose }: { onClose: () => void }) {
  const { state, mutate, saving } = useWorkspace()
  const [name, setName] = useState(state?.event.event_name || "")
  const [venue, setVenue] = useState(state?.event.venue || "")
  const [starts, setStarts] = useState(
    localDateInput(state?.event.build_starts),
  )
  const [deadline, setDeadline] = useState(
    localDateInput(state?.event.submission_deadline),
  )
  const [buffer, setBuffer] = useState(
    String(Math.abs(state?.event.submit_target_offset_hours ?? -2)),
  )
  const [format, setFormat] = useState(
    state?.event.submission_format || "unknown",
  )
  const [pitch, setPitch] = useState(
    String(state?.event.pitch_length_minutes || ""),
  )
  const [coordinator, setCoordinator] = useState(
    state?.event.coordination_maintainer || "",
  )
  const [tracks, setTracks] = useState((state?.event.tracks || []).join(", "))
  const [partners, setPartners] = useState(
    (state?.event.partners || []).join(", "),
  )
  const [known, setKnown] = useState(
    Boolean(state?.event.tracks_known_in_advance),
  )
  const [revision, setRevision] = useState(state?.revision)
  const [error, setError] = useState("")
  if (!state) return null
  async function save(event: FormEvent) {
    event.preventDefault()
    try {
      const config: EventConfig = {
        event_name: name,
        venue,
        build_starts: starts ? new Date(starts).toISOString() : "",
        submission_deadline: deadline ? new Date(deadline).toISOString() : "",
        submit_target_offset_hours: -Number(buffer),
        submission_format: format,
        pitch_length_minutes: pitch ? Number(pitch) : null,
        coordination_maintainer: coordinator,
        tracks: splitNames(tracks),
        partners: splitNames(partners),
        tracks_known_in_advance: known,
      }
      await mutate("/api/event", { event: config }, { revision })
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
      <DialogContent className="event-dialog sm:max-w-[640px]">
        <DialogHeader>
          <div className="dialog-icon">
            <FolderKanban size={22} />
          </div>
          <DialogTitle>
            {state.event_is_blank
              ? "Give your workspace a name"
              : "Project & event details"}
          </DialogTitle>
          <DialogDescription>
            {state.event_is_blank
              ? "Start with a name. Everything else can be filled in as you learn more."
              : "Update this event without resetting tasks, notes, or decisions."}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={save} className="dialog-form">
          <Field label="Workspace name">
            <Input
              autoFocus
              aria-label="Workspace name"
              placeholder="What are you working on?"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              maxLength={120}
            />
          </Field>
          <div className="form-grid">
            <Field label="Venue or location">
              <Input
                aria-label="Event venue"
                placeholder="Optional"
                value={venue}
                onChange={(e) => setVenue(e.target.value)}
              />
            </Field>
            <Field label="Coordination lead">
              <Pick
                label="Coordination lead"
                value={coordinator}
                onChange={setCoordinator}
                options={[
                  { value: "", label: "Choose later" },
                  ...state.team.members.map((m) => ({
                    value: m.name,
                    label: m.name,
                  })),
                ]}
              />
            </Field>
          </div>
          <div className="form-divider">
            <CalendarDays size={14} />
            Time and submission
          </div>
          <div className="form-grid">
            <Field label="Build starts">
              <Input
                aria-label="Build starts"
                type="datetime-local"
                value={starts}
                onChange={(e) => setStarts(e.target.value)}
              />
            </Field>
            <Field label="Official deadline">
              <Input
                aria-label="Submission deadline"
                type="datetime-local"
                value={deadline}
                onChange={(e) => setDeadline(e.target.value)}
              />
            </Field>
          </div>
          <p className="field-hint">
            Times are entered in{" "}
            {Intl.DateTimeFormat().resolvedOptions().timeZone} and stored with a
            timezone.
          </p>
          <div className="form-grid">
            <Field
              label="Submit early by"
              hint="Hours reserved before the official deadline."
            >
              <Input
                aria-label="Submit early hours"
                type="number"
                min="0.25"
                max="72"
                step="0.25"
                value={buffer}
                onChange={(e) => setBuffer(e.target.value)}
                required
              />
            </Field>
            <Field label="Submission format">
              <Pick
                label="Submission format"
                value={format}
                onChange={setFormat}
                options={[
                  { value: "unknown", label: "Not known yet" },
                  { value: "live_pitch", label: "Live pitch" },
                  { value: "video", label: "Recorded video" },
                  { value: "both", label: "Pitch and video" },
                ]}
              />
            </Field>
          </div>
          <details className="advanced-details">
            <summary>Tracks, partners & pitch length</summary>
            <div className="dialog-form mt-4">
              <Field label="Tracks" hint="Separate track names with commas.">
                <Input
                  aria-label="Event tracks"
                  value={tracks}
                  onChange={(e) => setTracks(e.target.value)}
                  placeholder="Leave blank until the reveal"
                />
              </Field>
              <label className="inline-checkbox">
                <Checkbox
                  checked={known}
                  onCheckedChange={(v) => setKnown(Boolean(v))}
                />
                Tracks are published before the event
              </label>
              <Field
                label="Partners"
                hint="Separate partner names with commas."
              >
                <Input
                  aria-label="Event partners"
                  value={partners}
                  onChange={(e) => setPartners(e.target.value)}
                />
              </Field>
              <Field label="Pitch length, in minutes">
                <Input
                  aria-label="Pitch length"
                  type="number"
                  min="0.5"
                  max="180"
                  step="0.5"
                  value={pitch}
                  onChange={(e) => setPitch(e.target.value)}
                  placeholder="Not known yet"
                />
              </Field>
            </div>
          </details>
          <FormError
            message={error}
            current={state.event}
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
              {state.event_is_blank ? "Create workspace" : "Save details"}
            </SaveButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function SettingsPage({ onConfigure }: { onConfigure: () => void }) {
  const { state, mutate, saving, refresh } = useWorkspace()
  const [key, setKey] = useState("")
  const [showKey, setShowKey] = useState(false)
  const [keyError, setKeyError] = useState("")
  if (!state) return null
  const ownership = state.owners_raw
    .split("## Per-person")[0]
    .split("\n")
    .filter((line) => line.startsWith("|") && !line.includes("---"))
    .map((line) =>
      line
        .split("|")
        .slice(1, -1)
        .map((v) => v.trim()),
    )
    .filter(
      (row) =>
        row.length >= 2 &&
        !["Directory", "Feature", "Role", "Person"].includes(row[0]),
    )
  async function saveKey(event: FormEvent) {
    event.preventDefault()
    try {
      await mutate("/api/settings/openai", { key }, { quiet: true })
      setKey("")
      setKeyError("")
      toast.success("API key saved on this machine", {
        description:
          "It is never committed or sent back to the browser. AI requests remain optional.",
      })
    } catch (e) {
      setKeyError((e as Error).message)
    }
  }
  async function assign(path: string, owner: string) {
    if (state!.event_is_blank) {
      onConfigure()
      return
    }
    try {
      await mutate("/api/owners", { key: path, owner })
    } catch {
      return
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="Make it your team's workspace"
        title="Team & settings"
        description="Project details, responsibilities, and the optional tools that help you work."
      />
      <div className="settings-grid">
        <div className="settings-main">
          <section className="workspace-card">
            <SectionHeading
              title="Project & event"
              action="Edit details"
              onAction={onConfigure}
            />
            <div className="project-settings-summary">
              <span className="project-emblem">
                <FolderKanban size={27} />
              </span>
              <div>
                <h2>{state.event.event_name || "No workspace configured"}</h2>
                <p>
                  {state.event.venue ||
                    "Add a name and the details you know. Leave the rest for later."}
                </p>
              </div>
            </div>
            <div className="settings-values">
              <div>
                <span>Build starts</span>
                <strong>{formatDate(state.event.build_starts, true)}</strong>
              </div>
              <div>
                <span>Submission deadline</span>
                <strong>
                  {formatDate(state.event.submission_deadline, true)}
                </strong>
              </div>
              <div>
                <span>Coordination lead</span>
                <strong>
                  {state.event.coordination_maintainer || "Not assigned"}
                </strong>
              </div>
              <div>
                <span>Submission format</span>
                <strong>
                  {
                    (
                      {
                        unknown: "Not known yet",
                        live_pitch: "Live pitch",
                        video: "Video",
                        both: "Pitch and video",
                      } as Record<string, string>
                    )[state.event.submission_format || "unknown"]
                  }
                </strong>
              </div>
            </div>
          </section>
          <section className="workspace-card">
            <SectionHeading
              title="People in this workspace"
              count={state.team.members.length}
            />
            <div className="settings-team">
              {state.team.members.map((member) => (
                <div key={member.name}>
                  <Avatar name={member.name} />
                  <section>
                    <strong>{member.name}</strong>
                    <p>{member.background || "No background added"}</p>
                  </section>
                  <Badge variant="outline">
                    {member.harness === "claude-code"
                      ? "Claude Code"
                      : member.harness === "codex"
                        ? "Codex"
                        : member.harness}
                  </Badge>
                </div>
              ))}
            </div>
            <p className="section-footnote">
              Your reusable roster comes from team.json. Product
              responsibilities are assigned below, not inferred from background.
            </p>
          </section>
          <section className="workspace-card">
            <SectionHeading title="Who owns what" />
            <p className="section-description">
              Choose an accountable person for each area. Changes update the
              ownership file your agents read.
            </p>
            <div className="ownership-list">
              {ownership.map((row) => (
                <div key={row[0]}>
                  <section>
                    <strong>
                      {row[0].startsWith("app/")
                        ? (
                            {
                              "app/frontend": "Frontend",
                              "app/backend": "Backend",
                              "app/agents": "AI services",
                              "app/shared": "Shared interfaces",
                            } as Record<string, string>
                          )[row[0]] || row[0]
                        : row[0].replaceAll("-", " ")}
                    </strong>
                    {row[0].startsWith("app/") && <small>{row[0]}</small>}
                  </section>
                  {row[0] === "app/shared" ? (
                    <Badge variant="secondary">
                      <LockKeyhole size={12} />
                      Generated
                    </Badge>
                  ) : (
                    <Pick
                      label={`Owner for ${row[0]}`}
                      value={row[1] === "unassigned" ? "" : row[1]}
                      onChange={(v) => void assign(row[0], v)}
                      disabled={saving}
                      options={[
                        { value: "", label: "Unassigned" },
                        ...state.team.members.map((m) => ({
                          value: m.name,
                          label: m.name,
                        })),
                      ]}
                    />
                  )}
                </div>
              ))}
            </div>
          </section>
        </div>
        <aside className="settings-aside">
          <section className="workspace-card ai-settings">
            <div className="ai-settings-top">
              <span className="dialog-icon">
                <Sparkles size={21} />
              </span>
              <Badge variant="secondary">Optional</Badge>
            </div>
            <h2>A little help from AI</h2>
            <p>
              Turn transcripts into proposed decisions, tasks, and ideas. You
              stay in control of what is saved.
            </p>
            <div
              className={
                state.ai.configured
                  ? "integration-status configured"
                  : "integration-status"
              }
            >
              <span />
              {state.ai.configured
                ? "OpenAI key configured"
                : "No OpenAI key configured"}
            </div>
            {state.ai.source === "environment" ? (
              <div className="field-hint">
                Your key is managed by the OPENAI_API_KEY environment variable.
                Update it there and restart the server.
              </div>
            ) : (
              <form onSubmit={saveKey} className="dialog-form">
                <Field
                  label={
                    state.ai.configured ? "Replace API key" : "OpenAI API key"
                  }
                >
                  <div className="key-input">
                    <Input
                      aria-label="OpenAI API key"
                      type={showKey ? "text" : "password"}
                      autoComplete="new-password"
                      spellCheck={false}
                      placeholder="sk-…"
                      value={key}
                      onChange={(e) => setKey(e.target.value)}
                      required
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      aria-label={showKey ? "Hide API key" : "Show API key"}
                      onClick={() => setShowKey((v) => !v)}
                    >
                      {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
                    </Button>
                  </div>
                </Field>
                <FormError message={keyError} />
                <SaveButton saving={saving}>Save key locally</SaveButton>
              </form>
            )}
            <p className="key-privacy">
              <ShieldCheck size={14} />
              Stored in a gitignored file on this machine. Never shared with
              teammates, included in Git, or returned by the API.
            </p>
          </section>
          <section className="workspace-card sharing-settings">
            <SectionHeading title="Sharing & freshness" />
            <div className="sharing-status">
              <GitBranch size={18} />
              <div>
                <strong>{state.freshness.branch || "Detached checkout"}</strong>
                <span>
                  Coordination branch: {state.freshness.coordination_branch}
                </span>
              </div>
            </div>
            <div className="settings-values single">
              <div>
                <span>Saved revision</span>
                <strong>
                  {state.freshness.head?.slice(0, 8) || "No commits yet"}
                </strong>
              </div>
              <div>
                <span>Local changes</span>
                <strong>{state.freshness.local_changes.length} files</strong>
              </div>
              <div>
                <span>Last remote check</span>
                <strong>
                  {formatDate(
                    state.freshness.remote_check?.last_success_at,
                    true,
                  )}
                </strong>
              </div>
              <div>
                <span>Cached upstream</span>
                <strong>
                  {state.freshness.upstream
                    ? `${state.freshness.ahead} ahead · ${state.freshness.behind} behind`
                    : "Not configured"}
                </strong>
              </div>
            </div>
            <div className="sharing-explainer">
              Dashboard saves update this clone. They are not live on other
              machines until committed, pushed, integrated and pulled.
            </div>
            <Button
              variant="outline"
              className="w-full"
              onClick={() =>
                void navigator.clipboard
                  .writeText(
                    "Review and publish the accepted coordination changes in team-setup/state and team-setup/board/tasks.json. Exclude secrets, runtime logs, and unrelated product work. Sync the agreed coordination branch safely without discarding local edits.",
                  )
                  .then(() =>
                    toast.success(
                      "Request copied — paste it into your coding agent",
                    ),
                  )
                  .catch(() => toast.error("Clipboard access unavailable"))
              }
            >
              <Copy size={14} />
              Copy sharing request
            </Button>
            <Button
              variant="ghost"
              className="mt-2 w-full"
              onClick={() => void refresh()}
            >
              <RefreshCw size={14} />
              Refresh local workspace
            </Button>
          </section>
        </aside>
      </div>
    </>
  )
}
