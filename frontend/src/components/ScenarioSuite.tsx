import { useState } from "react";
import { api } from "../api";
import type { SuitePayload } from "../types";
import { IconAlert, IconCheck, IconPlay, OutcomeChip, fmtTime } from "./ui";

/** AC2 / FAQ Q48: all five seeded scenarios against their predefined expected outcomes, run live. */
export function ScenarioSuite({ personaId }: { personaId: string }) {
  const [out, setOut] = useState<SuitePayload | null>(null);
  const [busy, setBusy] = useState(false);
  async function run() {
    setBusy(true);
    try { setOut(await api.suite(personaId)); } finally { setBusy(false); }
  }
  const allGreen = out && out.summary.passed === out.summary.total;
  return (
    <div className="page" style={{ display: "grid", gap: 16 }}>
      <div className="card">
        <div className="card-h">
          <h2>Seeded scenario results</h2>
          <div className="right">
            {out && <span className={`chip ${allGreen ? "chip-pass" : "chip-exception"}`}>
              {allGreen ? <IconCheck size={13} /> : <IconAlert size={13} />}{out.summary.passed} / {out.summary.total} match expected outcome</span>}
            <button className="btn btn-primary btn-sm" onClick={run} disabled={busy}><IconPlay size={13} />Run all 5</button>
          </div>
        </div>
        <div className="card-b small muted">
          Each scenario runs through the same deterministic engine against the active external rule file and is compared with its
          predefined expected outcome (overall result plus each expected rule, field and exception type). The same check runs in
          pytest and writes <span className="mono">reports/scenario_results.md</span>.
          {out && <> Last run {fmtTime(out.generated_at)} · {out.config.file} v{out.config.version} · <span className="mono">{out.config.short_hash}</span>.</>}
        </div>
      </div>
      {out && (
        <div className="card">
          <table className="table">
            <thead><tr><th>#</th><th>Scenario</th><th>Organizer expected outcome</th><th>Expected</th><th>Actual</th><th>Exceptions raised</th><th>Result</th></tr></thead>
            <tbody>
              {out.scenarios.map((r) => (
                <tr key={r.scenario_id} className={r.status === "FAIL" ? "cmp-changed" : ""}>
                  <td className="mono">{r.scenario_id}</td>
                  <td><strong>{r.name}</strong><div className="src">{r.seeded_condition}</div></td>
                  <td className="small">{r.organizer_expected_outcome}</td>
                  <td><OutcomeChip outcome={r.expected_overall} /></td>
                  <td><OutcomeChip outcome={r.actual_overall} /></td>
                  <td className="small">
                    {r.exception_details.length === 0 ? <span className="muted">none</span> : r.exception_details.map((d) => (
                      <div key={d.rule + d.field}><span className="rule-ref">{d.rule}</span> {d.field}: <span className="mono">{d.expected}</span> → <span className="mono">{d.actual}</span></div>
                    ))}
                  </td>
                  <td>{r.status === "PASS"
                    ? <span className="chip chip-pass"><IconCheck size={12} />PASS</span>
                    : <span className="chip chip-exception"><IconAlert size={12} />DIFFERS</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="card-b small muted">{out.notice}</div>
        </div>
      )}
    </div>
  );
}
