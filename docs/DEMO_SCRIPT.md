# Five-minute demo script (FAQ Q52 + organizer "winning demo moment")

Setup before recording: `./run.sh` (or `.\run.ps1`), browser at 1920×1080 on http://localhost:8000, persona =
**Checker · Dana Whitfield**, and `config/rules/ach_db_next_day.yaml` open in an editor on a second window.
Reset state first: stop the app, delete `runtime/`, restart (clean audit trail).

| Time | Do | Say (operations story, no invented numbers) |
|---|---|---|
| 0:00–0:25 | Show header badge and the *Process* tab flow strip. | "C-247489: an independent checker compares the approved maintenance request with what TNAL and GPS say was implemented. We automate the comparison, not the approval. Everything here is synthetic; every enterprise system is simulated." |
| 0:25–0:55 | Review tab → scenario **1 Clean match** → *Run validation*. Click *View YAML*, close. | "One request, one TNAL/GPS change record. The rules live in this external YAML file — read on every run. PASS is decision support: the item is still *Awaiting checker decision*." |
| 0:55–1:45 | Scenario **2 Field mismatch** → Run. Point at the crimson EXCEPTION, the highlighted digit, rule FLD-002 v1, the reason, the sources. Click the row for trace. | "The processor keyed 2,500,000 against an approved 250,000. The configured equality rule names the field, expected value from the request, actual value from TNAL row 000201, the rule and version, and why." |
| 1:45–2:25 | Scenario **4 Unauthorized change** → Run. Scenario **5 Missing evidence** → Run. (Optionally 3.) | "SEC codes changed without being requested — AUT-001. Signed authorization absent in DMS — EVD-001, evidence exception for investigation." |
| 2:25–3:20 | Scenario **1** again, Run (PASS). In the editor change EVD-002 `enabled: false` → `true` and `version: 1.0.0` → `1.1.0`. Save. Point at the gold *Rule file changed* banner. *Re-run with new rules*. | "Control owner tightens policy: settlement-account changes now need callback verification. One line in config — no code, no restart. Same inputs, new config hash, scenario 1 is now an EXCEPTION citing EVD-002." **Then revert the edit.** |
| 3:20–3:40 | Back on scenario **2** run → *Evidence .md* download, open it briefly. | "Exportable evidence: inputs, config version and sha256, every finding, the decision, the audit events." |
| 3:40–4:20 | Switch persona to **Maker · Priya Nair**. Show lock. Click *Attempt anyway* → HTTP 403 SELF_APPROVAL_BLOCKED. Switch back to **Checker**, choose *Investigate*, comment, *Record decision*. | "Priya implemented this change. The UI locks her out and the API refuses her — segregation of duties is enforced server-side. Dana, the independent checker, records Investigate. That gold panel is the human-approval boundary; the engine has no way to approve." |
| 4:20–5:00 | *Audit trail* tab (search the run ID) → *Process* tab → architecture slide. | "Every run records input IDs, config version and hash, rule results, the blocked attempt and the checker decision. Simulated systems and assumptions are listed. Next steps: workflow integration, evidence packaging, a second control — once the business confirms the field dictionary and baselines." |

## Fallbacks
- Live failure: play the recorded video; `reports/scenario_results.md` shows all five outcomes and the AC4 comparison.
- Config edit typo: the rule panel shows the exact YAML error (line/field) and refuses to run — that is a feature; fix and re-run.
- Do not claim volumes, handling time or savings. Baselines have not been provided.

## Likely judge questions
- **Why config-driven?** Control owners change evidence policy and field rules without a release; every result records the exact config hash used, so behaviour changes are traceable.
- **Why can't the engine approve?** The result type has no approval field; only `DecisionRecord` does, created by the API for an independent checker. PASS and EXCEPTION both require a human decision.
- **How is SoD enforced?** Server-side in `sod.py`: implementer of the change → 403 `SELF_APPROVAL_BLOCKED`; any maker → 403 `ROLE_NOT_PERMITTED`; blocked attempts are audited.
- **What is real vs simulated?** Engine, rules, UI, decisions and audit are real code. ServiceNow, DMS, TNAL, GPS, ACH/AES and CheckMate are simulated by synthetic JSON files.
- **Path to production?** The organizer's data-gap table in the README: field dictionary and keys, rule catalogue, evidence policy, operating model, baselines and NFRs.
