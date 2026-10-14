"""Shareable originals and illustrative tasks for the connected public drill."""

TASK_EXAMPLES = [
    {"title": "Repair the sample worker", "labels": ["python", "debugging"],
     "content": "Repair the sample worker's incorrect result aggregation and explain the change."},
    {"content": "Investigate a second sample worker that returns duplicate results."},
]
GUIDE_BYTES = b"""# Sample worker repair project

Investigate and repair the assigned sample worker. Submit one ZIP containing
`task.toml` and `evidence/results`. Explain the work in the submission summary
and confirm rights_confirmed in the attestation. Individual files must be at
most 1000000 bytes and the package at most 5000000 bytes.

The project intake image checks the package's project-specific rules. The
post-submit image checks the supplied evidence. The sample image has bounded
fixture markers for negative trials; it does not claim general code judging.
Project managers separately approve the proposed pre- and post-submit rules.
The locked review policy determines whether passing work needs human review.
"""
CORRECTION_REASON = "Confirm that both task examples use the same project artifact and evidence rules."
