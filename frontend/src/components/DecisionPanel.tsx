import { useEffect, useState } from "react";
import { ApiError, api } from "../api";
import type { ApiErrorBody, DecisionRecord, DecisionType, DocumentExtraction, Persona, ValidationResult } from "../types";
import { DecisionChip, IconDownload, IconLock, IconSearch, IconShield, IconSpark, fmtTime } from "./ui";

export function DecisionPanel({ result, decision, persona, personas, extraction, onRecorded }: {
  result: ValidationResult | null;
  extraction: DocumentExtraction | null;
  decision: DecisionRecord | null;
  persona: Persona | null;
  personas: Persona[];
  onRecorded: (d: DecisionRecord) => void;
}) {
  const [choice, setChoice] = useState<DecisionType | null>(null);
  const [comment, setComment] = useState("");
  const [ack, setAck] = useState(false);
  const [aiReviewed, setAiReviewed] = useState(false);
  const [error, setError] = useState<ApiErrorBody | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { setChoice(null); setComment(""); setAck(false); setAiReviewed(false); setError(null); }, [result?.run_id, persona?.id]);

  const isImplementer = !!(persona && result && persona.id === result.implemented_by);
  const isChecker = persona?.role === "CHECKER" && !isImplementer;
  const hasExceptions = (result?.exception_count ?? 0) > 0;
  const approvingExceptions = choice === "APPROVE" && hasExceptions;
  const minLen = approvingExceptions ? 20 : 5;
  const needsAiReview = extraction?.status === "EXTRACTED";
  const canSubmit = !!choice && comment.trim().length >= minLen && (!approvingExceptions || ack) && (!needsAiReview || aiReviewed) && !busy;
  const maker = personas.find((p) => p.id === result?.implemented_by);

  async function submit(force = false) {
    if (!result || !persona || (!force && !choice)) return;
    setBusy(true);
    setError(null);
    try {
      const resp = await api.decide(result.run_id, persona.id, choice ?? "APPROVE",
        force && comment.trim().length < 5 ? "Attempted approval of own change" : comment, ack || force, aiReviewed || force);
      onRecorded(resp.decision);
    } catch (e) {
      setError(e instanceof ApiError ? e.body : { code: "ERROR", message: String(e), details: [] });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card boundary">
      <div className="card-h">
        <IconShield />
        <h2>Human-approval boundary · Checker decision</h2>
      </div>
      <div className="card-b" style={{ display: "grid", gap: 12 }}>
        {!result && <div className="muted">Run a validation first. The engine never approves; only an independent checker can.</div>}

        {result && decision && (
          <div className="receipt">
            <DecisionChip decision={decision.decision} />
            <div><strong>{decision.actor_name}</strong> <span className="muted">({decision.actor_id}, {decision.actor_role})</span></div>
            <div className="small muted">Recorded {fmtTime(decision.recorded_at)} · {decision.decision_id}</div>
            <div className="small">Engine outcome at decision: <strong>{decision.engine_outcome}</strong>
              {decision.acknowledged_exceptions && " · exceptions explicitly acknowledged"}
              {decision.ai_review_confirmed && " · AI-extracted values reviewed"}</div>
            <blockquote style={{ margin: 0, padding: "8px 12px", borderLeft: "3px solid var(--line-strong)", background: "var(--surface-2)" }}>{decision.comment}</blockquote>
            {decision.decision === "INVESTIGATE" && (
              <div className="small muted">
                Reference process: the checker contacts the original processor, corrections or documents are provided, and the item is revalidated.
                Exception routing and rework are <strong>not built</strong> in this prototype (out of scope; would be CheckMate · simulated).
              </div>
            )}
          </div>
        )}

        {result && !decision && persona && !isChecker && (
          <div className="lock" role="note">
            <IconLock size={22} />
            <div>
              <strong>{isImplementer ? "Segregation of duties: self-approval blocked" : "Only an independent checker may decide"}</strong>
              {isImplementer
                ? <>You ({persona.name}, {persona.id}) implemented {result.change_id}. A maker cannot record a decision on their own change.</>
                : <>{persona.name} has the MAKER role. Approve or Investigate is reserved for the independent reviewer.</>}
              <div style={{ marginTop: 8 }}>
                <button className="btn-link" onClick={() => submit(true)} disabled={busy}>
                  Attempt anyway to show server-side enforcement
                </button>
              </div>
            </div>
          </div>
        )}

        {result && !decision && (
          <fieldset disabled={!isChecker || busy} style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 4, opacity: isChecker ? 1 : 0.5 }}>
            <div className="choice" role="group" aria-label="Checker decision">
              <button type="button" className="approve" aria-pressed={choice === "APPROVE"} onClick={() => setChoice("APPROVE")}>
                <span className="h" style={{ color: "var(--pass-ink)" }}><IconShield size={16} />Approve</span>
                <span className="d">Implementation matches the approved request</span>
              </button>
              <button type="button" className="investigate" aria-pressed={choice === "INVESTIGATE"} onClick={() => setChoice("INVESTIGATE")}>
                <span className="h" style={{ color: "var(--inv-ink)" }}><IconSearch size={16} />Investigate</span>
                <span className="d">Return to processor for correction or evidence</span>
              </button>
            </div>
            <label className="field-label" htmlFor="comment">
              Checker comment (required{approvingExceptions ? ", min. 20 characters justification" : ""})
            </label>
            <textarea id="comment" value={comment} onChange={(e) => setComment(e.target.value)}
              placeholder={choice === "INVESTIGATE" ? "What needs correcting or providing, and by whom" : "What you verified"} />
            {approvingExceptions && (
              <label className="ack">
                <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
                <span>I am approving despite <strong>{result.exception_count} open exception{result.exception_count > 1 ? "s" : ""}</strong>.
                  My justification above is recorded with this decision.</span>
              </label>
            )}
            {needsAiReview && (
              <label className="ack ai-ack">
                <input type="checkbox" checked={aiReviewed} onChange={(e) => setAiReviewed(e.target.checked)} />
                <span><IconSpark size={13} /> I reviewed the {extraction!.ai_assisted ? <strong>AI-assisted</strong> : "parser"} values extracted from the authorization form
                  ({extraction!.disagreements} cross-check difference{extraction!.disagreements === 1 ? "" : "s"}). They are advisory and did not set the engine result.</span>
              </label>
            )}
            <button className="btn btn-primary" style={{ marginTop: 10 }} onClick={() => submit()} disabled={!canSubmit}>
              Record decision as {persona?.name ?? "—"}
            </button>
          </fieldset>
        )}

        {error && (
          <div className="err" role="alert">
            <strong>{error.code === "SELF_APPROVAL_BLOCKED" || error.code === "ROLE_NOT_PERMITTED" ? "Blocked by the server (HTTP 403)" : "Not recorded"}</strong>
            <div>{error.message}</div>
            <div className="small mono" style={{ marginTop: 4 }}>{error.code}</div>
          </div>
        )}

        {result && (
          <div style={{ display: "grid", gap: 6, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
            <div className="small muted">
              Maker of this change: <strong>{maker ? `${maker.name} (${maker.id})` : result.implemented_by}</strong>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <a className="btn btn-sm" href={api.evidenceUrl(result.run_id, "md")} download><IconDownload size={14} />Evidence .md</a>
              <a className="btn btn-sm" href={api.evidenceUrl(result.run_id, "json")} download><IconDownload size={14} />Evidence .json</a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
