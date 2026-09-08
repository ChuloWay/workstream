# WS-AUTH-001 — Current pre-review activation map

Use the [current plan](PLAN.md) and
[cross-owner order](../../WS-ARCH-001/planning/PLAN.md#current-dependency-contract).
The [verbatim former map](../pre-cutover/CHUNK_MAP.md) preserves all completed
work and historical proposals.

| Boundary | Current owner and prerequisite |
|---|---|
| AUTH-12B2 | Complete; POL-04B is the live consumer |
| AUTH-12F4 | AUTH approval adapter after hidden POL-05A, before POL-05B |
| AUTH-12G | AUTH post-policy adapters after hidden POL-06A, before POL-06B |
| AUTH-12H | AUTH exact activation of hidden CP07 after POL-07 |
| CP05 | AUTH exact five policy actions after merged CP04A/CP04B |
| ARCH-03C | AUTH task/assignment activation after ARCH-03B; replaces broad AUTH-13 |
| ARCH-04D | AUTH materialization/final-result activation after ARCH-04B/04C; replaces AUTH-14/XINT-06B |

Guide activation needs CP05 -> CP06 -> hidden CP07 and POL-07, which also
requires independent ARCH-04A registered-capability proof. It does not need
a Task, Submission, CheckerRun, CP09 deletion or REV execution.
