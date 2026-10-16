import type { Inputs, ValidationResult } from "../types";
import { IconAlert, IconCheck, SimTag, shown } from "./ui";

const TYPE_SHORT: Record<string, string> = {
  MISMATCH: "Mismatch",
  MISSING_FIELD: "Missing",
  UNAUTHORIZED_CHANGE: "Not requested",
  SOURCE_INCONSISTENT: "GPS ≠ TNAL",
};

/** Request ↔ TNAL ↔ GPS on one row per field. Highlights come from the engine's findings, never from UI logic. */
export function SideBySide({ inputs, result }: { inputs: Inputs; result: ValidationResult }) {
  const { request, implemented_change: change } = inputs;
  const requested = new Map((request.requested_changes ?? []).map((c) => [c.field, c.requested_value]));
  // Latest TNAL row per field is the implemented value (same assumption as the engine).
  const tnal = new Map<string, { old: string | null; new: string | null; id: string; at: string }>();
  for (const t of change.tnal_entries ?? []) {
    const prev = tnal.get(t.field);
    if (!prev || t.changed_at >= prev.at) tnal.set(t.field, { old: t.old_value, new: t.new_value, id: t.record_id, at: t.changed_at });
  }
  const gps = new Map((change.gps_changes ?? []).map((g) => [g.field, g.new_value]));
  const fields = Array.from(new Set([...requested.keys(), ...tnal.keys(), ...gps.keys()]));

  const issues = new Map<string, { type: string; rule: string }[]>();
  for (const f of result.findings) {
    if (f.result !== "EXCEPTION" || !f.exception_type) continue;
    if (!TYPE_SHORT[f.exception_type]) continue;
    const list = issues.get(f.field) ?? [];
    list.push({ type: f.exception_type, rule: `${f.rule_id} v${f.rule_version}` });
    issues.set(f.field, list);
  }
  const label = (f: string) => result.findings.find((x) => x.field === f)?.field_label ?? f;
  const has = (f: string, ...types: string[]) => (issues.get(f) ?? []).some((i) => types.includes(i.type));

  return (
    <div className="card">
      <div className="card-h">
        <h2>Side-by-side · request ↔ TNAL ↔ GPS</h2>
        <div className="right"><SimTag>SYNTHETIC</SimTag><span className="small muted">highlights come from the rule engine's findings</span></div>
      </div>
      <table className="table sbs">
        <thead>
          <tr>
            <th>Field</th>
            <th>Approved request <span className="src">ServiceNow · simulated</span></th>
            <th>Implemented · TNAL <span className="src">old → new</span></th>
            <th>GPS change report</th>
            <th>Engine verdict</th>
          </tr>
        </thead>
        <tbody>
          {fields.map((f) => {
            const t = tnal.get(f);
            const bad = (issues.get(f) ?? []).length > 0;
            return (
              <tr key={f} className={bad ? "sbs-bad" : ""}>
                <td><strong>{label(f)}</strong><div className="src mono">{f}</div></td>
                <td className={has(f, "UNAUTHORIZED_CHANGE") ? "cell-flag" : ""}>
                  {requested.has(f) ? <span className="val">{shown(requested.get(f))}</span> : <span className="small muted">not in request</span>}
                </td>
                <td className={has(f, "MISMATCH", "MISSING_FIELD", "UNAUTHORIZED_CHANGE") ? "cell-flag" : ""}>
                  {t ? <><span className="val muted-val">{shown(t.old)}</span> → <span className="val">{shown(t.new)}</span><div className="src mono">{t.id}</div></>
                    : <span className="val placeholder">no TNAL row</span>}
                </td>
                <td className={has(f, "SOURCE_INCONSISTENT") ? "cell-flag" : ""}>
                  {gps.has(f) ? <span className="val">{shown(gps.get(f))}</span> : <span className="small muted">{change.gps_report_available === false ? "no GPS report" : "not on report"}</span>}
                </td>
                <td>
                  {bad
                    ? (issues.get(f) ?? []).map((i) => (
                      <div key={i.rule + i.type} className="chip chip-exception sbs-chip"><IconAlert size={12} />{TYPE_SHORT[i.type]} · {i.rule}</div>
                    ))
                    : <span className="chip chip-pass sbs-chip"><IconCheck size={12} />Consistent</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="card-b small muted" style={{ paddingTop: 8 }}>
        Evidence indicators:{" "}
        {Object.entries(request.evidence ?? {}).map(([k, v]) => (
          <span key={k} className={`chip ${v ? "chip-pass" : "chip-exception"} sbs-chip`} style={{ marginRight: 6 }}>
            {v ? <IconCheck size={12} /> : <IconAlert size={12} />}{k.replace(/_/g, " ")}: {v ? "present" : "absent"}
          </span>
        ))}
        {Object.keys(request.evidence ?? {}).length === 0 && "none on the request"}
      </div>
    </div>
  );
}
