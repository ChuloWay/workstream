# WS-AUTH-001 — Current pre-review activation map

Use the [current plan](PLAN.md) and
[cross-owner order](../../WS-ARCH-001/planning/PLAN.md#current-dependency-contract).
The [verbatim former map](../pre-cutover/CHUNK_MAP.md) preserves all completed
work and historical proposals.

| Boundary | Current owner and prerequisite |
|---|---|
| AUTH-12B2 | Complete; POL-04B is the live consumer |
| [AUTH-12F4](chunks/WS-AUTH-001-12F4-submission-policy-approval.md) | AUTH full-proposal read, setup-wide correction and approval after hidden POL-05A, before POL-05B |
| [AUTH-12G](chunks/WS-AUTH-001-12G-post-submit-checker-policy-mutations.md) | AUTH post-policy adapters after hidden POL-06A, before POL-06B |
| [AUTH-12H](../WS-AUTH-001-12H.md) | Complete: exact manager authority for hidden CP07; HTTP exposure remains pending |
| CP05 | AUTH exact five policy actions after merged CP04A/CP04B |
| ARCH-03C | AUTH task/assignment activation after ARCH-03B and AUTH-OUTBOX-02 (active CON-02B dispatcher mechanics); replaces broad AUTH-13 |
| ARCH-04D | AUTH materialization/output plus CHECKERS execute/finalize activation after ARCH-04B/04B2/04C; replaces AUTH-14/XINT-06B |
| [AUTH-OUTBOX-01](PLAN.md#ws-auth-001-outbox-01--unavailable-dispatcher-contract) | Complete: unavailable exact dispatcher identity/action/phase contract; CON-02B and AUTH-OUTBOX-02 mechanics complete; feature authority/registration remain separate |
| [AUTH-OUTBOX-02](PLAN.md#ws-auth-001-outbox-02--exact-dispatcher-activation) | Complete: exact dispatcher mechanics activation, phase audit custody and bounded prefork workers; feature handlers remain unregistered |
| [ARCH-04E2](../../WS-ARCH-001/planning/chunks/WS-ARCH-001-04E-canonical-allow-review.md#current-bounded-sequence) | Exact TASK routing handler authority after hidden 04E1, before live 04E3 |

Guide activation needs CP05 -> CP06 -> hidden CP07 and POL-07, which also
requires independent ARCH-04A registered-capability proof. It does not need
a Task, Submission, CheckerRun, CP09 deletion or REV execution.
