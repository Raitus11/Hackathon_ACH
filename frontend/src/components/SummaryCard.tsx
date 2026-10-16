import type { DecisionRecord, Persona, ValidationResult } from "../types";
import { DecisionChip, IconInfo, OutcomeChip, fmtTime } from "./ui";

export function SummaryCard({ result, decision, personas }: {
  result: ValidationResult; decision: DecisionRecord | null; personas: Persona[];
}) {
  const exc = result.overall === "EXCEPTION";
  const maker = personas.find((p) => p.id === result.implemented_by);
  const headline = exc
    ? `${result.exception_count} exception${result.exception_count > 1 ? "s" : ""} for checker investigation`
    : "All configured checks matched — ready for checker review";
  return (
    <div className="card summary" aria-live="polite">
      <div className={`summary-top ${exc ? "is-exception" : "is-pass"}`}>
        <OutcomeChip outcome={result.overall} large />
        <div style={{ flex: 1, minWidth: 0 }}>
          <h1>{headline}</h1>
          <div className="sub">
            {result.customer_name} · {result.request_id} · engine result from {result.config_file} v{result.config_version}
          </div>
        </div>
        <DecisionChip decision={decision?.decision ?? null} />
      </div>
      <div className="notice">
        <IconInfo />
        <span><strong>Decision support only.</strong> This result is not an approval. The independent checker records the final
          Approve or Investigate decision{exc ? "" : ", even on a PASS"}. Deterministic rule result: the same inputs and rule file
          always give the same findings, so no confidence score applies.</span>
      </div>
      <ul className="reasons">
        {result.summary_reasons.map((r) => <li key={r}>{r}</li>)}
      </ul>
      <dl className="meta-grid">
        <div><dt>Request (expected)</dt><dd>{result.request_id}</dd></div>
        <div><dt>Implemented change (actual)</dt><dd>{result.change_id}</dd></div>
        <div><dt>Implemented by (maker)</dt><dd>{maker ? `${maker.name} · ${maker.id}` : result.implemented_by}</dd></div>
        <div><dt>Customer</dt><dd>{result.customer_id}</dd></div>
        <div><dt>Run ID</dt><dd className="mono">{result.run_id}</dd></div>
        <div><dt>Evaluated</dt><dd>{fmtTime(result.evaluated_at)}</dd></div>
        <div><dt>Rule set · version</dt><dd>{result.ruleset_id} · v{result.config_version}</dd></div>
        <div><dt>Config sha256</dt><dd className="mono" title={result.config_hash}>{result.config_hash.slice(0, 16)}…</dd></div>
      </dl>
    </div>
  );
}
