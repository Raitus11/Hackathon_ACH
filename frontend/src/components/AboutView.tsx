import type { Meta } from "../types";
import { SimTag } from "./ui";

const FLOW = [
  { lane: "Customer", text: "Submits maintenance request and documents", sim: true },
  { lane: "Maker (ACH processor)", text: "Implements the change in ACH / AES / GPS", sim: true },
  { lane: "Systems", text: "TNAL audit log + GPS change report produced", sim: true },
  { lane: "This prototype", text: "Config-driven first-pass comparison → explainable PASS / EXCEPTION", sim: false },
  { lane: "Checker (independent)", text: "Reviews findings, records Approve or Investigate", human: true },
  { lane: "Rework loop", text: "Processor correction and revalidation — explained only, not built", sim: true },
];

export function AboutView({ meta }: { meta: Meta }) {
  return (
    <div className="page" style={{ display: "grid", gap: 16 }}>
      <div className="card">
        <div className="card-h"><h2>Where the prototype sits · {meta.control_id} {meta.control_name}</h2></div>
        <div className="card-b">
          <div className="flow">
            {FLOW.map((s) => (
              <div key={s.lane} className={`step ${s.human ? "human" : ""} ${s.sim ? "sim" : ""}`}>
                <b>{s.lane}</b>{s.text}
                {s.sim && <div style={{ marginTop: 6 }}><SimTag /></div>}
              </div>
            ))}
          </div>
          <p className="small muted" style={{ marginBottom: 0 }}>
            Automate the comparison, not the approval. The engine output has no approval field; only the checker decision record does,
            and the API refuses it from the maker of the change.
          </p>
        </div>
      </div>
      <div className="about-grid">
        <div className="card">
          <div className="card-h"><h2>Simulated systems</h2></div>
          <table className="table">
            <thead><tr><th>System</th><th>Role in the control</th><th>In this prototype</th></tr></thead>
            <tbody>
              {meta.simulated_systems.map((s) => (
                <tr key={s.name}><td><strong>{s.name}</strong></td><td>{s.role}</td><td><SimTag>{s.status}</SimTag></td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card">
          <div className="card-h"><h2>Assumptions (pending organizer confirmation)</h2></div>
          <ol className="card-b" style={{ margin: 0, paddingLeft: 36, display: "grid", gap: 6 }}>
            {meta.assumptions.map((a) => <li key={a}>{a}</li>)}
          </ol>
        </div>
      </div>
      <div className="card">
        <div className="card-h"><h2>Test personas (synthetic)</h2></div>
        <table className="table">
          <thead><tr><th>ID</th><th>Name</th><th>Role</th><th>Can record a decision?</th></tr></thead>
          <tbody>
            {meta.personas.map((p) => (
              <tr key={p.id}>
                <td className="mono">{p.id}</td><td>{p.name}</td><td>{p.title}</td>
                <td>{p.role === "CHECKER" ? "Yes, on changes they did not implement" : "No — maker; self-approval blocked in UI and API"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="small muted">
        Prototype for the COO Technology Global Hackathon. Synthetic data only. Not production-ready and not a replacement for existing controls.
      </p>
    </div>
  );
}
