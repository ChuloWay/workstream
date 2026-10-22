# Example task brief: recover a file-processing queue after interruption

## Authoring assignment

Create a terminal task in which the solver repairs a local file-processing queue.
The queue accepts jobs, persists their progress and writes a result for each
completed job. Its starting implementation mishandles interruption and replay.

Give the solver a small working application, a documented command interface,
representative inputs and a reproducible failure. The solver must investigate
and repair the application while preserving its documented behavior.

## Required behavior to specify

- A durable job identifier distinguishes a repeated delivery from a new job.
- Repeating an already completed job returns its retained result without
  performing its effect again.
- A restart recovers interrupted work without losing previously completed jobs.
- Reusing an identifier with different input is rejected without changing the
  original job or its result.
- A failed input does not corrupt unrelated jobs, and the status command reports
  a useful, accurate outcome.

As the task author, define the exact command and data formats, interruption
points, recovery rules and observable effects in the solver instructions. Choose
storage and programming tools appropriate to this small local application.
Do not require external accounts or a network service.

## Deliverable

Provide the complete task package described in the project guide: starting
workspace, environment, solver instructions, metadata, reference repair,
verification and author notes. Your tests should observe persisted state and
effects before and after restart. Include a plausible repair that passes an
ordinary successful run but fails one of the interruption or replay cases.

This brief is illustrative. It does not prescribe a single implementation or
make this task identifier an eligibility rule for other tasks in the project.
