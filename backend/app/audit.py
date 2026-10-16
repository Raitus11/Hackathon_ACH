"""Append-only audit log (JSON Lines). Prototype traceability design per FAQ Q39, not production
retention. There is no update or delete path in the code."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLog:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)

    def append(self, event_type: str, *, run_id: str | None, actor: str | None, payload: dict[str, Any]) -> dict:
        event = {
            "event_id": f"EVT-{uuid.uuid4().hex[:12].upper()}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "run_id": run_id,
            "actor": actor,
            "payload": payload,
        }
        line = json.dumps(event, sort_keys=True, default=str)
        with self._lock, self._path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return event

    def read(self, run_id: str | None = None) -> list[dict]:
        events: list[dict] = []
        with self._path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    event = json.loads(line)
                    if run_id is None or event.get("run_id") == run_id:
                        events.append(event)
        return events
