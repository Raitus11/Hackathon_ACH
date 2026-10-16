import { useEffect, useState } from "react";
import { api } from "../api";
import type { Persona, QueueItem } from "../types";
import { IconAlert, SimTag, fmtTime } from "./ui";

/** Mock exception queue (stretch goal; FAQ Q15). Items arrive when the checker records Investigate. */
export function ExceptionQueue({ personas, persona, refreshKey }: { personas: Persona[]; persona: Persona | null; refreshKey: number }) {
  const [items, setItems] = useState<QueueItem[]>([]);
  const [label, setLabel] = useState("");
  const [mine, setMine] = useState(false);
  useEffect(() => {
    api.queue().then((q) => { setItems(q.items); setLabel(q.label); }).catch(() => setItems([]));
  }, [refreshKey]);
  const name = (id: string) => personas.find((p) => p.id === id)?.name ?? id;
  const isMaker = persona?.role === "MAKER";
  const shownItems = isMaker && mine ? items.filter((i) => i.routed_to === persona?.id) : items;

  return (
    <div className="page" style={{ display: "grid", gap: 16 }}>
      <div className="card">
        <div className="card-h">
          <h2>Exception queue</h2>
          <div className="right"><SimTag>SIMULATED · CheckMate routing</SimTag></div>
        </div>
        <div className="card-b small">
          <div className="notice" style={{ margin: 0 }}><IconAlert size={14} /><span>{label}</span></div>
          <div className="muted" style={{ marginTop: 8 }}>
            Flow shown: checker records <strong>Investigate</strong> → item is routed to the original processor with the exact
            findings and the checker's comment. Approve never routes anything. No status here changes the engine result or the
            decision record.
          </div>
          {isMaker && (
            <label className="small" style={{ display: "inline-flex", gap: 6, marginTop: 8 }}>
              <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} /> Only items routed to me ({persona?.name})
            </label>
          )}
        </div>
      </div>
      {shownItems.length === 0 && (
        <div className="card empty"><h2>Queue is empty</h2><p>Run an exception scenario and record Investigate as the checker.</p></div>
      )}
      {shownItems.map((i) => (
        <div key={i.queue_item_id} className={`card q-item ${persona && i.routed_to === persona.id ? "q-mine" : ""}`}>
          <div className="card-h">
            <span className="mono">{i.queue_item_id}</span>
            <h2 style={{ marginLeft: 8 }}>{i.customer_name} · {i.request_id}</h2>
            <div className="right">
              <span className="chip chip-investigate">Awaiting processor correction</span>
              <SimTag />
            </div>
          </div>
          <div className="card-b q-meta small">
            <span><b>Routed to</b> {name(i.routed_to)} ({i.routed_to}) · {i.routed_to_role}</span>
            <span><b>By</b> {i.routed_by_name} ({i.routed_by}) · {fmtTime(i.routed_at)}</span>
            <span><b>Run</b> <span className="mono">{i.run_id}</span> · decision <span className="mono">{i.decision_id}</span> · config <span className="mono">{i.config_version_hash}</span></span>
          </div>
          <table className="mini" style={{ margin: "0 16px 8px", width: "calc(100% - 32px)" }}>
            <thead><tr><th>Rule</th><th>Field</th><th>Expected</th><th>Actual</th><th>Type</th></tr></thead>
            <tbody>
              {i.exceptions.map((e) => (
                <tr key={e.rule_id + e.field} className="flag">
                  <td className="mono nw">{e.rule_id} v{e.rule_version}</td>
                  <td>{e.field_label}</td>
                  <td className="mono">{e.expected}</td>
                  <td className="mono">{e.actual}</td>
                  <td className="small">{e.exception_type}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="card-b small" style={{ paddingTop: 4 }}><b>Checker comment:</b> {i.checker_comment}</div>
        </div>
      ))}
    </div>
  );
}
