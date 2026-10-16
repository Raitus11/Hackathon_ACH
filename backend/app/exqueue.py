"""Mock exception queue (stretch goal: "mock exception routing to a workflow queue", FAQ Q15).

SIMULATED. When the checker records Investigate, the item is written to a local JSON Lines
queue addressed to the original processor. There is no CheckMate task, no notification, no
correction or resubmission workflow (all out of scope). Append-only, like the audit log.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import DecisionRecord, FindingResult, ValidationResult
from .explain import show

SIMULATION_LABEL = ("SIMULATED CheckMate exception routing. No real task is created and the processor is not "
                    "contacted. Correction, resubmission and revalidation are out of scope (FAQ Q15, Q33).")


class ExceptionQueue:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)

    def route(self, result: ValidationResult, decision: DecisionRecord) -> dict[str, Any]:
        exceptions = [
            {"rule_id": f.rule_id, "rule_version": f.rule_version, "field": f.field, "field_label": f.field_label,
             "exception_type": f.exception_type.value if f.exception_type else None,
             "expected": show(f.expected_value), "actual": show(f.actual_value), "reason": f.reason}
            for f in result.findings if f.result is FindingResult.EXCEPTION
        ]
        item = {
            "queue_item_id": f"EXQ-{uuid.uuid4().hex[:8].upper()}",
            "routed_at": datetime.now(timezone.utc).isoformat(),
            "run_id": result.run_id,
            "request_id": result.request_id,
            "change_id": result.change_id,
            "customer_id": result.customer_id,
            "customer_name": result.customer_name,
            "engine_outcome": result.overall.value,
            "routed_to": result.implemented_by,
            "routed_to_role": "ACH processor (original maker)",
            "routed_by": decision.actor_id,
            "routed_by_name": decision.actor_name,
            "decision_id": decision.decision_id,
            "checker_comment": decision.comment,
            "exceptions": exceptions,
            "status": "AWAITING_PROCESSOR_CORRECTION",
            "simulated": True,
            "config_version_hash": result.config_hash[:12],
        }
        with self._lock, self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item, sort_keys=True) + "\n")
        return item

    def read(self) -> list[dict[str, Any]]:
        with self._path.open("r", encoding="utf-8") as handle:
            items = [json.loads(line) for line in handle if line.strip()]
        return list(reversed(items))
