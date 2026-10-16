import { useRef, useState } from "react";
import { ApiError, api } from "../api";
import type { ApiErrorBody, CsvBatch, CsvBatchItem } from "../types";
import { OutcomeChip } from "./ui";

const EXPECTED_FILES = [
  "customer_maintenance_request.csv",
  "customer_request_change.csv",
  "request_document.csv",
  "tnal_audit_event.csv",
];

export function CsvBatchPanel({
  personaId,
  selectedRunId,
  onOpen,
  onError,
}: {
  personaId: string;
  selectedRunId: string | null;
  onOpen: (item: CsvBatchItem, batch: CsvBatch) => void;
  onError: (e: ApiErrorBody) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [batch, setBatch] = useState<CsvBatch | null>(null);
  const [busy, setBusy] = useState(false);
  const [picked, setPicked] = useState<string[]>([]);

  async function validate() {
    const list = Array.from(input.current?.files ?? []);
    setPicked(list.map((f) => f.name));
    if (!list.length) {
      onError({ code: "NO_FILES", message: "Select the four CSV files of the input set first.", details: [] });
      return;
    }
    setBusy(true);
    try {
      const files = await Promise.all(list.map(async (f) => ({ name: f.name, content: await f.text() })));
      const b = await api.runCsvBatch(files, personaId);
      setBatch(b);
      const first = b.items.find((i) => i.run_id) ?? b.items[0];
      if (first) onOpen(first, b);
    } catch (e) {
      onError(e instanceof ApiError ? e.body : { code: "ERROR", message: String(e), details: [] });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <div className="card-h">
        <h2>CSV input set</h2>
        <div className="right small muted">team export · 4 files</div>
      </div>
      <div className="card-b upload" style={{ minWidth: 0, gridTemplateColumns: "minmax(0, 1fr)" }}>
        <label>
          Select all four CSV files
          <input
            ref={input}
            type="file"
            multiple
            accept=".csv,text/csv"
            onChange={(e) => setPicked(Array.from(e.target.files ?? []).map((f) => f.name))}
          />
        </label>
        <span className="small muted" style={{ minWidth: 0 }}>
          {EXPECTED_FILES.map((f) => (
            <span key={f} style={{ display: "block", overflowWrap: "anywhere", fontSize: 11,
              color: picked.includes(f) ? "var(--pass-ink)" : undefined }}>
              {picked.includes(f) ? "✓ " : "· "}
              <span className="mono">{f}</span>
            </span>
          ))}
        </span>
        <button className="btn btn-sm" onClick={validate} disabled={busy}>
          {busy ? "Validating…" : "Validate every request"}
        </button>
        <span className="small muted">
          Each request runs through the same pipeline and rule file. Open a row to review and decide.
        </span>
      </div>

      {batch && (
        <>
          <div className="card-b" style={{ paddingTop: 0 }}>
            <div className="small" style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <span className="chip chip-pass">{batch.summary.pass} pass</span>
              <span className="chip chip-exception">{batch.summary.exception} exception</span>
              {batch.summary.rejected > 0 && <span className="chip chip-neutral">{batch.summary.rejected} rejected</span>}
            </div>
            <div className="small muted" style={{ marginTop: 6 }}>
              <span className="mono">{batch.batch_id}</span> · rules {batch.config_file} v{batch.config_version} ·
              mapping {batch.mapping_file}
            </div>
            {batch.warnings.length > 0 && (
              <details style={{ marginTop: 6 }}>
                <summary className="small" style={{ color: "var(--inv-ink)", cursor: "pointer" }}>
                  {batch.warnings.length} data warning{batch.warnings.length === 1 ? "" : "s"}
                </summary>
                <ul className="small" style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                  {batch.warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              </details>
            )}
          </div>
          <div style={{ padding: 8, paddingTop: 0 }}>
            {batch.items.map((it, i) => (
              <button
                key={it.request_id}
                className="scenario"
                aria-pressed={!!it.run_id && it.run_id === selectedRunId}
                onClick={() => onOpen(it, batch)}
              >
                <span className="num">{i + 1}</span>
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span className="t" style={{ display: "block" }}>{it.request_id}</span>
                  <span style={{ display: "block", margin: "3px 0" }}>
                    {it.overall ? <OutcomeChip outcome={it.overall} /> : <span className="chip chip-neutral">REJECTED</span>}
                  </span>
                  <span className="d" style={{ display: "block" }}>
                    {it.scenario_title || it.customer_name || "—"}
                  </span>
                  <span className="d" style={{ display: "block" }}>
                    {it.error
                      ? it.error.code
                      : it.exceptions.length
                        ? it.exceptions.map((e) => `${e.rule_id} ${e.exception_type}`).join(", ")
                        : "No exceptions"}
                  </span>
                </span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
