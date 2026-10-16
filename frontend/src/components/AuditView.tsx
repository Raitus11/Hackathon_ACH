import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { AuditEvent, Persona } from "../types";
import { fmtTime } from "./ui";

const TONE: Record<string, string> = {
  VALIDATION_RUN_COMPLETED: "var(--info-ink)",
  CHECKER_DECISION_RECORDED: "var(--pass-ink)",
  DECISION_BLOCKED: "var(--exc-ink)",
  EVIDENCE_EXPORTED: "var(--text-2)",
};

export function AuditView({ personas, refreshKey }: { personas: Persona[]; refreshKey: number }) {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [q, setQ] = useState("");
  useEffect(() => { api.audit().then(setEvents).catch(() => setEvents([])); }, [refreshKey]);
  const name = (id: string | null) => (id ? personas.find((p) => p.id === id)?.name ?? id : "system");
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return needle ? events.filter((e) => JSON.stringify(e).toLowerCase().includes(needle)) : events;
  }, [events, q]);
  return (
    <div className="page">
      <div className="card">
        <div className="card-h">
          <h2>Audit trail · append-only</h2>
          <div className="right">
            <input className="search" placeholder="Search run ID, request, rule, actor, event…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        </div>
        <div className="card-b small muted" style={{ paddingBottom: 0 }}>
          Every run records input identifiers, configuration version and sha256, rule results and digests; every checker decision
          and every blocked attempt is recorded. Prototype traceability design (FAQ Q39) — not production audit retention.
        </div>
        <table className="table" style={{ marginTop: 12 }}>
          <thead><tr><th>Time</th><th>Event</th><th>Run</th><th>Actor</th><th>Details</th></tr></thead>
          <tbody>
            {filtered.map((e) => (
              <tr key={e.event_id}>
                <td style={{ whiteSpace: "nowrap" }}>{fmtTime(e.timestamp)}</td>
                <td><span className="evt-type" style={{ color: TONE[e.event_type] ?? "var(--text)" }}>{e.event_type}</span></td>
                <td className="mono">{e.run_id ?? "—"}</td>
                <td>{name(e.actor)}</td>
                <td><div className="payload">{JSON.stringify(e.payload, null, 1).replace(/[{}"]/g, "").trim()}</div></td>
              </tr>
            ))}
            {filtered.length === 0 && <tr><td colSpan={5} className="muted">No events yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
