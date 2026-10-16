# Architecture and process flow

> SYNTHETIC DATA · SIMULATED SYSTEMS · PROTOTYPE. Not production-ready; not a replacement for existing controls.

## 1. Component architecture (organizer reference pattern)

```mermaid
flowchart LR
  subgraph IN["INPUTS (synthetic · simulated)"]
    R["Maintenance request<br/>ServiceNow / Fulfillment (SIMULATED)<br/>request.json"]
    C["Implemented change<br/>TNAL audit log + GPS report (SIMULATED)<br/>change.json"]
    E["Evidence indicators<br/>DMS (SIMULATED)<br/>on request.json"]
  end

  subgraph ING["INGEST & NORMALIZE · backend/app/ingest.py"]
    V["Schema validation<br/>(Pydantic, structured errors)"]
    M["Record matcher<br/>request_id + customer_id"]
    N["Canonical ACH maintenance model<br/>MaintenanceCase + input digest"]
  end

  subgraph CS["CONTROL SERVICES"]
    CFG[("External rule file<br/>config/rules/ach_db_next_day.yaml<br/>safe YAML · schema-validated · sha256<br/>re-read every run")]
    ENG["Validation engine · engine.py<br/>request_approved · required · equality<br/>authorized_scope · source_consistency · evidence_present"]
    EXP["Explainability service · explain.py<br/>configured reason templates"]
  end

  subgraph RES["RESULTS & EVIDENCE"]
    VR["ValidationResult (immutable)<br/>PASS / EXCEPTION · field findings<br/>rule id + version · config sha256<br/>NO approval field"]
    EP["Evidence pack export<br/>.md / .json"]
  end

  subgraph HUM["CHECKER EXPERIENCE · human-approval boundary"]
    UI["Exception-first review (React)<br/>expected vs actual · rule · reason · source"]
    D["Decision: Approve / Investigate<br/>+ mandatory comment<br/>DecisionRecord (separate, write-once)"]
  end

  subgraph X["CROSS-CUTTING"]
    SOD["RBAC + SoD · sod.py<br/>maker self-approval blocked in API (403)"]
    AUD["Append-only audit log<br/>runtime/audit.jsonl"]
    LOG["Structured JSON logs<br/>correlation + run IDs"]
    TST["Test harness · pytest<br/>5-scenario report"]
  end

  R --> V
  C --> V
  E --> V
  V --> M --> N --> ENG
  CFG --> ENG
  ENG --> EXP --> VR
  VR --> UI --> D
  VR --> EP
  D -.->|enforced by| SOD
  VR -.-> AUD
  D -.-> AUD

  classDef human fill:#fff6d6,stroke:#ffcd41,stroke-width:3px,color:#2b2b2b;
  classDef sim fill:#eef3fa,stroke:#1d4f91,stroke-dasharray:4 3,color:#2b2b2b;
  class HUM,UI,D human;
  class R,C,E sim;
```

**Human-approval boundary.** Everything left of the checker experience is automated comparison. The engine result type
(`ValidationResult`) has no approval field. The only object that can carry Approve is `DecisionRecord`, which the API
creates only for a CHECKER persona who did not implement the change.

## 2. Where the prototype sits in C-247489

```mermaid
flowchart TB
  A["Customer submits maintenance request + documents<br/>(ServiceNow / Fulfillment, DMS) · SIMULATED"]
  B["ACH processor (maker) implements change<br/>ACH / AES / GPS · NOT INTEGRATED"]
  C["TNAL audit log + GPS change report produced · SIMULATED"]
  D["CheckMate daily task to independent reviewer · SIMULATED"]
  P["THIS PROTOTYPE<br/>config-driven first-pass comparison<br/>explainable PASS / EXCEPTION"]
  H{"Independent checker decides<br/>HUMAN-APPROVAL BOUNDARY"}
  OK["Approve · evidence retained"]
  INV["Investigate · contact processor"]
  RW["Correction / documents → revalidation<br/>explained only, not built (out of scope)"]
  A --> B --> C --> D --> P --> H
  H -->|Approve| OK
  H -->|Investigate| INV --> RW -.-> P

  classDef human fill:#fff6d6,stroke:#ffcd41,stroke-width:3px;
  classDef proto fill:#ffffff,stroke:#d71e28,stroke-width:3px;
  classDef sim fill:#eef3fa,stroke:#1d4f91,stroke-dasharray:4 3;
  class H human;
  class P proto;
  class A,B,C,D,RW sim;
```

## 3. Request lifecycle

| Step | Component | Output | Trace kept |
|---|---|---|---|
| 1 | `ingest.parse_inputs` | Typed request + change | Structured schema errors with source and field path |
| 2 | `ingest.match_records` | Matched pair | Rejects mismatched request_id / customer_id |
| 3 | `ingest.build_case` | `MaintenanceCase` | sha256 input digest |
| 4 | `config.load_ruleset` | Validated rule set | File name, version, sha256; snapshot in `runtime/configs/` |
| 5 | `engine.evaluate` | Findings in config order | Rule id + version, expected/actual values and their sources |
| 6 | `explain.render` | Reason text | From the configured template only |
| 7 | API `POST /api/runs` | `ValidationResult` | Audit `VALIDATION_RUN_COMPLETED`; `runtime/runs/<run>.json` |
| 8 | API `POST /api/runs/{id}/decision` | `DecisionRecord` or 403/422/409 | Audit `CHECKER_DECISION_RECORDED` or `DECISION_BLOCKED` |
| 9 | API `GET /api/runs/{id}/evidence` | Evidence pack | Inputs, config text, findings, decision, audit events |

## 4. Rule precedence

Rules run in the order listed in the YAML. One root cause produces one exception: if an enabled `required` rule covers a
field and the implemented value is blank or absent, the `equality` rule skips that field instead of also reporting a
mismatch. An `equality` rule with no `required` coverage still reports an absent value as a mismatch.
