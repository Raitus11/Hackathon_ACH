import type {
  ApiErrorBody,
  AuditEvent,
  Comparison,
  ConfigOption,
  Metrics,
  QueueItem,
  SuitePayload,
  ConfigPayload,
  CsvBatch,
  DecisionRecord,
  DecisionType,
  Inputs,
  Meta,
  RunPayload,
  ScenarioSummary,
  UsagePayload,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, public body: ApiErrorBody) {
    super(body.message);
  }
}

async function call<T>(path: string, init: RequestInit = {}, personaId?: string): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (personaId) headers["X-Persona-Id"] = personaId;
  const resp = await fetch(`/api${path}`, { ...init, headers: { ...headers, ...(init.headers ?? {}) } });
  const text = await resp.text();
  const data = text ? JSON.parse(text) : null;
  if (!resp.ok) {
    const body: ApiErrorBody = data?.error ?? { code: `HTTP_${resp.status}`, message: resp.statusText, details: [] };
    throw new ApiError(resp.status, body);
  }
  return data as T;
}

export const api = {
  meta: () => call<Meta>("/meta"),
  scenarios: () => call<ScenarioSummary[]>("/scenarios"),
  scenario: (id: string) =>
    call<{ request: Inputs["request"]; implemented_change: Inputs["implemented_change"]; data_note: string }>(
      `/scenarios/${encodeURIComponent(id)}`,
    ),
  config: () => call<ConfigPayload>("/config"),
  runScenario: (scenarioId: string, personaId: string) =>
    call<RunPayload>("/runs", { method: "POST", body: JSON.stringify({ scenario_id: scenarioId }) }, personaId),
  runFiles: (request: unknown, change: unknown, documentText: string | null, personaId: string) =>
    call<RunPayload>(
      "/runs",
      { method: "POST", body: JSON.stringify({ request, implemented_change: change, document_text: documentText }) },
      personaId,
    ),
  run: (runId: string) => call<RunPayload>(`/runs/${encodeURIComponent(runId)}`),
  runCsvBatch: (files: { name: string; content: string }[], personaId: string) =>
    call<CsvBatch>("/csv/batches", { method: "POST", body: JSON.stringify({ files }) }, personaId),
  decide: (runId: string, personaId: string, decision: DecisionType, comment: string, acknowledge: boolean, aiReviewed: boolean) =>
    call<{ decision: DecisionRecord; routed: QueueItem | null }>(
      `/runs/${encodeURIComponent(runId)}/decision`,
      {
        method: "POST",
        body: JSON.stringify({ decision, comment, acknowledge_exceptions: acknowledge, ai_review_confirmed: aiReviewed }),
      },
      personaId,
    ),
  configs: () => call<ConfigOption[]>("/configs"),
  compare: (source: { scenario_id: string } | { request: unknown; implemented_change: unknown }, baseline: string, candidate: string, personaId: string) =>
    call<Comparison>("/compare", { method: "POST", body: JSON.stringify({ ...source, baseline, candidate }) }, personaId),
  queue: () => call<{ label: string; items: QueueItem[] }>("/queue"),
  suite: (personaId: string) => call<SuitePayload>("/scenarios/suite", { method: "POST" }, personaId),
  metrics: () => call<Metrics>("/metrics"),
  llmUsage: () => call<UsagePayload>("/llm/usage"),
  clearLlmCache: (personaId: string) => call<{ entries_removed: number }>("/llm/cache/clear", { method: "POST" }, personaId),
  audit: (runId?: string) => call<AuditEvent[]>(`/audit${runId ? `?run_id=${encodeURIComponent(runId)}` : ""}`),
  evidenceUrl: (runId: string, format: "json" | "md") => `/api/runs/${encodeURIComponent(runId)}/evidence?format=${format}`,
};
