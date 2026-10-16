import { Fragment, useState } from "react";
import type { Finding, ValidationResult } from "../types";
import { DiffValue, IconChevron, ResultChip } from "./ui";

const TYPE_LABEL: Record<string, string> = {
  MISMATCH: "Field mismatch",
  MISSING_FIELD: "Missing field",
  UNAUTHORIZED_CHANGE: "Unauthorized change",
  MISSING_EVIDENCE: "Missing evidence",
  REQUEST_NOT_APPROVED: "Request not approved",
  SOURCE_INCONSISTENT: "GPS / TNAL inconsistent",
};

function Row({ f, open, onToggle }: { f: Finding; open: boolean; onToggle: () => void }) {
  const exc = f.result === "EXCEPTION";
  const diff = exc && (f.exception_type === "MISMATCH" || f.exception_type === "UNAUTHORIZED_CHANGE" || f.exception_type === "SOURCE_INCONSISTENT");
  return (
    <Fragment>
      <tr className={`row ${exc ? "exc" : ""}`} onClick={onToggle} aria-expanded={open}>
        <td style={{ width: 138 }}>
          <ResultChip result={f.result} />
          {exc && <div className="src" style={{ color: "var(--exc-ink)", fontWeight: 600 }}>{TYPE_LABEL[f.exception_type ?? ""]}</div>}
        </td>
        <td style={{ width: 170 }}>
          <strong>{f.field_label}</strong>
          <div className="src mono">{f.field}</div>
        </td>
        <td>
          <DiffValue value={f.expected_value} other={f.actual_value} highlight={diff} />
          <div className="src">{f.expected_source}</div>
        </td>
        <td>
          <DiffValue value={f.actual_value} other={f.expected_value} highlight={diff} />
          <div className="src">{f.actual_source}</div>
        </td>
        <td style={{ width: 112 }}>
          <span className="rule-ref">{f.rule_id}</span> <span className="muted small">v{f.rule_version}</span>
          <div className="src">{f.rule_type}</div>
        </td>
        <td className="reason">
          {f.reason}
          <span style={{ float: "right", color: "var(--text-3)" }}><IconChevron open={open} /></span>
        </td>
      </tr>
      {open && (
        <tr className="detail">
          <td colSpan={6}>
            <dl className="detail-grid">
              <dt>Finding</dt><dd className="mono">{f.finding_id}</dd>
              <dt>Configured rule</dt><dd><span className="rule-ref">{f.rule_id} v{f.rule_version}</span> — {f.rule_description} ({f.rule_type}, severity {f.severity})</dd>
              <dt>Expected value from</dt><dd>{f.expected_source}</dd>
              <dt>Actual value from</dt><dd>{f.actual_source}</dd>
              <dt>Result</dt><dd>{f.result}{f.exception_type ? ` · ${f.exception_type}` : ""}</dd>
            </dl>
          </td>
        </tr>
      )}
    </Fragment>
  );
}

export function FindingsTable({ result }: { result: ValidationResult }) {
  const [open, setOpen] = useState<string | null>(null);
  const [showMatches, setShowMatches] = useState(result.overall === "PASS");
  const exceptions = result.findings.filter((f) => f.result === "EXCEPTION");
  const matches = result.findings.filter((f) => f.result === "MATCH");
  const toggle = (id: string) => setOpen((cur) => (cur === id ? null : id));
  const header = (
    <thead>
      <tr>
        <th>Result</th><th>Field</th><th>Expected · source</th><th>Actual · source</th><th>Rule</th><th>Reason</th>
      </tr>
    </thead>
  );
  return (
    <div className="card">
      <div className="card-h">
        <h2>Field-level findings</h2>
        <div className="right small muted">
          {exceptions.length} exception{exceptions.length === 1 ? "" : "s"} · {matches.length} matching check{matches.length === 1 ? "" : "s"} · click a row for trace
        </div>
      </div>
      {exceptions.length > 0 && (
        <table className="table">
          {header}
          <tbody>{exceptions.map((f) => <Row key={f.finding_id} f={f} open={open === f.finding_id} onToggle={() => toggle(f.finding_id)} />)}</tbody>
        </table>
      )}
      <button className="group-toggle" onClick={() => setShowMatches((v) => !v)} aria-expanded={showMatches}>
        <IconChevron open={showMatches} /> {showMatches ? "Hide" : "Show"} {matches.length} matching check{matches.length === 1 ? "" : "s"}
      </button>
      {showMatches && (
        <table className="table">
          {exceptions.length === 0 && header}
          <tbody>{matches.map((f) => <Row key={f.finding_id} f={f} open={open === f.finding_id} onToggle={() => toggle(f.finding_id)} />)}</tbody>
        </table>
      )}
    </div>
  );
}
