import { useEffect, useMemo, useState } from "react";
import type { AgentStep } from "../types";

/**
 * Animated replay of one recorded run: each agent lights up in execution order, a packet travels
 * along the handoff edge, and the hop is captioned with what was consumed and produced.
 * The Document Extraction Agent's output travels only to the checker — never to the Rule Engine.
 */

type NodeKey = "intake" | "matcher" | "extract" | "rules" | "explain" | "evidence" | "checker";

const NODES: Record<NodeKey, { x: number; y: number; label: string; agent?: string; phase: number }> = {
  intake: { x: 70, y: 70, label: "Intake", agent: "Intake Agent", phase: 0 },
  matcher: { x: 250, y: 70, label: "Matcher", agent: "Matcher Agent", phase: 1 },
  extract: { x: 470, y: 190, label: "Doc Extraction", agent: "Document Extraction Agent", phase: 2 },
  rules: { x: 470, y: 70, label: "Rule Engine", agent: "Rule Engine Agent", phase: 3 },
  explain: { x: 660, y: 70, label: "Explainer", agent: "Explainer Agent", phase: 4 },
  evidence: { x: 850, y: 70, label: "Evidence", agent: "Evidence Agent", phase: 5 },
  checker: { x: 1050, y: 110, label: "Checker", phase: 6 },
};

const EDGES: { id: string; from: NodeKey; to: NodeKey; phase: number; d: string; advisory?: boolean }[] = [
  { id: "i-m", from: "intake", to: "matcher", phase: 1, d: "M 96 70 L 224 70" },
  { id: "m-x", from: "matcher", to: "extract", phase: 2, d: "M 272 84 C 340 160, 390 190, 444 190" },
  { id: "m-r", from: "matcher", to: "rules", phase: 3, d: "M 276 70 L 444 70" },
  { id: "r-e", from: "rules", to: "explain", phase: 4, d: "M 496 70 L 634 70" },
  { id: "e-v", from: "explain", to: "evidence", phase: 5, d: "M 686 70 L 824 70" },
  { id: "v-c", from: "evidence", to: "checker", phase: 6, d: "M 875 76 C 940 90, 980 100, 1022 106" },
  { id: "x-c", from: "extract", to: "checker", phase: 6, d: "M 496 190 C 760 220, 960 196, 1028 128", advisory: true },
];

const STEP_MS = 750;

function short(agent: string) {
  return agent.replace(" Agent", "");
}

export function AgentFlow({ steps, runId, compact = false }: { steps: AgentStep[]; runId: string; compact?: boolean }) {
  const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const [phase, setPhase] = useState<number>(reduced ? 7 : 0);
  const [playing, setPlaying] = useState(!reduced);
  const byAgent = useMemo(() => new Map(steps.map((s) => [s.agent, s])), [steps]);

  useEffect(() => { setPhase(reduced ? 7 : 0); setPlaying(!reduced); }, [runId, reduced]);
  useEffect(() => {
    if (!playing) return;
    if (phase >= 7) { setPlaying(false); return; }
    const t = window.setTimeout(() => setPhase((p) => p + 1), STEP_MS);
    return () => window.clearTimeout(t);
  }, [phase, playing]);

  const nodeState = (key: NodeKey) => {
    const n = NODES[key];
    if (phase < n.phase) return "pending";
    if (phase === n.phase) return "active";
    return "done";
  };
  const statusClass = (key: NodeKey) => {
    const s = NODES[key].agent ? byAgent.get(NODES[key].agent!) : undefined;
    if (!s) return "human";
    if (s.status === "EXCEPTIONS_FOUND" || s.status === "FAILED") return "bad";
    if (s.status === "NO_DOCUMENT") return "warn";
    return "ok";
  };

  // The hop currently in flight (for the caption).
  const order = steps.slice().sort((a, b) => a.order - b.order);
  const phaseAgent = Object.values(NODES).find((n) => n.phase === Math.min(phase, 6));
  const current = phaseAgent?.agent ? byAgent.get(phaseAgent.agent) : undefined;
  const revealed = order.filter((s) => {
    const k = (Object.keys(NODES) as NodeKey[]).find((key) => NODES[key].agent === s.agent)!;
    return NODES[k].phase <= phase;
  });

  return (
    <div className={`card agent-flow ${compact ? "flow-compact" : ""}`}>
      <div className="card-h">
        <h2>Agent handoffs</h2>
        <div className="right">
          <span className="small muted">Replay of recorded run {runId} · per-agent timings are real</span>
          <button className="btn btn-sm" onClick={() => { setPhase(0); setPlaying(true); }}>Replay</button>
          {playing && <button className="btn btn-sm" onClick={() => { setPhase(7); setPlaying(false); }}>Skip</button>}
        </div>
      </div>
      <svg viewBox="0 0 1120 262" className="flow-svg" role="img" aria-label="Agent pipeline handoff diagram">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--line-strong)" />
          </marker>
          <marker id="arrow-on" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--text-2)" />
          </marker>
        </defs>

        {/* lanes */}
        <text x="16" y="24" className="lane">CONTROL PATH · deterministic · decides PASS / EXCEPTION</text>
        <text x="16" y="252" className="lane lane-ai">ADVISORY PATH · document extraction → checker only</text>
        <line x1="470" y1="138" x2="470" y2="164" className="no-edge" />
        <text x="482" y="157" className="no-edge-label">✕ never read by Rule Engine</text>

        {EDGES.map((e) => {
          const on = phase >= e.phase;
          return (
            <g key={e.id}>
              <path d={e.d} className={`edge ${on ? "on" : ""} ${e.advisory ? "advisory" : ""}`}
                    markerEnd={`url(#${on ? "arrow-on" : "arrow"})`} />
              {phase === e.phase && playing && (
                <circle key={`${e.id}-${runId}-${phase}`} r="6" className={`packet ${e.advisory ? "packet-ai" : ""}`}>
                  <animateMotion dur={`${STEP_MS * 0.8}ms`} path={e.d} fill="freeze" />
                </circle>
              )}
            </g>
          );
        })}

        {(Object.keys(NODES) as NodeKey[]).map((key) => {
          const n = NODES[key];
          const st = nodeState(key);
          const step = n.agent ? byAgent.get(n.agent) : undefined;
          const ai = step?.kind === "AI_ASSISTED";
          const isChecker = key === "checker";
          return (
            <g key={key} transform={`translate(${n.x} ${n.y})`} className={`node ${st} ${st === "done" ? statusClass(key) : ""} ${isChecker ? "human" : ""} ${key === "extract" ? "extract" : ""} ${ai ? "ai" : ""}`}>
              {st === "active" && <circle r="34" className="halo" />}
              <circle r={isChecker ? 28 : 24} className="disc" />
              <text y="5" textAnchor="middle" className="num">{isChecker ? "✓?" : n.phase + 1}</text>
              <text y={isChecker ? 48 : 44} textAnchor="middle" className="nlabel">{n.label}</text>
              {step && st === "done" && (
                <text y={isChecker ? 62 : 58} textAnchor="middle" className="nsub">{step.duration_ms.toFixed(1)} ms · {step.status.replace("_", " ").toLowerCase()}</text>
              )}
              {isChecker && <text y="62" textAnchor="middle" className="nsub">{phase >= 6 ? "awaiting human decision" : "human-approval boundary"}</text>}
            </g>
          );
        })}
      </svg>

      <div className="hop">
        {phase >= 7 || !current ? (
          <span className="small muted">All six agents completed. Control now sits with the independent checker; no agent can approve.</span>
        ) : (
          <HopLine step={current} />
        )}
      </div>

      {!compact && (
        <ol className="hop-log">
          {revealed.map((s) => <li key={s.agent}><HopLine step={s} /></li>)}
        </ol>
      )}
    </div>
  );
}

function HopLine({ step }: { step: AgentStep }) {
  return (
    <div className="hop-line">
      <span className={`hop-agent ${step.kind === "AI_ASSISTED" ? "ai" : ""}`}>{step.order}. {short(step.agent)}</span>
      <span className="hop-io"><b>in</b> {step.consumes.join(" · ")}</span>
      <span className="hop-arrow">→</span>
      <span className="hop-io"><b>out</b> {step.produces.join(" · ")}</span>
      <span className="hop-arrow">⇒</span>
      <span className="hop-to">{step.hands_to.map(short).join(" + ")}</span>
    </div>
  );
}
