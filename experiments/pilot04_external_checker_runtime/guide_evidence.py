"""Small evidence oracle for the recorded guide drill; no product authority."""


def verify_source_commitment(source, attempt, *, examples, examples_hash, source_hash):
    """Reject substituted source/examples or a runtime observing another input."""
    if (source["task_examples"] != examples
            or source["task_examples_hash"] != examples_hash
            or source["manifest_json"]["task_examples_hash"] != examples_hash
            or source["manifest_json"]["task_examples_count"] != len(examples)
            or source["bundle_hash"] != source_hash):
        raise AssertionError("guide/example/source commitment differs")
    if attempt["canonical_result"]["setup_notes"] != [
        "Recorded provider observed examples " + examples_hash,
        "Recorded provider observed input " + attempt["canonical_input_hash"],
    ]:
        raise AssertionError("worker observed another committed input")
