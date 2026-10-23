use std::collections::VecDeque;
use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::sync::atomic::AtomicBool;
use std::sync::Mutex;
use std::time::{Duration, Instant};

#[allow(dead_code)]
#[path = "../src/trial_docker.rs"]
mod trial_docker;
#[allow(dead_code)]
#[path = "../src/trial_engine.rs"]
mod trial_engine;
#[allow(dead_code)]
#[path = "../src/trial_relay.rs"]
mod trial_relay;

use trial_docker::*;
use trial_engine::*;
use trial_relay::*;

#[derive(Default)]
struct FakeControl {
    creates: Mutex<Vec<OwnedContainerCreate>>,
    limits: Mutex<Vec<ContainerExecutionLimits>>,
    observations: Mutex<VecDeque<ObservedContainerExit>>,
    cleaned: Mutex<Vec<RuntimeOwner>>,
}

impl RuntimeControl for FakeControl {
    fn require_image(
        &self,
        config_image_id: &str,
        _platform_identity_digest: &str,
        _deadline: Instant,
    ) -> Result<(), RuntimeControlFailure> {
        assert_eq!(config_image_id, digest('4'));
        Ok(())
    }

    fn require_offline_cache(
        &self,
        root: &Path,
        inventory_digest: &str,
    ) -> Result<(), RuntimeControlFailure> {
        assert!(root.is_absolute());
        assert_eq!(inventory_digest, digest('5'));
        Ok(())
    }

    fn create_owned_container(
        &self,
        request: OwnedContainerCreate,
        _deadline: Instant,
        _invocation_cancelled: &AtomicBool,
        _relay_cancelled: &AtomicBool,
    ) -> Result<(), RuntimeControlFailure> {
        self.creates.lock().unwrap().push(request);
        Ok(())
    }

    fn run_owned_container(
        &self,
        _owner: &RuntimeOwner,
        _name: &str,
        _writable_roots: &[PathBuf],
        limits: &ContainerExecutionLimits,
        _invocation_cancelled: &AtomicBool,
        _relay_cancelled: &AtomicBool,
    ) -> Result<ObservedContainerExit, RuntimeControlFailure> {
        self.limits.lock().unwrap().push(limits.clone());
        self.observations
            .lock()
            .unwrap()
            .pop_front()
            .ok_or(RuntimeControlFailure::InvalidObservation)
    }

    fn load_single_owned_image(
        &self,
        _owner: &RuntimeOwner,
        _archive: &Path,
        expected_tag: &str,
        _maximum_bytes: u64,
        _deadline: Instant,
    ) -> Result<LoadedOwnedImage, RuntimeControlFailure> {
        assert!(expected_tag.starts_with("workstream-trial:"));
        Ok(LoadedOwnedImage {
            config_image_id: digest('a'),
            archive_sha256: digest('b'),
            archive_byte_count: 4096,
        })
    }

    fn cleanup_owner(
        &self,
        owner: &RuntimeOwner,
        _deadline: Instant,
    ) -> Result<(), RuntimeControlFailure> {
        self.cleaned.lock().unwrap().push(owner.clone());
        Ok(())
    }
}

fn digest(character: char) -> String {
    format!("sha256:{}", character.to_string().repeat(64))
}

fn identity() -> SandboxBackendIdentity {
    SandboxBackendIdentity {
        engine_identity_digest: digest('1'),
        child_runtime: "runsc".into(),
        child_runtime_config_digest: digest('2'),
        child_host_uds: "none".into(),
        platform: "linux/amd64".into(),
        platform_identity_digest: digest('3'),
        builder_image_digest: digest('4'),
        offline_cache_digest: digest('5'),
        approved_base_digests: vec![digest('6')],
    }
}

fn resources() -> TrialResources {
    TrialResources {
        cpu_quota_millis: 500,
        cpu_time_ms: 2000,
        memory_bytes: 64 * 1024 * 1024,
        disk_bytes: 32 * 1024 * 1024,
        maximum_entries: 100,
        pids: 16,
    }
}

fn overruns() -> SandboxEnforcementOverruns {
    SandboxEnforcementOverruns {
        wall_time_ms: 100,
        cpu_time_ms: 200,
        memory_bytes: 1024,
        pids: 1,
        disk_bytes: 4096,
        entries: 2,
    }
}

fn observed(workspace: bool) -> ObservedContainerExit {
    ObservedContainerExit {
        termination: RuntimeTermination::Exited,
        exit_code: Some(0),
        signal: None,
        stdout: "ok\n".into(),
        stderr: String::new(),
        elapsed_ms: 20,
        cpu_time_ms: 10,
        peak_memory_bytes: 1024,
        peak_pids: 1,
        written_bytes: 128,
        written_entries: 1,
        measurement_method: "cgroup_v2_and_owned_tree".into(),
        workspace_before_sha256: workspace.then(|| digest('7')),
        workspace_after_sha256: workspace.then(|| digest('8')),
    }
}

struct Root(PathBuf);

impl Root {
    fn new() -> Self {
        let root = std::env::temp_dir().join(format!(
            "workstream-trial-docker-test-{}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir(&root).unwrap();
        fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
        Self(root)
    }

    fn child(&self, name: &str) -> PathBuf {
        let path = self.0.join(name);
        fs::create_dir(&path).unwrap();
        path
    }
}

impl Drop for Root {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn backend(root: &Root) -> DockerTrialBackend<FakeControl> {
    let cache = root.child("cache");
    DockerTrialBackend::new(
        DockerTrialConfiguration {
            identity: identity(),
            deployment_owner: "deployment_a".into(),
            request_digest: digest('9'),
            attempt_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00001".into(),
            runtime_key: "runsc".into(),
            builder_image_id: digest('4'),
            offline_cache_root: cache,
            maximum_candidate_archive_bytes: 64 * 1024 * 1024,
            candidate_uid: 65532,
            candidate_gid: 65532,
        },
        FakeControl {
            observations: Mutex::new(VecDeque::from([observed(false), observed(true)])),
            ..FakeControl::default()
        },
    )
    .unwrap()
}

#[test]
fn backend_emits_offline_bounded_builder_and_socketless_candidate_specs() {
    let root = Root::new();
    let context = root.child("context");
    let output = root.child("output");
    let workspace = root.child("workspace");
    let source = root.child("source");
    let backend = backend(&root);
    let deadline = Instant::now() + Duration::from_secs(2);
    let cancelled = AtomicBool::new(false);
    let build = backend
        .build(
            &SandboxBuildRequest {
                owner_id: format!("trial_{}", "a".repeat(32)),
                context_root: context,
                context_relative: ".".into(),
                dockerfile_relative: "Containerfile".into(),
                output_archive: output.join("candidate.tar"),
                destination: "workstream-trial:test".into(),
                platform: "linux/amd64".into(),
                resources: resources(),
                timeout_ms: 1000,
                maximum_output_bytes: 4096,
                enforcement_overruns: overruns(),
            },
            deadline,
            &cancelled,
            &cancelled,
        )
        .unwrap();
    assert_eq!(build.observation.candidate_image_digest, Some(digest('a')));
    backend
        .run_step(
            &SandboxStepRequest {
                owner_id: format!("trial_{}", "a".repeat(32)),
                slot_id: "slot_a".into(),
                candidate_image_digest: digest('a'),
                workspace_root: workspace,
                visible_roles: vec![("source".into(), source)],
                visible_role_inventory_digests: vec![RoleInventoryDigest {
                    role: "source".into(),
                    digest: digest('c'),
                }],
                command: vec!["/candidate/check".into(), "case-a".into()],
                working_directory: ".".into(),
                resources: resources(),
                timeout_ms: 500,
                maximum_output_bytes: 4096,
                enforcement_overruns: overruns(),
            },
            1,
            deadline,
            &cancelled,
            &cancelled,
        )
        .unwrap();
    let creates = backend.control.creates.lock().unwrap();
    assert_eq!(creates.len(), 2);
    let builder = &creates[0].arguments;
    assert!(builder.windows(2).any(|item| item == ["--network", "none"]));
    assert!(builder
        .windows(2)
        .any(|item| item == ["--runtime", "runsc"]));
    assert_eq!(
        builder.iter().filter(|item| *item == "--cap-add").count(),
        4
    );
    assert!(!builder.iter().any(|item| item == "--privileged"));
    assert!(!builder.iter().any(|item| item == "--mount"));
    assert_eq!(creates[0].mounts.len(), 3);
    assert_eq!(
        creates[0].mounts[0].class,
        OwnedMountClass::ProjectedContext
    );
    assert_eq!(creates[0].mounts[1].class, OwnedMountClass::OfflineCache);
    assert_eq!(creates[0].mounts[2].class, OwnedMountClass::CandidateOutput);
    assert!(creates[0].mounts[0].readonly && creates[0].mounts[1].readonly);
    assert!(!creates[0].mounts[2].readonly);
    let candidate = &creates[1].arguments;
    assert!(candidate.iter().any(|item| item == "--read-only"));
    assert!(candidate
        .windows(2)
        .any(|item| item == ["--user", "65532:65532"]));
    assert!(!candidate.iter().any(|item| item.contains("docker.sock")));
    assert!(!candidate.iter().any(|item| item.contains("execution.sock")));
    assert!(!candidate.iter().any(|item| item.contains("model.sock")));
    assert!(!candidate.iter().any(|item| item == "--cap-add"));
    assert!(!candidate.iter().any(|item| item == "--mount"));
    assert_eq!(creates[1].mounts[0].class, OwnedMountClass::TrialState);
    assert_eq!(
        creates[1].mounts[1].class,
        OwnedMountClass::VerifiedMaterial
    );
    assert!(!creates[1].mounts[0].readonly);
    assert!(creates[1].mounts[1].readonly);
    drop(creates);
    let limits = backend.control.limits.lock().unwrap();
    assert_eq!(limits[1].wall_time_overrun_ms, 100);
    assert_eq!(limits[1].cpu_time_overrun_ms, 200);
    drop(limits);
    backend
        .cleanup(&format!("trial_{}", "a".repeat(32)), deadline)
        .unwrap();
    assert_eq!(backend.control.cleaned.lock().unwrap().len(), 1);
}

#[test]
fn backend_rejects_runtime_profile_that_would_expose_host_uds() {
    let root = Root::new();
    let mut identity = identity();
    identity.child_host_uds = "open".into();
    let result = DockerTrialBackend::new(
        DockerTrialConfiguration {
            identity,
            deployment_owner: "deployment_a".into(),
            request_digest: digest('9'),
            attempt_id: "018f6f49-66b8-7d2a-bf4d-0e2eeaa00001".into(),
            runtime_key: "runsc".into(),
            builder_image_id: digest('4'),
            offline_cache_root: root.child("cache"),
            maximum_candidate_archive_bytes: 1024,
            candidate_uid: 65532,
            candidate_gid: 65532,
        },
        FakeControl::default(),
    );
    assert_eq!(
        result.err().unwrap().code,
        TrialRelayFailure::InvalidRequest
    );
}
