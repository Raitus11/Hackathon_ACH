"""CSV input-set adapter: turns the team's 4-file export into the canonical request / change JSON.

The adapter only reshapes data. It produces exactly the dicts that the JSON upload path takes
(MaintenanceRequest + ImplementedChange), so every CSV request runs through the same agent
pipeline, rule engine, findings, checker decision, evidence pack and audit trail.

  customer_maintenance_request.csv  -> one MaintenanceRequest per request_id
  customer_request_change.csv       -> requested_changes (+ evidence_required_for flags)
  request_document.csv              -> evidence indicators
  tnal_audit_event.csv              -> ImplementedChange.tnal_entries (no GPS report in this set)

Every cell is read as text, so routing numbers keep their leading zeros. Spreadsheet exports
often drop them anyway; the aba_routing normalizer in the rule config handles that at compare time.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .ingest import IngestError

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_REQUESTS = 500

# canonical column -> accepted header spellings (compared lower-case, trimmed)
SCHEMAS: dict[str, dict[str, tuple[str, ...]]] = {
    "customer_maintenance_request": {
        "request_id": ("request_id",),
        "customer_id": ("customer_id",),
        "build_type": ("build_type", "request_type"),
        "request_status": ("request_status", "status"),
        "requestor_id": ("requestor_id", "maker_id", "submitted_by"),
        "approver_id": ("approver_id", "checker_id", "approved_by"),
        "scenario_key": ("scenario_key",),
        "scenario_title": ("scenario_title",),
        "submitted_at": ("submitted_at",),
        "updated_at": ("updated_at",),
    },
    "customer_request_change": {
        "request_change_id": ("request_change_id",),
        "request_id": ("request_id",),
        "field_code": ("field_code",),
        "field_label": ("field_label",),
        "change_action": ("change_action",),
        "requested_value": ("requested_value",),
        "secondary_approval_required": ("secondary_approval_required", "secondary_approval"),
        "supporting_document_required": ("supporting_document_required", "supporting_doc_required",
                                         "supporting_document"),
        "sequence_number": ("sequence_number", "sequence"),
    },
    "request_document": {
        "document_id": ("document_id",),
        "request_id": ("request_id",),
        "document_type": ("document_type",),
        "is_secondary_approval_evidence": ("is_secondary_approval_evidence",),
    },
    "tnal_audit_event": {
        "audit_event_id": ("audit_event_id", "audit_id", "event_id"),
        "request_id": ("request_id",),
        "company_id": ("company_id",),
        "company_name": ("company_name",),
        "event_time": ("event_time", "event_timestamp"),
        "operator_id": ("operator_id",),
        "action_type": ("action_type",),
        "canonical_field": ("canonical_field",),
        "old_value": ("old_value",),
        "new_value": ("new_value",),
    },
}

REQUIRED = {
    "customer_maintenance_request": {"request_id", "customer_id", "request_status", "requestor_id", "approver_id"},
    "customer_request_change": {"request_id", "field_code", "requested_value", "supporting_document_required"},
    "request_document": {"request_id", "is_secondary_approval_evidence"},
    "tnal_audit_event": {"audit_event_id", "request_id", "event_time", "operator_id", "canonical_field",
                         "old_value", "new_value"},
}

FILE_KEYS = tuple(SCHEMAS)
_TRUE = {"1", "Y", "YES", "TRUE", "T"}
_DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M",
                 "%m/%d/%Y %I:%M %p", "%m/%d/%Y", "%Y-%m-%d")


@dataclass(frozen=True)
class CsvMapping:
    field_codes: dict[str, str]          # SOURCE_CODE -> rule field key
    secondary_indicator: str
    request_type_column: str
    sha256: str

    def field_key(self, code: str) -> tuple[str, bool]:
        """Rule field key for a source code, and whether it was explicitly mapped."""
        c = (code or "").strip().upper()
        if c in self.field_codes:
            return self.field_codes[c], True
        key = re.sub(r"[^a-z0-9_]+", "_", c.lower()).strip("_") or "unknown_field"
        if not key[0].isalpha():
            key = f"f_{key}"
        return key[:64], False


def load_mapping(path: Path) -> CsvMapping:
    raw = path.read_bytes() if path.is_file() else b""
    data = yaml.safe_load(raw.decode("utf-8")) if raw else {}
    data = data or {}
    codes: dict[str, str] = {}
    for key, aliases in (data.get("field_codes") or {}).items():
        for a in [key, *(aliases or [])]:
            codes[str(a).strip().upper()] = str(key).strip()
    return CsvMapping(
        field_codes=codes,
        secondary_indicator=str(data.get("secondary_approval_indicator") or "secondary_approval_evidence"),
        request_type_column=str(data.get("request_type_column") or "build_type"),
        sha256=hashlib.sha256(raw).hexdigest(),
    )


@dataclass
class CsvCase:
    request_id: str
    request: dict[str, Any]
    implemented_change: dict[str, Any]
    scenario_key: str = ""
    scenario_title: str = ""


@dataclass
class CsvBatchInput:
    cases: list[CsvCase]
    files: dict[str, dict[str, Any]]      # file_key -> {name, sha256, rows}
    warnings: list[str] = field(default_factory=list)
    mapping_sha256: str = ""


# ------------------------------------------------------------------ parsing helpers


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _resolve(file_key: str, headers: list[str]) -> dict[str, str]:
    norm = {h.strip().lower(): h for h in headers if h}
    mapping: dict[str, str] = {}
    missing: list[str] = []
    for canon, aliases in SCHEMAS[file_key].items():
        hit = next((norm[a] for a in aliases if a in norm), None)
        if hit is None:
            # Unique-prefix fallback, e.g. "supporting_document_req" for supporting_document_required.
            cands = [orig for low, orig in norm.items() if any(low.startswith(a) for a in aliases)]
            hit = cands[0] if len(cands) == 1 else None
        if hit is not None:
            mapping[canon] = hit
        elif canon in REQUIRED[file_key]:
            missing.append(canon)
    if missing:
        raise IngestError(
            "CSV_COLUMNS_MISSING",
            f"{file_key}.csv is missing required column(s): {', '.join(missing)}",
            [{"source": f"{file_key}.csv", "location": "header",
              "message": f"missing {', '.join(missing)}; found: {', '.join(h for h in headers if h)}"}],
        )
    return mapping


def _rows(file_key: str, text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text))
    mapping = _resolve(file_key, list(reader.fieldnames or []))
    out = []
    for raw in reader:
        if not any((v or "").strip() for v in raw.values() if isinstance(v, str)):
            continue  # trailing blank rows from spreadsheet exports
        out.append({c: (raw.get(h) or "").strip() for c, h in mapping.items()})
    return out


def _flag(value: str) -> bool:
    return (value or "").strip().upper() in _TRUE


def _iso(value: str) -> str | None:
    v = (value or "").strip()
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        dt = None
        for fmt in _DATE_FORMATS:
            try:
                dt = datetime.strptime(v, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # exports carry no zone; treated as UTC
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _seq(value: str) -> tuple[int, str]:
    try:
        return (int(float(value)), value)
    except ValueError:
        return (10**9, value)


def _clip(value: str, n: int) -> str:
    return value if len(value) <= n else value[: n - 1] + "…"


# ------------------------------------------------------------------ adapter


def file_key_for(filename: str) -> str | None:
    stem = Path(filename).stem.strip().lower()
    if stem in SCHEMAS:
        return stem
    # Tolerate "tnal_audit_event (1).csv" style browser download names.
    base = re.sub(r"[\s_-]*\(\d+\)$", "", stem)
    return base if base in SCHEMAS else None


def collect_files(files: list[tuple[str, bytes]]) -> dict[str, tuple[str, bytes]]:
    by_key: dict[str, tuple[str, bytes]] = {}
    problems: list[dict] = []
    for name, data in files:
        key = file_key_for(name)
        if key is None:
            problems.append({"source": name, "location": "filename",
                             "message": f"not one of {', '.join(k + '.csv' for k in FILE_KEYS)}"})
        elif key in by_key:
            problems.append({"source": name, "location": "filename", "message": f"duplicate of {by_key[key][0]}"})
        elif len(data) > MAX_FILE_BYTES:
            problems.append({"source": name, "location": "size", "message": f"exceeds {MAX_FILE_BYTES // 1024 // 1024} MB"})
        else:
            by_key[key] = (name, data)
    for key in FILE_KEYS:
        if key not in by_key:
            problems.append({"source": f"{key}.csv", "location": "file", "message": "required file not provided"})
    if problems:
        raise IngestError("CSV_FILES_INVALID", "The CSV input set is incomplete or has unexpected files", problems)
    return by_key


def build_batch(files: list[tuple[str, bytes]], mapping: CsvMapping) -> CsvBatchInput:
    by_key = collect_files(files)
    text = {k: _decode(data) for k, (_, data) in by_key.items()}
    rows = {k: _rows(k, text[k]) for k in FILE_KEYS}
    warnings: list[str] = []

    requests: dict[str, dict[str, str]] = {}
    for r in rows["customer_maintenance_request"]:
        if not r["request_id"]:
            warnings.append("customer_maintenance_request.csv has a row with a blank request_id; skipped")
            continue
        if r["request_id"] in requests:
            warnings.append(f"Duplicate request_id {r['request_id']} in customer_maintenance_request.csv; last row used")
        requests[r["request_id"]] = r
    if len(requests) > MAX_REQUESTS:
        raise IngestError("CSV_TOO_LARGE", f"At most {MAX_REQUESTS} requests per upload; got {len(requests)}")

    changes: dict[str, list[dict[str, str]]] = defaultdict(list)
    docs: dict[str, list[dict[str, str]]] = defaultdict(list)
    audit: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows["customer_request_change"]:
        changes[r["request_id"]].append(r)
    for r in rows["request_document"]:
        docs[r["request_id"]].append(r)
    for r in rows["tnal_audit_event"]:
        audit[r["request_id"]].append(r)

    for label, grouped in (("customer_request_change", changes), ("request_document", docs),
                           ("tnal_audit_event", audit)):
        orphans = sorted(set(grouped) - set(requests))
        if orphans:
            warnings.append(f"{label}.csv references request_id(s) not in customer_maintenance_request.csv "
                            f"(ignored): {', '.join(orphans)}")

    unmapped: set[str] = set()
    cases: list[CsvCase] = []
    for rid, req in requests.items():
        # ---- requested changes (one per field; latest sequence wins if a field is repeated)
        requested: dict[str, str] = {}
        flagged: list[str] = []
        for c in sorted(changes.get(rid, []), key=lambda c: _seq(c.get("sequence_number", ""))):
            key, mapped = mapping.field_key(c["field_code"])
            if not mapped:
                unmapped.add(c["field_code"])
            if key in requested:
                warnings.append(f"{rid}: field {c['field_code']} is requested more than once; last row used")
            requested[key] = c["requested_value"]
            if (_flag(c.get("supporting_document_required", "")) or _flag(c.get("secondary_approval_required", ""))) \
                    and key not in flagged:
                flagged.append(key)

        # ---- evidence indicators from documents
        evidence: dict[str, bool] = {}
        for d in docs.get(rid, []):
            if _flag(d["is_secondary_approval_evidence"]):
                evidence[mapping.secondary_indicator] = True
            elif d.get("document_type"):
                k, _ = mapping.field_key(d["document_type"])
                evidence[f"document_{k}"[:64]] = True

        # ---- TNAL audit rows
        events = audit.get(rid, [])
        tnal_entries: list[dict[str, Any]] = []
        operators: list[str] = []
        times: list[str] = []
        company_name = ""
        for e in events:
            key, mapped = mapping.field_key(e["canonical_field"])
            if not mapped:
                unmapped.add(e["canonical_field"])
            when = _iso(e["event_time"])
            if when is None:
                warnings.append(f"{rid}: audit event {e['audit_event_id']} has unreadable event_time "
                                f"'{e['event_time']}'; request submission time used")
                when = _iso(req.get("submitted_at", "")) or "1970-01-01T00:00:00Z"
            op = e["operator_id"] or "UNKNOWN"
            operators.append(op)
            times.append(when)
            company_name = company_name or e.get("company_name", "")
            tnal_entries.append({
                "record_id": _clip(f"TNAL-{e['audit_event_id']}", 64),
                "customer_id": e.get("company_id") or req["customer_id"],
                "field": key,
                "old_value": e["old_value"] or None,
                "new_value": e["new_value"] or None,
                "changed_by": _clip(op, 64),
                "changed_at": when,
            })

        implemented_by = ",".join(dict.fromkeys(operators)) or "NO-TNAL-ACTIVITY"
        implemented_at = (max(times) if times else None) or _iso(req.get("updated_at", "")) \
            or _iso(req.get("submitted_at", "")) or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        request = {
            "request_id": rid,
            "customer_id": req["customer_id"],
            "customer_name": _clip(company_name or req["customer_id"], 128),
            "request_type": (req.get(mapping.request_type_column) or req.get("build_type") or "MAINTENANCE"),
            "status": req["request_status"] or "UNKNOWN",
            "submitted_by": req["requestor_id"] or "UNKNOWN",
            "approved_by": req["approver_id"] or None,
            "approved_at": None,
            "requested_changes": [{"field": f, "requested_value": v} for f, v in requested.items()],
            "evidence": evidence,
            "evidence_required_for": flagged,
            "source_system": "Customer maintenance request CSV (team input set, SYNTHETIC)",
        }
        change = {
            "change_id": _clip(f"TNAL-{rid}", 64),
            "request_id": rid,
            "customer_id": req["customer_id"],
            "implemented_by": _clip(implemented_by, 64),
            "implemented_at": implemented_at,
            "tnal_entries": tnal_entries,
            "gps_changes": [],
            "gps_report_available": False,
            "source_systems": ["TNAL Critical Field Audit Log CSV export (team input set, SYNTHETIC)"],
        }
        cases.append(CsvCase(rid, request, change, req.get("scenario_key", ""), req.get("scenario_title", "")))

    if unmapped:
        warnings.append("Field code(s) not in config/csv_mapping.yaml, used as-is: "
                        + ", ".join(sorted(unmapped))
                        + ". Add them to the mapping and to the rule-config field dictionary.")

    files_meta = {
        k: {"name": by_key[k][0], "sha256": hashlib.sha256(by_key[k][1]).hexdigest(), "rows": len(rows[k])}
        for k in FILE_KEYS
    }
    return CsvBatchInput(cases=cases, files=files_meta, warnings=warnings, mapping_sha256=mapping.sha256)


def schema_description() -> dict[str, Any]:
    return {
        k: {"filename": f"{k}.csv",
            "required": [c for c in SCHEMAS[k] if c in REQUIRED[k]],
            "optional": [c for c in SCHEMAS[k] if c not in REQUIRED[k]]}
        for k in FILE_KEYS
    }
