import { useEffect, useState } from "react"
import {
  ArrowRight,
  ArrowUpRight,
  CalendarDays,
  Check,
  CheckCheck,
  ChevronRight,
  CircleDashed,
  Clock3,
  FileText,
  Flag,
  GitBranch,
  Lightbulb,
  MessageSquareText,
  Plus,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Avatar, EmptyState, SectionHeading, StatusBadge } from "./shared"
import { blockers, docLabels, formatDate, relativeTime } from "@/lib/format"
import { useWorkspace } from "@/lib/workspace"
import { cn } from "@/lib/utils"
import type { Page, Task } from "@/lib/types"

export function Overview({
  navigate,
  onNewTask,
  onEditTask,
  onConfigure,
}: {
  navigate: (page: Page) => void
  onNewTask: () => void
  onEditTask: (task: Task) => void
  onConfigure: () => void
}) {
  const { state, docs, mutate, saving } = useWorkspace()
  const [confirmStage, setConfirmStage] = useState(false)
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(interval)
  }, [])
  if (!state) return null
  const complete = state.tasks.filter((t) => t.status === "demo-ready").length
  const percent = state.tasks.length
    ? Math.round((complete / state.tasks.length) * 100)
    : 0
  const blocked = state.tasks.filter(
    (t) => t.status !== "demo-ready" && blockers(t, state.tasks).length,
  )
  const inProgress = state.tasks.filter((t) => t.status === "building").length
  const current = state.pipeline.stages.find(
    (s) => s.id === state.pipeline.current_stage,
  )
  const remaining = state.pipeline.countdown.submit_target
    ? Math.floor(
        (Date.parse(state.pipeline.countdown.submit_target) - now) / 1000,
      )
    : null
  const timeUnits =
    remaining !== null && remaining >= 0
      ? [
          Math.floor(remaining / 86400),
          Math.floor(remaining / 3600) % 24,
          Math.floor(remaining / 60) % 60,
        ]
      : null
  const milestones = Array.from(
    new Set(state.tasks.map((t) => t.mvp).filter(Boolean)),
  ) as string[]
  async function advance() {
    if (!current) return
    try {
      await mutate(
        "/api/stage",
        current.status === "pending" ? { stage_id: current.id } : {},
      )
      setConfirmStage(false)
    } catch {
      return
    }
  }
  const greeting = new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  }).format(new Date())
  return (
    <>
      <div className="overview-greeting">
        <div>
          <p className="date-line">{greeting}</p>
          <h1>
            {state.event_is_blank
              ? "Your next great idea starts here."
              : "A little clarity. A lot of progress."}
          </h1>
          <p>
            A shared home for your plans, your people, and what happens next.
          </p>
        </div>
        <Button variant="outline" onClick={onConfigure}>
          <CalendarDays size={15} />
          {state.event_is_blank ? "Set up workspace" : "Project details"}
        </Button>
      </div>
      {state.event_is_blank && (
        <section className="welcome-banner">
          <div className="welcome-art" aria-hidden="true">
            <div className="art-card art-back">
              <span />
              <span />
            </div>
            <div className="art-card art-front">
              <span className="art-check">
                <Check size={15} />
              </span>
              <div>
                <span />
                <span />
              </div>
            </div>
            <span className="art-spark">
              <Sparkles size={17} />
            </span>
          </div>
          <div className="welcome-copy">
            <span className="small-label">A fresh workspace</span>
            <h2>
              Less keeping track.
              <br />
              More moving forward.
            </h2>
            <p>
              Name your project, bring your notes, and turn your next
              conversation into clear next steps. Nothing is pre-filled.
            </p>
          </div>
          <div className="welcome-actions">
            <Button onClick={onConfigure}>
              Set up your workspace
              <ArrowRight size={15} />
            </Button>
            <Button variant="ghost" onClick={() => navigate("notes")}>
              <MessageSquareText size={15} />
              Explore meeting notes
            </Button>
          </div>
        </section>
      )}
      <div className="metrics-grid">
        {[
          {
            label: "Tasks completed",
            value: state.tasks.length
              ? `${complete}/${state.tasks.length}`
              : "—",
            note: "Small steps, visible progress",
            icon: CheckCheck,
            tone: "purple",
          },
          {
            label: "In progress",
            value: state.tasks.length ? inProgress : "—",
            note: "Work currently marked as building",
            icon: Clock3,
            tone: "blue",
          },
          {
            label: "Needs attention",
            value: state.tasks.length ? blocked.length : "—",
            note: "Tasks waiting on a dependency",
            icon: Flag,
            tone: "amber",
          },
          {
            label: "Team members",
            value: state.team.members.length,
            note: "One shared view of the work",
            icon: Users,
            tone: "mint",
          },
        ].map((metric) => (
          <section className="metric-card" key={metric.label}>
            <div className="metric-label">
              <span>{metric.label}</span>
              <span className={`metric-icon ${metric.tone}`}>
                <metric.icon size={17} />
              </span>
            </div>
            <div className="metric-number">{metric.value}</div>
            <p>{metric.note}</p>
          </section>
        ))}
      </div>
      <div className="overview-columns">
        <div className="overview-main">
          <section className="workspace-card journey-card">
            <SectionHeading
              title="The path to your demo"
              action="View details"
              onAction={() => navigate("settings")}
            />
            <div className="journey">
              {state.pipeline.stages.map((stage, index) => (
                <div
                  key={stage.id}
                  className={cn(
                    "journey-step",
                    stage.status === "done" && "step-done",
                    stage.id === current?.id && "step-current",
                  )}
                >
                  <span className="step-number">
                    {stage.status === "done" ? <Check size={13} /> : index + 1}
                  </span>
                  <span>{stage.name}</span>
                </div>
              ))}
            </div>
            <div className="journey-footer">
              <div>
                <span className="small-label">
                  {current ? "Current focus" : "Start with the problem"}
                </span>
                <p>
                  {current?.exit_condition ||
                    "Configure your event, capture the challenge, and agree on the outcome."}
                </p>
              </div>
              {current ? (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setConfirmStage(true)}
                  disabled={current.status === "done"}
                >
                  {current.status === "pending"
                    ? "Start stage"
                    : "Complete stage"}
                  <ArrowRight size={14} />
                </Button>
              ) : (
                <Button variant="outline" size="sm" onClick={onConfigure}>
                  Get started
                  <ArrowRight size={14} />
                </Button>
              )}
            </div>
          </section>
          <section className="workspace-card">
            <SectionHeading
              title="Up next"
              count={
                state.tasks.filter((t) => t.status !== "demo-ready").length
              }
              action="Open board"
              onAction={() => navigate("tasks")}
            />
            {!state.tasks.some((t) => t.status !== "demo-ready") ? (
              <EmptyState
                compact
                icon={CheckCheck}
                title={
                  state.tasks.length
                    ? "A clear board. Nice work."
                    : "Make the next step a clear one"
                }
                description={
                  state.tasks.length
                    ? "Run the demo smoke before calling the whole project ready."
                    : "Add your first task and give everyone a place to start."
                }
                action={
                  <Button variant="outline" size="sm" onClick={onNewTask}>
                    <Plus size={14} />
                    Add a task
                  </Button>
                }
              />
            ) : (
              <div className="next-tasks">
                {state.tasks
                  .filter((t) => t.status !== "demo-ready")
                  .slice(0, 5)
                  .map((task) => (
                    <button
                      className="next-task"
                      key={task.id}
                      onClick={() => onEditTask(task)}
                    >
                      <CircleDashed size={17} />
                      <div>
                        <strong>{task.title}</strong>
                        <span>
                          {task.mvp || "No milestone"}
                          {blockers(task, state.tasks).length > 0
                            ? " · Waiting on a dependency"
                            : ""}
                        </span>
                      </div>
                      <StatusBadge status={task.status} />
                      {task.owner && <Avatar name={task.owner} small />}
                      <ChevronRight size={14} />
                    </button>
                  ))}
              </div>
            )}
          </section>
          <section className="workspace-card">
            <SectionHeading
              title="Keep the important things close"
              action="All documents"
              onAction={() => navigate("documents")}
            />
            <div className="document-shortcuts">
              {(["challenge", "demo_script", "contract"] as const).map(
                (key, index) => (
                  <button key={key} onClick={() => navigate("documents")}>
                    <span
                      className={cn(
                        "document-icon",
                        ["lavender", "peach", "mint"][index],
                      )}
                    >
                      <FileText size={22} strokeWidth={1.6} />
                    </span>
                    <strong>{docLabels[key]}</strong>
                    <span>
                      {docs?.[key]?.not_written_yet
                        ? "Ready for your first words"
                        : "Open document"}
                    </span>
                    <ArrowUpRight size={14} />
                  </button>
                ),
              )}
            </div>
          </section>
          <section className="workspace-card">
            <SectionHeading title="Recorded changes" />
            <div className="activity-list">
              {state.commits.slice(0, 4).map((commit) => (
                <div className="activity-item" key={commit.sha}>
                  <Avatar name={commit.author} small />
                  <div>
                    <p>
                      <strong>{commit.author}</strong>
                      <span>{commit.message}</span>
                    </p>
                    <small>
                      {relativeTime(commit.timestamp)} ·{" "}
                      {commit.sha.slice(0, 7)}
                    </small>
                  </div>
                </div>
              ))}
              {!state.commits.length && (
                <EmptyState
                  compact
                  icon={GitBranch}
                  title="The story starts with your first commit"
                  description="Recorded changes will appear here as your team builds."
                />
              )}
            </div>
            <p className="section-footnote">
              Local Git history, not live teammate presence.
            </p>
          </section>
        </div>
        <aside className="overview-aside">
          <section className="deadline-card">
            <div className="deadline-label">
              <Clock3 size={16} />
              <span>Time to submit</span>
            </div>
            {timeUnits ? (
              <div className="time-units">
                {timeUnits.map((value, i) => (
                  <div key={i}>
                    <strong>{String(value).padStart(2, "0")}</strong>
                    <span>{["days", "hours", "minutes"][i]}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="no-deadline">
                <CalendarDays size={24} />
                <h3>
                  {remaining !== null && remaining < 0
                    ? "Submission target passed"
                    : "Make room for the finish"}
                </h3>
                <p>
                  {remaining !== null && remaining < 0
                    ? "Review the event dates or confirm your submission."
                    : "Set a deadline to see your team's countdown here."}
                </p>
              </div>
            )}
            <div className="deadline-details">
              <span>Early submit target</span>
              <strong>
                {formatDate(state.pipeline.countdown.submit_target, true)}
              </strong>
            </div>
            <div className="deadline-details">
              <span>Official deadline</span>
              <strong>
                {formatDate(state.pipeline.countdown.real_deadline, true)}
              </strong>
            </div>
            <button className="deadline-edit" onClick={onConfigure}>
              Edit event details
              <ArrowUpRight size={13} />
            </button>
          </section>
          <section className="workspace-card progress-card">
            <SectionHeading title="Project progress" />
            <div className="progress-ring">
              <svg viewBox="0 0 120 120" aria-hidden="true">
                <circle cx="60" cy="60" r="50" className="ring-track" />
                <circle
                  cx="60"
                  cy="60"
                  r="50"
                  className="ring-fill"
                  strokeDasharray={`${percent * Math.PI} 314.16`}
                />
              </svg>
              <div>
                <strong>{state.tasks.length ? `${percent}%` : "—"}</strong>
                <span>tasks complete</span>
              </div>
            </div>
            <div className={cn("readiness", state.smoke_current && "verified")}>
              <ShieldCheck size={14} />
              {state.smoke_current
                ? "Current demo smoke passed"
                : "Integrated demo not verified yet"}
            </div>
            {milestones.length > 0 && (
              <div className="milestone-progress">
                {milestones.slice(0, 4).map((mvp) => {
                  const tasks = state.tasks.filter((t) => t.mvp === mvp)
                  const done = tasks.filter(
                    (t) => t.status === "demo-ready",
                  ).length
                  return (
                    <div key={mvp}>
                      <div>
                        <span>{mvp}</span>
                        <span>
                          {done}/{tasks.length}
                        </span>
                      </div>
                      <Progress value={(done / tasks.length) * 100} />
                    </div>
                  )
                })}
              </div>
            )}
          </section>
          <section className="workspace-card">
            <SectionHeading
              title="Your team"
              action="Manage"
              onAction={() => navigate("settings")}
            />
            <div className="team-list">
              {state.team.members.map((member) => {
                const count = state.tasks.filter(
                  (t) => t.owner === member.name && t.status !== "demo-ready",
                ).length
                return (
                  <div key={member.name}>
                    <Avatar name={member.name} />
                    <div>
                      <strong>{member.name}</strong>
                      <span>
                        {count
                          ? `${count} open ${count === 1 ? "task" : "tasks"}`
                          : "No assigned work"}
                      </span>
                    </div>
                    <span className="member-count">{count || "—"}</span>
                  </div>
                )
              })}
            </div>
          </section>
          <button className="capture-card" onClick={() => navigate("notes")}>
            <span>
              <Sparkles size={19} />
            </span>
            <h3>
              Good conversations.
              <br />
              Clear next steps.
            </h3>
            <p>
              Bring a transcript. Keep decisions, ideas and action items
              together.
            </p>
            <strong>
              Capture meeting notes
              <ArrowRight size={14} />
            </strong>
          </button>
        </aside>
      </div>
      <Dialog open={confirmStage} onOpenChange={setConfirmStage}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {current?.status === "pending"
                ? "Start this stage?"
                : "Ready for the next stage?"}
            </DialogTitle>
            <DialogDescription>
              {current?.name}.{" "}
              {current?.status !== "pending" &&
                "Confirm that the team has met the exit condition before continuing."}
            </DialogDescription>
          </DialogHeader>
          <div className="stage-condition">
            <Flag size={17} />
            <p>{current?.exit_condition}</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmStage(false)}>
              Not yet
            </Button>
            <Button onClick={advance} disabled={saving}>
              {current?.status === "pending"
                ? "Start stage"
                : "Confirm and continue"}
              <ArrowRight size={14} />
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
