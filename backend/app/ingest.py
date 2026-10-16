"""Ingest & normalize: schema validation, record matching, canonical maintenance model."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import ValidationError

from .models import ImplementedChange, ImplementedValue, MaintenanceCase, MaintenanceRequest


class IngestError(Exception):
    def __init__(self, code: str, message: str, details: list[dict] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or []


def _validation_details(source: str, exc: ValidationError) -> list[dict]:
    return [
        {"source": source, "location": ".".join(str(p) for p in err["loc"]), "message": err["msg"]}
        for err in exc.errors(include_url=False, include_input=False)
    ]


def parse_inputs(request_data: Any, change_data: Any) -> tuple[MaintenanceRequest, ImplementedChange]:
    details: list[dict] = []
    request = change = None
    try:
        request = MaintenanceRequest.model_validate(request_data)
    except ValidationError as exc:
        details += _validation_details("request", exc)
    try:
        change = ImplementedChange.model_validate(change_data)
    except ValidationError as exc:
        details += _validation_details("implemented_change", exc)
    if details or request is None or change is None:
        raise IngestError("SCHEMA_VALIDATION_FAILED", "Input files failed schema validation", details)
    return request, change


def match_records(request: MaintenanceRequest, change: ImplementedChange) -> None:
    """Record matcher: the change record must belong to this request and customer."""
    problems: list[dict] = []
    if change.request_id != request.request_id:
        problems.append(
            {"source": "matcher", "location": "request_id",
             "message": f"change record references {change.request_id}, request is {request.request_id}"}
        )
    if change.customer_id != request.customer_id:
        problems.append(
            {"source": "matcher", "location": "customer_id",
             "message": f"change record customer {change.customer_id} != request customer {request.customer_id}"}
        )
    for entry in change.tnal_entries:
        if entry.customer_id != request.customer_id:
            problems.append(
                {"source": "matcher", "location": f"tnal_entries.{entry.record_id}",
                 "message": f"TNAL row belongs to customer {entry.customer_id}"}
            )
    if problems:
        raise IngestError("RECORD_MATCH_FAILED", "Request and implemented-change record do not match", problems)


def _digest(request: MaintenanceRequest, change: ImplementedChange) -> str:
    payload = json.dumps(
        {"request": request.model_dump(mode="json"), "change": change.model_dump(mode="json")},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_case(request_data: Any, change_data: Any) -> MaintenanceCase:
    request, change = parse_inputs(request_data, change_data)
    match_records(request, change)

    implemented: dict[str, ImplementedValue] = {}
    # If a field was changed more than once, the latest TNAL row is the implemented value.
    for entry in sorted(change.tnal_entries, key=lambda e: (e.changed_at, e.record_id)):
        implemented[entry.field] = ImplementedValue(
            field=entry.field,
            old_value=entry.old_value,
            new_value=entry.new_value,
            record_id=entry.record_id,
            changed_by=entry.changed_by,
            changed_at=entry.changed_at,
        )

    return MaintenanceCase(
        request=request,
        change=change,
        requested={c.field: c.requested_value for c in request.requested_changes},
        implemented=implemented,
        gps={g.field: g.new_value for g in change.gps_changes},
        evidence=dict(request.evidence),
        input_digest=_digest(request, change),
    )
