//! Fixed project checker for the reviewed public terminal-benchmark package.

use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::fs;
use std::io::{self, Read};
use std::path::{Path, PathBuf};
use workstream_checker_sdk::{
    completed_result, parse_request, terminal_benchmark_plan, Finding, ValidatedRequest,
    MAX_REQUEST_BYTES,
};

const INPUT_ROOT: &str = "/work/input";
const CONFIG_VERSION: &str = "terminal_benchmark_project.v1";
const BASE: &str = "python:3.12-slim-bookworm@sha256:6e13e65c55e33adf203d77ee371cf8bf5d81bd4902ef07565721f46bf44917af";
const MAX_PROJECT_BYTES: u64 = 2 * 1024 * 1024;
const TASKS: [&str; 5] = [
    "terminal-atomic-import",
    "terminal-config-overlay",
    "terminal-event-rollup",
    "terminal-file-inventory",
    "terminal-ledger-reconcile",
];
const FILES: [&str; 8] = [
    ".dockerignore",
    "environment/Dockerfile",
    "instruction.md",
    "solution/program.py",
    "task.toml",
    "tests/cases.json",
    "tests/test_task.py",
    "workspace/program.py",
];
const DIRECTORIES: [&str; 4] = ["environment", "solution", "tests", "workspace"];

fn main() {
    if run().is_err() {
        std::process::exit(2);
    }
}

fn run() -> Result<(), ()> {
    let mut bytes = Vec::new();
    io::stdin()
        .take((MAX_REQUEST_BYTES + 1) as u64)
        .read_to_end(&mut bytes)
        .map_err(|_| ())?;
    let request = parse_request(&bytes).map_err(|_| ())?;
    let task = configured_task(&request).map_err(|_| ())?;
    let findings = validate_package(&request, Path::new(INPUT_ROOT), task);
    let value = if request.phase == "post_submit"
        && !findings.iter().any(|finding| finding.level == "error")
    {
        terminal_benchmark_plan(&request, task).map_err(|_| ())?
    } else {
        completed_result(&request, findings).map_err(|_| ())?
    };
    serde_json::to_writer(io::stdout(), &value).map_err(|_| ())
}

fn configured_task(request: &ValidatedRequest) -> Result<&str, ()> {
    let configuration = request
        .value
        .get("configuration")
        .and_then(Value::as_object)
        .ok_or(())?;
    if configuration.len() != 2
        || configuration.get("schema_version").and_then(Value::as_str) != Some(CONFIG_VERSION)
    {
        return Err(());
    }
    let task = configuration
        .get("external_task_id")
        .and_then(Value::as_str)
        .ok_or(())?;
    TASKS.binary_search(&task).map_err(|_| ())?;
    Ok(task)
}

fn finding(code: &str, message: &str, path: Option<&str>) -> Finding {
    Finding {
        check_id: "terminal.package".into(),
        code: code.into(),
        level: "error".into(),
        message: message.into(),
        path: path.map(str::to_owned),
        line: None,
    }
}

fn validate_package(request: &ValidatedRequest, root: &Path, task: &str) -> Vec<Finding> {
    let mut findings = Vec::new();
    let Some(manifest) = request
        .value
        .get("input")
        .and_then(Value::as_object)
        .and_then(|input| input.get("manifest"))
        .and_then(Value::as_array)
    else {
        return vec![finding(
            "manifest_missing",
            "Verified package inventory is missing.",
            None,
        )];
    };
    let mut observed_files = BTreeSet::new();
    let mut observed_directories = BTreeSet::new();
    let mut observed_paths = BTreeSet::new();
    let mut total = 0_u64;
    for item in manifest {
        let Some(entry) = item.as_object() else {
            return vec![finding(
                "manifest_invalid",
                "Verified package inventory is invalid.",
                None,
            )];
        };
        let Some(path) = entry.get("normalized_path").and_then(Value::as_str) else {
            return vec![finding(
                "manifest_invalid",
                "Verified package inventory is invalid.",
                None,
            )];
        };
        if !observed_paths.insert(path.to_owned()) {
            findings.push(finding(
                "duplicate_path",
                "Package path is duplicated.",
                Some(path),
            ));
            continue;
        }
        match entry.get("entry_type").and_then(Value::as_str) {
            Some("directory") => {
                observed_directories.insert(path.to_owned());
                if !DIRECTORIES.contains(&path) {
                    findings.push(finding(
                        "forbidden_path",
                        "Package contains a directory outside the fixed project contract.",
                        Some(path),
                    ));
                }
                continue;
            }
            Some("file") => {
                observed_files.insert(path.to_owned());
            }
            _ => {
                findings.push(finding(
                    "manifest_invalid",
                    "Verified package inventory has an unsupported entry type.",
                    Some(path),
                ));
                continue;
            }
        }
        total = total.saturating_add(
            entry
                .get("byte_count")
                .and_then(Value::as_u64)
                .unwrap_or(u64::MAX),
        );
        if !FILES.contains(&path) {
            findings.push(finding(
                "forbidden_path",
                "Package contains a file outside the fixed project contract.",
                Some(path),
            ));
        }
    }
    if total > MAX_PROJECT_BYTES {
        findings.push(finding(
            "project_too_large",
            "Package exceeds the fixed project byte limit.",
            None,
        ));
    }
    for path in FILES {
        if !observed_files.contains(path) {
            findings.push(finding(
                "required_member_missing",
                "Required package member is missing.",
                Some(path),
            ));
        }
    }
    for path in DIRECTORIES {
        if !observed_directories.contains(path) {
            findings.push(finding(
                "required_member_missing",
                "Required package directory is missing.",
                Some(path),
            ));
        }
    }
    if !findings.is_empty() {
        return findings;
    }

    let mut contents = Map::new();
    for path in FILES {
        let full = root.join(path);
        let data = match read_regular(&full, MAX_PROJECT_BYTES as usize) {
            Ok(data) => data,
            Err(()) => {
                findings.push(finding(
                    "member_unreadable",
                    "Required package member is not a bounded regular file.",
                    Some(path),
                ));
                continue;
            }
        };
        let expected = manifest
            .iter()
            .find(|item| item["normalized_path"] == path)
            .and_then(Value::as_object);
        let digest = format!("sha256:{:x}", Sha256::digest(&data));
        if expected.is_none_or(|entry| {
            entry.get("byte_count").and_then(Value::as_u64) != Some(data.len() as u64)
                || entry.get("sha256").and_then(Value::as_str) != Some(&digest)
        }) {
            findings.push(finding(
                "member_changed",
                "Package member differs from verified inventory.",
                Some(path),
            ));
            continue;
        }
        match String::from_utf8(data) {
            Ok(text) => {
                contents.insert(path.into(), Value::String(text));
            }
            Err(_) => findings.push(finding(
                "text_invalid",
                "Package text must be valid UTF-8.",
                Some(path),
            )),
        }
    }
    if !findings.is_empty() {
        return findings;
    }
    validate_fixed_text(&contents, task, &mut findings);
    findings
}

fn read_regular(path: &PathBuf, maximum: usize) -> Result<Vec<u8>, ()> {
    let metadata = fs::symlink_metadata(path).map_err(|_| ())?;
    if !metadata.file_type().is_file()
        || metadata.file_type().is_symlink()
        || metadata.len() > maximum as u64
    {
        return Err(());
    }
    fs::read(path).map_err(|_| ())
}

fn validate_fixed_text(contents: &Map<String, Value>, task: &str, findings: &mut Vec<Finding>) {
    let text = |path: &str| contents.get(path).and_then(Value::as_str).unwrap_or("");
    let expected_task = format!(
        "external_task_id = \"{task}\"\nentrypoint = [\"python\", \"/workspace/program.py\", \"INPUT.json\", \"OUTPUT.json\"]\ntest_command = [\"python\", \"/tests/test_task.py\", \"/workspace/program.py\"]\nbuild_context = \".\"\ndockerfile = \"environment/Dockerfile\"\nreference_program = \"solution/program.py\"\n"
    );
    if text("task.toml") != expected_task {
        findings.push(finding(
            "metadata_invalid",
            "Task metadata differs from the fixed project contract.",
            Some("task.toml"),
        ));
    }
    let expected_dockerfile = format!(
        "FROM {BASE}\nENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1\nRUN mkdir -p /workspace && chown 65532:65532 /workspace\nWORKDIR /workspace\nCOPY --chown=65532:65532 workspace/ /workspace/\nUSER 65532:65532\n"
    );
    if text("environment/Dockerfile") != expected_dockerfile {
        findings.push(finding(
            "dockerfile_invalid",
            "Dockerfile differs from the approved offline recipe.",
            Some("environment/Dockerfile"),
        ));
    }
    if text(".dockerignore") != "solution/\ntests/\n" {
        findings.push(finding(
            "build_context_unsafe",
            "Build context must exclude solution and tests.",
            Some(".dockerignore"),
        ));
    }
    for path in [
        "instruction.md",
        "workspace/program.py",
        "solution/program.py",
        "tests/test_task.py",
    ] {
        if text(path).trim().is_empty() {
            findings.push(finding(
                "member_empty",
                "Required package member is empty.",
                Some(path),
            ));
        }
    }
    let cases: Value = match serde_json::from_str(text("tests/cases.json")) {
        Ok(value) => value,
        Err(_) => {
            findings.push(finding(
                "cases_invalid",
                "Golden cases must be valid JSON.",
                Some("tests/cases.json"),
            ));
            return;
        }
    };
    let Some(cases) = cases.as_array() else {
        findings.push(finding(
            "cases_invalid",
            "Golden cases must be a non-empty array.",
            Some("tests/cases.json"),
        ));
        return;
    };
    let mut names = BTreeSet::new();
    if cases.is_empty()
        || cases.len() > 64
        || cases.iter().any(|case| !valid_case(case, &mut names))
    {
        findings.push(finding(
            "cases_invalid",
            "Golden cases must use the fixed bounded case structure with unique names.",
            Some("tests/cases.json"),
        ));
    }
}

fn valid_case<'a>(case: &'a Value, names: &mut BTreeSet<&'a str>) -> bool {
    let Some(case) = case.as_object() else {
        return false;
    };
    if !case
        .keys()
        .all(|key| matches!(key.as_str(), "name" | "steps" | "files"))
    {
        return false;
    }
    let Some(name) = case.get("name").and_then(Value::as_str) else {
        return false;
    };
    if name.is_empty() || name.len() > 128 || !names.insert(name) {
        return false;
    }
    let Some(steps) = case.get("steps").and_then(Value::as_array) else {
        return false;
    };
    if steps.is_empty()
        || steps.len() > 64
        || steps.iter().any(|step| {
            step.as_object().is_none_or(|step| {
                !step.contains_key("input")
                    || !step.contains_key("expected")
                    || !step
                        .keys()
                        .all(|key| matches!(key.as_str(), "input" | "expected" | "database_rows"))
            })
        })
    {
        return false;
    }
    case.get("files").is_none_or(|files| {
        files.as_object().is_some_and(|files| {
            files.len() <= 256
                && files.iter().all(|(path, contents)| {
                    safe_case_path(path)
                        && contents.as_str().is_some_and(|text| text.len() <= 65_536)
                })
        })
    })
}

fn safe_case_path(path: &str) -> bool {
    !path.is_empty()
        && path.len() <= 512
        && !path.starts_with('/')
        && !path.contains('\0')
        && path.split('/').all(|part| !matches!(part, "" | "." | ".."))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fixed_corpus_packages_satisfy_project_text_contract() {
        let corpus =
            Path::new(env!("CARGO_MANIFEST_DIR")).join("../../pilots/terminal_benchmark/packages");
        for task in TASKS {
            let package = corpus.join(task.trim_start_matches("terminal-"));
            let mut contents = Map::new();
            for path in FILES {
                contents.insert(
                    path.into(),
                    Value::String(fs::read_to_string(package.join(path)).unwrap()),
                );
            }
            let mut findings = Vec::new();
            validate_fixed_text(&contents, task, &mut findings);
            assert!(findings.is_empty(), "{task}: {findings:?}");
        }
    }

    #[test]
    fn fixed_corpus_packages_satisfy_the_complete_pre_contract() {
        let corpus =
            Path::new(env!("CARGO_MANIFEST_DIR")).join("../../pilots/terminal_benchmark/packages");
        for task in TASKS {
            let package = corpus.join(task.trim_start_matches("terminal-"));
            let request = package_request(&package);
            assert!(
                validate_package(&request, &package, task).is_empty(),
                "{task}"
            );
        }
    }

    #[test]
    fn unsafe_build_context_and_unpinned_base_are_actionable() {
        let mut contents = Map::new();
        for path in FILES {
            contents.insert(path.into(), Value::String("value\n".into()));
        }
        contents.insert(".dockerignore".into(), Value::String("tests/\n".into()));
        contents.insert(
            "environment/Dockerfile".into(),
            Value::String("FROM python:latest\n".into()),
        );
        contents.insert(
            "tests/cases.json".into(),
            serde_json::json!([]).to_string().into(),
        );
        let mut findings = Vec::new();
        validate_fixed_text(&contents, TASKS[0], &mut findings);
        assert!(findings
            .iter()
            .any(|item| item.code == "build_context_unsafe"));
        assert!(findings
            .iter()
            .any(|item| item.code == "dockerfile_invalid"));
    }

    #[test]
    fn package_inventory_rejects_extra_missing_and_oversized_members() {
        let package = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../pilots/terminal_benchmark/packages/ledger-reconcile");
        let request = package_request(&package);

        let mut extra = request.clone();
        extra.value["input"]["manifest"]
            .as_array_mut()
            .unwrap()
            .push(serde_json::json!({
                "normalized_path": "private/hidden.txt",
                "entry_type": "file",
                "byte_count": 1,
                "sha256": format!("sha256:{}", "1".repeat(64)),
                "executable": false,
            }));
        assert!(validate_package(&extra, &package, TASKS[4])
            .iter()
            .any(|finding| finding.code == "forbidden_path"));

        let mut missing = request.clone();
        missing.value["input"]["manifest"]
            .as_array_mut()
            .unwrap()
            .retain(|item| item["normalized_path"] != "tests");
        assert!(validate_package(&missing, &package, TASKS[4])
            .iter()
            .any(|finding| finding.code == "required_member_missing"));

        let mut oversized = request;
        oversized.value["input"]["manifest"]
            .as_array_mut()
            .unwrap()
            .iter_mut()
            .find(|item| item["normalized_path"] == "workspace/program.py")
            .unwrap()["byte_count"] = Value::from(MAX_PROJECT_BYTES + 1);
        assert!(validate_package(&oversized, &package, TASKS[4])
            .iter()
            .any(|finding| finding.code == "project_too_large"));
    }

    fn package_request(package: &Path) -> ValidatedRequest {
        let mut manifest = Vec::new();
        for path in DIRECTORIES {
            manifest.push(serde_json::json!({
                "normalized_path": path,
                "entry_type": "directory",
            }));
        }
        for path in FILES {
            let bytes = fs::read(package.join(path)).unwrap();
            manifest.push(serde_json::json!({
                "normalized_path": path,
                "entry_type": "file",
                "byte_count": bytes.len(),
                "sha256": format!("sha256:{:x}", Sha256::digest(&bytes)),
                "executable": false,
            }));
        }
        ValidatedRequest {
            value: serde_json::json!({"input":{"manifest":manifest}}),
            request_digest: format!("sha256:{}", "0".repeat(64)),
            registry_entry_id: "019a0000-0000-7000-8000-000000000001".into(),
            registry_entry_digest: format!("sha256:{}", "1".repeat(64)),
            image_digest: format!("sha256:{}", "2".repeat(64)),
            configuration_digest: format!("sha256:{}", "3".repeat(64)),
            phase: "pre_submit".into(),
            cpu_millis: 500,
            memory_bytes: 128 * 1024 * 1024,
            deadline_ms: 30_000,
            maximum_output_bytes: 32_768,
        }
    }
}
