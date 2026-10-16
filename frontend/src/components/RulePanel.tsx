import { useEffect, useRef, useState } from "react";
import type { ApiErrorBody, ConfigPayload, ValidationResult } from "../types";
import { IconFile, IconPlay, fmtTime } from "./ui";

function Yaml({ text, hotRules }: { text: string; hotRules: Set<string> }) {
  const ref = useRef<HTMLPreElement>(null);
  useEffect(() => {
    // Jump to the first rule that raised an exception in the current run.
    ref.current?.querySelector(".hl")?.scrollIntoView({ block: "center" });
  }, []);
  let inHot = false;
  return (
    <pre ref={ref} className="yaml" aria-label="Rule configuration YAML">
      {text.split("\n").map((line, i) => {
        const id = line.match(/^\s*-\s*id:\s*([A-Z]+-\d+)/)?.[1];
        if (id) inHot = hotRules.has(id);
        else if (/^\S/.test(line)) inHot = false;
        const comment = line.trimStart().startsWith("#");
        return (
          <span key={i} className={inHot ? "hl" : undefined} style={{ display: "block" }}>
            <span className="ln">{i + 1}</span>
            <span className={comment ? "cm" : undefined}>{line || " "}</span>
          </span>
        );
      })}
    </pre>
  );
}

export function RulePanel({ config, configError, result, onRerun, busy }: {
  config: ConfigPayload | null;
  configError: ApiErrorBody | null;
  result: ValidationResult | null;
  onRerun: () => void;
  busy: boolean;
}) {
  const [showYaml, setShowYaml] = useState(false);
  const changed = !!(config && result && config.sha256 !== result.config_hash);
  const hot = new Set((result?.findings ?? []).filter((f) => f.result === "EXCEPTION").map((f) => f.rule_id));
  const evals = new Map((result?.rule_evaluations ?? []).map((e) => [e.rule_id, e]));

  return (
    <div className="card">
      <div className="card-h">
        <h2>External rule configuration</h2>
        <div className="right">
          {config && <button className="btn btn-sm" onClick={() => setShowYaml((v) => !v)}><IconFile size={14} />{showYaml ? "Hide" : "View"} YAML</button>}
        </div>
      </div>
      <div className="card-b" style={{ display: "grid", gap: 12 }}>
        {configError && (
          <div className="err" role="alert">
            <strong>Rule file rejected: {configError.message}</strong>
            <ul>{configError.details.map((d, i) => <li key={i}>{d.location ? <code>{d.location}</code> : null} {d.message}{d.line ? ` (line ${d.line})` : ""}</li>)}</ul>
            <div className="small" style={{ marginTop: 6 }}>Fix the YAML and re-run. Nothing is evaluated with an invalid rule set.</div>
          </div>
        )}
        {config && (
          <>
            <div className="ruleset-head">
              <span className="name">{config.ruleset.name}</span>
              <span className="small muted">
                <code>config/rules/{config.file}</code> · v{config.ruleset.version} · sha256 <code>{config.short_hash}</code>
              </span>
              <span className="small muted">Read from disk on every run · loaded {fmtTime(config.loaded_at)}</span>
            </div>
            {changed && (
              <div className="changed-banner" role="status">
                <strong>Rule file changed since this run.</strong>
                <span>Run used v{result!.config_version} ({result!.config_hash.slice(0, 12)}); file is now v{config.ruleset.version} ({config.short_hash}). No code was changed.</span>
                <div><button className="btn btn-primary btn-sm" onClick={onRerun} disabled={busy}><IconPlay size={13} />Re-run with new rules</button></div>
              </div>
            )}
            <div>
              {config.rules.map((r) => {
                const ev = evals.get(r.id);
                const outcome = ev && !changed
                  ? ev.status === "EVALUATED" ? `${ev.checks} check${ev.checks === 1 ? "" : "s"} · ${ev.exceptions} exc.` : ev.status.replace("_", " ").toLowerCase()
                  : null;
                return (
                  <div key={r.id} className={`rule ${r.enabled ? "" : "off"}`}>
                    <span><span className="id">{r.id}</span> <span className="small muted">v{r.version} · {r.type}</span></span>
                    <span style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      {outcome && <span className="small" style={{ color: hot.has(r.id) ? "var(--exc-ink)" : "var(--text-3)", fontWeight: hot.has(r.id) ? 700 : 400 }}>{outcome}</span>}
                      <span className={`state ${r.enabled ? "on" : "off"}`}>{r.enabled ? "ENABLED" : "DISABLED"}</span>
                    </span>
                    <span className="desc">{r.description}</span>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
      {config && showYaml && (
        <div className="overlay" role="dialog" aria-modal="true" aria-label="Rule configuration" onClick={() => setShowYaml(false)}>
          <div className="card modal" onClick={(e) => e.stopPropagation()}>
            <div className="card-h">
              <h2>config/rules/{config.file} · v{config.ruleset.version} · sha256 {config.short_hash}</h2>
              <div className="right">
                <span className="small muted">Read-only view. Edit the file on disk, then re-run.</span>
                <button className="btn btn-sm" onClick={() => setShowYaml(false)}>Close</button>
              </div>
            </div>
            <Yaml text={config.raw_yaml} hotRules={hot} />
          </div>
        </div>
      )}
    </div>
  );
}
