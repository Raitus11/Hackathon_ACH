import { useState } from "react";
import type { AgentStep } from "../types";
import { IconAlert, IconCheck, IconChevron, IconSpark } from "./ui";

const STATUS: Record<AgentStep["status"], { cls: string; label: string }> = {
  OK: { cls: "chip-pass", label: "OK" },
  EXCEPTIONS_FOUND: { cls: "chip-exception", label: "EXCEPTIONS FOUND" },
  NO_DOCUMENT: { cls: "chip-investigate", label: "NO DOCUMENT" },
  FAILED: { cls: "chip-exception", label: "FAILED" },
  SKIPPED: { cls: "chip-neutral", label: "SKIPPED" },
};

function KindTag({ kind }: { kind: AgentStep["kind"] }) {
  return kind === "AI_ASSISTED"
    ? <span className="ai-tag"><IconSpark size={12} />AI-ASSISTED</span>
    : <span className="det-tag">DETERMINISTIC</span>;
}

/** Compact strip for the review page. */
export function PipelineStrip({ steps, onOpen }: { steps: AgentStep[]; onOpen: () => void }) {
  return (
    <div className="card pipe-strip" role="list" aria-label="Agent pipeline">
      {steps.map((s, i) => {
        const bad = s.status === "EXCEPTIONS_FOUND" || s.status === "FAILED";
        return (
          <div key={s.agent} className="pipe-node" role="listitem">
            <span className={`pipe-dot ${bad ? "bad" : s.status === "OK" ? "ok" : "warn"} ${s.kind === "AI_ASSISTED" ? "ai" : ""}`}>
              {s.kind === "AI_ASSISTED" ? <IconSpark size={12} /> : bad ? <IconAlert size={12} /> : <IconCheck size={12} />}
            </span>
            <span className="pipe-name">{s.agent.replace(" Agent", "")}</span>
            <span className="pipe-ms">{s.duration_ms.toFixed(1)} ms</span>
            {i < steps.length - 1 && <span className="pipe-arrow" aria-hidden>→</span>}
          </div>
        );
      })}
      <button className="btn btn-sm" style={{ marginLeft: "auto" }} onClick={onOpen}>Agent trace</button>
    </div>
  );
}

/** Full view for the Agent pipeline tab. */
export function AgentPipelineView({ steps, runId }: { steps: AgentStep[] | null; runId: string | null }) {
  const [open, setOpen] = useState<number | null>(3);
  if (!steps || !runId) {
    return <div className="page"><div className="card empty"><h2>No run yet</h2><p>Run a validation on the review tab to see the agent trace.</p></div></div>;
  }
  const total = steps.reduce((a, s) => a + s.duration_ms, 0);
  return (
    <div className="page" style={{ display: "grid", gap: 16 }}>
      <div className="card">
        <div className="card-h">
          <h2>Agent pipeline · {runId}</h2>
          <div className="right small muted">{steps.length} agents · {total.toFixed(1)} ms total · fixed order, single responsibility each</div>
        </div>
        <div className="card-b small muted">
          Five agents are deterministic code. One agent uses an LLM, only to read the authorization form for the checker; its output is
          advisory and is never read by the Rule Engine Agent. <strong>No agent can approve.</strong> The decision belongs to the independent checker.
        </div>
      </div>
      <ol className="agent-list">
        {steps.map((s) => {
          const st = STATUS[s.status];
          const isOpen = open === s.order;
          return (
            <li key={s.agent} className={`card agent ${s.kind === "AI_ASSISTED" ? "agent-ai" : ""}`}>
              <button className="agent-h" onClick={() => setOpen(isOpen ? null : s.order)} aria-expanded={isOpen}>
                <span className="agent-n">{s.order}</span>
                <span className="agent-t">
                  <strong>{s.agent}</strong>
                  <span className="small muted">{s.responsibility}</span>
                </span>
                <KindTag kind={s.kind} />
                <span className={`chip ${st.cls}`}>{st.label}</span>
                <span className="small muted mono" style={{ width: 70, textAlign: "right" }}>{s.duration_ms.toFixed(2)} ms</span>
                <IconChevron open={isOpen} />
              </button>
              <div className="agent-sum">{s.summary}</div>
              {isOpen && <pre className="agent-out">{JSON.stringify(s.output, null, 2)}</pre>}
            </li>
          );
        })}
      </ol>
      <div className="card">
        <div className="card-h"><h2>Human-approval boundary</h2></div>
        <div className="card-b small">After the Evidence Agent, control passes to the independent checker, who records Approve or Investigate.
          The API rejects decisions from the maker of the change, and requires confirmation that AI-extracted values were reviewed.</div>
      </div>
    </div>
  );
}
