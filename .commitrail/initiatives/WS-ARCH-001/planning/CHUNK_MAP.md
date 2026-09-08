# WS-ARCH-001 — Current remaining change map

Use the [current dependency contract](PLAN.md#current-dependency-contract).
The [preserved map](../pre-cutover/CHUNK_MAP.md) retains the complete original
work accounting. Foundations through 02H and CP04B are complete; none restart.

| Boundary | Owner outcome | Risk | Current dependency |
|---|---|---|---|
| `WS-ARCH-001-02I` | Admission-only public API/dispatch cutover and removal of legacy route reachability; physical economic cleanup remains CP09 after zero consumers | L1 | Deferred after 02H plus split 03/04/05 remediation, revision, checker-output and REV admission prerequisites |
| [WS-ARCH-001-CP05](chunks/WS-ARCH-001-CP05-auth-policy-activation.md) | AUTH exact ContributionPolicy activation | L1 | Proposed skeleton after CP04 evidence |
| [WS-ARCH-001-CP06](chunks/WS-ARCH-001-CP06-con-policy-validation-port.md) | CON guide-activation/revision policy-validation port | L1 | Proposed skeleton after CP05 |
| [WS-ARCH-001-CP07](chunks/WS-ARCH-001-CP07-project-guide-policy-binding.md) | PROJECT hidden activation/binding and replacement readiness guard | L1 | Planned after CP06; AUTH-12H later supplies live activation authority |
| [WS-ARCH-001-CP08](chunks/WS-ARCH-001-CP08-task-attempt-policy-lineage.md) | TASK/Assignment/Submission policy-lineage schema and public facts | L1 | Proposed foundation after CP07; no commands |
| [WS-ARCH-001-CP09](chunks/WS-ARCH-001-CP09-legacy-economic-removal.md) | Physical retired economic-path cleanup coordination | L1 | Planned after all legacy consumers, including CHECKERS/public 02I, are replaced; not an allow_review dependency |
| [WS-ARCH-001-03A](chunks/WS-ARCH-001-03A-project-current-generation-api.md) | PROJECT current approved unified-generation public facts | L1 | Planned after AUTH-12H, CP07, and CP08; may reuse CP07 public guide fact but cannot duplicate its write |
| [WS-ARCH-001-03B](chunks/WS-ARCH-001-03B-task-assignment-api.md) | TASK readiness, claim, assignment and locked-context public commands/facts | L1 | Sole behavior owner after 03A and CP08; consumes CP08 fields/facts to write Task -> Assignment -> Submission lineage |
| [WS-ARCH-001-03C](chunks/WS-ARCH-001-03C-auth-task-readiness.md) | Exact task/assignment action activation, routing and invalidation proof | L1 | Planned after 03A/03B, CP08 and AUTH-OUTBOX-02; replacement precedes physical cleanup |
| [WS-ARCH-001-04A](chunks/WS-ARCH-001-04A-checker-post-submit-api.md) | CHECKER post-submit contract and registered evaluator conformance | L1 | Planned from merged catalogue/unified contracts; precedes POL-07, no task/guide activation dependency |
| [WS-ARCH-001-04B](chunks/WS-ARCH-001-04B-art-post-submit-materialization.md) | ART exact verified Submission materialization | L1 | Planned after 04A, POL-07, 03C and merged 02H |
| [WS-ARCH-001-04B2](chunks/WS-ARCH-001-04B-art-post-submit-materialization.md#arch-04b2--separate-art-output-custody-child) | ART generated-output/log custody and verified binding | L1 | 04A public request/run facts plus merged ART foundations; no CHECKERS private lookup |
| [WS-ARCH-001-04C](chunks/WS-ARCH-001-04C-checker-current-result.md) | CHECKER hidden durable current output and supersession behavior | L1 | Planned after 04A/04B/04B2; production remains deny-only |
| [WS-ARCH-001-04D](chunks/WS-ARCH-001-04D-auth-post-submit-activation.md) | AUTH exact fixed-service post-submit activation (replaces XINT-06B) | L1 | Planned after 04B/04C evidence |
| [WS-ARCH-001-04E](chunks/WS-ARCH-001-04E-canonical-allow-review.md) | TASK automatic dispatch/current routing integration and canonical `allow_review` manifest | L1 | Coordination: hidden 04E1 -> AUTH 04E2 -> live 04E3, also requiring 04D and AUTH-OUTBOX-02 |
| [WS-ARCH-001-04F](chunks/WS-ARCH-001-04F-checker-remediation.md) | Contributor-correctable checker failures and same-lineage admission-backed replacement Submission | L1 | Planned after 04E; replaces XINT-05C, required before public 02I, not before REV begins from `allow_review` |

CP09, 04E and 04F are coordination parents, not permission for multi-owner PRs.
Only CP09 and 04F are outside the `allow_review` critical path; 04E's children
deliver that boundary. Each remaining implementation
expands its current child contract into one existing-initiative change record
with exact paths, schema head, proof commands and impact-routed reviewers.
That expansion belongs to its implementation PR, not an extra approval loop.
No new product implementation starts automatically on merge of this plan.
