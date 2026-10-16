# CSV input set (sample)

Reconstructed from screenshots of the team-provided export
(`ACH_Maker_Checker_Validation-Synthetic-Data/export`). Column values that were truncated in the
spreadsheet view were completed by hand, so treat this as a test fixture. Use the real export for the demo.

Expected outcomes under `config/rules/ach_db_next_day.yaml`:

| Request | Scenario | Overall | Exception |
|---|---|---|---|
| REQ-1001 | clean-match | PASS | none |
| REQ-1002 | field-mismatch | EXCEPTION | FLD-002 settlement_routing_number MISMATCH (121000248 vs 91000019) |
| REQ-1003 | missing-implementation | EXCEPTION | FLD-001 settlement_routing_number MISSING_FIELD |
| REQ-1004 | unauthorized-implementation | EXCEPTION | AUT-001 settlement_routing_number UNAUTHORIZED_CHANGE |
| REQ-1005 | missing-evidence | EXCEPTION | EVD-003 secondary_approval_evidence MISSING_EVIDENCE |
