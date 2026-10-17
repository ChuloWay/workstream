# Original terminal benchmark pilot corpus

This is the shareable project input for [#576](https://github.com/Flow-Research/workstream/issues/576).
It supplies five task-authoring briefs, independent golden cases and reference
packages. It is not a production checker or an uploaded-code runner.

Run the trusted native calibration from the repository root:

```bash
python3 pilots/terminal_benchmark/verify_corpus.py
```

Python 3.12 standard-library modules are sufficient. The command executes only
the reviewed fixed corpus, creates temporary workspaces, and checks three
reference runs, failed unchanged starters, plausible wrong solutions, malformed
packages and ineffective-test detection. It verifies exact file membership and
SHA-256 values from `corpus.json` before running code. This is an integrity check,
not a signature or permission to execute an untrusted replacement corpus.
Do not use this script on uploaded submissions.

## Inputs and ownership

- [guide.md](guide.md) is the human-readable project guide.
- [guide-request.json](guide-request.json) uses the current guide-creation schema,
  including five meaningful task examples and one declared Markdown document.
- [tasks.json](tasks.json) is the sole native TaskImportDocument. It contains no
  invented package fields or required task-local acceptance criteria.
- [corpus.json](corpus.json) binds package paths, external task IDs and file hashes.
- [negative-cases.json](negative-cases.json) specifies the bad-package/near-miss
  probes and names their expected rejecting boundaries.

Upload the exact checked-in `guide.md` bytes through the authorized guide-document
API using its declared `text/markdown` media type, which the current guide owner
supports. Retain that document's SHA-256 as drill evidence. The JSON declaration
alone does not upload bytes or start a completed setup run. No binary or private
document is checked into this corpus.

Each package is independently usable as an example submission ZIP. Archive its
contents at the ZIP root, with no enclosing `packages/<name>/` directory. Runtime
build context excludes reference solutions and tests. Trusted reference
calibration overlays `solution/program.py` into a separate workspace; tests are
injected separately. Candidate execution must not receive `solution/`.

## What remains

[#493](https://github.com/Flow-Research/workstream/issues/493) owns real offline
builds, registered project PRE/POST images and gVisor execution. The fixed recipe
and `task.toml` commands are inputs to that implementation, not proof it exists.
Approved base-cache availability, platform compatibility and Docker build failure
are deliberately outside the native verifier's claims.

[#580](https://github.com/Flow-Research/workstream/issues/580) owns supported
Operator registration. [#555](https://github.com/Flow-Research/workstream/issues/555)
combines these assets with actual setup inference, authorized approvals and
activation, import/release, contributor intake, workers, failure/retry and exact
ContributionRecord evidence. Policy suggestions in the guide require separate
manager and Finance decisions. No API credentials, approval receipts or product
records are fabricated by this corpus.

These compact examples test the mechanics of task authoring; they make no claim
about general benchmark difficulty, novelty or resistance to strategic solvers.
