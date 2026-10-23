# WS-AGENT-001 — Replaceable guide runtimes

- Disposition: Planned

Workstream must switch agent runtimes and inference providers without changing
PROJECTS/ART business logic or source-evidence schema. The user explicitly asked
for OpenRouter and a second real OmniCoreAgent adapter to prove that boundary.
The first hosted contribution journey remains the delivery objective.

The current OpenAI-hosted file/attachment coupling violates that boundary.
Use trusted on-demand document tools, a fixed isolated parser and the existing
compilation/result contract. Each adapter owns its SDK mechanics; the core owns
exact source access, immutable attempt evidence and overall run bounds.

1. [Neutral tools and OpenRouter](WS-AGENT-001-01.md): replace the current hosted
   document path, preserve historical facts/cleanup, qualify OpenAI Agents SDK.
2. OmniCoreAgent qualification (companion change): register the real second
   runtime, handle its native mechanics inside its adapter, run the same contract
   and live-guide qualification in its isolated dependency environment.

SDK environments may differ; product contracts and core behavior must not.
No speculative Claude adapter, generic plugin platform, runtime-generated shell
or future product work. No full hosted journey is claimed by adapter tests.
Merged PR #651's draft-review/checker-specification behavior remains required
for every runtime. Retained unresolved provider attempts cannot be reset or rerun.
