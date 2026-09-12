import type { Task, TaskStatus } from "./types"

export const taskStatuses: TaskStatus[] = [
  "backlog",
  "building",
  "integrating",
  "demo-ready",
]
export const statusLabels: Record<TaskStatus, string> = {
  backlog: "To do",
  building: "In progress",
  integrating: "In review",
  "demo-ready": "Done",
}
export const docLabels = {
  challenge: "Project brief",
  demo_script: "Demo script",
  not_building: "Out of scope",
  contract: "Technical contract",
  architecture: "Architecture",
  partner_notes: "Partner notes",
} as const

export function initials(name: string) {
  return (
    name
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((s) => s[0])
      .join("")
      .toUpperCase() || "?"
  )
}
export function colorIndex(name: string) {
  return [...name].reduce((sum, letter) => sum + letter.charCodeAt(0), 0) % 6
}
export function formatDate(value: string | null | undefined, time = false) {
  if (!value || Number.isNaN(Date.parse(value))) return "Not scheduled"
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    ...(time ? ({ hour: "numeric", minute: "2-digit" } as const) : {}),
  }).format(new Date(value))
}
export function relativeTime(value: string) {
  const minutes = Math.round((Date.now() - Date.parse(value)) / 60000)
  if (!Number.isFinite(minutes)) return ""
  if (minutes < -1) return formatDate(value, true)
  if (minutes < 1) return "Just now"
  if (minutes < 60) return `${minutes}m ago`
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h ago`
  return formatDate(value)
}
export function blockers(task: Task, tasks: Task[]) {
  return (task.depends_on || []).filter(
    (id) => tasks.find((t) => t.id === id)?.status !== "demo-ready",
  )
}
export function overdue(task: Task) {
  return (
    task.status !== "demo-ready" &&
    Boolean(
      task.resolved_target && Date.parse(task.resolved_target) < Date.now(),
    )
  )
}
export function splitNames(value: string) {
  return value
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean)
}
export function localDateInput(value?: string) {
  if (!value || Number.isNaN(Date.parse(value))) return ""
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16)
}
