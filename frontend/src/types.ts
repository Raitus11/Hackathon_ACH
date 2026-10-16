export type Outcome = "PASS" | "EXCEPTION";
export type FindingResult = "MATCH" | "EXCEPTION";
export type DecisionType = "APPROVE" | "INVESTIGATE";

export interface Persona {
  id: string;
  name: string;
  role: "MAKER" | "CHECKER";
  title: string;
}

export interface Meta {
  app_name: string;
  control_id: string;
  control_name: string;
  label: string;
  simulated_systems: { name: string; role: string; status: string }[];
  assumptions: string[];
  personas: Persona[];
}

export interface ScenarioSummary {
  id: string;
  folder: string;
  name: string;
  seeded_condition: string;
  organizer_expected_outcome: string;
  request_id: string;
  customer_name: string;
  implemented_by: string;
  expected_overall: Outcome;
}

export interface RequestedChange {
  field: string;
  requested_value: string;
}

export interface MaintenanceRequest {
  request_id: string;
  customer_id: string;
  customer_name: string;
  request_type: string;
  status: string;
  submitted_by: string;
  approved_by?: string | null;
  approved_at?: string | null;
  requested_changes: RequestedChange[];
  evidence: Record<string, boolean>;
  source_system?: string;
}

export interface TnalEntry {
  record_id: string;
  customer_id: string;
  field: string;
  old_value: string | null;
  new_value: string | null;
  changed_by: string;
  changed_at: string;
}

export interface ImplementedChange {
  change_id: string;
  request_id: string;
  customer_id: string;
  implemented_by: string;
  implemented_at: string;
  tnal_entries: TnalEntry[];
  gps_changes: { field: string; new_value: string | null }[];
}

export interface Inputs {
  request: MaintenanceRequest;
  implemented_change: ImplementedChange;
}

export interface Finding {
  finding_id: string;
  rule_id: string;
  rule_version: number;
  rule_type: string;
  rule_description: string;
  severity: string;
  field: string;
  field_label: string;
  expected_value: string | null;
  expected_source: string;
  actual_value: string | null;
  actual_source: string;
  result: FindingResult;
  exception_type: string | null;
  reason: string;
}

export interface RuleEvaluation {
  rule_id: string;
  rule_version: number;
  rule_type: string;
  description: string;
  status: "EVALUATED" | "NOT_APPLICABLE" | "DISABLED";
  checks: number;
  exceptions: number;
}

export interface ValidationResult {
  run_id: string;
  evaluated_at: string;
  scenario_id: string | null;
  request_id: string;
  change_id: string;
  customer_id: string;
  customer_name: string;
  implemented_by: string;
  overall: Outcome;
  exception_count: number;
  match_count: number;
  findings: Finding[];
  rule_evaluations: RuleEvaluation[];
  summary_reasons: string[];
  ruleset_id: string;
  control_id: string;
  config_version: string;
  config_hash: string;
  config_file: string;
  input_digest: string;
  findings_digest: string;
  decision_support_notice: string;
}

export interface DecisionRecord {
  decision_id: string;
  run_id: string;
  decision: DecisionType;
  actor_id: string;
  actor_name: string;
  actor_role: string;
  comment: string;
  acknowledged_exceptions: boolean;
  ai_review_confirmed?: boolean;
  engine_outcome: Outcome;
  config_hash: string;
  recorded_at: string;
}

export interface RunPayload {
  result: ValidationResult;
  decision: DecisionRecord | null;
  extraction?: DocumentExtraction;
  pipeline?: AgentStep[];
}

export interface RuleConfig {
  id: string;
  version: number;
  type: string;
  description: string;
  severity: string;
  enabled: boolean;
  [key: string]: unknown;
}

export interface ConfigPayload {
  file: string;
  sha256: string;
  short_hash: string;
  loaded_at: string;
  ruleset: { id: string; control_id: string; name: string; version: string; effective_date: string; owner: string };
  fields: Record<string, { label: string; normalize: string[] }>;
  rules: RuleConfig[];
  raw_yaml: string;
}

export interface AuditEvent {
  event_id: string;
  timestamp: string;
  event_type: string;
  run_id: string | null;
  actor: string | null;
  payload: Record<string, unknown>;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  details: { location?: string; message: string; source?: string; line?: number; column?: number }[];
}

export type Agreement = "AGREES" | "DISAGREES" | "NOT_IN_DOCUMENT" | "NOT_IN_REQUEST";

export interface ExtractedField {
  name: string;
  label: string;
  extracted_value: string | null;
  confidence: number;
  request_value: string | null;
  agreement: Agreement;
}

export interface DocumentExtraction {
  status: "EXTRACTED" | "NO_DOCUMENT" | "FAILED";
  ai_assisted: boolean;
  document_id: string | null;
  document_type: string;
  provider: string;
  model: string;
  simulated: boolean;
  prompt_version: string;
  cache: "MISS" | "HIT_LOCAL" | "NONE";
  fields: ExtractedField[];
  signature_present: boolean | null;
  signature_confidence: number | null;
  date_signed: string | null;
  disagreements: number;
  low_confidence: number;
  notes: string | null;
  error: string | null;
  notice: string;
}

export interface AgentStep {
  order: number;
  agent: string;
  responsibility: string;
  kind: "DETERMINISTIC" | "AI_ASSISTED";
  status: "OK" | "EXCEPTIONS_FOUND" | "NO_DOCUMENT" | "FAILED" | "SKIPPED";
  duration_ms: number;
  summary: string;
  output: Record<string, unknown>;
  consumes: string[];
  produces: string[];
  hands_to: string[];
}

export interface LlmStatus {
  provider: string;
  mode: "deterministic" | "llm";
  mode_flag: string | null;
  model: string | null;
  simulated: boolean;
  label: string;
  prompt_version: string;
  response_cache_enabled: boolean;
  pricing_per_million: { input?: number; cached_input?: number; output?: number };
  pricing_note: string;
}

export interface UsageRecord {
  call_id: string;
  timestamp: string;
  run_id: string;
  agent: string;
  request_id: string;
  document_id: string;
  provider: string;
  model: string;
  simulated: boolean;
  prompt_version: string;
  local_cache_hit: boolean;
  input_tokens: number;
  uncached_input_tokens: number;
  cached_input_tokens: number;
  cache_write_tokens: number;
  output_tokens: number;
  tokens_saved_input?: number;
  tokens_saved_output?: number;
  latency_ms: number;
  estimated_cost_usd: number;
  cost_without_cache_usd: number;
}

export interface UsagePayload {
  status: LlmStatus;
  summary: {
    requests: number;
    llm_calls: number;
    local_cache_hits: number;
    input_tokens: number;
    cached_input_tokens: number;
    uncached_input_tokens: number;
    output_tokens: number;
    cache_write_tokens: number;
    tokens_saved_by_local_cache: number;
    prompt_cache_hit_rate: number;
    estimated_cost_usd: number;
    cost_without_caching_usd: number;
    savings_usd: number;
    avg_latency_ms: number;
  };
  records: UsageRecord[];
}

export interface ConfigOption {
  key: string;
  kind: "ACTIVE" | "SAMPLE" | "SNAPSHOT" | "UNKNOWN";
  label: string;
  version?: string;
  sha256?: string;
  short_hash?: string;
  valid: boolean;
  error?: string;
}

export type ReplayChange = "NEW_EXCEPTION" | "RESOLVED" | "CHECK_ADDED" | "CHECK_REMOVED" | "UNCHANGED";

export interface ReplayFinding {
  rule_id: string;
  field: string;
  field_label: string;
  baseline_result: "MATCH" | "EXCEPTION" | "NOT_CHECKED";
  candidate_result: "MATCH" | "EXCEPTION" | "NOT_CHECKED";
  baseline_rule_version: number | null;
  candidate_rule_version: number | null;
  expected_value: string | null;
  actual_value: string | null;
  baseline_reason: string | null;
  candidate_reason: string | null;
  change: ReplayChange;
}

export interface ReplayResultSummary {
  overall: Outcome;
  exception_count: number;
  match_count: number;
  findings_digest: string;
  exception_rules: string[];
}

export interface Comparison {
  request_id: string;
  change_id: string;
  input_digest: string;
  baseline: ConfigOption;
  candidate: ConfigOption;
  baseline_result: ReplayResultSummary;
  candidate_result: ReplayResultSummary;
  outcome_changed: boolean;
  changed_findings: number;
  findings: ReplayFinding[];
  rule_diffs: { rule_id: string; change: "ADDED" | "REMOVED" | "MODIFIED"; attributes: { name: string; before: unknown; after: unknown }[] }[];
  notice: string;
}

export interface QueueItem {
  queue_item_id: string;
  routed_at: string;
  run_id: string;
  request_id: string;
  change_id: string;
  customer_id: string;
  customer_name: string;
  engine_outcome: Outcome;
  routed_to: string;
  routed_to_role: string;
  routed_by: string;
  routed_by_name: string;
  decision_id: string;
  checker_comment: string;
  exceptions: { rule_id: string; rule_version: number; field: string; field_label: string; exception_type: string | null;
    expected: string; actual: string; reason: string }[];
  status: string;
  simulated: boolean;
  config_version_hash: string;
}

export interface SuiteRow {
  scenario_id: string;
  name: string;
  seeded_condition: string;
  organizer_expected_outcome: string;
  expected_overall: Outcome;
  actual_overall: Outcome;
  expected_exceptions: string[][];
  actual_exceptions: string[][];
  status: "PASS" | "FAIL";
  findings_digest: string;
  exception_details: { field: string; expected: string; actual: string; rule: string }[];
  expectation_baseline: string | null;
}

export interface SuitePayload {
  generated_at: string;
  config: { file: string; version: string; short_hash: string };
  summary: { total: number; passed: number };
  scenarios: SuiteRow[];
  notice: string;
}

export interface Metrics {
  runs: number;
  pass: number;
  exception: number;
  exceptions_by_rule: Record<string, number>;
  decisions: { APPROVE: number; INVESTIGATE: number };
  blocked_attempts: number;
  self_approval_blocked: number;
  routed_to_queue: number;
  avg_run_ms: number | null;
  note: string;
}
