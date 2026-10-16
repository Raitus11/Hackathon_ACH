import type { ReactNode } from "react";
import type { DecisionType, Outcome } from "../types";

type IconProps = { size?: number };
const base = (size: number) => ({
  width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
  strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true,
});

export const IconCheck = ({ size = 16 }: IconProps) => (
  <svg {...base(size)}><circle cx="12" cy="12" r="9" /><path d="m8 12.5 2.6 2.6L16 9.5" /></svg>
);
export const IconAlert = ({ size = 16 }: IconProps) => (
  <svg {...base(size)}><path d="M8.2 3h7.6L21 8.2v7.6L15.8 21H8.2L3 15.8V8.2z" /><path d="M12 7.5v5.5M12 16.5h.01" /></svg>
);
export const IconSearch = ({ size = 16 }: IconProps) => (
  <svg {...base(size)}><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4.2-4.2" /></svg>
);
export const IconLock = ({ size = 16 }: IconProps) => (
  <svg {...base(size)}><rect x="4.5" y="10.5" width="15" height="10" rx="2" /><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" /></svg>
);
export const IconShield = ({ size = 16 }: IconProps) => (
  <svg {...base(size)}><path d="M12 3 5 6v5.5c0 4.4 3 8 7 9.5 4-1.5 7-5.1 7-9.5V6z" /><path d="m9 12 2.2 2.2L15 10.5" /></svg>
);
export const IconPlay = ({ size = 16 }: IconProps) => (
  <svg {...base(size)}><path d="M7 5v14l11-7z" /></svg>
);
export const IconDownload = ({ size = 16 }: IconProps) => (
  <svg {...base(size)}><path d="M12 4v11M7.5 10.5 12 15l4.5-4.5M5 20h14" /></svg>
);
export const IconFile = ({ size = 16 }: IconProps) => (
  <svg {...base(size)}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></svg>
);
export const IconChevron = ({ size = 16, open = false }: IconProps & { open?: boolean }) => (
  <svg {...base(size)} style={{ transform: open ? "rotate(90deg)" : "none", transition: "transform .12s" }}>
    <path d="m9 6 6 6-6 6" />
  </svg>
);
export const IconSpark = ({ size = 16 }: IconProps) => (
  <svg {...base(size)}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18" /></svg>
);
export const IconInfo = ({ size = 16 }: IconProps) => (
  <svg {...base(size)}><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></svg>
);

export function OutcomeChip({ outcome, large }: { outcome: Outcome; large?: boolean }) {
  const pass = outcome === "PASS";
  return (
    <span className={`chip ${pass ? "chip-pass" : "chip-exception"} ${large ? "chip-lg" : ""}`}>
      {pass ? <IconCheck size={large ? 20 : 14} /> : <IconAlert size={large ? 20 : 14} />}
      {outcome}
    </span>
  );
}

export function ResultChip({ result }: { result: "MATCH" | "EXCEPTION" }) {
  return result === "MATCH" ? (
    <span className="chip chip-pass"><IconCheck size={13} />MATCH</span>
  ) : (
    <span className="chip chip-exception"><IconAlert size={13} />EXCEPTION</span>
  );
}

export function DecisionChip({ decision }: { decision: DecisionType | null }) {
  if (!decision) return <span className="chip chip-neutral"><IconLock size={13} />Awaiting checker decision</span>;
  return decision === "APPROVE" ? (
    <span className="chip chip-approve"><IconShield size={13} />APPROVED BY CHECKER</span>
  ) : (
    <span className="chip chip-investigate"><IconSearch size={13} />INVESTIGATE</span>
  );
}

export const SimTag = ({ children = "SIMULATED" }: { children?: ReactNode }) => <span className="sim-tag">{children}</span>;

/** Display a value the way the engine reports it: <absent>, <blank> or the raw string. */
export function shown(value: string | null | undefined): string {
  if (value === null || value === undefined) return "<absent>";
  if (value.trim() === "") return "<blank>";
  return value;
}

/** Highlight the differing middle segment between two strings (common prefix/suffix kept plain). */
export function DiffValue({ value, other, highlight }: { value: string | null; other: string | null; highlight: boolean }) {
  const text = shown(value);
  const placeholder = text.startsWith("<");
  if (!highlight || placeholder || other === null || other.trim() === "") {
    return <span className={`val ${placeholder ? "placeholder" : ""}`}>{text}</span>;
  }
  let p = 0;
  while (p < text.length && p < other.length && text[p] === other[p]) p++;
  let s = 0;
  while (s < text.length - p && s < other.length - p && text[text.length - 1 - s] === other[other.length - 1 - s]) s++;
  const mid = text.slice(p, text.length - s);
  return (
    <span className="val">
      {text.slice(0, p)}
      {mid ? <mark>{mid}</mark> : <mark>&#8203;</mark>}
      {text.slice(text.length - s)}
    </span>
  );
}

export const fmtTime = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "medium" });
