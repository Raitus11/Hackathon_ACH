import { useEffect, useState } from "react";
import { api } from "../api";
import type { UsagePayload, UsageRecord } from "../types";
import { IconSpark, fmtTime } from "./ui";

const SERIES = [
  { key: "uncached_input_tokens" as const, label: "Input (uncached)", color: "var(--series-1)" },
  { key: "cached_input_tokens" as const, label: "Input (prompt cache read)", color: "var(--series-2)" },
  { key: "output_tokens" as const, label: "Output", color: "var(--series-3)" },
];

const n = (v: number) => v.toLocaleString();
const usd = (v: number) => `$${v.toFixed(v < 0.01 ? 5 : 4)}`;

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="tile">
      <div className="tile-l">{label}</div>
      <div className="tile-v">{value}</div>
      {sub && <div className="tile-s">{sub}</div>}
    </div>
  );
}

function Chart({ rows }: { rows: UsageRecord[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const data = rows.slice(-24);
  const max = Math.max(1, ...data.map((r) => r.uncached_input_tokens + r.cached_input_tokens + r.output_tokens));
  const H = 220, W = Math.max(480, data.length * 44), padL = 48, padB = 26, plotH = H - padB - 8;
  const bw = Math.min(26, (W - padL) / data.length - 10);
  const y = (v: number) => (v / max) * plotH;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => Math.round(max * t));
  return (
    <div style={{ position: "relative", overflowX: "auto" }}>
      <svg width={W} height={H} role="img" aria-label="Tokens per extraction request, stacked by type">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={padL} x2={W} y1={8 + plotH - y(t)} y2={8 + plotH - y(t)} stroke="var(--line)" />
            <text x={padL - 6} y={8 + plotH - y(t) + 4} textAnchor="end" fontSize="11" fill="var(--text-3)">{n(t)}</text>
          </g>
        ))}
        {data.map((r, i) => {
          const x = padL + 8 + i * ((W - padL - 8) / data.length);
          let base = 8 + plotH;
          const segs = SERIES.map((s) => ({ ...s, v: r[s.key] })).filter((s) => s.v > 0);
          return (
            <g key={r.call_id} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect x={x - 6} y={8} width={bw + 12} height={plotH} fill="transparent" />
              {r.local_cache_hit ? (
                <rect x={x} y={8 + plotH - 14} width={bw} height={14} rx={3} fill="none" stroke="var(--series-2)" strokeDasharray="3 2" />
              ) : segs.map((s, k) => {
                const h = Math.max(1, y(s.v) - (k < segs.length - 1 ? 2 : 0));
                base -= y(s.v);
                return <rect key={s.key} x={x} y={base + (k < segs.length - 1 ? 2 : 0)} width={bw} height={h}
                             rx={k === segs.length - 1 ? 4 : 0} fill={s.color} opacity={hover === null || hover === i ? 1 : 0.45} />;
              })}
              <text x={x + bw / 2} y={H - 8} textAnchor="middle" fontSize="10.5" fill="var(--text-3)">#{rows.length - data.length + i + 1}</text>
            </g>
          );
        })}
      </svg>
      {hover !== null && data[hover] && (
        <div className="tip" style={{ left: Math.min(padL + hover * ((W - padL) / data.length), W - 240) }}>
          <strong>#{rows.length - data.length + hover + 1} · {data[hover].request_id}</strong>
          <div className="small muted">{fmtTime(data[hover].timestamp)}</div>
          {data[hover].local_cache_hit
            ? <div>Local response cache hit · 0 tokens<br />saved {n((data[hover].tokens_saved_input ?? 0) + (data[hover].tokens_saved_output ?? 0))}</div>
            : SERIES.map((s) => (
              <div key={s.key} className="tip-row"><span className="sw" style={{ background: s.color }} />{s.label}<b>{n(data[hover][s.key])}</b></div>
            ))}
          <div className="tip-row">Est. cost<b>{usd(data[hover].estimated_cost_usd)}</b></div>
        </div>
      )}
    </div>
  );
}

export function TokenView({ refreshKey, personaId }: { refreshKey: number; personaId: string }) {
  const [data, setData] = useState<UsagePayload | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const load = () => api.llmUsage().then(setData).catch(() => setData(null));
  useEffect(() => { load(); }, [refreshKey]);

  if (!data) return <div className="page"><div className="card empty"><h2>No usage data</h2></div></div>;
  const s = data.summary;
  const rows = [...data.records].reverse(); // oldest first for the chart
  const p = data.status.pricing_per_million;
  return (
    <div className="page viz-root" style={{ display: "grid", gap: 16 }}>
      <div className="card">
        <div className="card-h">
          <span className="ai-tag"><IconSpark size={13} />AI-ASSISTED</span>
          <h2>Token analysis · Document Extraction Agent</h2>
          <div className="right">
            <span className={data.status.simulated ? "det-tag" : "ai-tag"}>{data.status.label}</span>
            <span className="small muted">{data.status.model} · {data.status.prompt_version}</span>
            <button className="btn btn-sm" onClick={async () => {
              const r = await api.clearLlmCache(personaId); setMsg(`Cleared ${r.entries_removed} cached response(s); next run is a cold call.`); load();
            }}>Clear caches</button>
          </div>
        </div>
        <div className="card-b small muted">
          Only one agent calls the LLM, so all tokens below belong to document extraction. Two caches reduce cost:
          <strong> provider prompt caching</strong> (the long, fixed system prompt is reused across documents, so it is read from cache)
          and the <strong>local response cache</strong> (an identical document + prompt version + model returns the stored extraction with zero tokens).
          {data.status.simulated
            ? " LLM is OFF (ACH_LLM_MODE=deterministic): no gateway call is made; token counts are estimates (≈4 chars/token) of what the call would use, and prompt caching is simulated. Set ACH_LLM_MODE=llm in .env to use the gateway."
            : " LLM is ON (ACH_LLM_MODE=llm): figures are the gateway's reported usage."}
          {msg && <div style={{ marginTop: 6, color: "var(--info-ink)" }}>{msg}</div>}
        </div>
      </div>

      <div className="tiles">
        <Tile label="Extraction requests" value={n(s.requests)} sub={`${n(s.llm_calls)} LLM calls · ${n(s.local_cache_hits)} local cache hits`} />
        <Tile label="Input tokens" value={n(s.input_tokens)} sub={`${n(s.uncached_input_tokens)} uncached`} />
        <Tile label="Cached input tokens" value={n(s.cached_input_tokens)} sub={`${(s.prompt_cache_hit_rate * 100).toFixed(1)}% of input from prompt cache`} />
        <Tile label="Output tokens" value={n(s.output_tokens)} sub={`avg latency ${s.avg_latency_ms} ms`} />
        <Tile label="Tokens avoided" value={n(s.tokens_saved_by_local_cache)} sub="by local response cache" />
        <Tile label="Est. cost (illustrative)" value={usd(s.estimated_cost_usd)} sub={`vs ${usd(s.cost_without_caching_usd)} without caching · saved ${usd(s.savings_usd)}`} />
      </div>

      <div className="card">
        <div className="card-h">
          <h2>Tokens per extraction request</h2>
          <div className="right legend">
            {SERIES.map((x) => <span key={x.key}><span className="sw" style={{ background: x.color }} />{x.label}</span>)}
            <span><span className="sw dashed" />Local cache hit (0 tokens)</span>
          </div>
        </div>
        <div className="card-b">{rows.length ? <Chart rows={rows} /> : <span className="muted">Run a scenario that has an authorization form (1–4) to see usage.</span>}</div>
      </div>

      <div className="card">
        <div className="card-h"><h2>Call log</h2><div className="right small muted">{data.status.pricing_note} In ${p.input ?? 0}/M · cached ${p.cached_input ?? 0}/M · out ${p.output ?? 0}/M</div></div>
        <table className="table">
          <thead><tr><th>Time</th><th>Run / request</th><th>Cache</th><th style={{ textAlign: "right" }}>Input</th><th style={{ textAlign: "right" }}>Cached in</th>
            <th style={{ textAlign: "right" }}>Cache write</th><th style={{ textAlign: "right" }}>Output</th><th style={{ textAlign: "right" }}>Latency</th><th style={{ textAlign: "right" }}>Est. cost</th></tr></thead>
          <tbody>
            {data.records.map((r) => (
              <tr key={r.call_id}>
                <td style={{ whiteSpace: "nowrap" }}>{fmtTime(r.timestamp)}</td>
                <td className="mono small">{r.run_id}<div className="src">{r.request_id} · {r.document_id}</div></td>
                <td>{r.local_cache_hit ? <span className="chip chip-pass">LOCAL HIT</span>
                  : r.cached_input_tokens > 0 ? <span className="chip chip-pass">PROMPT CACHE</span>
                  : <span className="chip chip-neutral">COLD</span>}</td>
                <td className="num">{n(r.input_tokens)}</td>
                <td className="num">{n(r.cached_input_tokens)}</td>
                <td className="num">{n(r.cache_write_tokens)}</td>
                <td className="num">{n(r.output_tokens)}</td>
                <td className="num">{r.latency_ms} ms</td>
                <td className="num">{usd(r.estimated_cost_usd)}</td>
              </tr>
            ))}
            {data.records.length === 0 && <tr><td colSpan={9} className="muted">No calls yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
