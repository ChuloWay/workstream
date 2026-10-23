"""Complete synthetic PRE/POST output example, never project evidence or policy."""

PROJECT_GUIDE_OUTPUT_EXAMPLE = {
    "hypothetical_guide": "Submit a root report file. Its conclusions must follow from its reported "
    "observations.",
    "assumption": "No project checkers are registered; model support is unavailable. These synthetic "
    "identities are not actual source references.",
    "result": {
        "status": "draft_ready_with_warnings",
        "findings": [],
        "submission_artifact_policy": {
            "packaging": "zip",
            "maximum_file_size_bytes": None,
            "maximum_package_size_bytes": None,
            "maximum_archive_size_bytes": None,
            "maximum_archive_entries": None,
            "allowed_storage_schemes": ["artifact"],
            "required_artifacts": ["report.md"],
            "forbidden_artifacts": [],
            "required_evidence": [],
            "attestation_terms": [],
        },
        "requirements": [
            {
                "requirement_id": "report_present",
                "statement": "The package includes a report as a root regular file.",
                "disposition": "pre_submit_capability_gap",
                "platform_coverage": None,
                "classification_rationale": "One exact file type check is bounded.",
                "check_specification": {
                    "evaluation_method": "static_inspection",
                    "execution_mode": "bounded_pre_submit",
                    "maximum_duration_seconds": 10,
                    "stage_rationale": "One exact file type check is bounded.",
                    "inputs": [
                        {
                            "input_id": "report",
                            "kind": "relative_file",
                            "relative_path": "report.md",
                            "purpose": "Supplies the report to inspect.",
                        }
                    ],
                    "check_steps": ["Require the declared root report to be a regular file."],
                    "pass_conditions": ["The required report exists as a regular file."],
                    "failure_findings": [
                        {
                            "code": "report_missing",
                            "level": "error",
                            "condition": "The required report is absent or has the wrong type.",
                            "message": "Provide the required report.",
                        }
                    ],
                    "positive_tests": ["A package with the required report passes."],
                    "negative_tests": [
                        {
                            "name": "missing_report",
                            "scenario": "The report is absent.",
                            "expected_verdict": "failed",
                            "expected_finding_codes": ["report_missing"],
                        }
                    ],
                    "runtime_dependencies": [
                        {
                            "dependency_id": "file_inspection",
                            "kind": "checker_tool",
                            "provisioning": "checker_implementation",
                            "purpose": "Inspect the required file type.",
                            "unavailable_code": "implementation_unavailable",
                        }
                    ],
                    "infrastructure_failures": [
                        {
                            "code": "implementation_unavailable",
                            "condition": "The required checker implementation is unavailable.",
                        }
                    ],
                },
                "evidence_refs": [
                    {
                        "source_item_id": "00000000-0000-4000-8000-000000000001",
                        "document_version_id": "00000000-0000-4000-8000-000000000002",
                        "sha256": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
                        "start_page": None,
                        "end_page": None,
                        "section": "Deliverable requirements",
                    }
                ],
            },
            {
                "requirement_id": "report_reasoning",
                "statement": "Report conclusions must be supported by reported observations.",
                "disposition": "post_submit_capability_gap",
                "platform_coverage": None,
                "classification_rationale": "Comparing conclusions with observations "
                "requires qualitative evaluation.",
                "check_specification": {
                    "evaluation_method": "model_evaluation",
                    "execution_mode": "background",
                    "maximum_duration_seconds": 120,
                    "stage_rationale": "Comparing conclusions "
                    "with observations "
                    "requires qualitative "
                    "evaluation.",
                    "inputs": [
                        {
                            "input_id": "report",
                            "kind": "relative_file",
                            "relative_path": "report.md",
                            "purpose": "Supplies the report to inspect.",
                        }
                    ],
                    "check_steps": [
                        "Read the reported observations and conclusions.",
                        "Identify any conclusion "
                        "that conflicts with or "
                        "lacks support in the "
                        "observations.",
                    ],
                    "pass_conditions": [
                        "Every conclusion is supported by the reported observations."
                    ],
                    "failure_findings": [
                        {
                            "code": "unsupported_conclusion",
                            "level": "error",
                            "condition": "A "
                            "conclusion "
                            "conflicts "
                            "with or "
                            "lacks "
                            "supporting "
                            "observations.",
                            "message": "Support each conclusion with reported observations.",
                        }
                    ],
                    "positive_tests": [
                        "A report whose conclusions follow its observations passes."
                    ],
                    "negative_tests": [
                        {
                            "name": "contradictory_report",
                            "scenario": "The conclusion contradicts a reported observation.",
                            "expected_verdict": "failed",
                            "expected_finding_codes": ["unsupported_conclusion"],
                        }
                    ],
                    "runtime_dependencies": [
                        {
                            "dependency_id": "reasoning_model",
                            "kind": "model_service",
                            "provisioning": "runtime_gap",
                            "purpose": "Apply the qualitative evidence rubric.",
                            "unavailable_code": "implementation_unavailable",
                        }
                    ],
                    "infrastructure_failures": [
                        {
                            "code": "implementation_unavailable",
                            "condition": "The required model service is unavailable.",
                        }
                    ],
                },
                "evidence_refs": [
                    {
                        "source_item_id": "00000000-0000-4000-8000-000000000001",
                        "document_version_id": "00000000-0000-4000-8000-000000000002",
                        "sha256": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
                        "start_page": None,
                        "end_page": None,
                        "section": "Deliverable requirements",
                    }
                ],
            },
        ],
        "pre_submit_bindings": [],
        "post_submit_bindings": [],
        "capability_suggestions": [
            {
                "requirement_id": "report_present",
                "stage": "pre_submit",
                "title": "Report file check",
                "rationale": "Implement the specified file predicate.",
                "evidence_refs": [
                    {
                        "source_item_id": "00000000-0000-4000-8000-000000000001",
                        "document_version_id": "00000000-0000-4000-8000-000000000002",
                        "sha256": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
                        "start_page": None,
                        "end_page": None,
                        "section": "Deliverable requirements",
                    }
                ],
            },
            {
                "requirement_id": "report_reasoning",
                "stage": "post_submit",
                "title": "Report reasoning review",
                "rationale": "Implement the specified background model rubric.",
                "evidence_refs": [
                    {
                        "source_item_id": "00000000-0000-4000-8000-000000000001",
                        "document_version_id": "00000000-0000-4000-8000-000000000002",
                        "sha256": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
                        "start_page": None,
                        "end_page": None,
                        "section": "Deliverable requirements",
                    }
                ],
            },
        ],
        "agent_name": "ProjectGuideCompilationAgent",
        "agent_version": "example_v1",
        "schema_version": "project_guide_compilation_result.v1",
    },
}
