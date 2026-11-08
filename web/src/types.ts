export type Domain = 'structural_codes' | 'site_safety' | 'tender_docs'
export type Family = 'clause_query' | 'safety_checklist' | 'unit_calc' | 'tender_extract' | 'incident_triage'
export type Status =
  | 'proposed' | 'gating' | 'adopted' | 'rejected' | 'quarantined' | 'inconclusive' | 'rolled_back' | 'expired'
export type Tier = 'low' | 'medium' | 'high'

export interface AuditRow { entry_id: number; event: string; actor: string; details_json: Record<string, unknown>; ts: string }

export interface Overview {
  config_version: number
  patch_counts: Partial<Record<Status, number>>
  kb_mode: 'synthetic' | 'real'
  kb_entries: number
  backend: string
  tasks: number
  feedback: number
  users: number
  rejections_remembered: number
  pending_approvals: number
  avg_gate_seconds: number | null
  replays: { replays: number; cache_hits: number; tokens_in: number; tokens_out: number; seconds: number }
  demo_mode: boolean
  worker: boolean
  recent_audit: AuditRow[]
}

export interface Op { op: string; path: string; value: unknown }
export interface Claim { subject: string | null; attribute: string | null; value: number | string | null; rule_text: string | null; text: string }

export interface PatchRow {
  patch_id: string
  type: 'memory_note' | 'instruction_rule' | 'tool_policy' | 'workflow_step'
  ops_json: Op[]
  claim_json: Claim | null
  warrant_json: { kind: string; ref: string | null; verified: boolean } | null
  witness_json: { family: Family; input: string; checker: Record<string, unknown> } | null
  scope_json: { task_types: string[]; conditions: Record<string, unknown> } | null
  risk_tier: Tier
  status: Status
  proposer: string | null
  created_ts: string
  claim_text: string
  users: string[]
}

export interface GateRun {
  run_id: number
  patch_id: string
  lock: string
  result: string
  metrics_json: Record<string, any>
  reasons_json: string[]
  ts: string
}
export interface PatchDetail { contract: Record<string, any>; status: Status; gate_runs: GateRun[] }

export interface Explain {
  patch_id: string
  status: Status
  headline: string
  lines: string[]
  decided_by: string | null
  claim: string
  locks: { lock: string; title: string; result: string; reasons: string[] }[]
}
export interface Passport {
  patch_id: string
  claim: string
  evidence: string
  rule: string
  method: string
  generated_by: string
  result: string
  next_action: string
  status: Status
  risk_tier: Tier
  note: string
}
export interface RollbackNote { version: number; restored_from: number; reason: string; actor: string; undone: string[]; headline: string; lines: string[] }
export interface VersionRow {
  version: number
  parent: number | null
  config_hash: string
  created_from_patch: string | null
  stage: string
  ts: string
  claim_text: string | null
  rollback_note: RollbackNote | null
}
export interface DiffItem { path: string; change: 'added' | 'removed' | 'changed'; before: unknown; after: unknown }
export interface TrustRow { user_id: string; trust: Record<Domain, number> }
export interface KBEntry {
  id: string; subject: string; attribute: string; value: number | string; unit: string | null; domain: Domain
  source_doc: string; section: string; page: number | null; quote: string | null; verified: boolean; verified_by: string | null
}
export interface TaskResp {
  task_id: string
  answer: string
  trace: { family: string; memory_ids: string[]; rule_ids: string[]; tool_calls: { tool: string; args: unknown[]; result: unknown }[]; workflow_steps: string[] }
  config_version: number
}
export interface TaskRow { task_id: string; user_id: string; family: Family; input: string; answer: string; config_version: number; latency_ms: number; ts: string }
export interface QueueItem { item_id: number; patch_id: string; reason: string; status: string; reviewer: string | null; ts: string }
export interface GateOutcome { patch_id: string; outcome: string; deciding_lock: string; reasons: string[]; metrics: Record<string, any>; config_version: number | null }

export interface ScenarioStep { title: string; status: 'ok' | 'bad' | 'warn' | 'info'; detail: string; lock?: string }
export interface ScenarioResult {
  id: number
  title: string
  summary: string
  steps: ScenarioStep[]
  patch_id: string | null
  outcome: string
  config_version: number
  simulated: boolean
  passport?: Passport
  explanation?: Explain
  [k: string]: unknown
}

export interface SeriesPoint { mean: number[]; se: number[] }
export interface EvalSummary {
  available: boolean
  backend?: string
  seeds?: number
  rounds?: number
  simulated?: boolean
  systems?: { id: string; name: string }[]
  improvement?: { rounds: number[]; series: Record<string, SeriesPoint> }
  attack?: Record<string, { bad_patch_acceptance: { mean: number; se: number }; regression_rate: { mean: number; se: number } }>
  ablation?: Record<string, number>
  far_frr?: { threshold: number; far: number; frr: number }[]
  notes?: string[]
}
