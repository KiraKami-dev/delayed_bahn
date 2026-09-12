import { useState, type FormEvent } from "react"
import {
  AlertCircle,
  ArrowRight,
  CalendarDays,
  CheckCheck,
  CircleDashed,
  GitBranch,
  GripVertical,
  LayoutGrid,
  List,
  MessageSquare,
  Plus,
  Search,
  Trash2,
  Users,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Avatar,
  EmptyState,
  Field,
  FormError,
  PageHeading,
  Pick,
  SaveButton,
  StatusBadge,
} from "./shared"
import {
  blockers,
  formatDate,
  overdue,
  statusLabels,
  taskStatuses,
} from "@/lib/format"
import { useWorkspace } from "@/lib/workspace"
import { cn } from "@/lib/utils"
import type { Task, TaskStatus } from "@/lib/types"

export function TaskBoard({
  onEdit,
  onNew,
}: {
  onEdit: (task: Task) => void
  onNew: (status?: TaskStatus) => void
}) {
  const { state, mutate, saving } = useWorkspace()
  const [query, setQuery] = useState("")
  const [owner, setOwner] = useState("all")
  const [mode, setMode] = useState("board")
  const [hover, setHover] = useState<TaskStatus | null>(null)
  if (!state) return null
  const tasks = state.tasks.filter(
    (task) =>
      `${task.title} ${task.notes} ${task.mvp}`
        .toLowerCase()
        .includes(query.toLowerCase()) &&
      (owner === "all" ||
        task.owner === owner ||
        (owner === "unassigned" && !task.owner)),
  )
  async function move(id: string, status: TaskStatus) {
    if (saving || !state) return
    try {
      await mutate("/api/tasks", {
        tasks: state.tasks.map((t) => (t.id === id ? { ...t, status } : t)),
      })
    } catch {
      return
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="Make progress, together"
        title="Task board"
        description="One place for priorities, ownership, and the next step."
      >
        <Button onClick={() => onNew()}>
          <Plus />
          New task
        </Button>
      </PageHeading>
      <div className="board-toolbar">
        <Tabs value={mode} onValueChange={setMode}>
          <TabsList className="bg-muted/80">
            <TabsTrigger value="board">
              <LayoutGrid size={14} />
              Board
            </TabsTrigger>
            <TabsTrigger value="list">
              <List size={14} />
              List
            </TabsTrigger>
          </TabsList>
        </Tabs>
        <div className="toolbar-right">
          <div className="search-field">
            <Search size={15} />
            <Input
              aria-label="Search tasks"
              placeholder="Search tasks…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="owner-filter">
            <Pick
              label="Filter by owner"
              value={owner}
              onChange={setOwner}
              options={[
                { value: "all", label: "Everyone" },
                { value: "unassigned", label: "Unassigned" },
                ...state.team.members.map((m) => ({
                  value: m.name,
                  label: m.name,
                })),
              ]}
            />
          </div>
        </div>
      </div>
      {mode === "board" ? (
        <div className="kanban-board">
          {taskStatuses.map((status) => {
            const group = tasks.filter((t) => t.status === status)
            return (
              <section
                key={status}
                className={cn(
                  "kanban-column",
                  hover === status && "drop-active",
                )}
                onDragOver={(e) => {
                  e.preventDefault()
                  setHover(status)
                }}
                onDragLeave={(e) => {
                  if (
                    !(e.relatedTarget instanceof Node) ||
                    !e.currentTarget.contains(e.relatedTarget)
                  )
                    setHover(null)
                }}
                onDrop={(e) => {
                  e.preventDefault()
                  setHover(null)
                  const id = e.dataTransfer.getData("text/hackos-task")
                  if (state.tasks.some((t) => t.id === id))
                    void move(id, status)
                }}
                aria-label={`${statusLabels[status]} column`}
              >
                <div className="column-heading">
                  <span className={cn("column-dot", `dot-${status}`)} />
                  <h2>{statusLabels[status]}</h2>
                  <span className="column-count">{group.length}</span>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Add task to ${statusLabels[status]}`}
                    onClick={() => onNew(status)}
                  >
                    <Plus size={15} />
                  </Button>
                </div>
                <div className="column-cards">
                  {group.map((task) => {
                    const blocked = blockers(task, state.tasks)
                    return (
                      <article
                        key={task.id}
                        className={cn(
                          "kanban-card",
                          overdue(task) && "card-overdue",
                        )}
                        draggable={!saving}
                        onDragStart={(e) => {
                          e.dataTransfer.setData("text/hackos-task", task.id)
                          e.dataTransfer.effectAllowed = "move"
                        }}
                      >
                        <button
                          className="card-open"
                          onClick={() => onEdit(task)}
                          aria-label={`Edit ${task.title}`}
                        >
                          <div className="card-topline">
                            {task.mvp ? (
                              <span className="milestone-tag">{task.mvp}</span>
                            ) : (
                              <span className="task-reference">
                                {task.id.slice(0, 8).toUpperCase()}
                              </span>
                            )}
                            <GripVertical size={14} className="drag-handle" />
                          </div>
                          <h3>{task.title}</h3>
                          {task.notes && (
                            <p className="task-excerpt">{task.notes}</p>
                          )}
                          {blocked.length > 0 && (
                            <div className="task-warning">
                              <GitBranch size={12} />
                              Waiting on {blocked.length}{" "}
                              {blocked.length === 1 ? "task" : "tasks"}
                            </div>
                          )}
                          <div className="card-bottom">
                            <div
                              className={cn(
                                "task-date",
                                overdue(task) && "text-destructive",
                              )}
                            >
                              <CalendarDays size={12} />
                              {task.resolved_target
                                ? formatDate(task.resolved_target)
                                : task.target_time || "No target yet"}
                            </div>
                            {task.owner ? (
                              <Avatar name={task.owner} small />
                            ) : (
                              <span
                                className="unassigned-avatar"
                                title="Unassigned"
                              >
                                <Users size={12} />
                              </span>
                            )}
                          </div>
                        </button>
                        {task.sub_owners?.length > 0 && (
                          <div className="task-helpers">
                            Helping: {task.sub_owners.join(", ")}
                          </div>
                        )}
                      </article>
                    )
                  })}
                  {!group.length && (
                    <div className="column-empty">
                      <CircleDashed size={22} />
                      <p>
                        {status === "demo-ready"
                          ? "Your wins will live here"
                          : "Nothing here yet"}
                      </p>
                    </div>
                  )}
                </div>
                <button className="column-add" onClick={() => onNew(status)}>
                  <Plus size={14} />
                  Add task
                </button>
              </section>
            )
          })}
        </div>
      ) : (
        <div className="data-table-wrap">
          {!tasks.length ? (
            <EmptyState
              icon={CheckCheck}
              title="A fresh start"
              description="Add a task, give it an owner, and make the next step clear."
              action={
                <Button onClick={() => onNew()}>
                  <Plus />
                  Create a task
                </Button>
              }
            />
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Status</th>
                  <th>Owner</th>
                  <th>Target</th>
                  <th>Milestone</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((task) => (
                  <tr key={task.id}>
                    <td>
                      <button
                        className="table-title"
                        onClick={() => onEdit(task)}
                      >
                        {task.title}
                        <ArrowRight size={14} />
                      </button>
                      {blockers(task, state.tasks).length > 0 && (
                        <span className="task-warning">
                          Blocked by a dependency
                        </span>
                      )}
                    </td>
                    <td>
                      <StatusBadge status={task.status} />
                    </td>
                    <td>
                      {task.owner ? (
                        <span className="inline-person">
                          <Avatar name={task.owner} small />
                          {task.owner}
                        </span>
                      ) : (
                        <span className="muted">Unassigned</span>
                      )}
                    </td>
                    <td className={cn(overdue(task) && "text-destructive")}>
                      {task.resolved_target
                        ? formatDate(task.resolved_target)
                        : "—"}
                    </td>
                    <td>
                      {task.mvp ? (
                        <Badge variant="secondary">{task.mvp}</Badge>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
      <div className="board-footnote">
        <GripVertical size={13} />
        Drag a card to move it, or open it to edit status and details. Done
        tasks still need an end-to-end demo check.
      </div>
    </>
  )
}

export function TaskEditor({
  task,
  initialStatus = "backlog",
  onClose,
}: {
  task?: Task
  initialStatus?: TaskStatus
  onClose: () => void
}) {
  const { state, mutate, saving } = useWorkspace()
  const [draft, setDraft] = useState<Task>(() =>
    task
      ? { ...task }
      : {
          id: `t-${crypto.randomUUID().replaceAll("-", "")}`,
          title: "",
          owner: null,
          sub_owners: [],
          depends_on: [],
          target_time: null,
          mvp: null,
          notes: "",
          stage: state?.pipeline.current_stage || null,
          status: initialStatus,
        },
  )
  const [revision, setRevision] = useState(state?.revision)
  const [error, setError] = useState("")
  const [confirmDelete, setConfirmDelete] = useState(false)
  if (!state) return null
  const update = <K extends keyof Task>(key: K, value: Task[K]) =>
    setDraft((d) => ({ ...d, [key]: value }))
  const latest = state.tasks.find((t) => t.id === draft.id)
  async function save(event: FormEvent) {
    event.preventDefault()
    if (!state) return
    if (task && !latest) {
      setError(
        "This task was removed by another update. Create a new task instead.",
      )
      return
    }
    try {
      const tasks = task
        ? state.tasks.map((t) => (t.id === draft.id ? draft : t))
        : [...state.tasks, draft]
      await mutate("/api/tasks", { tasks }, { revision })
      onClose()
    } catch (e) {
      setError((e as Error).message)
    }
  }
  async function remove() {
    if (!state) return
    try {
      await mutate(
        "/api/tasks",
        { tasks: state.tasks.filter((t) => t.id !== draft.id) },
        { revision },
      )
      onClose()
    } catch (e) {
      setConfirmDelete(false)
      setError((e as Error).message)
    }
  }
  return (
    <>
      <Sheet
        open
        onOpenChange={(open) => {
          if (!open && !saving) onClose()
        }}
      >
        <SheetContent className="editor-sheet w-full sm:max-w-[540px]">
          <SheetHeader className="editor-header">
            <div className="dialog-icon">
              <CheckCheck size={20} />
            </div>
            <SheetTitle>{task ? "Task details" : "Create a task"}</SheetTitle>
            <SheetDescription>
              {task
                ? "Keep the next step and its owner clear."
                : "Small, clear tasks make a big difference."}
            </SheetDescription>
          </SheetHeader>
          <form onSubmit={save} className="editor-form">
            <div className="editor-fields">
              <Field label="What needs to happen?">
                <Input
                  autoFocus
                  aria-label="Task title"
                  placeholder="Give this task a clear title"
                  value={draft.title}
                  onChange={(e) => update("title", e.target.value)}
                  required
                  maxLength={220}
                />
              </Field>
              <div className="form-grid">
                <Field label="Status">
                  <Pick
                    label="Task status"
                    value={draft.status}
                    onChange={(v) => update("status", v as TaskStatus)}
                    options={taskStatuses.map((s) => ({
                      value: s,
                      label: statusLabels[s],
                    }))}
                  />
                </Field>
                <Field label="Owner">
                  <Pick
                    label="Task owner"
                    value={draft.owner || ""}
                    onChange={(v) => update("owner", v || null)}
                    options={[
                      { value: "", label: "Unassigned" },
                      ...state.team.members.map((m) => ({
                        value: m.name,
                        label: m.name,
                      })),
                    ]}
                  />
                </Field>
              </div>
              <div className="form-grid">
                <Field
                  label="Milestone"
                  hint="Group related tasks, such as MVP 1."
                >
                  <Input
                    aria-label="Milestone"
                    placeholder="e.g. MVP 1"
                    value={draft.mvp || ""}
                    onChange={(e) => update("mvp", e.target.value || null)}
                  />
                </Field>
                <Field label="Target" hint="Percentage of the planning window.">
                  <Pick
                    label="Task target"
                    value={draft.target_time || ""}
                    onChange={(v) => update("target_time", v || null)}
                    options={[
                      { value: "", label: "No target" },
                      ...Array.from(
                        new Set([
                          ...(draft.target_time ? [draft.target_time] : []),
                          "T+15%",
                          "T+25%",
                          "T+40%",
                          "T+55%",
                          "T+65%",
                          "T+90%",
                        ]),
                      ).map((v) => ({ value: v, label: v })),
                    ]}
                  />
                </Field>
              </div>
              <Field label="Details">
                <Textarea
                  aria-label="Task details"
                  placeholder="What does done look like? Add context, links, or handoff notes."
                  rows={5}
                  value={draft.notes}
                  onChange={(e) => update("notes", e.target.value)}
                />
              </Field>
              <Field label="Helping with this">
                <div className="people-picker">
                  {state.team.members.map((member) => (
                    <label
                      className={cn(
                        "person-option",
                        draft.sub_owners.includes(member.name) && "selected",
                      )}
                      key={member.name}
                    >
                      <Checkbox
                        checked={draft.sub_owners.includes(member.name)}
                        onCheckedChange={(checked) =>
                          update(
                            "sub_owners",
                            checked
                              ? [...draft.sub_owners, member.name]
                              : draft.sub_owners.filter(
                                  (n) => n !== member.name,
                                ),
                          )
                        }
                      />
                      <Avatar name={member.name} small />
                      {member.name}
                    </label>
                  ))}
                </div>
              </Field>
              <Field
                label="Depends on"
                hint="This task is blocked until its dependencies are done."
              >
                {state.tasks.filter((t) => t.id !== draft.id).length ? (
                  <div className="dependency-picker">
                    {state.tasks
                      .filter((t) => t.id !== draft.id)
                      .map((t) => (
                        <label key={t.id}>
                          <Checkbox
                            checked={draft.depends_on.includes(t.id)}
                            onCheckedChange={(checked) =>
                              update(
                                "depends_on",
                                checked
                                  ? [...draft.depends_on, t.id]
                                  : draft.depends_on.filter(
                                      (id) => id !== t.id,
                                    ),
                              )
                            }
                          />
                          <span>{t.title}</span>
                          <StatusBadge status={t.status} />
                        </label>
                      ))}
                  </div>
                ) : (
                  <p className="field-hint">
                    Add another task to create a dependency.
                  </p>
                )}
              </Field>
              <FormError
                message={error}
                current={latest}
                onReview={
                  error.includes("changed")
                    ? () => {
                        setRevision(state.revision)
                        setError("")
                      }
                    : undefined
                }
              />
            </div>
            <div className="editor-footer">
              {task && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="text-destructive"
                  aria-label="Delete task"
                  onClick={() => setConfirmDelete(true)}
                  disabled={saving}
                >
                  <Trash2 size={16} />
                </Button>
              )}
              <div className="ml-auto flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={onClose}
                  disabled={saving}
                >
                  Cancel
                </Button>
                <SaveButton saving={saving}>
                  {task ? "Save task" : "Create task"}
                </SaveButton>
              </div>
            </div>
          </form>
        </SheetContent>
      </Sheet>
      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this task?</DialogTitle>
            <DialogDescription>
              “{draft.title}” will be removed. Tasks depending on it will show a
              missing dependency. This does not delete product code.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(false)}>
              Keep task
            </Button>
            <Button variant="destructive" onClick={remove} disabled={saving}>
              Delete task
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
