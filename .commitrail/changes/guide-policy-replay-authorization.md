# Reauthorize guide and policy mutation replays

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Exact draft-guide edit and review/revision policy replays require current canonical Project Manager authority before returning their immutable receipts.

## Intent

An exact replay key must recover an earlier guide or policy write only for the
same authorized human and identity link. This matters because a former Project
Manager currently recovers a 200 receipt after grant revocation, although a new
write returns 403. The original receipt remains historical evidence, not a
permission token or a request to repeat the write.

## Current behavior

The public guide PATCH and policy PUT dependencies verify the token/key and
resolve an actor, but do not consume authorization. In
`GuideMutationService.update_guide` and `ProjectPolicyMutationService._replace`,
the committed replay lookup returns before `prepared.prepare`/`consume`.
Policy reservation's concurrent-replay branch also returns before PREP. The
policy lookup does not compare the stored identity-link ID, unlike guide replay.
The #599 public socket/PostgreSQL probe demonstrated new-key 403 after a public
Project Manager grant revoke but exact-key 200 for all three writes; see
[issue #614](https://github.com/Flow-Research/workstream/issues/614).

The existing guide-create replay in `guide_mutation_service.py` shows that
replay must recheck current authority without another product write. Its
historical resource facts are available in stored creation custody; guide
PATCH stores only a resource digest, not the predecessor snapshot selector.
Policy replacement must preserve an old receipt after a legitimate successor
changes the current selector; replay cannot be gated by the current-policy
precondition.

## Bounded change

Allowed: `backend/app/modules/projects/guide_mutation_service.py`,
`policy_mutation_service.py`, and `policy_mutation_replay_repository.py` for
exact replay admission; focused existing/new tests under `backend/tests/` for
the three public routes and service/race behavior; this record; and only affected
README/roadmap wording if actual current claims need correction. Reuse existing
PREP/AUTH owners and stored replay identity; do not scan guide-source history.

Prohibited: CLI #599 files, new AUTH route/action/permission, client-side
authorization, compatibility implementation, backend schema/migration, retained
data deletion, broader replay rewrites, changed policy semantics, current
selector refetch, new write on replay, CI weakening, or altered public API
shapes. No new replay resource or persisted lineage field is authorized in this
bounded repair; a requirement for full historical-resource consumption would
need another plan review and explicit schema authority.

## Design and decisions

For each committed exact replay, validate actor/action/key, exact identity
link, project/guide, request digest and stored receipt before exposing it.
Guide PATCH custody additionally binds the persisted resource ID to the URL
guide ID, and the validated response ID/project ID to that same guide/project;
the non-null stored resource digest, operation ID and generation remain the
original write's evidence. Policy custody binds stored policy ID/generation/
hash to the validated response ID/generation/hash/project ID, the original
`If-Match` predecessor to the historical response's supersession, and the
persisted resource digest to the reconstructed original policy resource when
all original facts are available. Retain supported v1 response recovery. A
failed custody check is a conflict/integrity failure, never a successful replay.

After custody, call existing PREP `prepare` for the original action and exact
project, using stored operation selectors; close the unconsumed handle and
return the unchanged receipt. This is **current-authority receipt retrieval**,
not a completed mutation authorization or a new AUTH decision. PREP locks and
checks current actor, exact link, lifecycle, action availability, and effective
Project Manager grant for the requested project; its successful handle confers
no product write. A failed preparation uses the existing bounded denial
resource and AUTH evidence path. The route rolls back successful replay-only
state. Apply the same admission to policy's reservation-conflict branch. Match
the policy record's identity-link ID in both lookup and reservation
classification. No selection or edit runs twice.

The original guide PATCH `consume` guard checks resource type, exact scoped
project, and `target_kind=update`; policy `consume` checks its distinct review
or revision resource type and exact scoped project. These are mutation-resource
guards, not an additional current receipt-read grant. They were satisfied by
the original committed write; replay custody binds their stored digest and
response to the original target. Current guide draft status, predecessor
source snapshot, and selected-policy predecessor are new-write preconditions,
not current receipt-read requirements. `list_guide_source_snapshots` has no
limit/pagination and PATCH stores no predecessor snapshot selector, so reversing
its digest by candidate scan is not bounded or sound. No fabricated historical
resource is passed to `consume`.

Lock order: guide PATCH new write takes manager actor -> exact link -> scoped
grant -> project/guide/source -> guide replay row; exact replay takes an MVCC
replay read -> manager actor/link/grant, with **no** guide replay row lock.
Policy new write already takes a policy replay reservation row -> manager
actor/link/grant -> guide/policy; reservation-conflict replay retains that row
-> actor/link/grant order, while direct committed lookup is MVCC read ->
actor/link/grant. Concurrent same-key policy writers serialize at that same
reservation row; guide writers serialize at guide/project before their replay
row. Public grant revoke, actor suspend, and link revoke use a separate AUTH
idempotency row -> control -> caller actor/link/grant -> target grant or target
actor/link. They do not acquire either product replay table or product guide
rows, while receipt retrieval acquires no control or caller-admin target after
its target manager locks. Thus the added lock edges do not point back to a
lock held by those public revokers; focused PostgreSQL races will test this.

The native same-key race exposed an existing policy-reservation fault: its
no-op `ON CONFLICT DO UPDATE` fires the immutable replay trigger, whose
whole-row equality cannot compare the PostgreSQL `json` response column. One
overlapping PUT returned 503 with `could not identify an equality operator for
type json`. Within the existing replay repository, use the AUTH reservation
pattern: `ON CONFLICT DO NOTHING`, then lock the exact
actor/action/idempotency-key row with `SELECT ... FOR UPDATE` after the
conflicting insert resolves. This retains the reservation-row -> PREP order,
classifies the same link/project/guide/digest/hash mismatch, and does not
update a committed receipt or create a schema dependency. The isolated
PostgreSQL race must prove one response and one version after this repair.

The optimistic exact-replay lookup can miss an in-flight first writer. On
policy PUT, if that writer commits before the waiter's unlocked guide snapshot,
the changed review/revision selector raises a new-write 409 before reservation;
the same window can encounter a no-longer-draft guide. On guide PATCH, the
waiter can pass its first miss then wait on project/guide locks until the first
write commits, and a later status transition could make its draft guard reject
an exact receipt. Re-read only the exact actor/action/key receipt at these
new-write precondition boundaries; if present, run its same custody and current
PREP admission and return it, otherwise preserve the original error. The guide
waiter already holds its actor/link/grant locks before project/guide, so the
second PREP takes no new cross-transaction lock edge; close the first unused
handle on replay. No success decision is consumed twice.

Rejected: possession of a key as authority; scanning an unbounded source
history to reverse a digest; checking the current policy/snapshot as original;
fabricating a historical resource for `consume`; a new replay AUTH action or
parallel token. A full replay `consume` would require the unavailable original
guide predecessor selector, hence a separately approved schema/data plan.

## Acceptance criteria

- [ ] Public real-PostgreSQL requests prove original success and active
  same-key/same-body replay for guide PATCH, review PUT and revision PUT, with
  exactly one product version/edit and unchanged historical responses.
- [ ] Revoked manager grant, suspended actor and revoked exact identity link
  deny exact replay and fresh writes through canonical AUTH. Wrong project,
  foreign actor/link, changed body/key and wrong original `If-Match` cannot
  recover a receipt. Denial and mismatch preserve retained product facts.
- [ ] An authorized old review/revision policy replay still returns its original
  receipt after a successor policy is selected. Historical guide-source changes
  do not gate guide-edit replay or get substituted into its original receipt.
- [ ] Policy reservation races cannot bypass current AUTH or identity-link
  custody; serialization does not invert actor/link/grant and product lock order
  or create duplicate policy/guide rows, audit provenance or replay records.
- [ ] Existing relevant backend tests continue to pass; no skip, weakened
  assertion, new schema, or changed public contract is introduced.

## Risk and review routing

Risk class: L1 bounded authorization/replay repair. Urgency: blocks #599 write
readiness; no delivery date inferred. Work type: security bug. Required internal
review tracks after a clean candidate: security (grant/link/scope/replay), QA
and test delta (failing-before-fix public probe and unaffected controls),
architecture/reuse (canonical PREP and retained replay custody), docs (roadmap
claims), and senior engineering for lock/concurrency risk. The parent coordinates
reviewer slots and plan review. Human review focus: why replay preparation is
an AUTH-owned current-grant check without final consumption, no live selector dependence,
current authority on every replay,
identity-link custody, lock order/atomicity and unchanged retained evidence.
Separate PR; no merge without explicit approval.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Reproduced defect | #599 isolated public socket/PostgreSQL probe on main `51b868071`; unique database metadata `/tmp/workstream-599-config-isolation3.json` | Three fresh 403 controls and three exact revoked-grant replay 200 failures; database/role cleanup complete | This proves grant revocation, not actor/link or race behavior |
| Concurrent reservation diagnosis | Isolated public PostgreSQL run on `c003fee650936f819c1bf443dff43f5e96501a23`, `/tmp/workstream-614-replay-auth-concurrency.json` | One same-key policy PUT returned 200, the other 503 from immutable trigger's JSON whole-row equality on no-op conflict UPDATE; runner cleaned its DB/role | Resolved by exact-row `DO NOTHING` reservation and forced-overlap public proof below |
| Owner feasibility | Read-only trace of routes, PREP/AUTH, replay repositories, guide-create replay and existing tests | Existing `prepare` locks/rechecks actor, link and effective manager grant for original action/project; `close_handle` discards unused capability; both replay records retain original identity/digest/receipt | Current authority proven in public PostgreSQL; no final replay resource is consumed |
| Focused pure verification | `python -m pytest -q backend/tests/test_project_policy_mutations.py backend/tests/projects/review_policy/test_mutation.py`; targeted guide receipt/custody cases from `backend/tests/test_projects.py`; `ruff check` on changed backend files | Policy/legacy suite 30 passed; guide cases 4 passed; later custody/repository cases 6 passed; Ruff passed | Full suite and CI remain external gates |
| Native public verification | `backend/scripts/run_isolated_tests.py` on `fb28ef6d56300c7848817ecf846cba4955483499`, metadata `/tmp/workstream-614-replay-auth-3.json` | Five public cases passed, including forced same-key reservation overlap and review/revision/guide stale-miss recovery; revocation fixture timed out waiting for grant-query entry before committing the revoke; DB and role cleanup complete | Fixed test assumption after exact PostgreSQL lock diagnosis below |
| Revocation lock diagnosis | Isolated single public case on `a3d1c2685214e1bce4a7b59ddb8e28bc156628d2`, metadata `/tmp/workstream-614-replay-auth-lockdiag.json`; status probe on `6060236a94dfa8cb4b8a77f285220bcf9dc5935d`, metadata `/tmp/workstream-614-replay-auth-lockdiag2.json` | `pg_stat_activity` with `pg_blocking_pids`: waiter PID 1036 blocked by revoker PID 1037 on `transactionid`; SQL was `SELECT actor_profiles ... WHERE actor_profiles.id = $1::UUID FOR UPDATE`. After commit exact replay returned 403 `permission_not_granted`; both isolated DBs/roles cleaned. Hook missed because fixture actor ID is stored string while AUTH argument is UUID. | Test-only identifier comparison normalized; final clean run below passed |
| Final focused public proof | `backend/scripts/run_isolated_tests.py` on clean `bb1f703745bc21310789d3bdca30d224c8518ce5`, metadata `/tmp/workstream-614-replay-auth-final.json`, running `pytest -q tests/projects/test_guide_policy_replay_authorization.py --tb=short` | Six passed in 70.71s: three-route grant/actor/link denial with audit, historical policy receipts, forced same-key reservation overlap, both policy stale-miss schedules, guide stale-miss, and PostgreSQL revoke/replay lock order; unique database and role cleanup complete | Internal focused review and PR/CI remain outstanding |
| Static and record checks | Ruff lint on changed backend files; Ruff formatter on new public test and new replay repository; baseline formatter check for five affected existing files; `scripts/check_commitrail_records.py --base-ref 51b86807111ff25b067402219ba0b533e0750f3e`; `scripts/check_markdown_links.py`; `git diff --check` | Lint, new-file formatting, Commitrail, links and whitespace passed. Each of the five pre-existing files already fails whole-file Ruff formatting at base; this PR does not perform unrelated bulk formatting. | CI and reviewer verdicts remain outstanding |

## Reconciliation

- Current-source reconciliation: main `51b868071`; #599 CLI remains a separate frozen branch and is not a source for this PR.
- Next usable boundary: #599 reruns its intentionally failing exact-replay regression against this correction after merge/rebase.
- Remaining risks: `prepare`-only replay admission has no final resource guard or allowed replay audit event; exact persisted replay custody and current AUTH grant/lifecycle locks are its boundary. The focused PostgreSQL races establish the current lock order, but independent security/architecture review, CI and human review remain before readiness.
