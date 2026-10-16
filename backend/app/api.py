"""HTTP API. Run validation (any persona), record decisions (independent checker only)."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import __version__
from .audit import AuditLog
from .config import ConfigError, LoadedConfig, load_ruleset
from .agents import PipelineRun, run_pipeline
from .csv_ingest import CsvBatchInput, build_batch, load_mapping, schema_description
from .evidence import build_pack, render_markdown
from .exqueue import SIMULATION_LABEL, ExceptionQueue
from .replay import compare, describe, list_config_options, resolve
from .suite import run_suite
from .ingest import IngestError
from .llm import ExtractionService
from .logging_setup import configure_logging, correlation_id
from .models import DecisionInput, DecisionRecord, DocumentExtraction, Persona
from .scenarios import Scenario, load_scenarios
from .settings import Settings, load_settings
from .sod import SodViolation, check_decision_allowed, load_personas, open_exception_rules
from .store import RunStore

log = logging.getLogger("ach.api")

SIMULATED_SYSTEMS = [
    {"name": "ServiceNow / Fulfillment Platform", "role": "Maintenance request (expected values)", "status": "SIMULATED — synthetic JSON file"},
    {"name": "DMS", "role": "Supporting-document evidence indicators", "status": "SIMULATED — boolean indicators on the request"},
    {"name": "TNAL Critical Field Audit Log", "role": "Field-level old/new implemented values (actual values)", "status": "SIMULATED — synthetic JSON file"},
    {"name": "GPS Customer Data Change Report", "role": "Summary of customer data changes", "status": "SIMULATED — synthetic JSON file"},
    {"name": "ACH / AES / ACH Customer Database", "role": "Where the maker implements the change", "status": "NOT INTEGRATED — represented only by the TNAL/GPS files"},
    {"name": "CheckMate", "role": "Daily validation task and decision capture", "status": "SIMULATED — decision captured in this prototype only"},
    {"name": "LLM gateway", "role": "Document Extraction Agent only", "status": "SIMULATED offline mock by default; live gateway optional via config/llm.yaml"},
]

ASSUMPTIONS = [
    "All data is synthetic and pending organizer assets; customers, people and values are fictional.",
    "A change record is matched to a request by request_id, and customer_id must also agree.",
    "The request is the source of expected values; the TNAL record is the source of actual values.",
    "If a field changed more than once, the latest TNAL row is the implemented value.",
    "A missing or blank requested field is reported once, as MISSING_FIELD, not again as a mismatch.",
    "An unauthorized change is any TNAL field whose value changed and that was not in the request.",
    "Evidence is represented by boolean indicators; which indicators are required is set in the rule config.",
    "Identity is a persona header for demonstration. The maker of a change can never record its decision.",
    "The checker may Approve an item with exceptions only with explicit acknowledgement and a justification.",
    "The engine outcome is decision support. Nothing is approved without a recorded checker decision.",
    "AI is used by one agent only (document extraction, one synthetic form type). Its output is advisory, "
    "labelled, must be confirmed by the checker, and is never read by the rule engine.",
    "No volumes, handling times or savings are claimed; baselines have not been provided.",
]


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: str | None = None
    request: dict[str, Any] | None = None
    implemented_change: dict[str, Any] | None = None
    document_text: str | None = Field(default=None, max_length=20_000)

    @model_validator(mode="after")
    def _one_source(self) -> "RunRequest":
        has_files = self.request is not None or self.implemented_change is not None
        if bool(self.scenario_id) == has_files:
            raise ValueError("provide either scenario_id, or both request and implemented_change")
        if has_files and (self.request is None or self.implemented_change is None):
            raise ValueError("both request and implemented_change are required")
        return self


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: str | None = None
    request: dict[str, Any] | None = None
    implemented_change: dict[str, Any] | None = None
    baseline: str = Field(min_length=1, max_length=200)
    candidate: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _one_source(self) -> "CompareRequest":
        has_files = self.request is not None and self.implemented_change is not None
        if bool(self.scenario_id) == has_files:
            raise ValueError("provide either scenario_id, or both request and implemented_change")
        return self


class CsvFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    content: str = Field(max_length=5 * 1024 * 1024)


class CsvBatchRequest(BaseModel):
    """The team's CSV input set, sent as text (the browser reads the files; no multipart needed)."""
    model_config = ConfigDict(extra="forbid")
    files: list[CsvFile] = Field(min_length=1, max_length=8)


_BATCH_ID = re.compile(r"^BATCH-[0-9A-F]{12}$")


def _error(status: int, code: str, message: str, details: list | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, "details": details or []}})


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging()
    audit = AuditLog(settings.audit_path)
    store = RunStore(settings.runs_dir)
    personas = load_personas(settings.personas_path)
    extractor = ExtractionService(settings.llm_config_path, settings.runtime_dir, env_path=settings.env_path)
    configs_dir = settings.runtime_dir / "configs"
    configs_dir.mkdir(parents=True, exist_ok=True)
    samples_dir = settings.rules_path.parent / "samples"
    exq = ExceptionQueue(settings.runtime_dir / "exception_queue.jsonl")

    app = FastAPI(title="ACH Maker-Checker Validation (prototype)", version=__version__)

    def scenarios() -> dict[str, Scenario]:
        return {s.id: s for s in load_scenarios(settings.scenarios_dir)}

    def current_config() -> LoadedConfig:
        cfg = load_ruleset(settings.rules_path)  # re-read every time: hot reload by design
        snapshot = configs_dir / f"{cfg.sha256}.yaml"
        if not snapshot.exists():
            snapshot.write_text(cfg.raw_text, encoding="utf-8")
        return cfg

    def persona(persona_id: str | None) -> Persona:
        if not persona_id or persona_id not in personas:
            raise SodViolation("UNKNOWN_PERSONA", "Select a known test persona (X-Persona-Id header).", status=401)
        return personas[persona_id]

    # ------------------------------------------------------------- middleware and errors

    @app.middleware("http")
    async def _correlation(request: Request, call_next):
        cid = request.headers.get("X-Correlation-Id") or uuid.uuid4().hex[:16]
        token = correlation_id.set(cid)
        try:
            response = await call_next(request)
        finally:
            correlation_id.reset(token)
        response.headers["X-Correlation-Id"] = cid
        response.headers["X-Data-Classification"] = "SYNTHETIC"
        return response

    @app.exception_handler(ConfigError)
    async def _config_error(_: Request, exc: ConfigError):
        return _error(422, "CONFIG_INVALID", exc.message, exc.details)

    @app.exception_handler(IngestError)
    async def _ingest_error(_: Request, exc: IngestError):
        return _error(422, exc.code, exc.message, exc.details)

    @app.exception_handler(SodViolation)
    async def _sod_error(_: Request, exc: SodViolation):
        return _error(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        details = [{"location": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()]
        return _error(422, "REQUEST_INVALID", "Request body failed validation", details)

    # ------------------------------------------------------------- reference data

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__, "data_classification": "SYNTHETIC"}

    @app.get("/api/meta")
    def meta() -> dict:
        return {
            "app_name": "ACH Maker-Checker Validation Workbench",
            "control_id": "C-247489",
            "control_name": "ACH DB Next Day Validation",
            "label": "SYNTHETIC DATA · SIMULATED SYSTEMS · PROTOTYPE — NOT PRODUCTION",
            "simulated_systems": SIMULATED_SYSTEMS,
            "assumptions": ASSUMPTIONS,
            "personas": [p.model_dump() for p in personas.values()],
        }

    @app.get("/api/scenarios")
    def list_scenarios() -> list[dict]:
        return [
            {
                "id": s.id, "folder": s.folder, "name": s.name, "seeded_condition": s.seeded_condition,
                "organizer_expected_outcome": s.organizer_expected_outcome,
                "request_id": s.request.get("request_id"), "customer_name": s.request.get("customer_name"),
                "implemented_by": s.change.get("implemented_by"), "expected_overall": s.expected.get("overall"),
            }
            for s in scenarios().values()
        ]

    @app.get("/api/scenarios/{scenario_id}")
    def get_scenario(scenario_id: str) -> Any:
        s = scenarios().get(scenario_id)
        if not s:
            return _error(404, "SCENARIO_NOT_FOUND", f"No scenario {scenario_id}")
        return {"id": s.id, "name": s.name, "seeded_condition": s.seeded_condition, "data_note": s.data_note,
                "organizer_expected_outcome": s.organizer_expected_outcome,
                "request": s.request, "implemented_change": s.change, "expected": s.expected}

    @app.get("/api/config")
    def get_config() -> dict:
        cfg = current_config()
        rs = cfg.ruleset
        return {
            "file": cfg.path.name,
            "sha256": cfg.sha256,
            "short_hash": cfg.short_hash,
            "loaded_at": cfg.loaded_at.isoformat(),
            "ruleset": rs.ruleset.model_dump(),
            "fields": {k: v.model_dump() for k, v in rs.fields.items()},
            "rules": [r.model_dump() for r in rs.rules],
            "raw_yaml": cfg.raw_text,
        }

    def config_options():
        current_config()  # ensure the active file's snapshot exists
        recent = [(r.config_hash, r.run_id, r.evaluated_at.isoformat()) for r in store.list_runs()]
        return list_config_options(settings.rules_path, samples_dir, configs_dir, recent)

    @app.get("/api/configs")
    def list_configs() -> list[dict]:
        out = []
        for o in config_options():
            try:
                cfg = load_ruleset(o.path)
                out.append({**describe(cfg, o.key, [o]), "valid": True})
            except ConfigError as exc:
                out.append({"key": o.key, "kind": o.kind, "label": o.label, "valid": False, "error": exc.message})
        return out

    @app.post("/api/compare")
    def compare_configs(body: CompareRequest, x_persona_id: str | None = Header(default=None)) -> Any:
        if body.scenario_id:
            s = scenarios().get(body.scenario_id)
            if not s:
                return _error(404, "SCENARIO_NOT_FOUND", f"No scenario {body.scenario_id}")
            request_data, change_data = s.request, s.change
        else:
            request_data, change_data = body.request, body.implemented_change
        options = config_options()
        base, cand = resolve(body.baseline, options), resolve(body.candidate, options)
        out = compare(request_data, change_data, base, cand, scenario_id=body.scenario_id)
        out["baseline"] = describe(base, body.baseline, options)
        out["candidate"] = describe(cand, body.candidate, options)
        audit.append("RULE_VERSION_COMPARISON", run_id=None, actor=x_persona_id, payload={
            "scenario_id": body.scenario_id, "request_id": out["request_id"], "input_digest": out["input_digest"],
            "baseline": {"version": out["baseline"]["version"], "sha256": base.sha256,
                         "overall": out["baseline_result"]["overall"]},
            "candidate": {"version": out["candidate"]["version"], "sha256": cand.sha256,
                          "overall": out["candidate_result"]["overall"]},
            "changed_findings": out["changed_findings"]})
        return out

    @app.post("/api/scenarios/suite")
    def scenario_suite(x_persona_id: str | None = Header(default=None)) -> dict:
        cfg = current_config()
        out = run_suite(list(scenarios().values()), cfg)
        audit.append("SCENARIO_SUITE_RUN", run_id=None, actor=x_persona_id, payload={
            "config_version": cfg.ruleset.ruleset.version, "config_sha256": cfg.sha256, **out["summary"]})
        return out

    @app.get("/api/queue")
    def get_queue() -> dict:
        return {"label": SIMULATION_LABEL, "items": exq.read()}

    @app.get("/api/metrics")
    def metrics() -> dict:
        events = audit.read()
        runs = [e for e in events if e["event_type"] == "VALIDATION_RUN_COMPLETED"]
        by_rule: dict[str, int] = {}
        for e in runs:
            for rid in e["payload"].get("exception_rules", []):
                by_rule[rid] = by_rule.get(rid, 0) + 1
        decisions = [e for e in events if e["event_type"] == "CHECKER_DECISION_RECORDED"]
        blocked = [e for e in events if e["event_type"] == "DECISION_BLOCKED"]
        durations = [sum(st.get("duration_ms", 0) for st in store.extras(r.run_id).get("pipeline", []))
                     for r in store.list_runs()]
        return {
            "runs": len(runs),
            "pass": sum(1 for e in runs if e["payload"].get("engine_outcome") == "PASS"),
            "exception": sum(1 for e in runs if e["payload"].get("engine_outcome") == "EXCEPTION"),
            "exceptions_by_rule": dict(sorted(by_rule.items())),
            "decisions": {"APPROVE": sum(1 for e in decisions if e["payload"].get("decision") == "APPROVE"),
                          "INVESTIGATE": sum(1 for e in decisions if e["payload"].get("decision") == "INVESTIGATE")},
            "blocked_attempts": len(blocked),
            "self_approval_blocked": sum(1 for e in blocked if e["payload"].get("code") == "SELF_APPROVAL_BLOCKED"),
            "routed_to_queue": sum(1 for e in events if e["event_type"] == "EXCEPTION_ROUTED_SIMULATED"),
            "avg_run_ms": round(sum(durations) / len(durations), 2) if durations else None,
            "note": "Prototype counters derived from the local audit log. Not a monitoring platform.",
        }

    # ------------------------------------------------------------- validation

    @app.post("/api/runs")
    def run_validation(body: RunRequest, x_persona_id: str | None = Header(default=None)) -> Any:
        actor = personas.get(x_persona_id or "")
        if body.scenario_id:
            s = scenarios().get(body.scenario_id)
            if not s:
                return _error(404, "SCENARIO_NOT_FOUND", f"No scenario {body.scenario_id}")
            request_data, change_data, scenario_id, document = s.request, s.change, s.id, s.document_text
        else:
            request_data, change_data, scenario_id = body.request, body.implemented_change, None
            document = body.document_text

        cfg = current_config()
        pipe = run_pipeline(request_data, change_data, document, cfg, extractor, scenario_id=scenario_id)
        extras = complete_run(pipe, cfg, actor.id if actor else None, scenario_id)
        return {"result": pipe.result.model_dump(mode="json"), "decision": None, **extras}

    def complete_run(pipe: PipelineRun, cfg: LoadedConfig, actor_id: str | None, scenario_id: str | None,
                     source: dict | None = None) -> dict:
        """Persist a pipeline run and write its audit event. Shared by single runs and CSV batches."""
        result, case = pipe.result, pipe.case
        extras: dict[str, Any] = {"extraction": pipe.extraction.model_dump(mode="json"),
                                  "pipeline": [s.model_dump(mode="json") for s in pipe.steps]}
        if source:
            extras["source"] = source
        store.save_run(result, case, extras)
        audit.append(
            "VALIDATION_RUN_COMPLETED",
            run_id=result.run_id,
            actor=actor_id,
            payload={
                "scenario_id": scenario_id,
                "source": source,
                "request_id": result.request_id,
                "change_id": result.change_id,
                "engine_outcome": result.overall.value,
                "exception_rules": open_exception_rules(result),
                "config_file": result.config_file,
                "config_version": result.config_version,
                "config_sha256": result.config_hash,
                "input_digest": result.input_digest,
                "findings_digest": result.findings_digest,
                "agents": [f"{s.agent}:{s.status}" for s in pipe.steps],
                "ai_extraction": {"status": pipe.extraction.status, "provider": pipe.extraction.provider,
                                  "simulated": pipe.extraction.simulated, "cache": pipe.extraction.cache,
                                  "disagreements": pipe.extraction.disagreements,
                                  "used_by_rule_engine": False},
            },
        )
        log.info("validation run completed", extra={"run_id": result.run_id, "outcome": result.overall.value,
                                                   "config_hash": cfg.short_hash})
        return extras

    # ------------------------------------------------------------- CSV input set (team export, 4 files)

    batches_dir = settings.batches_dir
    batches_dir.mkdir(parents=True, exist_ok=True)

    @app.get("/api/csv/schema")
    def csv_schema() -> dict:
        mapping = load_mapping(settings.csv_mapping_path)
        by_key: dict[str, list[str]] = {}
        for code, key in mapping.field_codes.items():
            by_key.setdefault(key, []).append(code)
        return {"files": schema_description(), "mapping_file": settings.csv_mapping_path.name,
                "mapping_sha256": mapping.sha256, "field_codes": by_key}

    @app.post("/api/csv/batches")
    def csv_batch(body: CsvBatchRequest, x_persona_id: str | None = Header(default=None)) -> Any:
        actor = personas.get(x_persona_id or "")
        mapping = load_mapping(settings.csv_mapping_path)  # re-read every upload, like the rule file
        batch: CsvBatchInput = build_batch([(f.name, f.content.encode("utf-8")) for f in body.files], mapping)
        cfg = current_config()
        batch_id = f"BATCH-{uuid.uuid4().hex[:12].upper()}"

        items: list[dict[str, Any]] = []
        for case in batch.cases:
            item: dict[str, Any] = {"request_id": case.request_id, "scenario_key": case.scenario_key,
                                    "scenario_title": case.scenario_title, "run_id": None, "overall": None,
                                    "exception_count": 0, "exceptions": [], "error": None}
            source = {"kind": "CSV_BATCH", "batch_id": batch_id, "request_id": case.request_id}
            try:
                pipe = run_pipeline(case.request, case.implemented_change, None, cfg, extractor)
            except IngestError as exc:
                item["error"] = {"code": exc.code, "message": exc.message, "details": exc.details}
                audit.append("CSV_REQUEST_REJECTED", run_id=None, actor=actor.id if actor else None,
                             payload={**source, "code": exc.code, "details": exc.details})
                items.append(item)
                continue
            complete_run(pipe, cfg, actor.id if actor else None, None, source)
            r = pipe.result
            item.update({
                "run_id": r.run_id, "overall": r.overall.value, "exception_count": r.exception_count,
                "customer_name": r.customer_name,
                "exceptions": [{"rule_id": f.rule_id, "field": f.field, "field_label": f.field_label,
                                "exception_type": f.exception_type.value if f.exception_type else None,
                                "reason": f.reason}
                               for f in r.findings if f.exception_type is not None],
            })
            items.append(item)

        by_rule: dict[str, int] = {}
        for it in items:
            for e in it["exceptions"]:
                by_rule[e["rule_id"]] = by_rule.get(e["rule_id"], 0) + 1
        summary = {
            "requests": len(items),
            "pass": sum(1 for i in items if i["overall"] == "PASS"),
            "exception": sum(1 for i in items if i["overall"] == "EXCEPTION"),
            "rejected": sum(1 for i in items if i["error"]),
            "exceptions_by_rule": dict(sorted(by_rule.items())),
        }
        out = {
            "batch_id": batch_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "actor": actor.id if actor else None,
            "files": batch.files,
            "mapping_file": settings.csv_mapping_path.name,
            "mapping_sha256": batch.mapping_sha256,
            "config_file": cfg.path.name,
            "config_version": cfg.ruleset.ruleset.version,
            "config_sha256": cfg.sha256,
            "summary": summary,
            "warnings": batch.warnings,
            "items": items,
        }
        (batches_dir / f"{batch_id}.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
        audit.append("CSV_BATCH_VALIDATED", run_id=None, actor=actor.id if actor else None,
                     payload={"batch_id": batch_id, "files": batch.files, "mapping_sha256": batch.mapping_sha256,
                              "config_version": out["config_version"], "config_sha256": cfg.sha256,
                              "warnings": len(batch.warnings), **summary})
        log.info("csv batch validated", extra={"run_id": batch_id, "config_hash": cfg.short_hash})
        return out

    @app.get("/api/csv/batches")
    def list_batches() -> list[dict]:
        out = []
        for p in sorted(batches_dir.glob("BATCH-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:50]:
            try:
                b = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            out.append({"batch_id": b["batch_id"], "created_at": b["created_at"], "summary": b["summary"],
                        "config_version": b["config_version"]})
        return out

    @app.get("/api/csv/batches/{batch_id}")
    def get_batch(batch_id: str) -> Any:
        path = batches_dir / f"{batch_id}.json"
        if not _BATCH_ID.match(batch_id) or not path.is_file():
            return _error(404, "BATCH_NOT_FOUND", f"No batch {batch_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    @app.get("/api/runs")
    def list_runs() -> list[dict]:
        out = []
        for r in store.list_runs():
            d = store.decision(r.run_id)
            out.append({"run_id": r.run_id, "evaluated_at": r.evaluated_at.isoformat(), "scenario_id": r.scenario_id,
                        "request_id": r.request_id, "overall": r.overall.value, "config_version": r.config_version,
                        "config_hash": r.config_hash[:12], "decision": d.decision.value if d else None})
        return out

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> Any:
        found = store.get(run_id)
        if not found:
            return _error(404, "RUN_NOT_FOUND", f"No run {run_id}")
        result, case = found
        d = store.decision(run_id)
        return {"result": result.model_dump(mode="json"), "decision": d.model_dump(mode="json") if d else None,
                **store.extras(run_id),
                "inputs": {"request": case.request.model_dump(mode="json"),
                           "implemented_change": case.change.model_dump(mode="json")}}

    # ------------------------------------------------------------- human decision (approval boundary)

    @app.post("/api/runs/{run_id}/decision")
    def record_decision(run_id: str, body: DecisionInput, x_persona_id: str | None = Header(default=None)) -> Any:
        actor = persona(x_persona_id)
        found = store.get(run_id)
        if not found:
            return _error(404, "RUN_NOT_FOUND", f"No run {run_id}")
        result, _ = found
        ext_data = store.extras(run_id).get("extraction")
        extraction = DocumentExtraction.model_validate(ext_data) if ext_data else None
        try:
            check_decision_allowed(actor, result, body, extraction)
        except SodViolation as exc:
            audit.append("DECISION_BLOCKED", run_id=run_id, actor=actor.id,
                         payload={"code": exc.code, "attempted_decision": body.decision.value, "message": exc.message})
            log.warning("decision blocked", extra={"run_id": run_id, "actor": actor.id, "event": exc.code})
            raise
        record = DecisionRecord(
            decision_id=f"DEC-{uuid.uuid4().hex[:10].upper()}",
            run_id=run_id,
            decision=body.decision,
            actor_id=actor.id,
            actor_name=actor.name,
            actor_role=actor.role,
            comment=body.comment.strip(),
            acknowledged_exceptions=(body.decision.value == "APPROVE" and body.acknowledge_exceptions
                                     and result.exception_count > 0),
            ai_review_confirmed=bool(body.ai_review_confirmed and extraction and extraction.status == "EXTRACTED"),
            engine_outcome=result.overall,
            config_hash=result.config_hash,
            recorded_at=datetime.now(timezone.utc),
        )
        if not store.save_decision(record):
            return _error(409, "DECISION_ALREADY_RECORDED", "A checker decision is already recorded for this run. "
                          "Decisions are write-once; re-run validation to create a new item.")
        audit.append("CHECKER_DECISION_RECORDED", run_id=run_id, actor=actor.id,
                     payload={"decision": record.decision.value, "engine_outcome": result.overall.value,
                              "acknowledged_exceptions": record.acknowledged_exceptions,
                              "ai_review_confirmed": record.ai_review_confirmed, "comment": record.comment})
        routed = None
        if record.decision.value == "INVESTIGATE":
            routed = exq.route(result, record)
            audit.append("EXCEPTION_ROUTED_SIMULATED", run_id=run_id, actor=actor.id,
                         payload={"queue_item_id": routed["queue_item_id"], "routed_to": routed["routed_to"],
                                  "simulated": True, "exceptions": len(routed["exceptions"])})
        return {"decision": record.model_dump(mode="json"), "routed": routed}

    # ------------------------------------------------------------- traceability

    @app.get("/api/audit")
    def get_audit(run_id: str | None = Query(default=None)) -> list[dict]:
        return list(reversed(audit.read(run_id)))

    @app.get("/api/runs/{run_id}/evidence")
    def evidence(run_id: str, format: Literal["json", "md"] = "json") -> Response:
        found = store.get(run_id)
        if not found:
            return _error(404, "RUN_NOT_FOUND", f"No run {run_id}")
        result, case = found
        snapshot = configs_dir / f"{result.config_hash}.yaml"
        pack = build_pack(result, case, store.decision(run_id), audit.read(run_id),
                          snapshot.read_text(encoding="utf-8") if snapshot.exists() else None, store.extras(run_id))
        audit.append("EVIDENCE_EXPORTED", run_id=run_id, actor=None, payload={"format": format})
        filename = f"evidence_{result.request_id}_{run_id}.{format}"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        if format == "md":
            return PlainTextResponse(render_markdown(pack), media_type="text/markdown", headers=headers)
        return JSONResponse(pack, headers=headers)

    # ------------------------------------------------------------- AI extraction observability

    @app.get("/api/llm/status")
    def llm_status() -> dict:
        return extractor.status()

    @app.get("/api/llm/usage")
    def llm_usage() -> dict:
        return extractor.usage()

    @app.post("/api/llm/cache/clear")
    def llm_cache_clear(x_persona_id: str | None = Header(default=None)) -> dict:
        removed = extractor.clear_cache()
        audit.append("LLM_CACHE_CLEARED", run_id=None, actor=x_persona_id, payload={"entries_removed": removed})
        return {"entries_removed": removed}

    if settings.frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="ui")

    return app


app = create_app()
