import { useRef, useState, type ReactNode } from "react"
import {
  ArrowDown,
  ArrowRight,
  BookOpen,
  Check,
  CheckCheck,
  ChevronDown,
  Clipboard,
  FileText,
  Flag,
  FolderKanban,
  GitBranch,
  Lightbulb,
  MessageSquareText,
  Play,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { PageHeading } from "./shared"
import { useWorkspace } from "@/lib/workspace"
import type { Page } from "@/lib/types"

const chapters = [
  {
    id: "join",
    title: "Join the shared repository",
    icon: Users,
    audience: "Each teammate · once",
  },
  {
    id: "configure",
    title: "Set up the workspace",
    icon: FolderKanban,
    audience: "Coordinator · once per event",
  },
  {
    id: "scope",
    title: "Agree on the problem and demo",
    icon: FileText,
    audience: "Whole team",
  },
  {
    id: "plan",
    title: "Make the next steps visible",
    icon: CheckCheck,
    audience: "Each task owner",
  },
  {
    id: "decide",
    title: "Separate ideas from decisions",
    icon: Lightbulb,
    audience: "Throughout the event",
  },
  {
    id: "capture",
    title: "Turn conversations into action",
    icon: MessageSquareText,
    audience: "Whoever captures the meeting",
  },
  {
    id: "share",
    title: "Share updates and refresh agents",
    icon: GitBranch,
    audience: "Everyone · repeat regularly",
  },
  {
    id: "demo",
    title: "Verify, rehearse, and submit",
    icon: Flag,
    audience: "Demo lead and team",
  },
] as const

const initPrompt =
  "Initialize this checkout using the repository's AGENTS.md. Run the safe local bootstrap, confirm my roster identity if it is ambiguous, and start or reuse the dashboard. Report any approvals I need to give. Join the existing event state: do not reset the event, replace agent instructions, or change Git remotes."
const publishPrompt =
  "Review and publish the accepted coordination changes in team-setup/state and team-setup/board/tasks.json to our agreed coordination branch. Exclude secrets, runtime logs and unrelated product work. Preserve newer teammate changes; do not force-push, auto-stash, or discard local edits. Tell me if a conflict needs a decision."
const refreshPrompt =
  "Check local changes, fetch the agreed remote, and safely integrate our coordination branch. Do not overwrite or auto-stash my work. Then reread the current decisions, ownership, relevant task, scope and contract. Tell me what changed and which revision you are working from."

function CopyBlock({
  label,
  text,
  command = false,
}: {
  label: string
  text: string
  command?: boolean
}) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      toast.success(`${label} copied`)
    } catch {
      toast.error(
        "Clipboard access is unavailable. You can select and copy the text below.",
      )
    }
  }
  return (
    <div className="guide-copy-block">
      <div>
        <span>{label}</span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={copy}
          aria-label={`Copy ${label.toLowerCase()}`}
        >
          {copied ? <Check size={14} /> : <Clipboard size={14} />}
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      {command ? (
        <pre>
          <code>{text}</code>
        </pre>
      ) : (
        <p>{text}</p>
      )}
    </div>
  )
}

export function GuidePage({
  navigate,
  onConfigure,
}: {
  navigate: (page: Page) => void
  onConfigure: () => void
}) {
  const { state } = useWorkspace()
  const jumpTarget = useRef<string | null>(null)
  function jump(id: string) {
    const section = document.getElementById(`guide-${id}`)
    section?.scrollIntoView({ block: "start", behavior: "instant" })
    section?.focus({ preventScroll: true })
  }
  const open = (page: Page, label: string) => (
    <Button variant="outline" size="sm" onClick={() => navigate(page)}>
      {label}
      <ArrowRight size={14} />
    </Button>
  )
  const sections: Record<(typeof chapters)[number]["id"], ReactNode> = {
    join: (
      <>
        <ol>
          <li>
            The team creates <strong>one product repository</strong> from this
            template. Each teammate clones that same repository, rather than
            creating separate team copies.
          </li>
          <li>
            Open Claude Code, Codex, or your coding agent in the checkout. The
            agent instructions are already included; don't replace them with
            generated instructions.
          </li>
          <li>
            Ask the agent to initialize your machine. Confirm your identity or
            permissions if needed. Optional MCP services are not required for
            the dashboard.
          </li>
        </ol>
        <CopyBlock label="Initialization prompt" text={initPrompt} />
        <details className="guide-details">
          <summary>Prefer running the setup commands yourself?</summary>
          <CopyBlock
            label="Local setup commands"
            command
            text={
              "./bootstrap.sh\nnpm --prefix team-setup/board/web ci\nnpm --prefix team-setup/board/web run dev"
            }
          />
          <p>
            The development command starts the UI and Python API. Dependencies
            need installing once; this does not install a product stack or
            authenticate external services.
          </p>
        </details>
        <div className="guide-callout">
          <ShieldCheck size={17} />
          <p>
            <strong>Joining is not resetting.</strong> A new teammate must use
            the existing event state. Only the coordinator starts a new event,
            with explicit confirmation.
          </p>
        </div>
      </>
    ),
    configure: (
      <>
        <ol>
          <li>
            Choose <strong>Set up workspace</strong> on Overview, or{" "}
            <strong>Team & settings → Edit details</strong>.
          </li>
          <li>
            Add a workspace name. Fill in the location, build start, submission
            deadline and format as they become known. Unknown fields can stay
            blank.
          </li>
          <li>
            Choose a coordination lead. Your reusable roster stays in{" "}
            <code>team.json</code>; responsibilities are assigned fresh for this
            event.
          </li>
          <li>
            Keep an early submit target. Dates use the timezone shown in the
            form, and task targets are calculated against the planning window
            ending at that target.
          </li>
        </ol>
        <div className="guide-step-actions">
          <Button size="sm" onClick={onConfigure} disabled={!state}>
            Open workspace details
            <ArrowRight size={14} />
          </Button>
          {open("settings", "Team & settings")}
        </div>
        <p className="guide-note">
          Editing details does not reset tasks or decisions. Starting a
          different event uses the separately confirmed new-event script
          described in the FAQ below.
        </p>
      </>
    ),
    scope: (
      <>
        <ol>
          <li>
            Capture the organizer's problem and judging criteria before deciding
            what to build. Use your agent's reveal-capture prompt when the team
            is scouting different tracks.
          </li>
          <li>
            Write the chosen problem in{" "}
            <strong>Documents → Project brief</strong>. Record the accepted
            choice in Decisions.
          </li>
          <li>
            Write the short <strong>Demo script</strong> before making a large
            feature list. Put exclusions in <strong>Out of scope</strong>.
          </li>
          <li>
            Have the responsible agent prepare the{" "}
            <strong>Technical contract</strong>, mocks and generated
            Architecture. Complete each gate from Overview only when its exit
            condition is met.
          </li>
        </ol>
        <div className="guide-step-actions">
          {open("documents", "Open documents")}
          {open("overview", "View the stages")}
        </div>
        <div className="guide-callout">
          <ShieldCheck size={17} />
          <p>
            <strong>Frozen agreements are protected.</strong> Relevant documents
            become read-only after their gate. An approved change goes through
            the owning agent—not a silent dashboard edit.
          </p>
        </div>
      </>
    ),
    plan: (
      <>
        <ol>
          <li>
            Open <strong>Task board → New task</strong>. Give the task a clear
            outcome, one accountable owner, and enough context to understand
            what done means.
          </li>
          <li>
            Add helpers, a milestone such as your first MVP, and dependencies
            when needed. A missing or unfinished dependency is shown as a
            blocker.
          </li>
          <li>
            Move work through{" "}
            <strong>To do → In progress → In review → Done</strong>. Drag cards
            on desktop, or open a card and change Status on any device.
          </li>
          <li>
            Assign directory and gate responsibilities in{" "}
            <strong>Team & settings → Who owns what</strong>. Task ownership and
            directory ownership should agree.
          </li>
        </ol>
        <div className="guide-step-actions">
          {open("tasks", "Open task board")}
          {open("settings", "Assign responsibilities")}
        </div>
        <p className="guide-note">
          <strong>Targets are relative.</strong> T+40% means 40% of the time
          between build start and the early submit target—not 40% of the
          advertised event duration. A done card alone does not prove the
          integrated demo works.
        </p>
      </>
    ),
    decide: (
      <>
        <div className="guide-distinction">
          <div>
            <Lightbulb size={19} />
            <h3>Ideas are possibilities</h3>
            <p>
              Capture a suggestion in Ideas. Move it to Exploring or Set aside.
              It is not approved scope yet.
            </p>
          </div>
          <div>
            <CheckCheck size={19} />
            <h3>Decisions are agreements</h3>
            <p>
              Once the team agrees, use Turn into a decision. Record who decided
              and why. Changing direction creates a replacement and keeps the
              earlier decision in history.
            </p>
          </div>
        </div>
        <p>
          Use <strong>Research</strong> for findings from actual investigation.
          Preserve the original summary, then add evidence and a human
          assessment. AI suggestions are advisory, not proof that something is
          implemented.
        </p>
        <div className="guide-step-actions">
          {open("ideas", "Explore ideas")}
          {open("decisions", "Read current decisions")}
          {open("research", "Log research")}
        </div>
      </>
    ),
    capture: (
      <>
        <ol>
          <li>
            Open <strong>Meeting notes</strong>. Paste notes or import a text
            transcript: <code>.txt</code>, <code>.md</code>, <code>.srt</code>{" "}
            or <code>.vtt</code>.
          </li>
          <li>
            Choose <strong>Save notes only</strong> to preserve the original
            without AI. Saved notes can be reopened from the library.
          </li>
          <li>
            For AI assistance, add your personal OpenAI key in{" "}
            <strong>Team & settings</strong>, then choose{" "}
            <strong>Generate AI preview</strong>. This sends the transcript to
            OpenAI.
          </li>
          <li>
            Review the proposed decisions, tasks and ideas. Uncheck anything
            that wasn't agreed or doesn't belong, then{" "}
            <strong>Apply selected updates</strong>.
          </li>
        </ol>
        <div className="guide-step-actions">
          {open("notes", "Capture meeting notes")}
          {open("settings", "Configure optional AI")}
        </div>
        <div className="guide-callout">
          <Sparkles size={17} />
          <p>
            <strong>You approve the outcome.</strong> Unclear points stay
            flagged rather than becoming decisions. Originals remain saved if AI
            is unavailable. Keys stay on your machine; don't paste them into
            shared notes. Audio recording and transcription are not built into
            this dashboard.
          </p>
        </div>
      </>
    ),
    share: (
      <>
        <p>
          <strong>
            A dashboard save updates this clone, not every teammate's machine.
          </strong>{" "}
          Coordinate through the agreed shared branch and publish important
          decisions, blockers and ownership changes before affected work
          continues.
        </p>
        <div className="guide-sync-flow" aria-label="Synchronization sequence">
          {["Save", "Commit", "Push", "Integrate", "Pull", "Reread"].map(
            (step, index) => (
              <span key={step}>
                <b>{step}</b>
                {index < 5 && <ArrowRight size={13} aria-hidden="true" />}
              </span>
            ),
          )}
        </div>
        <CopyBlock
          label="Publish request for your agent"
          text={publishPrompt}
        />
        <CopyBlock
          label="Refresh request for your agent"
          text={refreshPrompt}
        />
        <ul>
          <li>
            Publish accepted coordination changes as small commits; don't wait
            for the entire feature to be finished.
          </li>
          <li>
            Pushing a work branch is not the same as integrating into the shared
            coordination branch.
          </li>
          <li>
            Before a new task, safely bring in the shared branch and have your
            running agent reread decisions, ownership, its task and the
            contract.
          </li>
        </ul>
        <div className="guide-step-actions">
          {open("settings", "Check sharing & freshness")}
        </div>
        <div className="guide-callout">
          <GitBranch size={17} />
          <p>
            <strong>Refresh is not pull.</strong> Refresh local workspace only
            rereads local files. A connection badge is not proof of remote
            freshness, and updated files do not automatically refresh an agent's
            context. Never blindly pull into dirty work or overwrite a
            teammate's changes.
          </p>
        </div>
      </>
    ),
    demo: (
      <>
        <ol>
          <li>
            Integrate the actual happy path and run the configured product smoke
            on the demo machine. The Overview distinguishes task progress from a
            verified demo.
          </li>
          <li>
            Keep the pitch current: problem, insight, demo, how it works, why
            this team, and next steps. Rehearse the real demo script.
          </li>
          <li>
            Prepare deterministic seed data, an offline fallback and a backup
            recording before the polish window ends.
          </li>
          <li>
            After intended work is committed and the working tree is clean,
            rerun smoke and take a confirmed snapshot. Restore into a separate
            worktree if needed, leaving ongoing work untouched.
          </li>
          <li>
            Submit at the early target. The final planning buffer is not another
            feature window.
          </li>
        </ol>
        <CopyBlock
          label="Demo verification commands"
          command
          text={
            "team-setup/scripts/smoke.sh\nteam-setup/scripts/snapshot.sh --confirm-demo"
          }
        />
        <p className="guide-note">
          Smoke must be configured for the chosen product first. An unconfigured
          check is not a pass, and snapshots require passing evidence for the
          current clean commit.
        </p>
        <div className="guide-step-actions">
          {open("overview", "Review demo readiness")}
        </div>
      </>
    ),
  }
  return (
    <>
      <PageHeading
        eyebrow="A practical start-to-finish guide"
        title="How to use hack-os"
        description="Know where to start, what to update, and how to keep the whole team aligned."
      >
        <Button variant="outline" onClick={() => jump("join")}>
          <Play size={15} />
          Start with step 1
        </Button>
      </PageHeading>
      <section className="guide-intro">
        <span className="dialog-icon">
          <BookOpen size={23} />
        </span>
        <div>
          <h2>One shared direction. A clear next step.</h2>
          <p>
            Use this page as your team's operating guide—not a checklist someone
            has to maintain. Setup happens once; planning, capture and sharing
            repeat as the work evolves.
          </p>
          <div className="guide-intro-tags">
            <Badge variant="secondary">8 practical steps</Badge>
            <Badge variant="secondary">
              For teammates and project managers
            </Badge>
            <Badge variant="secondary">No AI key required to start</Badge>
          </div>
        </div>
      </section>
      <div className="guide-mobile-index">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline">
              Jump to a step
              <ChevronDown size={15} />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            onCloseAutoFocus={(event) => {
              if (jumpTarget.current) {
                event.preventDefault()
                const target = jumpTarget.current
                jumpTarget.current = null
                jump(target)
              }
            }}
          >
            {chapters.map((chapter, index) => (
              <DropdownMenuItem
                key={chapter.id}
                onSelect={() => {
                  jumpTarget.current = chapter.id
                }}
              >
                {index + 1}. {chapter.title}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        <Button variant="ghost" onClick={() => jump("questions")}>
          Common questions
          <ArrowDown size={14} />
        </Button>
      </div>
      <div className="guide-layout">
        <aside className="guide-index">
          <nav aria-label="Guide steps">
            <h2>In this guide</h2>
            {chapters.map((chapter, index) => (
              <button key={chapter.id} onClick={() => jump(chapter.id)}>
                <span>{index + 1}</span>
                {chapter.title}
              </button>
            ))}
            <button onClick={() => jump("questions")}>
              <BookOpen size={15} />
              Common questions
            </button>
          </nav>
        </aside>
        <div className="guide-chapters">
          {chapters.map((chapter, index) => (
            <section
              className="workspace-card guide-step"
              id={`guide-${chapter.id}`}
              key={chapter.id}
              tabIndex={-1}
              aria-labelledby={`guide-title-${chapter.id}`}
            >
              <div className="guide-step-heading">
                <span className="guide-step-number">{index + 1}</span>
                <div>
                  <span className="guide-audience">{chapter.audience}</span>
                  <h2 id={`guide-title-${chapter.id}`}>{chapter.title}</h2>
                </div>
                <chapter.icon size={20} aria-hidden="true" />
              </div>
              <div className="guide-step-content">{sections[chapter.id]}</div>
            </section>
          ))}
          <section
            className="workspace-card guide-questions"
            id="guide-questions"
            tabIndex={-1}
            aria-labelledby="guide-questions-title"
          >
            <h2 id="guide-questions-title">Common questions</h2>
            <details>
              <summary>
                Can we use this without OpenAI or without internet?
              </summary>
              <p>
                Manual tasks, documents, ideas and raw notes use local files.
                OpenAI is optional. Without internet you cannot fetch or publish
                Git updates, and AI requests may fail; treat the workspace as a
                local snapshot. If the local API itself is unavailable, use the
                repository's markdown files while resolving it. This guide
                remains readable when the UI can load but the API cannot.
              </p>
            </details>
            <details>
              <summary>What should we do when a save is rejected?</summary>
              <p>
                Keep your draft. Another update may have changed the source
                files. Review the latest saved version before choosing to use
                its revision or retrying. Never discard newer work just to make
                a save succeed. Transcript previews made against old state need
                regenerating before confirmation.
              </p>
            </details>
            <details>
              <summary>How do we start another hackathon?</summary>
              <p>
                The coordinator stops other state writers and runs{" "}
                <code>team-setup/scripts/new-event.sh</code>. It requires
                explicit RESET confirmation, archives the previous state and
                tasks, keeps the roster, and clears event ownership for
                reassignment. Do not run it merely because a teammate joined. Do
                not reset an ongoing event to change its dates; edit those in
                Settings.
              </p>
            </details>
            <details>
              <summary>Do we have to commit every keystroke?</summary>
              <p>
                No. Publish accepted decisions and blockers promptly, routine
                coordination updates at agreed checkpoints, and code in coherent
                pieces. Reading shared state does not require a commit.
                Git-based sharing is explicit; automatic background publishing
                is not implemented.
              </p>
            </details>
            <details>
              <summary>How do we work on a phone?</summary>
              <p>
                Use the navigation button at the top left and the New menu for
                quick actions. Open a task to edit it or change Status instead
                of dragging. Lists and forms adapt to small screens; tables and
                tab bars can scroll within their own area. When connecting from
                another device, keep in mind that this server is
                localhost-only—don't expose the writable API publicly.
              </p>
            </details>
          </section>
        </div>
      </div>
    </>
  )
}
