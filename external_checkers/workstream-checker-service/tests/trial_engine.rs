use sha2::{Digest, Sha256};
use std::collections::VecDeque;
use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

#[allow(dead_code)]
#[path = "../src/trial_engine.rs"]
mod trial_engine;
#[allow(dead_code)]
#[path = "../src/trial_relay.rs"]
mod trial_relay;

use trial_engine::*;
use trial_relay::*;

static SEQUENCE: AtomicUsize = AtomicUsize::new(0);

struct Root(PathBuf);

impl Root {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "workstream-trial-engine-test-{}-{}",
            std::process::id(),
            SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o700)).unwrap();
        Self(path)
    }

    fn child(&self, name: &str) -> PathBuf {
        let path = self.0.join(name);
        fs::create_dir(&path).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o700)).unwrap();
        path
    }
}

impl Drop for Root {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[derive(Default)]
struct FakeBackend {
    builds: AtomicUsize,
    steps: AtomicUsize,
    cleanups: AtomicUsize,
    build_requests: Mutex<Vec<SandboxBuildRequest>>,
    step_requests: Mutex<Vec<SandboxStepRequest>>,
    outcomes: Mutex<VecDeque<TrialOperationOutcome>>,
}

impl TrialSandboxBackend for Arc<FakeBackend> {
    fn identity(&self) -> SandboxBackendIdentity {
        let profile = profile();
        SandboxBackendIdentity {
            engine_identity_digest: profile.engine_identity_digest,
            child_runtime: profile.child_runtime,
            child_runtime_config_digest: profile.child_runtime_config_digest,
            child_host_uds: profile.child_host_uds,
            platform: profile.platform,
            platform_identity_digest: profile.platform_identity_digest,
            builder_image_digest: profile.builder_image_digest,
            offline_cache_digest: profile.offline_cache_digest,
            approved_base_digests: profile.approved_base_digests,
        }
    }

    fn build(
        &self,
        request: &SandboxBuildRequest,
        _deadline: Instant,
        _invocation_cancelled: &AtomicBool,
        _relay_cancelled: &AtomicBool,
    ) -> Result<SandboxBuildResult, SandboxFailure> {
        self.builds.fetch_add(1, Ordering::Relaxed);
        assert!(request.context_root.join("source/main.txt").is_file());
        assert!(!request.context_root.join("protected/canary.txt").exists());
        assert_eq!(request.context_relative, ".");
        assert_eq!(request.dockerfile_relative, "source/Containerfile");
        self.build_requests.lock().unwrap().push(request.clone());
        Ok(SandboxBuildResult {
            observation: build_observation(),
        })
    }

    fn run_step(
        &self,
        request: &SandboxStepRequest,
        operation_order: u32,
        _deadline: Instant,
        _invocation_cancelled: &AtomicBool,
        _relay_cancelled: &AtomicBool,
    ) -> Result<SandboxStepResult, SandboxFailure> {
        self.steps.fetch_add(1, Ordering::Relaxed);
        assert_eq!(request.visible_roles.len(), 1);
        assert_eq!(request.visible_roles[0].role, "protected");
        assert_eq!(request.visible_roles[0].destination_relative, "protected");
        assert!(request
            .workspace_root
            .join("workspace/initial.txt")
            .is_file());
        assert_eq!(request.command, ["/candidate/check", "case-a"]);
        let outcome = self
            .outcomes
            .lock()
            .unwrap()
            .pop_front()
            .unwrap_or(TrialOperationOutcome::Succeeded);
        if outcome == TrialOperationOutcome::ExitNonzero {
            fs::write(
                request.workspace_root.join("interrupted.state"),
                b"retained\n",
            )
            .unwrap();
        }
        if request.slot_id == "slot_b" {
            assert!(request.workspace_root.join("interrupted.state").is_file());
        }
        self.step_requests.lock().unwrap().push(request.clone());
        Ok(SandboxStepResult {
            observation: TrialStepObservation {
                slot_id: request.slot_id.clone(),
                operation_order,
                workspace_identity: "workspace_a".into(),
                visible_role_inventory_digests: request.visible_role_inventory_digests.clone(),
                outcome,
                exit_code: Some(if outcome == TrialOperationOutcome::Succeeded {
                    0
                } else {
                    17
                }),
                signal: None,
                stdout: "ok\n".into(),
                stdout_sha256: hash(b"ok\n"),
                stderr: String::new(),
                stderr_sha256: hash(b""),
                workspace_before_sha256: digest('1'),
                workspace_after_sha256: digest('2'),
                elapsed_ms: 20,
                cpu_time_ms: 10,
                peak_memory_bytes: 1024,
                peak_pids: 1,
                written_bytes: 10,
                written_entries: 1,
                measurement_method: "cgroup_v2".into(),
            },
        })
    }

    fn cleanup(&self, _owner_id: &str, _deadline: Instant) -> Result<(), SandboxFailure> {
        self.cleanups.fetch_add(1, Ordering::Relaxed);
        Ok(())
    }
}

fn digest(character: char) -> String {
    format!("sha256:{}", character.to_string().repeat(64))
}

fn hash(value: &[u8]) -> String {
    format!("sha256:{:x}", Sha256::digest(value))
}

fn profile() -> TrialProfile {
    TrialProfile {
        profile_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00001".into(),
        profile_version: 1,
        profile_digest: digest('1'),
        trial_kind: "generic_build_run".into(),
        registry_entry_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00002".into(),
        registry_entry_digest: digest('2'),
        checker_image_digest: digest('3'),
        configuration_sha256: digest('4'),
        engine_identity_digest: digest('5'),
        child_runtime: "runsc".into(),
        child_runtime_config_digest: digest('5'),
        child_host_uds: "none".into(),
        platform: "linux/amd64".into(),
        platform_identity_digest: digest('6'),
        builder_image_digest: digest('7'),
        offline_cache_digest: digest('8'),
        approved_base_digests: vec![digest('9')],
        source_material_roles: vec!["submission_archive".into()],
        material_projections: vec![
            TrialMaterialProjectionProfile {
                role: "source".into(),
                source_role: "submission_archive".into(),
                projection_kind: "build_context".into(),
                source_relative: ".".into(),
                destination_relative: ".".into(),
                exclusions: vec!["protected".into()],
            },
            TrialMaterialProjectionProfile {
                role: "protected".into(),
                source_role: "submission_archive".into(),
                projection_kind: "state_overlay".into(),
                source_relative: "protected".into(),
                destination_relative: "protected".into(),
                exclusions: Vec::new(),
            },
            TrialMaterialProjectionProfile {
                role: "workspace_seed".into(),
                source_role: "submission_archive".into(),
                projection_kind: "state_seed".into(),
                source_relative: "workspace".into(),
                destination_relative: "workspace".into(),
                exclusions: Vec::new(),
            },
        ],
        build_context_roles: vec!["source".into()],
        allowed_material_roles: vec!["source".into(), "protected".into(), "workspace_seed".into()],
        required_slots: vec![TrialSlotProfile {
            slot_id: "slot_a".into(),
            seed_roles: vec!["workspace_seed".into()],
            visible_roles: vec!["protected".into()],
            fresh_workspace: true,
            retain_state_after: vec!["succeeded".into()],
        }],
        maximum_frame_bytes: 64 * 1024,
        maximum_response_bytes: 16 * 1024,
        maximum_steps: 1,
        maximum_build_timeout_ms: 2_000,
        maximum_step_timeout_ms: 1_000,
        maximum_step_output_bytes: 4_096,
        maximum_observation_bytes: 32 * 1024,
        maximum_receipt_bytes: 64 * 1024,
        maximum_cpu_quota_millis: 1_000,
        maximum_cpu_time_ms: 5_000,
        maximum_wall_time_overrun_ms: 100,
        maximum_cpu_time_overrun_ms: 100,
        maximum_memory_bytes: 64 * 1024 * 1024,
        maximum_memory_overrun_bytes: 1024,
        maximum_disk_bytes: 1024 * 1024,
        maximum_disk_overrun_bytes: 1024,
        maximum_entries: 100,
        maximum_entries_overrun: 1,
        maximum_pids: 16,
        maximum_pids_overrun: 1,
    }
}

fn resources() -> TrialResources {
    TrialResources {
        cpu_quota_millis: 500,
        cpu_time_ms: 2_000,
        memory_bytes: 32 * 1024 * 1024,
        disk_bytes: 512 * 1024,
        maximum_entries: 50,
        pids: 8,
    }
}

fn plan() -> TrialPlan {
    TrialPlan {
        schema_version: "workstream.checker_trial_plan.v1".into(),
        environment: TrialEnvironment {
            dockerfile: "source/Containerfile".into(),
            context: ".".into(),
            platform: "linux/amd64".into(),
        },
        resources: resources(),
        build_timeout_ms: 1_000,
        steps: vec![TrialStep {
            slot_id: "slot_a".into(),
            operation: "run".into(),
            state_source: "fresh".into(),
            visible_roles: vec!["protected".into()],
            command: vec!["/candidate/check".into(), "case-a".into()],
            working_directory: ".".into(),
            timeout_ms: 500,
        }],
    }
}

fn build_observation() -> TrialBuildObservation {
    TrialBuildObservation {
        outcome: TrialOperationOutcome::Succeeded,
        exit_code: Some(0),
        signal: None,
        stdout: "built\n".into(),
        stdout_sha256: hash(b"built\n"),
        stderr: String::new(),
        stderr_sha256: hash(b""),
        candidate_image_digest: Some(digest('a')),
        candidate_archive_digest: Some(digest('b')),
        elapsed_ms: 100,
        cpu_time_ms: 50,
        peak_memory_bytes: 4096,
        peak_pids: 2,
        written_bytes: 1024,
        written_entries: 2,
        measurement_method: "cgroup_v2".into(),
    }
}

fn context(root: &Root) -> TrialEngineContext {
    let material = root.child("material");
    let submission = material.join("submission_archive");
    fs::create_dir(&submission).unwrap();
    let source = submission.join("source");
    let protected = submission.join("protected");
    let workspace = submission.join("workspace");
    fs::create_dir(&source).unwrap();
    fs::create_dir(&protected).unwrap();
    fs::create_dir(&workspace).unwrap();
    fs::write(source.join("main.txt"), b"source\n").unwrap();
    fs::write(source.join("Containerfile"), b"FROM scratch\n").unwrap();
    fs::write(protected.join("canary.txt"), b"secret\n").unwrap();
    fs::write(workspace.join("initial.txt"), b"initial\n").unwrap();
    TrialEngineContext {
        identity: TrialRequestIdentity {
            request_digest: digest('1'),
            material_binding_digest: digest('2'),
            project_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00011".into(),
            task_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00012".into(),
            assignment_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00013".into(),
            submission_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00014".into(),
            submission_version: 1,
            requirement_id: "check_a".into(),
            registry_entry_id: profile().registry_entry_id,
            registry_entry_digest: profile().registry_entry_digest,
            checker_image_digest: profile().checker_image_digest,
            configuration_sha256: profile().configuration_sha256,
            evaluation_request_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00015".into(),
            evaluation_generation: 1,
            checker_run_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00016".into(),
            attempt_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00017".into(),
            result_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00018".into(),
            worker_lease_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00019".into(),
            worker_lease_generation: 1,
            worker_lease_expires_at: "2026-10-23T12:00:00Z".into(),
        },
        profile: profile(),
        verified_material_root: material,
        trial_scratch_root: root.child("scratch"),
    }
}

#[test]
fn engine_projects_only_authorized_roles_runs_exact_plan_and_cleans_owned_scratch() {
    let root = Root::new();
    let context = context(&root);
    let backend = Arc::new(FakeBackend::default());
    let execution = GenericTrialEngine::new(backend.clone())
        .execute(
            &context,
            &plan(),
            Instant::now() + Duration::from_secs(2),
            &AtomicBool::new(false),
            &AtomicBool::new(false),
        )
        .unwrap();
    assert!(execution.cleanup_confirmed);
    assert_eq!(backend.builds.load(Ordering::Relaxed), 1);
    assert_eq!(backend.steps.load(Ordering::Relaxed), 1);
    assert_eq!(backend.cleanups.load(Ordering::Relaxed), 1);
    assert_eq!(execution.material_inventory_digests.len(), 3);
    assert!(fs::read_dir(&context.trial_scratch_root)
        .unwrap()
        .next()
        .is_none());
}

#[test]
fn symlinked_material_is_infrastructure_and_never_reaches_backend() {
    let root = Root::new();
    let context = context(&root);
    std::os::unix::fs::symlink(
        context
            .verified_material_root
            .join("submission_archive/protected/canary.txt"),
        context
            .verified_material_root
            .join("submission_archive/source/escape"),
    )
    .unwrap();
    let backend = Arc::new(FakeBackend::default());
    let failure = GenericTrialEngine::new(backend.clone())
        .execute(
            &context,
            &plan(),
            Instant::now() + Duration::from_secs(2),
            &AtomicBool::new(false),
            &AtomicBool::new(false),
        )
        .unwrap_err();
    assert_eq!(failure.code, TrialRelayFailure::MaterialUnavailable);
    assert_eq!(backend.builds.load(Ordering::Relaxed), 0);
    assert_eq!(backend.cleanups.load(Ordering::Relaxed), 1);
}

fn continuation_context_and_plan(root: &Root) -> (TrialEngineContext, TrialPlan) {
    let mut context = context(root);
    context.profile.maximum_steps = 2;
    context.profile.required_slots = vec![
        TrialSlotProfile {
            slot_id: "slot_a".into(),
            seed_roles: vec!["workspace_seed".into()],
            visible_roles: vec!["protected".into()],
            fresh_workspace: true,
            retain_state_after: vec!["exit_nonzero".into()],
        },
        TrialSlotProfile {
            slot_id: "slot_b".into(),
            seed_roles: Vec::new(),
            visible_roles: vec!["protected".into()],
            fresh_workspace: false,
            retain_state_after: vec!["succeeded".into()],
        },
    ];
    let mut plan = plan();
    plan.steps.push(TrialStep {
        slot_id: "slot_b".into(),
        operation: "run".into(),
        state_source: "slot_a".into(),
        visible_roles: vec!["protected".into()],
        command: vec!["/candidate/check".into(), "case-a".into()],
        working_directory: ".".into(),
        timeout_ms: 500,
    });
    (context, plan)
}

#[test]
fn deliberate_work_failure_can_retain_state_but_resource_failure_cannot() {
    let root = Root::new();
    let (context, plan) = continuation_context_and_plan(&root);
    let backend = Arc::new(FakeBackend::default());
    backend.outcomes.lock().unwrap().extend([
        TrialOperationOutcome::ExitNonzero,
        TrialOperationOutcome::Succeeded,
    ]);
    let execution = GenericTrialEngine::new(backend.clone())
        .execute(
            &context,
            &plan,
            Instant::now() + Duration::from_secs(2),
            &AtomicBool::new(false),
            &AtomicBool::new(false),
        )
        .unwrap();
    assert_eq!(
        execution.steps[0].outcome,
        TrialOperationOutcome::ExitNonzero
    );
    assert_eq!(execution.steps[1].outcome, TrialOperationOutcome::Succeeded);
    assert_eq!(backend.steps.load(Ordering::Relaxed), 2);

    let root = Root::new();
    let (context, plan) = continuation_context_and_plan(&root);
    let backend = Arc::new(FakeBackend::default());
    backend
        .outcomes
        .lock()
        .unwrap()
        .push_back(TrialOperationOutcome::DeadlineExceeded);
    let execution = GenericTrialEngine::new(backend.clone())
        .execute(
            &context,
            &plan,
            Instant::now() + Duration::from_secs(2),
            &AtomicBool::new(false),
            &AtomicBool::new(false),
        )
        .unwrap();
    assert_eq!(
        execution.steps[0].outcome,
        TrialOperationOutcome::DeadlineExceeded
    );
    assert_eq!(
        execution.steps[1].outcome,
        TrialOperationOutcome::DependencySkipped
    );
    assert_eq!(backend.steps.load(Ordering::Relaxed), 1);
}
