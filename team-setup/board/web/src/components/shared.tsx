import { useId, type ReactNode } from "react"
import {
  AlertCircle,
  ArrowUpRight,
  Check,
  Circle,
  CircleDashed,
  Clock3,
  Loader2,
  type LucideIcon,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { colorIndex, initials, statusLabels } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { TaskStatus } from "@/lib/types"

export function Avatar({
  name,
  small = false,
}: {
  name: string
  small?: boolean
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={cn(
            "person-avatar",
            `avatar-${colorIndex(name)}`,
            small && "person-avatar-sm",
          )}
          aria-label={name}
        >
          {initials(name)}
        </span>
      </TooltipTrigger>
      <TooltipContent>{name}</TooltipContent>
    </Tooltip>
  )
}

export function StatusBadge({ status }: { status: TaskStatus }) {
  const Icon = {
    backlog: CircleDashed,
    building: Clock3,
    integrating: Circle,
    "demo-ready": Check,
  }[status]
  return (
    <span className={cn("status-badge", `status-${status}`)}>
      <Icon size={12} />
      {statusLabels[status]}
    </span>
  )
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: ReactNode
}) {
  const id = useId()
  return (
    <div className="form-field">
      <Label id={id}>{label}</Label>
      <div>{children}</div>
      {hint && <p className="field-hint">{hint}</p>}
    </div>
  )
}

export function Pick({
  label,
  value,
  onChange,
  options,
  placeholder = "Select an option",
  disabled = false,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
  placeholder?: string
  disabled?: boolean
}) {
  return (
    <Select
      value={value || "__none"}
      onValueChange={(v) => onChange(v === "__none" ? "" : v)}
      disabled={disabled}
    >
      <SelectTrigger className="w-full bg-white" aria-label={label}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent position="popper">
        {options.map((option) => (
          <SelectItem
            key={option.value || "__none"}
            value={option.value || "__none"}
          >
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  compact = false,
}: {
  icon: LucideIcon
  title: string
  description: string
  action?: ReactNode
  compact?: boolean
}) {
  return (
    <div className={cn("empty-state-new", compact && "empty-compact")}>
      <span className="empty-symbol">
        <Icon size={23} strokeWidth={1.6} />
      </span>
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  )
}

export function PageHeading({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow?: string
  title: string
  description: string
  children?: ReactNode
}) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="page-actions">{children}</div>
    </div>
  )
}

export function SectionHeading({
  title,
  count,
  action,
  onAction,
}: {
  title: string
  count?: number
  action?: string
  onAction?: () => void
}) {
  return (
    <div className="section-heading">
      <h2>
        {title}
        {count !== undefined && <Badge variant="secondary">{count}</Badge>}
      </h2>
      {action && (
        <Button variant="ghost" size="sm" onClick={onAction}>
          {action}
          <ArrowUpRight size={14} />
        </Button>
      )}
    </div>
  )
}

export function SaveButton({
  saving,
  children = "Save changes",
}: {
  saving: boolean
  children?: ReactNode
}) {
  return (
    <Button type="submit" disabled={saving}>
      {saving && <Loader2 className="animate-spin" size={15} />}
      {saving ? "Saving…" : children}
    </Button>
  )
}

export function FormError({
  message,
  current,
  onReview,
}: {
  message: string
  current?: unknown
  onReview?: () => void
}) {
  if (!message) return null
  return (
    <div className="form-error" role="alert">
      <AlertCircle size={16} />
      <div>
        <p>{message}</p>
        <p className="mt-1 text-xs">Your draft is still here.</p>
        {current !== undefined && (
          <details className="mt-2">
            <summary>Review the latest saved version</summary>
            <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-xs">
              {typeof current === "string"
                ? current
                : JSON.stringify(current, null, 2)}
            </pre>
          </details>
        )}
        {onReview && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-3"
            onClick={onReview}
          >
            I reviewed it — use the latest revision
          </Button>
        )}
      </div>
    </div>
  )
}
