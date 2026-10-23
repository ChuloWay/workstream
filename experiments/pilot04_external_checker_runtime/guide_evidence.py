"""Small evidence oracle for the recorded guide drill; no product authority."""


def verify_source_commitment(source, attempt, *, examples, examples_hash, source_hash,
                             source_id, original_sha256, accesses):
    """Check persisted input lineage and original-read custody, never generated prose."""
    if (source["task_examples"] != examples
            or source["task_examples_hash"] != examples_hash
            or source["manifest_json"]["task_examples_hash"] != examples_hash
            or source["manifest_json"]["task_examples_count"] != len(examples)
            or source["bundle_hash"] != source_hash):
        raise AssertionError("guide/example/source commitment differs")
    if (attempt["status"] != "compilation_persisted"
            or attempt["source_snapshot_hash"] != source_hash
            or str(attempt["source_snapshot_id"]) != source_id
            or attempt["canonical_input_hash"] != attempt["compiled_input_hash"]):
        raise AssertionError("worker input lineage differs")
    if not any(
        str(access["source_snapshot_id"]) == source_id
        and access["sha256"] == original_sha256
        and access["manifest_sha256"] == attempt["guide_material_hash"]
        and access["access_method"] == "trusted_parser"
        and access["operation"] == "read"
        for access in accesses
    ):
        raise AssertionError("worker original-read custody is missing")
