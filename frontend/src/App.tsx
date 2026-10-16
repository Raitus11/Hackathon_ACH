import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "./api";
import { AboutView } from "./components/AboutView";
import { AgentFlow } from "./components/AgentFlow";
import { AgentPipelineView } from "./components/AgentPipeline";
import { ExtractionCard } from "./components/ExtractionCard";
import { ExceptionQueue } from "./components/ExceptionQueue";
import { MakerFeedback } from "./components/MakerFeedback";
import { RuleCompare } from "./components/RuleCompare";
import { ScenarioSuite } from "./components/ScenarioSuite";
import { SideBySide } from "./components/SideBySide";
import { TokenView } from "./components/TokenView";
import { AuditView } from "./components/AuditView";
import { CsvBatchPanel } from "./components/CsvBatchPanel";
import { DecisionPanel } from "./components/DecisionPanel";
import { FindingsTable } from "./components/FindingsTable";
import { InputsPanel } from "./components/InputsPanel";
import { RulePanel } from "./components/RulePanel";
import { SummaryCard } from "./components/SummaryCard";
import { IconPlay, IconShield, OutcomeChip } from "./components/ui";
import type { AgentStep, ApiErrorBody, ConfigPayload, CsvBatch, CsvBatchItem, DecisionRecord, DocumentExtraction, Inputs, Meta, ScenarioSummary, ValidationResult } from "./types";

type Tab = "review" | "queue" | "suite" | "pipeline" | "tokens" | "audit" | "about";
type Source =
  | { kind: "scenario"; id: string }
  | { kind: "files"; name: string }
  | { kind: "csv"; batchId: string; requestId: string; title: string };

const asError = (e: unknown): ApiErrorBody =>
  e instanceof ApiError ? e.body : { code: "ERROR", message: e instanceof Error ? e.message : String(e), details: [] };

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [personaId, setPersonaId] = useState("C-2001");
  const [tab, setTab] = useState<Tab>("review");
  const [source, setSource] = useState<Source | null>(null);
  const [inputs, setInputs] = useState<Inputs | null>(null);
  const [note, setNote] = useState<string>();
  const [result, setResult] = useState<ValidationResult | null>(null);
  const [decision, setDecision] = useState<DecisionRecord | null>(null);
  const [extraction, setExtraction] = useState<DocumentExtraction | null>(null);
  const [pipeline, setPipeline] = useState<AgentStep[] | null>(null);
  const [docText, setDocText] = useState<string | null>(null);
  const [config, setConfig] = useState<ConfigPayload | null>(null);
  const [configError, setConfigError] = useState<ApiErrorBody | null>(null);
  const [runError, setRunError] = useState<ApiErrorBody | null>(null);
  const [busy, setBusy] = useState(false);
  const [auditKey, setAuditKey] = useState(0);
  const reqFile = useRef<HTMLInputElement>(null);
  const chgFile = useRef<HTMLInputElement>(null);
  const docFile = useRef<HTMLInputElement>(null);

  const refreshConfig = useCallback(async () => {
    try {
      setConfig(await api.config());
      setConfigError(null);
    } catch (e) {
      setConfigError(asError(e));
    }
  }, []);

  useEffect(() => {
    api.meta().then(setMeta);
    api.scenarios().then(setScenarios);
    refreshConfig();
  }, [refreshConfig]);

  // Watch the external rule file so a saved edit shows up immediately (no code, no restart).
  useEffect(() => {
    if (tab !== "review") return;
    const t = window.setInterval(refreshConfig, 2500);
    return () => window.clearInterval(t);
  }, [tab, refreshConfig]);

  const personas = meta?.personas ?? [];
  const persona = personas.find((p) => p.id === personaId) ?? null;

  async function selectScenario(id: string) {
    setSource({ kind: "scenario", id });
    setResult(null); setDecision(null); setRunError(null); setExtraction(null); setPipeline(null);
    const s = await api.scenario(id);
    setInputs({ request: s.request, implemented_change: s.implemented_change });
    setNote(s.data_note);
  }

  async function run() {
    if (!source) return;
    setBusy(true); setRunError(null);
    try {
      let payload;
      if (source.kind === "scenario") {
        payload = await api.runScenario(source.id, personaId);
      } else {
        if (!inputs) return;
        payload = await api.runFiles(inputs.request, inputs.implemented_change, docText, personaId);
      }
      setResult(payload.result);
      setDecision(payload.decision);
      setExtraction(payload.extraction ?? null);
      setPipeline(payload.pipeline ?? null);
    } catch (e) {
      setRunError(asError(e));
      setResult(null); setExtraction(null); setPipeline(null);
    } finally {
      setBusy(false);
      refreshConfig();
      setAuditKey((k) => k + 1);
    }
  }

  async function openCsvItem(item: CsvBatchItem, batch: CsvBatch) {
    setSource({ kind: "csv", batchId: batch.batch_id, requestId: item.request_id, title: item.scenario_title });
    setResult(null); setDecision(null); setExtraction(null); setPipeline(null); setDocText(null); setRunError(null);
    setNote(`From CSV input set ${batch.batch_id} (${Object.values(batch.files).map((f) => f.name).join(", ")}). ` +
      "No GPS report is part of this input set, so the GPS consistency rule is not applicable.");
    if (!item.run_id) {
      setInputs(null);
      setRunError(item.error ?? { code: "NOT_RUN", message: `${item.request_id} was not validated.`, details: [] });
      return;
    }
    try {
      const payload = await api.run(item.run_id);
      setInputs(payload.inputs ?? null);
      setResult(payload.result);
      setDecision(payload.decision);
      setExtraction(payload.extraction ?? null);
      setPipeline(payload.pipeline ?? null);
    } catch (e) {
      setRunError(asError(e));
    } finally {
      setAuditKey((k) => k + 1);
    }
  }

  async function loadFiles() {
    const rf = reqFile.current?.files?.[0];
    const cf = chgFile.current?.files?.[0];
    if (!rf || !cf) return;
    setRunError(null); setResult(null); setDecision(null); setExtraction(null); setPipeline(null);
    try {
      let request = JSON.parse(await rf.text());
      let change = JSON.parse(await cf.text());
      const isReq = (o: any) => o && Array.isArray(o.requested_changes);
      const isChg = (o: any) => o && Array.isArray(o.tnal_entries);
      let swapped = false;
      if (!isReq(request) && isReq(change) && isChg(request)) {
        [request, change] = [change, request];
        swapped = true;
      }
      const problems: { location: string; message: string }[] = [];
      if (!isReq(request)) problems.push({ location: rf.name, message: "is not a maintenance request (no requested_changes array)" });
      if (!isChg(change)) problems.push({ location: cf.name, message: "is not an implemented-change record (no tnal_entries array)" });
      if (problems.length) {
        setInputs(null); setSource(null);
        setRunError({ code: "WRONG_FILE_IN_SLOT", message: "Files do not match their slots.", details: problems });
        return;
      }
      const df = docFile.current?.files?.[0];
      setDocText(df ? await df.text() : null);
      setInputs({ request, implemented_change: change });
      setSource({ kind: "files", name: `${rf.name} + ${cf.name}` });
      setNote(`Loaded from files: ${rf.name}, ${cf.name}.${swapped ? " Request and change files were in swapped slots and were corrected." : ""} Must be synthetic data.`);
    } catch (e) {
      setRunError({ code: "FILE_NOT_JSON", message: `Could not parse file as JSON: ${String(e)}`, details: [] });
    }
  }

  const selectedId = source?.kind === "scenario" ? source.id : null;

  return (
    <>
      <header className="topbar">
        <div className="wordmark">
          <strong>ACH Validation Workbench</strong>
          <span>C-247489 · ACH DB Next Day Validation · Maker-Checker</span>
        </div>
        <span className="synthetic-badge" title="All data is synthetic. All enterprise systems are simulated.">
          <IconShield size={14} />SYNTHETIC DATA · SIMULATED SYSTEMS
        </span>
        <div className="spacer" />
        <div className="persona">
          <label htmlFor="persona">Acting as</label>
          <select id="persona" value={personaId} onChange={(e) => setPersonaId(e.target.value)}>
            {personas.map((p) => (
              <option key={p.id} value={p.id}>{p.role === "CHECKER" ? "Checker" : "Maker"} · {p.name} ({p.id})</option>
            ))}
          </select>
        </div>
      </header>

      <nav className="tabs" role="tablist">
        {([["review", "Validation review"], ["queue", "Exception queue"], ["suite", "Scenario results"], ["audit", "Audit trail"], ["pipeline", "Agent pipeline"], ["tokens", "Token analysis"], ["about", "Process, simulated systems & assumptions"]] as const).map(([k, label]) => (
          <button key={k} role="tab" className="tab" aria-selected={tab === k} onClick={() => { setTab(k); if (k === "audit" || k === "tokens" || k === "queue") setAuditKey((n) => n + 1); }}>
            {label}
          </button>
        ))}
      </nav>

      {tab === "queue" && <ExceptionQueue personas={personas} persona={persona} refreshKey={auditKey} />}
      {tab === "suite" && <ScenarioSuite personaId={personaId} />}
      {tab === "pipeline" && <AgentPipelineView steps={pipeline} runId={result?.run_id ?? null} />}
      {tab === "tokens" && <TokenView refreshKey={auditKey} personaId={personaId} />}
      {tab === "audit" && <AuditView personas={personas} refreshKey={auditKey} />}
      {tab === "about" && meta && <AboutView meta={meta} />}

      {tab === "review" && (
        <main className="workspace">
          <aside className="col">
            <div className="card">
              <div className="card-h"><h2>Seeded scenarios</h2><div className="right small muted">synthetic</div></div>
              <div style={{ padding: 8 }}>
                {scenarios.map((s, i) => (
                  <button key={s.id} className="scenario" aria-pressed={selectedId === s.id} onClick={() => selectScenario(s.id)}>
                    <span className="num">{i + 1}</span>
                    <span>
                      <span className="t">{s.name}</span>
                      <span className="d" style={{ display: "block" }}>{s.request_id} · {s.customer_name}</span>
                      <span className="d" style={{ display: "block" }}>Expected: {s.expected_overall}</span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
            <CsvBatchPanel personaId={personaId} selectedRunId={source?.kind === "csv" ? result?.run_id ?? null : null}
              onOpen={openCsvItem} onError={(e) => { setRunError(e); setSource(null); setInputs(null); setResult(null); }} />
            <div className="card">
              <div className="card-h"><h2>Load your own files</h2></div>
              <div className="card-b upload">
                <label>Maintenance request (JSON)<input ref={reqFile} type="file" accept="application/json,.json" /></label>
                <label>Implemented change · TNAL/GPS (JSON)<input ref={chgFile} type="file" accept="application/json,.json" /></label>
                <label>Authorization form (optional .txt) · AI-assisted<input ref={docFile} type="file" accept="text/plain,.txt" /></label>
                <button className="btn btn-sm" onClick={loadFiles}>Load files</button>
                <span className="small muted">Synthetic data only. Schema-validated and matched on request and customer ID.</span>
              </div>
            </div>
          </aside>

          <section className="col">
            {!source && (
              <div className="card empty">
                <h2>Select a seeded scenario or load a request and change record</h2>
                <p>The engine compares the approved request with the implemented TNAL/GPS change using the external rule file,
                  then hands an explainable PASS or EXCEPTION to the independent checker. It never approves anything.</p>
              </div>
            )}
            {source && (
              <div className="card" style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 16px" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600 }}>
                    {source.kind === "scenario" ? `${selectedId} · ${scenarios.find((s) => s.id === selectedId)?.name}`
                      : source.kind === "csv" ? `${source.requestId} · CSV input set` : source.name}
                  </div>
                  <div className="small muted">
                    {source.kind === "scenario" ? scenarios.find((s) => s.id === selectedId)?.seeded_condition
                      : source.kind === "csv" ? `${source.title || "Request"} · ${source.batchId}` : "Ad-hoc files"}
                    {config ? ` · rules ${config.file} v${config.ruleset.version} (${config.short_hash})` : ""}
                  </div>
                </div>
                {result && <OutcomeChip outcome={result.overall} />}
                <button className="btn btn-primary" onClick={run} disabled={busy || !inputs || !!configError}>
                  <IconPlay size={14} />{result ? "Re-run validation" : "Run validation"}
                </button>
              </div>
            )}
            {runError && (
              <div className="err" role="alert">
                <strong>{runError.message}</strong> <span className="mono small">({runError.code})</span>
                {runError.details.length > 0 && (
                  <ul>{runError.details.map((d, i) => <li key={i}>{d.source ? `${d.source}: ` : ""}<code>{d.location}</code> {d.message}</li>)}</ul>
                )}
              </div>
            )}
            {result && persona && <MakerFeedback result={result} persona={persona} />}
            {result && <SummaryCard result={result} decision={decision} personas={personas} />}
            {result && <FindingsTable key={result.run_id} result={result} />}
            {result && inputs && <SideBySide inputs={inputs} result={result} />}
            {source && inputs && (
              <RuleCompare personaId={personaId} refreshKey={auditKey}
                source={source.kind === "scenario" ? { scenario_id: source.id } : { request: inputs.request, implemented_change: inputs.implemented_change }} />
            )}
            {pipeline && result && <AgentFlow steps={pipeline} runId={result.run_id} compact />}
            {extraction && <ExtractionCard extraction={extraction} />}
            {inputs && <InputsPanel inputs={inputs} result={result} note={note} />}
          </section>

          <aside className="col">
            <DecisionPanel result={result} decision={decision} persona={persona} personas={personas} extraction={extraction}
              onRecorded={(d) => { setDecision(d); setAuditKey((k) => k + 1); }} onOpenQueue={() => { setTab("queue"); setAuditKey((k) => k + 1); }} />
            <RulePanel config={config} configError={configError} result={result} onRerun={run} busy={busy} />
          </aside>
        </main>
      )}
      <div className="footer-note">
        Prototype · synthetic data · simulated integrations (ServiceNow, DMS, TNAL, GPS, CheckMate). Not production-ready and not a
        replacement for existing controls. The engine result is decision support; the checker remains the final decision-maker.
      </div>
    </>
  );
}
