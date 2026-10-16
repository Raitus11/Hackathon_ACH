# Five-minute demo script (FAQ Q52 order + organizer "winning demo moment")

**Story:** a processor's implemented change differs from the approved request; a configured rule surfaces it with an exact
explanation; the checker investigates instead of approving. No invented incidents, volumes or savings.

**Setup before recording**
- Start the app, open http://localhost:8000 at 1920×1080, persona **Checker · Dana Whitfield**.
- Open `config/rules/ach_db_next_day.yaml` in an editor in a second window.
- Reset state: stop the app, delete `runtime/`, restart. This gives a clean audit trail and an empty queue.
- Do a dry run once, then reset again.

| Time | Q52 step | Do | Say |
|---|---|---|---|
| 0:00–0:20 | Context | Header badge, then the *Process* tab flow strip. | "Control C-247489: an independent checker compares the approved maintenance request with what TNAL and GPS say was implemented. We automate the comparison, not the approval. All data is synthetic and every enterprise system is simulated." |
| 0:20–0:50 | 1, 2: load inputs, show the external config, run | *Validation review* → scenario **2 Field mismatch**. Point at the rule panel, click *View YAML* and close it. Click *Run validation*. | "One request from ServiceNow and one TNAL/GPS change record, both simulated. The rules live in this external YAML file, which is re-read on every run." |
| 0:50–1:40 | 3: summary and drill-down | Crimson EXCEPTION card, then the findings row (highlighted digit, FLD-002 v1, reason, sources), then the **Side-by-side** grid (request ↔ TNAL ↔ GPS, the flagged TNAL cell). | "Approved 250,000, implemented 2,500,000. The rule names the field, the expected value and where it came from, the actual value and its TNAL row, the rule and its version, and why it's an exception. Same inputs and same rules always give the same result, so there's no confidence score to argue about." |
| 1:40–2:10 | 4: other seeded exceptions | Scenario **4 Unauthorized change** → Run. Scenario **5 Missing evidence** → Run. | "SEC codes changed without being requested: AUT-001. Signed authorization form missing: EVD-001, an evidence exception for investigation." |
| 2:10–3:10 | 5: rule change with no code edit (**winning moment**) | Scenario **1 Clean match** → Run (PASS). In the editor set EVD-002 `enabled: false` → `true` and ruleset `version: 1.0.0` → `1.1.0`. Save. Point at the *Rule file changed* banner. Click *Re-run validation* (now EXCEPTION, EVD-002). Scroll to **Rule version comparison**: baseline is the config used by the first run, candidate is the active file. Click *Compare*. | "The control owner tightens policy: settlement-account changes now need callback verification. One line of config, no code, no restart. The comparison replays the same inputs under both versions: v1.0.0 PASS, v1.1.0 EXCEPTION. It shows exactly which rule changed (`enabled false → true`) and which finding flipped." **Revert the edit afterwards.** |
| 3:10–3:30 | 6: export evidence | Back on scenario **2** → *Evidence .md*. Open it briefly. | "The evidence pack: inputs, config version and sha256, every finding, the decision and the audit events." |
| 3:30–4:20 | 7: SoD, human decision, boundary | Switch persona to **Maker · Priya Nair**: the *Processor feedback* card appears with the exact discrepancy, and the decision panel is locked. Click *Attempt anyway* → HTTP 403 `SELF_APPROVAL_BLOCKED`. Switch back to **Checker**, choose *Investigate*, write a comment, tick the extraction review, *Record decision*. Click *Open exception queue*. | "Priya implemented this change. She sees clear feedback on what doesn't match, but the UI locks her out and the API refuses her. Dana, the independent checker, records Investigate at the human-approval boundary. The item goes to a simulated exception queue for the original processor. Correction and resubmission stay out of scope." |
| 4:20–5:00 | 8: architecture, traceability, assumptions | *Scenario results* tab → *Run all 5* (5/5). *Audit trail* tab: metrics strip, search the run ID. *Process* tab, then the architecture slide. | "All five seeded scenarios match their expected outcomes, live and in pytest. Every run records input IDs, config version and hash, rule results, the blocked attempt and the decision. Simulated systems and assumptions are listed. Next step: workflow integration, once the business confirms the field dictionary, rule catalogue and baselines." |

## What not to spend time on
- *Agent pipeline* and *Token analysis*: show them only if a judge asks. They support the story, they are not the story.
  The answer: "Each step is a separately testable component with a declared input/output contract. AI reads the form for the
  checker. It is advisory, labelled, and never read by the rule engine."

## Fallbacks
- If the live demo fails, play the recorded video. `reports/scenario_results.md` shows all five outcomes and the AC4 comparison.
- If a config edit has a typo, the rule panel shows the exact YAML error and refuses to run. Fix it and re-run. This is a feature.
- Do not claim volumes, handling time or savings. Baselines have not been provided.

## Likely judge questions
- **Why config-driven?** Control owners change evidence policy and field rules without a release. Every result records the exact
  config hash used, and the comparison view replays any input under any two versions.
- **Why can't the engine approve?** The result type has no approval field. Only `DecisionRecord` has one, and the API creates it
  for an independent checker. PASS and EXCEPTION both require a human decision.
- **How is SoD enforced?** Server-side in `sod.py`. The implementer of the change gets 403 `SELF_APPROVAL_BLOCKED`, any maker gets
  403 `ROLE_NOT_PERMITTED`, and blocked attempts are audited.
- **What happens after Investigate?** The item is routed to a *simulated* exception queue for the original processor, with the
  findings and the checker comment. No CheckMate task is created and nobody is contacted (FAQ Q15, Q33).
- **What is real vs simulated?** The engine, rules, UI, decisions, queue file and audit log are real code. ServiceNow, DMS, TNAL,
  GPS, ACH/AES, CheckMate and the LLM gateway are simulated.
- **Where is AI used?** In one agent only, which reads the authorization form. Its output is labelled, shows confidence and must
  be confirmed by the checker, and the rule engine never reads it. "AI reads the document; rules decide; the checker approves."
- **Path to production?** The organizer's data-gap table in the README: field dictionary and keys, rule catalogue, evidence
  policy, operating model, baselines and NFRs.
