"""Agent pipeline orchestrator. Six single-responsibility agents run in a fixed order.

Only the Document Extraction Agent uses an LLM, and its output is advisory: the Rule Engine Agent
never reads it. PASS/EXCEPTION comes from the deterministic rule engine alone, and no agent can
approve anything — that remains the independent checker's decision.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from .config import LoadedConfig
from .engine import evaluate
from .ingest import IngestError, match_records, parse_inputs, build_case
from .llm import ExtractionService
from .models import AgentStep, DocumentExtraction, MaintenanceCase, ValidationResult


@dataclass(frozen=True)
class PipelineRun:
    result: ValidationResult
    case: MaintenanceCase
    extraction: DocumentExtraction
    steps: tuple[AgentStep, ...]


class _Timer:
    def __enter__(self) -> "_Timer":
        self.t = time.perf_counter()
        return self

    def __exit__(self, *_: Any) -> None:
        self.ms = round((time.perf_counter() - self.t) * 1000, 2)


def run_pipeline(request_data: Any, change_data: Any, document_text: str | None, cfg: LoadedConfig,
                 extractor: ExtractionService, scenario_id: str | None = None) -> PipelineRun:
    run_id = f"RUN-{uuid.uuid4().hex[:12].upper()}"
    steps: list[AgentStep] = []

    def step(agent: str, responsibility: str, kind: str, status: str, ms: float, summary: str, output: dict) -> None:
        steps.append(AgentStep(order=len(steps) + 1, agent=agent, responsibility=responsibility, kind=kind,  # type: ignore[arg-type]
                               status=status, duration_ms=ms, summary=summary, output=output))  # type: ignore[arg-type]

    # 1. Intake Agent — schema validation of both synthetic inputs.
    with _Timer() as t:
        request, change = parse_inputs(request_data, change_data)
    step("Intake Agent", "Schema-validate the request and the TNAL/GPS change record", "DETERMINISTIC", "OK", t.ms,
         f"Request {request.request_id} and change {change.change_id} passed schema validation.",
         {"request_id": request.request_id, "change_id": change.change_id,
          "requested_fields": [c.field for c in request.requested_changes],
          "tnal_rows": len(change.tnal_entries), "gps_rows": len(change.gps_changes)})

    # 2. Matcher Agent — pair the change record with the request and build the canonical model.
    with _Timer() as t:
        match_records(request, change)
        case = build_case(request_data, change_data)
    step("Matcher Agent", "Match the change record to its request and normalise to the canonical model", "DETERMINISTIC",
         "OK", t.ms, f"Matched on request_id {request.request_id} and customer_id {request.customer_id}.",
         {"join_keys": ["request_id", "customer_id"], "input_digest": case.input_digest,
          "implemented_fields": sorted(case.implemented)})

    # 3. Document Extraction Agent — AI-assisted, advisory only.
    with _Timer() as t:
        extraction = extractor.extract(document_text, request, cfg.ruleset, run_id)
    if extraction.status == "EXTRACTED":
        summary = (f"Extracted {len(extraction.fields)} field(s) from the authorization form "
                   f"({'local cache hit, 0 tokens' if extraction.cache == 'HIT_LOCAL' else ('deterministic parser, LLM off' if extraction.simulated else 'LLM call')}); "
                   f"{extraction.disagreements} differ from the request, {extraction.low_confidence} low-confidence. "
                   "Advisory — not used by the rule engine.")
        status = "OK"
    elif extraction.status == "NO_DOCUMENT":
        summary, status = "No authorization form on file; nothing to extract.", "NO_DOCUMENT"
    else:
        summary, status = f"Extraction failed ({extraction.error}). Deterministic validation continues unaffected.", "FAILED"
    step("Document Extraction Agent", "Read the synthetic authorization form and transcribe it for the checker",
         "DETERMINISTIC" if extraction.simulated else "AI_ASSISTED", status, t.ms, summary,
         {"provider": extraction.provider, "model": extraction.model, "simulated": extraction.simulated,
          "cache": extraction.cache, "document_id": extraction.document_id,
          "used_by_rule_engine": False})

    # 4. Rule Engine Agent — the only component that produces PASS / EXCEPTION.
    with _Timer() as t:
        result = evaluate(case, cfg, scenario_id=scenario_id, run_id=run_id)
    evaluated = [e for e in result.rule_evaluations if e.status == "EVALUATED"]
    step("Rule Engine Agent", "Apply the external YAML rules deterministically", "DETERMINISTIC",
         "EXCEPTIONS_FOUND" if result.exception_count else "OK", t.ms,
         f"{len(evaluated)} rule(s) evaluated from {result.config_file} v{result.config_version}: "
         f"{result.overall.value} with {result.exception_count} exception(s).",
         {"overall": result.overall.value, "config_sha256": result.config_hash,
          "rules": [{"rule_id": e.rule_id, "status": e.status, "checks": e.checks, "exceptions": e.exceptions}
                    for e in result.rule_evaluations],
          "findings_digest": result.findings_digest})

    # 5. Explainer Agent — reasons come only from configured templates.
    with _Timer() as t:
        reasons = list(result.summary_reasons)
    step("Explainer Agent", "Render every finding into a checker-readable reason from the configured templates",
         "DETERMINISTIC", "OK", t.ms, f"{len(result.findings)} finding(s) explained; {len(reasons)} summary reason(s).",
         {"summary_reasons": reasons})

    # 6. Evidence Agent — traceable, exportable record (decision is appended later by the checker).
    with _Timer() as t:
        manifest = {"run_id": run_id, "input_digest": result.input_digest, "config_sha256": result.config_hash,
                    "findings_digest": result.findings_digest, "exports": ["md", "json"]}
    step("Evidence Agent", "Assemble the traceable evidence pack for export", "DETERMINISTIC", "OK", t.ms,
         "Evidence pack ready. Awaiting the independent checker's decision.", manifest)

    # Handoff contract: what each agent consumed, what it produced, and who receives it.
    src = "authorization_form.txt" if document_text else "no authorization form on file"
    ext_out = (f"{len(extraction.fields)} extracted field(s) + confidence, {extraction.disagreements} cross-check difference(s)"
               if extraction.status == "EXTRACTED" else f"extraction status {extraction.status}")
    handoffs = {
        "Intake Agent": (
            [f"request {request.request_id} (ServiceNow · SIMULATED)", f"change {change.change_id} (TNAL/GPS · SIMULATED)"],
            ["typed, schema-valid MaintenanceRequest", f"typed ImplementedChange ({len(change.tnal_entries)} TNAL rows)"],
            ["Matcher Agent"]),
        "Matcher Agent": (
            ["typed request + typed change"],
            [f"canonical MaintenanceCase (matched on {request.request_id} / {request.customer_id})",
             f"input digest {case.input_digest[:12]}…"],
            ["Document Extraction Agent", "Rule Engine Agent"]),
        "Document Extraction Agent": (
            [src, "request values (for side-by-side cross-check only)"],
            [ext_out],
            ["Independent checker (advisory, never the Rule Engine)"]),
        "Rule Engine Agent": (
            ["canonical MaintenanceCase", f"{result.config_file} v{result.config_version} · sha256 {result.config_hash[:12]}…"],
            [f"{len(result.findings)} immutable finding(s)", f"overall {result.overall.value} ({result.exception_count} exception(s))"],
            ["Explainer Agent"]),
        "Explainer Agent": (
            [f"{len(result.findings)} finding(s) + configured reason templates"],
            [f"{len(result.summary_reasons)} checker-readable reason(s)"],
            ["Evidence Agent"]),
        "Evidence Agent": (
            ["result, inputs, config snapshot"],
            [f"evidence pack manifest · findings digest {result.findings_digest[:12]}…"],
            ["Independent checker (human-approval boundary)"]),
    }
    steps = [s.model_copy(update={"consumes": tuple(handoffs[s.agent][0]), "produces": tuple(handoffs[s.agent][1]),
                                  "hands_to": tuple(handoffs[s.agent][2])}) for s in steps]
    return PipelineRun(result=result, case=case, extraction=extraction, steps=tuple(steps))


__all__ = ["run_pipeline", "PipelineRun", "IngestError"]
