"""Run and decision store: in memory, mirrored to runtime/runs/<run_id>.json for traceability."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from .models import DecisionRecord, MaintenanceCase, ValidationResult


class RunStore:
    def __init__(self, runs_dir: Path) -> None:
        self._dir = runs_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._results: dict[str, ValidationResult] = {}
        self._cases: dict[str, MaintenanceCase] = {}
        self._decisions: dict[str, DecisionRecord] = {}
        self._extras: dict[str, dict] = {}

    def _persist(self, run_id: str) -> None:
        payload = {
            "result": self._results[run_id].model_dump(mode="json"),
            "inputs": {
                "request": self._cases[run_id].request.model_dump(mode="json"),
                "implemented_change": self._cases[run_id].change.model_dump(mode="json"),
            },
            "decision": self._decisions[run_id].model_dump(mode="json") if run_id in self._decisions else None,
            **self._extras.get(run_id, {}),
        }
        (self._dir / f"{run_id}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def save_run(self, result: ValidationResult, case: MaintenanceCase, extras: dict | None = None) -> None:
        with self._lock:
            self._results[result.run_id] = result
            self._cases[result.run_id] = case
            self._extras[result.run_id] = extras or {}
            self._persist(result.run_id)

    def get(self, run_id: str) -> tuple[ValidationResult, MaintenanceCase] | None:
        with self._lock:
            if run_id not in self._results:
                return None
            return self._results[run_id], self._cases[run_id]

    def extras(self, run_id: str) -> dict:
        with self._lock:
            return dict(self._extras.get(run_id, {}))

    def decision(self, run_id: str) -> DecisionRecord | None:
        with self._lock:
            return self._decisions.get(run_id)

    def save_decision(self, record: DecisionRecord) -> bool:
        """Returns False if a decision already exists (decisions are write-once)."""
        with self._lock:
            if record.run_id in self._decisions:
                return False
            self._decisions[record.run_id] = record
            self._persist(record.run_id)
            return True

    def list_runs(self) -> list[ValidationResult]:
        with self._lock:
            return sorted(self._results.values(), key=lambda r: r.evaluated_at, reverse=True)
