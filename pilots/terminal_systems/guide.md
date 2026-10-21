# Terminal Systems — contributor guide

## The work

Create practical software tasks that another person or coding agent can solve
from a terminal. Each task should present a credible engineering problem,
provide the files and environment needed to investigate it, and allow the
finished work to be evaluated against clear requirements.

You are authoring the task, its starting environment, its reference solution and
its verification suite. The eventual solver is a different participant. Write
their instructions for someone who has not seen your solution or test code.

Tasks may involve application behavior, data processing, storage, build tools or
operations. Choose tools appropriate to the problem. This project does not limit
authors to one programming language, source filename or list of task identifiers.

## A useful task

Start with an observable problem and a reason it matters. Describe the starting
state, the intended result and any constraints the solver must preserve. Include
enough information to distinguish a correct solution from a plausible shortcut.

A task should require investigation and several related decisions. For example,
repairing a retrying job processor involves both preserving successful work and
handling an interrupted attempt; checking only its final exit status would miss
the essential behavior. Do not add unrelated obstacles just to make a task longer.

The task brief identifies the area of work. You must develop it into a complete
solver-facing specification. Resolve ambiguous requirements while authoring;
the verifier must not introduce rules that the solver could not discover in the
instructions or supplied specifications.

## What to deliver

Submit one ZIP containing a self-contained task package. Put its contents at the
archive root. Organize it as follows:

| Path | Purpose |
|---|---|
| `instruction.md` | The solver's objective, inputs, observable outputs, constraints and relevant examples. |
| `task.toml` | Task identity, environment requirements, execution commands and resource estimates. |
| `environment/` | Container build definition, dependency locks and environment setup assets. |
| `workspace/` | Starting source, configuration, data and other files available to the solver. |
| `solution/` | A reference implementation or reproducible repair procedure. |
| `tests/` | Verification entry point, cases and independently established expected results. |
| `AUTHOR_NOTES.md` | Explanation of the problem, verification coverage, validation observations and any known limitations. |

Subdirectories and additional files are allowed when the task needs them. Explain
their purpose in the author notes. Keep private credentials, personal information,
unrelated logs, caches and generated build output out of the package. Include
appropriate license notices for any material you are entitled to redistribute.

In `task.toml`, document the task's unique identifier and title, the supported
container platform, dependency and build requirements, commands to apply the
reference and run verification, their working directories, and expected CPU,
memory, disk and time needs. Commands must run unattended and report failure
through a nonzero exit status. Do not rely on an author's machine configuration.
Any project-wide machine-readable metadata schema must be supplied with the
project's authoring tools before contributors are asked to submit against it.

## Environment and reproducibility

The starting environment must build reproducibly from declared inputs. Pin base
images by digest and dependencies by exact version or lockfile. State the target
platform rather than assuming the evaluator has your workstation's architecture.

Supply the necessary data and dependency inventory. Build and execution must be
possible using prepared offline materials; a missing dependency must not be
silently downloaded during evaluation. If a brief cannot be delivered under that
constraint, raise the dependency before implementing the task.

The solver works without administrator privileges. Keep reference solutions,
verification code and expected answers outside the solver's environment.
Verification must operate on the solver's actual output or changed workspace;
it must not repair the submission or replace it with the reference first.

Use fresh workspaces for independent runs. Control randomness and incidental
variation that could change a correctness result. Specify tolerances where exact
equality is inappropriate and explain their justification.

## Reference solution

Supply a reference that performs the requested work from the same starting state
available to the solver. It must compute the result or apply the repair, rather
than return answers copied from the expected-result files.

The reference demonstrates that the task is achievable. It is not the source of
truth for the requirements. Establish expected results independently from the
written specification and check disagreements rather than changing tests simply
to agree with the reference.

## Verification quality

Evaluate behavior and relevant retained effects. A successful process exit is
insufficient when the requirement concerns written records, recovered state,
ordered results or preserved files.

Cover the main behavior, meaningful boundary conditions and the interactions
most likely to expose an incomplete solution. Check invalid input where the
instructions define it. Avoid enforcing a particular internal implementation
unless the task explicitly requires that implementation.

The untouched starting workspace must fail at least one substantive requirement.
The reference must satisfy all stated requirements. Include a plausible incomplete
repair and demonstrate which requirement rejects it. A suite that accepts an
unchanged starter, empty output or an implementation that only reproduces the
example output is not adequate.

Repeat reference verification in three fresh workspaces. Record the commands,
observed outcomes and resource usage in the author notes. These observations
help others reproduce your work; the submitted package must remain independently
verifiable. Do not claim measured difficulty without an actual evaluation that
supports that claim.

## Before submitting

Read the instructions as a solver who cannot see your private authoring files.
Check that every enforced rule is discoverable and every required result can be
observed. Rebuild from the declared inputs, check the starter, reference and
incomplete repair, and confirm the package includes everything needed to repeat
those checks.

If feedback identifies a defect, correct the package and rerun the affected
verification. Explain what changed and any remaining limitation. Do not alter
the task's objective merely to make a failing implementation pass.
