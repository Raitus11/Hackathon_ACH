"""LLM providers behind one interface.

MockProvider          offline and deterministic; labelled SIMULATED. Parses the synthetic form
                      with simple patterns and reports estimated token usage, including a
                      simulated provider prompt cache keyed on the system-prompt prefix.
OpenAICompatibleProvider  any gateway exposing POST {base_url}/chat/completions (e.g. an enterprise LLM gateway).
                      Reads real usage, including cached prompt tokens when the gateway reports them.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx

from .prompt import estimate_tokens, prefix_hash


class ProviderError(Exception):
    pass


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    provider: str
    simulated: bool
    input_tokens: int          # total prompt tokens, including any served from cache
    output_tokens: int
    cached_input_tokens: int   # prompt tokens served from the provider's prompt cache
    cache_write_tokens: int    # prompt tokens written to the provider's prompt cache
    latency_ms: float


class Provider(Protocol):
    name: str
    model: str
    simulated: bool

    def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse: ...


# ---------------------------------------------------------------- mock


_LINE = re.compile(r"^\s*([A-Za-z][A-Za-z ()/]+?)\s*:\s*(.+?)\s*$")
_ANNOTATION = re.compile(r"\s*\((handwritten|illegible|struck through)\)\s*$", re.IGNORECASE)


class MockProvider:
    """Deterministic stand-in so the demo never depends on network access. Clearly SIMULATED."""

    name = "mock"
    simulated = True

    def __init__(self, model: str, field_labels: dict[str, str], state_path: Path) -> None:
        self.model = model
        self._labels = {label.casefold(): key for key, label in field_labels.items()}
        self._state_path = state_path
        self._lock = threading.Lock()

    def _seen_prefixes(self) -> set[str]:
        if self._state_path.exists():
            return set(json.loads(self._state_path.read_text(encoding="utf-8")))
        return set()

    def _remember(self, prefixes: set[str]) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(json.dumps(sorted(prefixes)), encoding="utf-8")

    def _extract(self, user_prompt: str) -> dict[str, Any]:
        body = user_prompt.split("<document>", 1)[-1].split("</document>", 1)[0]
        out: dict[str, Any] = {
            "document_type": "CUSTOMER_AUTHORIZATION_FORM",
            "customer_name": {"value": None, "confidence": 0.2},
            "customer_id": {"value": None, "confidence": 0.2},
            "request_reference": {"value": None, "confidence": 0.2},
            "requested_changes": [],
            "signature_present": {"value": False, "confidence": 0.9},
            "date_signed": {"value": None, "confidence": 0.2},
            "notes": None,
        }
        header = {"customer name": "customer_name", "customer id": "customer_id",
                  "request reference": "request_reference", "date signed": "date_signed"}
        unmapped: list[str] = []
        for raw in body.splitlines():
            m = _LINE.match(raw)
            if not m:
                continue
            label, value = m.group(1).strip(), m.group(2).strip()
            key = label.casefold()
            if key in header:
                out[header[key]] = {"value": value, "confidence": 0.99}
            elif key == "signature":
                out["signature_present"] = {"value": "[signed]" in value.casefold(), "confidence": 0.98}
            elif key in self._labels:
                annotated = bool(_ANNOTATION.search(value))
                out["requested_changes"].append({
                    "field": self._labels[key],
                    "value": _ANNOTATION.sub("", value),
                    "confidence": 0.74 if annotated else 0.97,
                })
            elif key not in {"document type", "authorized signer"}:
                unmapped.append(label)
        if unmapped:
            out["notes"] = "Unmapped lines: " + ", ".join(unmapped)
        return out

    def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        started = time.perf_counter()
        text = json.dumps(self._extract(user_prompt), separators=(",", ":"))
        system_tokens = estimate_tokens(system_prompt)
        with self._lock:
            seen = self._seen_prefixes()
            key = prefix_hash(system_prompt)
            hit = key in seen
            if not hit:
                seen.add(key)
                self._remember(seen)
        return LLMResponse(
            text=text,
            model=self.model,
            provider=self.name,
            simulated=True,
            input_tokens=system_tokens + estimate_tokens(user_prompt),
            output_tokens=estimate_tokens(text),
            cached_input_tokens=system_tokens if hit else 0,
            cache_write_tokens=0 if hit else system_tokens,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )


# ---------------------------------------------------------------- OpenAI-compatible gateway


class OpenAICompatibleProvider:
    name = "openai_compatible"
    simulated = False

    def __init__(self, settings: dict[str, Any], transport: httpx.BaseTransport | None = None) -> None:
        if not settings.get("base_url") or not settings.get("model"):
            raise ProviderError("LLM mode needs ACH_LLM_BASE_URL and ACH_LLM_MODEL (or base_url/model in config/llm.yaml)")
        self.model = settings["model"]
        self._base_url = str(settings["base_url"]).rstrip("/")
        self._settings = settings
        token = settings.get("_api_key") or os.environ.get(settings.get("api_key_env") or "", "")
        if not token:
            raise ProviderError(f"Environment variable {settings.get('api_key_env')} is not set")
        scheme = settings.get("auth_scheme", "Bearer")
        self._headers = {
            settings.get("auth_header", "Authorization"): f"{scheme} {token}".strip() if scheme else token,
            "Content-Type": "application/json",
            **{str(k): str(v) for k, v in (settings.get("extra_headers") or {}).items()},
        }
        verify: bool | str = settings.get("ca_bundle") or True
        self._client = httpx.Client(timeout=float(settings.get("timeout_seconds", 30)), verify=verify,
                                    transport=transport)

    @staticmethod
    def _usage(usage: dict[str, Any]) -> tuple[int, int, int, int]:
        prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
        cached = int(details.get("cached_tokens") or usage.get("cache_read_input_tokens") or 0)
        written = int(usage.get("cache_creation_input_tokens") or 0)
        if usage.get("cache_read_input_tokens") is not None or written:
            # Some providers report uncached input separately; make input_tokens the total.
            prompt = int(usage.get("input_tokens") or 0) + cached + written
        return prompt, completion, cached, written

    def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        body: dict[str, Any] = {
            "model": self.model,
            "temperature": self._settings.get("temperature", 0),
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        }
        if self._settings.get("json_mode", True):
            body["response_format"] = {"type": "json_object"}
        attempts = int(self._settings.get("max_retries", 2)) + 1
        last: Exception | None = None
        for attempt in range(attempts):
            started = time.perf_counter()
            try:
                resp = self._client.post(f"{self._base_url}/chat/completions", headers=self._headers, json=body)
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                if resp.status_code >= 400:
                    raise ProviderError(f"Gateway returned HTTP {resp.status_code}: {resp.text[:300]}")
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                prompt, completion, cached, written = self._usage(data.get("usage") or {})
                return LLMResponse(
                    text=text, model=data.get("model", self.model), provider=self.name, simulated=False,
                    input_tokens=prompt, output_tokens=completion, cached_input_tokens=cached,
                    cache_write_tokens=written, latency_ms=round((time.perf_counter() - started) * 1000, 2),
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = exc
                if attempt < attempts - 1:
                    time.sleep(0.5 * (2 ** attempt))
                    continue
            except (KeyError, IndexError, ValueError) as exc:
                raise ProviderError(f"Unexpected gateway response shape: {exc}") from exc
        raise ProviderError(f"Gateway unreachable after {attempts} attempt(s): {last}")
