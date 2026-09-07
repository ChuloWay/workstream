# Commitrail in Workstream

Commitrail is Workstream's repository-native engineering method. It preserves
useful intent, boundaries, evidence, review findings, and decisions without
becoming a permission system or a stale copy of GitHub.

```text
Intent -> Plan -> Bounded Change -> Tests -> Review -> PR -> Human Merge
```

## Sources of authority

1. Code, migrations, tests, accepted ADRs, and canonical specifications define
   implemented and required product behavior.
2. [`docs/roadmap_status.md`](../docs/roadmap_status.md) is the current product
   capability ledger.
3. [Open pull requests](https://github.com/Flow-Research/workstream/pulls), CI,
   reviews, approvals, and merge state live on GitHub.
4. [`INDEX.md`](INDEX.md) records durable engineering dispositions and links to
   concise multi-PR initiative context.

Commitrail records explain work. GitHub permissions and branch protection
govern contribution authority. Humans decide product intent, material risk,
approval, and merge.

## Smallest useful record

| Change | Record |
|---|---|
| Editorial correction to README or ordinary documentation outside process-control paths | PR description with intent and scope |
| Meaningful single-PR change without an initiative | One `changes/<slug>.md` based on `CHANGE_TEMPLATE.md` |
| Multi-PR initiative | One initiative `OVERVIEW.md` plus one change record per PR |
| Exceptional risk | Add only evidence or decisions needed to control that risk |

Use a lowercase kebab-case standalone filename, for example
`changes/fix-guide-validation.md` and declare `- Initiative: None` exactly once.
Standalone records need no initiative overview
or index row. Changes belonging to an existing initiative keep its record layout.
Exactly one change record is used per implementation PR across both layouts.

The validator requires a record for changes under `backend/`, `frontend/src/`,
`scripts/`, `.agents/skills/`, `.codex/agents/`, `.ci/`, `.github/workflows/`,
`.commitrail/`, and `docs/engineering/`, and for `AGENTS.md`, `CONTRIBUTING.md`,
and `.github/pull_request_template.md`. Even a small correction in those paths
uses a concise record. Mixing a README edit with those changes is not exempt.
Other paths are not classified semantically by this gate: meaningful behavior,
configuration, dependency, or specification changes still require a record and
appropriate review. A passing path check does not establish low risk.

Do not commit transient labels such as “in review,” “CI pending,” or “ready to
merge.” GitHub already owns those facts. Durable dispositions are `Planned`,
`Complete`, `Stopped`, and `Superseded`.

The record owns durable intent, boundaries, design decisions, acceptance claims,
and remaining risk. The PR links that record and owns current diff, command
results, exact-head reviewer freshness, CI, and conversations. Do not repeat the
same narrative or store the record's own candidate SHA inside it: that forces
another commit and immediately makes the SHA stale. Each overview links the
current usable change record before historical discovery. Read archives only
when the current boundary adopts or needs a specific source.

Risk classes are defined once in
[`risk-router`](../.agents/skills/risk-router/SKILL.md): L0 highest, L1 bounded
high risk, L2 routine low risk. Documentation uses its semantic risk.

## Starting work

1. Pull current `main` and read `CONTRIBUTING.md`.
2. Check the capability ledger, this index, canonical specifications, and open
   PRs for overlap.
3. Confirm intent and non-goals.
4. Use the smallest record above.
5. Implement, test, run impact-routed review, reconcile with current `main`,
   and open a PR.
6. Stop for human approval and merge.

Distinct initiatives may proceed concurrently. A new base invalidates only the
evidence affected by its changed impact cone.

## Exact pre-cutover work records

Every active initiative carried into Commitrail retains a verbatim
`pre-cutover/` copy of its former status, chunk map, intent, discovery, plan,
decisions, risks, chunk contracts, evidence, reviews, and other initiative
files. This preserves the complete accounting of delivered, current, blocked,
superseded, and remaining work without summarizing it away.

These exact files are handoff evidence, not an executable queue, permission
source, or instruction to repeat the former automation. Each initiative's
`OVERVIEW.md` remains the current entry point and links to its full record.
[`PRE_CUTOVER_MANIFEST.tsv`](initiatives/WS-ENG-009/PRE_CUTOVER_MANIFEST.tsv)
binds every preserved source and destination to its Git blob at the declared
cutover base. Agent Gates rejects a missing, extra, or modified preserved file;
corrections belong in current Commitrail records rather than edits to history.
