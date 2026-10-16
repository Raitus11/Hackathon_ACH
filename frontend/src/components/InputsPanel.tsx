import type { Inputs, ValidationResult } from "../types";
import { SimTag, fmtTime, shown } from "./ui";

export function InputsPanel({ inputs, result, note }: { inputs: Inputs; result: ValidationResult | null; note?: string }) {
  const { request, implemented_change: change } = inputs;
  const flagged = new Set(
    (result?.findings ?? []).filter((f) => f.result === "EXCEPTION").map((f) => f.field.replace(/^evidence\./, "")),
  );
  const requested = new Set((request.requested_changes ?? []).map((c) => c.field));
  return (
    <div className="card">
      <div className="card-h">
        <h2>Loaded inputs</h2>
        <div className="right"><SimTag>SYNTHETIC</SimTag></div>
      </div>
      <div className="inputs">
        <section>
          <h3>Approved maintenance request <SimTag>ServiceNow · SIMULATED</SimTag></h3>
          <dl className="kv">
            <dt>Request</dt><dd>{request.request_id}</dd>
            <dt>Customer</dt><dd>{request.customer_name} · {request.customer_id}</dd>
            <dt>Type · status</dt><dd>{request.request_type} · {request.status}</dd>
            <dt>Approved by</dt><dd>{request.approved_by ?? "—"}{request.approved_at ? ` · ${fmtTime(request.approved_at)}` : ""}</dd>
          </dl>
          <table className="mini">
            <thead><tr><th>Field</th><th>Requested value</th></tr></thead>
            <tbody>
              {(request.requested_changes ?? []).map((c) => (
                <tr key={c.field} className={flagged.has(c.field) ? "flag" : ""}>
                  <td className="mono">{c.field}</td><td className="mono">{shown(c.requested_value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="small muted" style={{ marginTop: 10 }}>Evidence indicators <SimTag>DMS · SIMULATED</SimTag></div>
          <div className="ev">
            {Object.keys(request.evidence).length === 0 && <span className="chip chip-exception">none on file</span>}
            {Object.entries(request.evidence ?? {}).map(([k, v]) => (
              <span key={k} className={`chip ${v ? "chip-pass" : "chip-neutral"}`}>{k}: {v ? "present" : "not provided"}</span>
            ))}
          </div>
        </section>
        <section>
          <h3>Implemented change <SimTag>TNAL + GPS · SIMULATED</SimTag></h3>
          <dl className="kv">
            <dt>Change</dt><dd>{change.change_id}</dd>
            <dt>Implemented by</dt><dd>{change.implemented_by} (maker)</dd>
            <dt>Implemented at</dt><dd>{fmtTime(change.implemented_at)}</dd>
          </dl>
          <table className="mini">
            <thead><tr><th>TNAL row</th><th>Field</th><th>Old → New</th></tr></thead>
            <tbody>
              {(change.tnal_entries ?? []).map((t) => (
                <tr key={t.record_id} className={flagged.has(t.field) ? "flag" : ""}>
                  <td className="mono nw">{t.record_id}</td>
                  <td className="mono">
                    {t.field}
                    {!requested.has(t.field) && <div className="small" style={{ color: "var(--exc-ink)", fontWeight: 600 }}>not in request</div>}
                  </td>
                  <td className="mono">{shown(t.old_value)} → <strong>{shown(t.new_value)}</strong></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="small muted" style={{ marginTop: 10 }}>
            GPS change report lists {change.gps_changes.length} field{change.gps_changes.length === 1 ? "" : "s"}: {" "}
            <span className="mono">{(change.gps_changes ?? []).map((g) => g.field).join(", ") || "none"}</span>
          </div>
        </section>
      </div>
      {note && <div className="footer-note" style={{ paddingTop: 8 }}>{note}</div>}
    </div>
  );
}
