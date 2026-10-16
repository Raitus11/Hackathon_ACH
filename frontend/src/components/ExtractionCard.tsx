import type { Agreement, DocumentExtraction } from "../types";
import { IconSpark, shown } from "./ui";

const AGREE: Record<Agreement, { label: string; cls: string }> = {
  AGREES: { label: "Matches request", cls: "chip-pass" },
  DISAGREES: { label: "Differs from request", cls: "chip-exception" },
  NOT_IN_DOCUMENT: { label: "Not on form", cls: "chip-investigate" },
  NOT_IN_REQUEST: { label: "Not in request", cls: "chip-investigate" },
};

function Confidence({ value, present }: { value: number; present: boolean }) {
  if (!present) return <span className="muted small">—</span>;
  const pct = Math.round(value * 100);
  const low = value < 0.8;
  return (
    <span className="conf" title={`Model confidence ${pct}%`}>
      <span className="conf-bar"><span style={{ width: `${pct}%` }} className={low ? "low" : ""} /></span>
      <span className={`small ${low ? "conf-low" : ""}`}>{pct}%{low ? " · review" : ""}</span>
    </span>
  );
}

export function ExtractionCard({ extraction }: { extraction: DocumentExtraction }) {
  const e = extraction;
  return (
    <div className="card ai-card">
      <div className="card-h">
        {e.ai_assisted ? <span className="ai-tag"><IconSpark size={13} />AI-ASSISTED</span> : <span className="det-tag">DETERMINISTIC · LLM OFF</span>}
        <h2>Document Extraction Agent · authorization form</h2>
        <div className="right small muted">
          {e.ai_assisted ? "LIVE LLM" : "ACH_LLM_MODE=deterministic"} · {e.model} · {e.prompt_version}
          {e.cache === "HIT_LOCAL" && <span className="sim-tag" style={{ marginLeft: 6 }}>CACHE HIT · 0 tokens</span>}
        </div>
      </div>
      <div className="ai-notice small">{e.notice}</div>
      {e.status === "NO_DOCUMENT" && (
        <div className="card-b"><span className="chip chip-investigate">No authorization form on file</span>
          <span className="small muted" style={{ marginLeft: 8 }}>Nothing to extract. The deterministic evidence rule decides on the indicator.</span></div>
      )}
      {e.status === "FAILED" && (
        <div className="card-b"><div className="err"><strong>Extraction unavailable.</strong> {e.error}
          <div className="small">The validation result above is unaffected: it never depends on this agent.</div></div></div>
      )}
      {e.status === "EXTRACTED" && (
        <>
          <table className="table">
            <thead><tr><th>Field on form</th><th>{e.ai_assisted ? "Extracted (AI)" : "Extracted (parser)"}</th><th>Confidence</th><th>Approved request</th><th>Cross-check</th></tr></thead>
            <tbody>
              {e.fields.map((f) => (
                <tr key={f.name}>
                  <td><strong>{f.label}</strong><div className="src mono">{f.name}</div></td>
                  <td><span className={`val ${f.extracted_value === null ? "placeholder" : ""}`}>{shown(f.extracted_value)}</span></td>
                  <td><Confidence value={f.confidence} present={f.extracted_value !== null} /></td>
                  <td><span className="val">{shown(f.request_value)}</span></td>
                  <td><span className={`chip ${AGREE[f.agreement].cls}`}>{AGREE[f.agreement].label}</span></td>
                </tr>
              ))}
              <tr>
                <td><strong>Signature</strong><div className="src">form marker</div></td>
                <td><span className="val">{e.signature_present ? "present" : "not found"}</span></td>
                <td><Confidence value={e.signature_confidence ?? 0} present /></td>
                <td className="muted small">{e.date_signed ? `signed ${e.date_signed}` : "—"}</td>
                <td><span className={`chip ${e.signature_present ? "chip-pass" : "chip-investigate"}`}>{e.signature_present ? "Signed" : "Check form"}</span></td>
              </tr>
            </tbody>
          </table>
          <div className="card-b small muted" style={{ paddingTop: 10 }}>
            {e.disagreements} cross-check difference(s), {e.low_confidence} low-confidence value(s). Document {e.document_id}.
            {e.notes ? ` Notes: ${e.notes}` : ""}
          </div>
        </>
      )}
    </div>
  );
}
