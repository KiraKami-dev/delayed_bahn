export type TaskStatus = "backlog" | "building" | "integrating" | "demo-ready"
export type IdeaStatus = "raised" | "exploring" | "adopted" | "discarded"
export type Page =
  | "overview"
  | "tasks"
  | "ideas"
  | "decisions"
  | "documents"
  | "research"
  | "notes"
  | "settings"
  | "guide"
export interface Member {
  name: string
  harness: string
  background?: string
}
export interface Task {
  id: string
  title: string
  status: TaskStatus
  owner: string | null
  sub_owners: string[]
  depends_on: string[]
  target_time: string | null
  resolved_target?: string | null
  mvp: string | null
  stage: string | null
  notes: string
}
export interface Idea {
  id: string
  timestamp: string
  idea: string
  who: string
  status: IdeaStatus
}
export interface Decision {
  id: string
  timestamp: string
  decision: string
  who: string
  reason: string
  supersedes?: string | null
  superseded_by?: string | null
  promotes_idea?: string | null
}
export interface Research {
  id: string
  topic: string
  summary: string
  logged_by: string
  logged_at: string
  viability: "untested" | "feasible" | "not-viable" | "implemented"
  viability_reasoning: string
  override: boolean
  evidence?: string
  confirmed_by?: string
  linked_idea?: string | null
  linked_mvp?: string | null
  assessment?: { viability: string; viability_reasoning: string }
}
export interface Stage {
  id: string
  name: string
  status: "pending" | "in_progress" | "done"
  exit_condition: string
  owner: string
  resolved_start: string | null
  resolved_end: string | null
  completed_at?: string | null
  schedule_note?: string
}
export interface EventConfig {
  event_name?: string
  venue?: string
  build_starts?: string
  submission_deadline?: string
  submit_target_offset_hours?: number
  tracks?: string[]
  partners?: string[]
  tracks_known_in_advance?: boolean
  submission_format?: string
  pitch_length_minutes?: number | null
  coordination_branch?: string
  coordination_maintainer?: string
  [key: string]: unknown
}
export interface Meeting {
  id: string
  title: string
  excerpt: string
  created_at: string
}
export interface BoardState {
  revision: string
  csrf_token: string
  workspace_id: string
  event_is_blank: boolean
  example_mode: boolean
  event: EventConfig
  team: { team_name?: string; members: Member[] }
  tasks: Task[]
  ideas: Idea[]
  decisions: Decision[]
  research: Research[]
  owners_raw: string
  meetings: Meeting[]
  ai: {
    configured: boolean
    source: "environment" | "local" | "none"
    available: boolean
  }
  pipeline: {
    current_stage: string | null
    stages: Stage[]
    warning?: string | null
    countdown: {
      submit_target: string | null
      real_deadline: string | null
      buffer_starts?: string | null
      seconds_to_submit_target: number | null
    }
  }
  freshness: {
    head: string | null
    branch: string | null
    upstream: string | null
    ahead: number | null
    behind: number | null
    local_changes: string[]
    coordination_branch: string
    coordination_maintainer: string
    remote_check?: { last_success_at?: string; ok?: boolean }
  }
  commits: {
    sha: string
    timestamp: string
    author: string
    message: string
    files: string[]
  }[]
  contract_drift: boolean | null
  smoke_current: boolean
  smoke_last: { ok: boolean; timestamp: string; detail: string } | null
  snapshot_tags: string[]
}
export type DocKey =
  | "challenge"
  | "demo_script"
  | "not_building"
  | "contract"
  | "architecture"
  | "partner_notes"
export interface Document {
  content: string
  not_written_yet: boolean
  editable: boolean
  locked_reason?: string
}
export type Documents = Record<DocKey, Document> & { revision: string }
export interface Extraction {
  decisions: { text: string; who?: string }[]
  ideas: { text: string; who?: string }[]
  tasks: {
    title: string
    owner?: string | null
    sub_owners?: string[]
    target_time?: string | null
    mvp?: string | null
    stage?: string | null
  }[]
  flagged: string[]
}
export interface NotesPreview extends Extraction {
  preview_id?: string
  meeting_file: string
  warning?: string
  revision: string
}
export interface MutationResult {
  ok: boolean
  revision: string
  warning?: string
  error?: string
  [key: string]: unknown
}
