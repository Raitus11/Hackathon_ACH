import { useEffect, useState } from "react";
import { ApiError, api } from "../api";
import type { Comparison, ConfigOption, ReplayChange } from "../types";
import { IconPlay, OutcomeChip, shown } from "./ui";

type Source = { scenario_id: string } | { request: unknown; implemented_change: unknown };

const CHANGE: Record<ReplayChange, { label: string; cls: string }> = {
  NEW_EXCEPTION: { label: "New exception", cls: "chip-exception" },
  RESOLVED: { label: "Resolved", cls: "chip-pass" },
  CHECK_ADDED: { label: "Check added", cls: "chip-investigate" },
  CHECK_REMOVED: { label: "Check removed", cls: "chip-neutral" },
  UNCHANGED: { label: "Unchanged", cls: "chip-neutral" },
};

const RESULT_LABEL: Record<string, string> = { MATCH: "Match", EXCEPTION: "Exception", NOT_CHECKED: "Not checked" };

function fmt(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") return v.length > 60 ? `${v.slice(0, 57)}…` : v;
  return JSON.stringify(v);
}

function pickDefaults(options: ConfigOption[]): [string, string] {
  const active = options.find((o) => o.key === "active");
  const snapshot = options.find((o) => o.kind === "SNAPSHOT" && o.valid && o.sha256 !== active?.sha256);
  if (snapshot) return [snapshot.key, "active"];
  const sample = options.find((o) => o.kind === "SAMPLE" && o.valid);
  return ["active", sample?.key ?? "active"];
}

/** Rule version comparison + scenario replay: the same inputs under two rule configurations. */
export function RuleCompare({ source, personaId, refreshKey }: { source: Source; personaId: string; refreshKey: number }) {
  const [options, setOptions] = useState<ConfigOption[]>([]);
  const [baseline, setBaseline] = useState("");
  const [candidate, setCandidate] = useState("");
  const [out, setOut] = useState<Comparison | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    api.configs().then((opts) => {
      setOptions(opts);
      const [b, c] = pickDefaults(opts);
      setBaseline(b); setCandidate(c); setOut(null);
    }).catch(() => setOptions([]));
  }, [refreshKey, JSON.stringify(source)]);

  async function replay() {
    setBusy(true); setError(null);
    try {
      setOut(await api.compare(source, baseline, candidate, personaId));
    } catch (e) {
      setError(e instanceof ApiError ? `${e.body.message} (${e.body.code})` : String(e));
      setOut(null);
    } finally {
      setBusy(false);
    }
  }

  const label = (o: ConfigOption) => `${o.label}${o.version ? ` · v${o.version}` : ""}${o.short_hash ? ` · ${o.short_hash}` : ""}`;
  const rows = out ? (showAll ? out.findings : out.findings.filter((f) => f.change !== "UNCHANGED")) : [];

  return (
    <div className="card">
      <div className="card-h">
        <h2>Rule version comparison · scenario replay</h2>
        <div className="right small muted">same inputs · two rule configurations · no code change</div>
      </div>
      <div className="card-b cmp-controls">
        <label>Baseline
          <select value={baseline} onChange={(e) => setBaseline(e.target.value)}>
            {options.map((o) => <option key={o.key} value={o.key} disabled={!o.valid}>{label(o)}</option>)}
          </select>
        </label>
        <span className="cmp-arrow" aria-hidden>→</span>
        <label>Candidate
          <select value={candidate} onChange={(e) => setCandidate(e.target.value)}>
            {options.map((o) => <option key={o.key} value={o.key} disabled={!o.valid}>{label(o)}</option>)}
          </select>
        </label>
        <button className="btn btn-sm" onClick={replay} disabled={busy || !baseline || !candidate}><IconPlay size={13} />Compare</button>
      </div>
      {error && <div className="err" style={{ margin: "0 16px 12px" }}>{error}</div>}
      {out && (
        <>
          <div className="cmp-head">
            <div>
              <div className="small muted">{out.baseline.label}</div>
              <div className="cmp-ver">v{out.baseline.version} <span className="mono small muted">{out.baseline.short_hash}</span></div>
              <OutcomeChip outcome={out.baseline_result.overall} />
              <span className="small muted"> {out.baseline_result.exception_count} exception(s)</span>
            </div>
            <div className="cmp-mid">
              {out.outcome_changed
                ? <span className="chip chip-investigate">Outcome changed</span>
                : <span className="chip chip-neutral">Outcome unchanged</span>}
              <div className="small muted">{out.changed_findings} finding(s) changed</div>
            </div>
            <div>
              <div className="small muted">{out.candidate.label}</div>
              <div className="cmp-ver">v{out.candidate.version} <span className="mono small muted">{out.candidate.short_hash}</span></div>
              <OutcomeChip outcome={out.candidate_result.overall} />
              <span className="small muted"> {out.candidate_result.exception_count} exception(s)</span>
            </div>
          </div>

          <div className="card-b" style={{ paddingTop: 0 }}>
            <div className="cmp-sub">What changed in the external rule file</div>
            {out.rule_diffs.length === 0 && <div className="small muted">No rule differences: both configurations define identical rules.</div>}
            <ul className="cmp-diffs">
              {out.rule_diffs.map((d) => (
                <li key={d.rule_id}>
                  <span className="rule-ref">{d.rule_id}</span> <span className="small muted">{d.change.toLowerCase()}</span>
                  {d.attributes.map((a) => (
                    <span key={a.name} className="cmp-attr"><code>{a.name}</code> <s>{fmt(a.before)}</s> → <strong>{fmt(a.after)}</strong></span>
                  ))}
                </li>
              ))}
            </ul>
          </div>

          <table className="table">
            <thead><tr><th>Rule</th><th>Field</th><th>Baseline</th><th>Candidate</th><th>Change</th><th>Candidate reason</th></tr></thead>
            <tbody>
              {rows.map((f) => (
                <tr key={`${f.rule_id}-${f.field}`} className={f.change !== "UNCHANGED" ? "cmp-changed" : ""}>
                  <td><span className="rule-ref">{f.rule_id}</span>
                    <div className="src">v{f.baseline_rule_version ?? "—"} → v{f.candidate_rule_version ?? "—"}</div></td>
                  <td><strong>{f.field_label}</strong><div className="src mono">{f.field}</div></td>
                  <td>{RESULT_LABEL[f.baseline_result]}</td>
                  <td><strong>{RESULT_LABEL[f.candidate_result]}</strong></td>
                  <td><span className={`chip ${CHANGE[f.change].cls}`}>{CHANGE[f.change].label}</span></td>
                  <td className="reason">{f.candidate_reason ?? f.baseline_reason ?? "—"}
                    {f.change !== "UNCHANGED" && f.expected_value !== null && (
                      <div className="src">expected {shown(f.expected_value)} · actual {shown(f.actual_value)}</div>)}</td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={6} className="muted">No finding changed between the two configurations.</td></tr>}
            </tbody>
          </table>
          <div className="card-b small muted cmp-foot">
            <button className="btn-link" onClick={() => setShowAll((v) => !v)}>{showAll ? "Show changed findings only" : `Show all ${out.findings.length} findings`}</button>
            <span>{out.notice} Input digest <span className="mono">{out.input_digest.slice(0, 12)}</span>.</span>
          </div>
        </>
      )}
    </div>
  );
}
