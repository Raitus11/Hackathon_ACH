import type { Persona, ValidationResult } from "../types";
import { IconAlert, IconCheck, IconInfo, shown } from "./ui";

const TYPE_LABEL: Record<string, string> = {
  MISMATCH: "Implemented value differs from the approved request",
  MISSING_FIELD: "Requested change not completed",
  UNAUTHORIZED_CHANGE: "Field changed without being requested",
  MISSING_EVIDENCE: "Required supporting evidence missing",
  REQUEST_NOT_APPROVED: "Request not approved",
  SOURCE_INCONSISTENT: "GPS report does not match the TNAL implementation",
};

/** Scope doc §1.3: ACH processors (makers) receive clear feedback when their change does not match the approved request.
 *  Read-only. The maker cannot record a decision; correction and resubmission are out of scope. */
export function MakerFeedback({ result, persona }: { result: ValidationResult; persona: Persona }) {
  if (persona.role !== "MAKER") return null;
  const own = persona.id === result.implemented_by;
  const exceptions = result.findings.filter((f) => f.result === "EXCEPTION");
  return (
    <div className={`card maker-fb ${exceptions.length ? "has-exc" : ""}`}>
      <div className="card-h">
        <h2>Processor feedback · {own ? `your change ${result.change_id}` : `change ${result.change_id}`}</h2>
        <div className="right small muted">read-only · maker view</div>
      </div>
      {!own && (
        <div className="card-b small">
          <IconInfo size={14} /> {persona.name} did not implement this change (maker: {result.implemented_by}). Shown for information only.
        </div>
      )}
      {exceptions.length === 0 ? (
        <div className="card-b">
          <span className="chip chip-pass"><IconCheck size={13} />No differences from the approved request</span>
          <span className="small muted" style={{ marginLeft: 8 }}>Awaiting the independent checker's decision.</span>
        </div>
      ) : (
        <>
          <div className="card-b small" style={{ paddingBottom: 6 }}>
            The first-pass comparison found {exceptions.length} item{exceptions.length > 1 ? "s" : ""} the independent checker will
            review. Nothing has been decided yet; you cannot record a decision on your own change.
          </div>
          <ol className="fb-list">
            {exceptions.map((f) => (
              <li key={f.finding_id}>
                <div className="fb-title"><IconAlert size={13} /> <strong>{f.field_label}</strong> — {TYPE_LABEL[f.exception_type ?? ""] ?? f.exception_type}</div>
                <div className="fb-vals">
                  <span>Approved / expected <span className="val">{shown(f.expected_value)}</span></span>
                  <span>You implemented <span className="val">{shown(f.actual_value)}</span></span>
                  <span className="rule-ref">{f.rule_id} v{f.rule_version}</span>
                </div>
                <div className="small muted">{f.reason}</div>
              </li>
            ))}
          </ol>
          <div className="card-b small muted" style={{ paddingTop: 0 }}>
            In the live process the checker contacts you and you correct the change or supply documents. That rework loop is
            outside this prototype (FAQ Q15, Q33).
          </div>
        </>
      )}
    </div>
  );
}
