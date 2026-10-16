"""Document Extraction Agent service: provider selection, local response cache, token ledger and
the side-by-side comparison with the request. Never raises into the validation path: any failure
becomes status FAILED and the deterministic validation continues unaffected."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..config import RuleSet
from ..envfile import Env
from ..models import Agreement, DocumentExtraction, ExtractedField, MaintenanceRequest
from ..normalize import normalize
from .prompt import build_system_prompt, build_user_prompt, prefix_hash
from .providers import LLMResponse, MockProvider, OpenAICompatibleProvider, Provider, ProviderError

LOW_CONFIDENCE = 0.80
MAX_DOCUMENT_CHARS = 20_000


# ---------------------------------------------------------------- strict parse of model output


class _Val(BaseModel):
    model_config = ConfigDict(extra="ignore")
    value: Any = None
    confidence: float = Field(default=0.0)


class _Change(BaseModel):
    model_config = ConfigDict(extra="ignore")
    field: str
    value: Any = None
    confidence: float = 0.0


class _Extraction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    customer_name: _Val = _Val()
    customer_id: _Val = _Val()
    request_reference: _Val = _Val()
    requested_changes: list[_Change] = []
    signature_present: _Val = _Val()
    date_signed: _Val = _Val()
    notes: str | None = None


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _s(v: Any) -> str | None:
    return None if v is None else str(v)


# ---------------------------------------------------------------- service


class ExtractionService:
    def __init__(self, config_path: Path, runtime_dir: Path, transport: httpx.BaseTransport | None = None,
                 env_path: Path | None = None) -> None:
        self._config_path = config_path
        self._env = Env(env_path or config_path.parents[1] / ".env")
        self._cache_dir = runtime_dir / "llm_cache"
        self._ledger = runtime_dir / "llm_usage.jsonl"
        self._mock_state = runtime_dir / "llm_mock_prefix_cache.json"
        self._transport = transport
        self._lock = threading.Lock()
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._ledger.touch(exist_ok=True)

    # -- configuration

    def settings(self) -> dict[str, Any]:
        data = yaml.safe_load(self._config_path.read_text(encoding="utf-8")) if self._config_path.exists() else {}
        data = data or {}
        env = self._env
        # ACH_LLM_MODE is the on/off switch: "llm" = call the gateway, "deterministic" = no LLM call.
        mode = (env.get("ACH_LLM_MODE") or "").strip().lower()
        if mode in ("llm", "live", "on", "true", "1"):
            data["provider"] = "openai_compatible"
        elif mode in ("deterministic", "off", "false", "0", "mock"):
            data["provider"] = "mock"
        else:
            data["provider"] = env.get("ACH_LLM_PROVIDER") or data.get("provider", "mock")
        oc = dict(data.get("openai_compatible") or {})
        oc["base_url"] = env.get("ACH_LLM_BASE_URL") or oc.get("base_url")
        oc["model"] = env.get("ACH_LLM_MODEL") or oc.get("model")
        oc["ca_bundle"] = env.get("ACH_LLM_CA_BUNDLE") or oc.get("ca_bundle")
        oc["_api_key"] = env.get(oc.get("api_key_env") or "APEX_API_KEY") or ""
        data["openai_compatible"] = oc
        data["_mode_flag"] = mode or None
        return data

    def _provider(self, settings: dict[str, Any], ruleset: RuleSet) -> Provider:
        labels = {k: v.label for k, v in ruleset.fields.items()}
        if settings["provider"] == "openai_compatible":
            return OpenAICompatibleProvider(settings.get("openai_compatible") or {}, transport=self._transport)
        if settings["provider"] == "mock":
            return MockProvider((settings.get("mock") or {}).get("model", "mock-extractor-v1"), labels, self._mock_state)
        raise ProviderError(f"Unknown provider '{settings['provider']}'")

    def status(self) -> dict[str, Any]:
        s = self.settings()
        provider = s["provider"]
        model = (s.get("mock") or {}).get("model") if provider == "mock" else (s.get("openai_compatible") or {}).get("model")
        return {
            "provider": provider,
            "mode": "deterministic" if provider == "mock" else "llm",
            "mode_flag": s.get("_mode_flag"),
            "model": model,
            "simulated": provider == "mock",
            "label": "DETERMINISTIC · no LLM call" if provider == "mock" else "LIVE LLM via gateway",
            "prompt_version": s.get("prompt_version", "extraction-v1"),
            "response_cache_enabled": bool((s.get("response_cache") or {}).get("enabled", True)),
            "pricing_per_million": s.get("pricing_per_million") or {},
            "pricing_note": "Illustrative pricing from config/llm.yaml; replace with the gateway rate card.",
        }

    # -- ledger

    def _record(self, entry: dict[str, Any]) -> dict[str, Any]:
        with self._lock, self._ledger.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def usage(self) -> dict[str, Any]:
        rows = [json.loads(l) for l in self._ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
        price = self.settings().get("pricing_per_million") or {}
        p_in, p_cached, p_out = (float(price.get(k, 0)) for k in ("input", "cached_input", "output"))
        for r in rows:
            uncached = r["input_tokens"] - r["cached_input_tokens"]
            r["uncached_input_tokens"] = uncached
            r["estimated_cost_usd"] = round(
                (uncached * p_in + r["cached_input_tokens"] * p_cached + r["output_tokens"] * p_out) / 1_000_000, 6)
            r["cost_without_cache_usd"] = round(
                ((r["input_tokens"] + r.get("tokens_saved_input", 0)) * p_in
                 + (r["output_tokens"] + r.get("tokens_saved_output", 0)) * p_out) / 1_000_000, 6)
        calls = [r for r in rows if not r["local_cache_hit"]]
        total_in = sum(r["input_tokens"] for r in rows)
        cached_in = sum(r["cached_input_tokens"] for r in rows)
        summary = {
            "requests": len(rows),
            "llm_calls": len(calls),
            "local_cache_hits": len(rows) - len(calls),
            "input_tokens": total_in,
            "cached_input_tokens": cached_in,
            "uncached_input_tokens": total_in - cached_in,
            "output_tokens": sum(r["output_tokens"] for r in rows),
            "cache_write_tokens": sum(r["cache_write_tokens"] for r in rows),
            "tokens_saved_by_local_cache": sum(r.get("tokens_saved_input", 0) + r.get("tokens_saved_output", 0) for r in rows),
            "prompt_cache_hit_rate": round(cached_in / total_in, 4) if total_in else 0.0,
            "estimated_cost_usd": round(sum(r["estimated_cost_usd"] for r in rows), 6),
            "cost_without_caching_usd": round(sum(r["cost_without_cache_usd"] for r in rows), 6),
            "avg_latency_ms": round(sum(r["latency_ms"] for r in calls) / len(calls), 1) if calls else 0.0,
        }
        summary["savings_usd"] = round(summary["cost_without_caching_usd"] - summary["estimated_cost_usd"], 6)
        return {"summary": summary, "records": list(reversed(rows)), "status": self.status()}

    def clear_cache(self) -> int:
        removed = 0
        with self._lock:
            for f in self._cache_dir.glob("*.json"):
                f.unlink()
                removed += 1
            if self._mock_state.exists():
                self._mock_state.unlink()
        return removed

    # -- extraction

    def extract(self, document_text: str | None, request: MaintenanceRequest, ruleset: RuleSet,
                run_id: str) -> DocumentExtraction:
        s = self.settings()
        prompt_version = s.get("prompt_version", "extraction-v1")
        st = self.status()
        base = {"provider": st["provider"], "model": st["model"] or "unknown", "simulated": st["simulated"],
                "prompt_version": prompt_version, "ai_assisted": not st["simulated"]}
        if st["simulated"]:
            base["notice"] = ("DETERMINISTIC extraction (ACH_LLM_MODE=deterministic, no LLM call). Advisory only: values must be "
                              "reviewed by the checker and do not change the PASS/EXCEPTION result. Token figures are estimates "
                              "of what an LLM call would use.")
        if not document_text or not document_text.strip():
            return DocumentExtraction(status="NO_DOCUMENT", notes="No authorization form on file for this request.", **base)

        document_text = document_text[:MAX_DOCUMENT_CHARS]
        document_id = "DOC-" + hashlib.sha256(document_text.encode("utf-8")).hexdigest()[:12].upper()
        labels = {k: v.label for k, v in ruleset.fields.items()}
        system_prompt = build_system_prompt(labels, prompt_version)
        user_prompt = build_user_prompt(document_text)
        cache_key = hashlib.sha256(
            f"{prompt_version}|{base['provider']}|{base['model']}|{prefix_hash(system_prompt)}|{document_text}".encode()
        ).hexdigest()
        cache_file = self._cache_dir / f"{cache_key}.json"
        use_cache = bool((s.get("response_cache") or {}).get("enabled", True))

        ledger = {
            "call_id": f"LLM-{uuid.uuid4().hex[:10].upper()}", "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id, "agent": "Document Extraction Agent", "request_id": request.request_id,
            "document_id": document_id, "prompt_version": prompt_version, **{k: base[k] for k in ("provider", "model", "simulated")}, "mode": st["mode"],
        }
        try:
            if use_cache and cache_file.exists():
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                text = cached["text"]
                self._record({**ledger, "local_cache_hit": True, "input_tokens": 0, "output_tokens": 0,
                              "cached_input_tokens": 0, "cache_write_tokens": 0, "latency_ms": 0.0,
                              "tokens_saved_input": cached["input_tokens"], "tokens_saved_output": cached["output_tokens"]})
                cache_state = "HIT_LOCAL"
            else:
                response: LLMResponse = self._provider(s, ruleset).complete(system_prompt, user_prompt)
                text = response.text
                if use_cache:
                    cache_file.write_text(json.dumps({"text": text, "input_tokens": response.input_tokens,
                                                      "output_tokens": response.output_tokens}), encoding="utf-8")
                self._record({**ledger, "model": response.model, "local_cache_hit": False,
                              "input_tokens": response.input_tokens, "output_tokens": response.output_tokens,
                              "cached_input_tokens": response.cached_input_tokens,
                              "cache_write_tokens": response.cache_write_tokens, "latency_ms": response.latency_ms})
                cache_state = "MISS"
            parsed = _Extraction.model_validate(json.loads(text))
        except (ProviderError, ValidationError, ValueError, OSError) as exc:
            return DocumentExtraction(status="FAILED", document_id=document_id, error=str(exc)[:400], **base)

        return self._compare(parsed, request, ruleset, document_id, cache_state, base)

    def _compare(self, x: _Extraction, request: MaintenanceRequest, ruleset: RuleSet, document_id: str,
                 cache_state: str, base: dict[str, Any]) -> DocumentExtraction:
        fields: list[ExtractedField] = []

        def add(name: str, label: str, value: Any, conf: float, req_value: str | None, steps: list[str]) -> None:
            v = _s(value)
            if v is None:
                agreement = Agreement.NOT_IN_DOCUMENT
            elif req_value is None:
                agreement = Agreement.NOT_IN_REQUEST
            else:
                same = normalize(v, steps) == normalize(req_value, steps)
                agreement = Agreement.AGREES if same else Agreement.DISAGREES
            fields.append(ExtractedField(name=name, label=label, extracted_value=v, confidence=_clamp(conf),
                                         request_value=req_value, agreement=agreement))

        add("customer_id", "Customer ID", x.customer_id.value, x.customer_id.confidence, request.customer_id, ["trim", "upper"])
        add("request_reference", "Request reference", x.request_reference.value, x.request_reference.confidence,
            request.request_id, ["trim", "upper"])
        requested = {c.field: c.requested_value for c in request.requested_changes}
        seen: set[str] = set()
        for change in x.requested_changes:
            if change.field in seen:
                continue
            seen.add(change.field)
            add(change.field, ruleset.label(change.field), change.value, change.confidence,
                requested.get(change.field), ruleset.normalizers(change.field))
        for fld, value in requested.items():
            if fld not in seen:
                fields.append(ExtractedField(name=fld, label=ruleset.label(fld), extracted_value=None, confidence=0.0,
                                             request_value=value, agreement=Agreement.NOT_IN_DOCUMENT))
        sig = x.signature_present.value
        sig_bool = sig if isinstance(sig, bool) else (str(sig).strip().lower() == "true" if sig is not None else None)
        return DocumentExtraction(
            status="EXTRACTED", document_id=document_id, cache=cache_state, fields=tuple(fields),  # type: ignore[arg-type]
            signature_present=sig_bool, signature_confidence=_clamp(x.signature_present.confidence),
            date_signed=_s(x.date_signed.value),
            disagreements=sum(f.agreement in (Agreement.DISAGREES, Agreement.NOT_IN_DOCUMENT, Agreement.NOT_IN_REQUEST)
                              for f in fields),
            low_confidence=sum(f.extracted_value is not None and f.confidence < LOW_CONFIDENCE for f in fields),
            notes=x.notes, **base,
        )
