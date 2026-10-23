//! Digest-bound Docker/runsc backend for the generic trial engine.

use crate::trial_engine::{
    SandboxBackendIdentity, SandboxBuildRequest, SandboxBuildResult, SandboxEnforcementOverruns,
    SandboxFailure, SandboxStepRequest, SandboxStepResult, TrialSandboxBackend,
};
use crate::trial_relay::{
    TrialBuildObservation, TrialOperationOutcome, TrialRelayFailure, TrialStepObservation,
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Seek, SeekFrom};
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::AtomicBool;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};
use workstream_checker_sdk::canonical_hash;

static RUNTIME_FILE_SEQUENCE: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Debug, Deserialize, Hash, PartialEq, Eq, Serialize)]
pub(crate) struct RuntimeOwner {
    pub(crate) deployment_owner: String,
    pub(crate) request_digest: String,
    pub(crate) attempt_id: String,
    pub(crate) trial_owner_id: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct OwnedContainerCreate {
    pub(crate) owner: RuntimeOwner,
    pub(crate) name: String,
    /// Docker `create` arguments after ownership labels and before the image.
    pub(crate) arguments: Vec<String>,
    pub(crate) mounts: Vec<OwnedBindMount>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum OwnedMountClass {
    ProjectedContext,
    OfflineCache,
    CandidateOutput,
    TrialState,
    VerifiedMaterial,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct OwnedBindMount {
    pub(crate) source: PathBuf,
    pub(crate) destination: String,
    pub(crate) readonly: bool,
    pub(crate) class: OwnedMountClass,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct ContainerExecutionLimits {
    pub(crate) deadline: Instant,
    pub(crate) operation_timeout_ms: u64,
    pub(crate) cpu_time_ms: u64,
    pub(crate) wall_time_overrun_ms: u64,
    pub(crate) cpu_time_overrun_ms: u64,
    pub(crate) memory_bytes: u64,
    pub(crate) memory_overrun_bytes: u64,
    pub(crate) pids: u64,
    pub(crate) pids_overrun: u64,
    pub(crate) disk_bytes: u64,
    pub(crate) disk_overrun_bytes: u64,
    pub(crate) entries: u64,
    pub(crate) entries_overrun: u64,
    pub(crate) output_bytes: usize,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum RuntimeTermination {
    Exited,
    Signalled,
    DeadlineExceeded,
    CpuExceeded,
    MemoryExceeded,
    PidExceeded,
    DiskExceeded,
    OutputExceeded,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct ObservedContainerExit {
    pub(crate) termination: RuntimeTermination,
    pub(crate) exit_code: Option<i32>,
    pub(crate) signal: Option<i32>,
    pub(crate) stdout: String,
    pub(crate) stderr: String,
    pub(crate) elapsed_ms: u64,
    pub(crate) cpu_time_ms: u64,
    pub(crate) peak_memory_bytes: u64,
    pub(crate) peak_pids: u64,
    pub(crate) written_bytes: u64,
    pub(crate) written_entries: u64,
    pub(crate) measurement_method: String,
    pub(crate) workspace_before_sha256: Option<String>,
    pub(crate) workspace_after_sha256: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct LoadedOwnedImage {
    pub(crate) config_image_id: String,
    pub(crate) archive_sha256: String,
    pub(crate) archive_byte_count: u64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum RuntimeControlFailure {
    InvalidConfiguration,
    ImageUnavailable,
    CacheUnavailable,
    LaunchUnavailable,
    DeadlineExceeded,
    Cancelled,
    CapacityExceeded,
    InvalidObservation,
    CleanupUnsettled,
}

/// Module-neutral owner/cancellation/measurement surface extracted from main by #492.
pub(crate) trait RuntimeControl: Send + Sync + 'static {
    fn require_image(
        &self,
        config_image_id: &str,
        identity: &SandboxBackendIdentity,
        runtime_key: &str,
        deadline: Instant,
    ) -> Result<(), RuntimeControlFailure>;

    fn require_offline_cache(
        &self,
        root: &std::path::Path,
        inventory_digest: &str,
    ) -> Result<(), RuntimeControlFailure>;

    fn create_owned_container(
        &self,
        request: OwnedContainerCreate,
        deadline: Instant,
        invocation_cancelled: &AtomicBool,
        relay_cancelled: &AtomicBool,
    ) -> Result<(), RuntimeControlFailure>;

    fn run_owned_container(
        &self,
        owner: &RuntimeOwner,
        name: &str,
        writable_roots: &[PathBuf],
        limits: &ContainerExecutionLimits,
        invocation_cancelled: &AtomicBool,
        relay_cancelled: &AtomicBool,
    ) -> Result<ObservedContainerExit, RuntimeControlFailure>;

    /// Validate exactly one expected tag/image in the archive before and after load.
    fn load_single_owned_image(
        &self,
        owner: &RuntimeOwner,
        archive: &std::path::Path,
        expected_tag: &str,
        maximum_bytes: u64,
        deadline: Instant,
    ) -> Result<LoadedOwnedImage, RuntimeControlFailure>;

    /// Kill/remove only exact owner-labelled containers/images and confirm absence.
    fn cleanup_owner(
        &self,
        owner: &RuntimeOwner,
        deadline: Instant,
    ) -> Result<(), RuntimeControlFailure>;
}

#[derive(Default)]
struct OwnedRuntimeResources {
    containers: Vec<String>,
    images: Vec<(String, String)>,
}

/// Concrete Docker CLI + cgroup-v2 control used on a dedicated runsc node.
pub(crate) struct DockerRuntimeControl {
    docker_binary: PathBuf,
    runtime_root: PathBuf,
    runtime_configuration: PathBuf,
    owned: Mutex<HashMap<RuntimeOwner, OwnedRuntimeResources>>,
}

impl DockerRuntimeControl {
    pub(crate) fn new(
        docker_binary: PathBuf,
        runtime_root: PathBuf,
        runtime_configuration: PathBuf,
    ) -> Result<Self, RuntimeControlFailure> {
        let binary = fs::canonicalize(&docker_binary)
            .map_err(|_| RuntimeControlFailure::InvalidConfiguration)?;
        let binary_metadata = fs::symlink_metadata(&binary)
            .map_err(|_| RuntimeControlFailure::InvalidConfiguration)?;
        let root = fs::canonicalize(&runtime_root)
            .map_err(|_| RuntimeControlFailure::InvalidConfiguration)?;
        let root_metadata =
            fs::symlink_metadata(&root).map_err(|_| RuntimeControlFailure::InvalidConfiguration)?;
        let runtime_configuration = fs::canonicalize(&runtime_configuration)
            .map_err(|_| RuntimeControlFailure::InvalidConfiguration)?;
        let configuration_metadata = fs::symlink_metadata(&runtime_configuration)
            .map_err(|_| RuntimeControlFailure::InvalidConfiguration)?;
        if !binary_metadata.file_type().is_file()
            || binary_metadata.permissions().mode() & 0o111 == 0
            || !root_metadata.file_type().is_dir()
            || root_metadata.file_type().is_symlink()
            || root_metadata.permissions().mode() & 0o077 != 0
            || !configuration_metadata.file_type().is_file()
            || configuration_metadata.file_type().is_symlink()
        {
            return Err(RuntimeControlFailure::InvalidConfiguration);
        }
        Ok(Self {
            docker_binary: binary,
            runtime_root: root,
            runtime_configuration,
            owned: Mutex::new(HashMap::new()),
        })
    }

    fn command(
        &self,
        arguments: &[String],
        deadline: Instant,
        maximum_output: usize,
    ) -> Result<CommandResult, RuntimeControlFailure> {
        let nonce = format!(
            "{:016x}",
            RUNTIME_FILE_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        );
        let stdout_path = self.runtime_root.join(format!(".runtime-{nonce}.stdout"));
        let stderr_path = self.runtime_root.join(format!(".runtime-{nonce}.stderr"));
        let stdout = create_output(&stdout_path)?;
        let stderr = create_output(&stderr_path)?;
        let mut child = Command::new(&self.docker_binary)
            .args(arguments)
            .stdin(Stdio::null())
            .stdout(stdout)
            .stderr(stderr)
            .spawn()
            .map_err(|_| RuntimeControlFailure::LaunchUnavailable)?;
        let status = loop {
            if Instant::now() >= deadline {
                let _ = child.kill();
                let _ = child.wait();
                remove_outputs(&stdout_path, &stderr_path);
                return Err(RuntimeControlFailure::DeadlineExceeded);
            }
            match child.try_wait() {
                Ok(Some(status)) => break status,
                Ok(None) => {
                    if output_size(&stdout_path, &stderr_path)? > maximum_output as u64 {
                        let _ = child.kill();
                        let _ = child.wait();
                        remove_outputs(&stdout_path, &stderr_path);
                        return Err(RuntimeControlFailure::CapacityExceeded);
                    }
                }
                Err(_) => {
                    remove_outputs(&stdout_path, &stderr_path);
                    return Err(RuntimeControlFailure::LaunchUnavailable);
                }
            }
            thread::sleep(Duration::from_millis(5));
        };
        let stdout = read_bounded(&stdout_path, maximum_output)?;
        let stderr = read_bounded(&stderr_path, maximum_output.saturating_sub(stdout.len()))?;
        remove_outputs(&stdout_path, &stderr_path);
        Ok(CommandResult {
            success: status.success(),
            stdout,
            stderr,
        })
    }

    fn kill_container(&self, name: &str, deadline: Instant) {
        let _ = self.command(&["kill".into(), name.into()], deadline, 64 * 1024);
    }

    fn container_pid(&self, name: &str, deadline: Instant) -> Option<u32> {
        let output = self
            .command(
                &[
                    "inspect".into(),
                    "--format".into(),
                    "{{.State.Pid}}".into(),
                    name.into(),
                ],
                deadline,
                1024,
            )
            .ok()?;
        if !output.success {
            return None;
        }
        std::str::from_utf8(&output.stdout)
            .ok()?
            .trim()
            .parse()
            .ok()
    }

    fn container_state(
        &self,
        name: &str,
        deadline: Instant,
    ) -> Result<ContainerState, RuntimeControlFailure> {
        let output = self.command(
            &[
                "inspect".into(),
                "--format".into(),
                "{{json .State}}".into(),
                name.into(),
            ],
            deadline,
            64 * 1024,
        )?;
        if !output.success {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        let value: serde_json::Value = serde_json::from_slice(&output.stdout)
            .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        Ok(ContainerState {
            exit_code: value
                .get("ExitCode")
                .and_then(serde_json::Value::as_i64)
                .and_then(|item| i32::try_from(item).ok()),
            oom_killed: value
                .get("OOMKilled")
                .and_then(serde_json::Value::as_bool)
                .unwrap_or(false),
        })
    }
}

struct CommandResult {
    success: bool,
    stdout: Vec<u8>,
    #[allow(dead_code)]
    stderr: Vec<u8>,
}

struct ContainerState {
    exit_code: Option<i32>,
    oom_killed: bool,
}

#[derive(Default)]
struct Measurements {
    cgroup_samples: u64,
    cpu_time_ms: u64,
    peak_memory_bytes: u64,
    peak_pids: u64,
    written_bytes: u64,
    written_entries: u64,
}

impl RuntimeControl for DockerRuntimeControl {
    fn require_image(
        &self,
        config_image_id: &str,
        identity: &SandboxBackendIdentity,
        runtime_key: &str,
        deadline: Instant,
    ) -> Result<(), RuntimeControlFailure> {
        if !valid_sha256(config_image_id)
            || !valid_relative_label(runtime_key)
            || !valid_sha256(&identity.engine_identity_digest)
            || !valid_sha256(&identity.child_runtime_config_digest)
            || !valid_sha256(&identity.platform_identity_digest)
            || identity.child_runtime != "runsc"
            || identity.child_host_uds != "none"
        {
            return Err(RuntimeControlFailure::InvalidConfiguration);
        }
        let configuration = read_bounded(&self.runtime_configuration, 1024 * 1024)?;
        if sha256_bytes(&configuration) != identity.child_runtime_config_digest {
            return Err(RuntimeControlFailure::ImageUnavailable);
        }
        let configuration: serde_json::Value = serde_json::from_slice(&configuration)
            .map_err(|_| RuntimeControlFailure::InvalidConfiguration)?;
        let runtime = configuration
            .pointer(&format!("/runtimes/{runtime_key}"))
            .and_then(serde_json::Value::as_object)
            .ok_or(RuntimeControlFailure::ImageUnavailable)?;
        let runtime_path = runtime
            .get("path")
            .and_then(serde_json::Value::as_str)
            .map(std::path::Path::new)
            .ok_or(RuntimeControlFailure::ImageUnavailable)?;
        let runtime_arguments = runtime
            .get("runtimeArgs")
            .and_then(serde_json::Value::as_array)
            .ok_or(RuntimeControlFailure::ImageUnavailable)?;
        if !runtime_path.is_absolute()
            || runtime_arguments.iter().any(|value| {
                value.as_str().is_some_and(|argument| {
                    argument.starts_with("--host-uds=") && argument != "--host-uds=none"
                })
            })
            || !runtime_arguments
                .iter()
                .any(|value| value.as_str() == Some("--host-uds=none"))
        {
            return Err(RuntimeControlFailure::ImageUnavailable);
        }
        let runtime_path =
            fs::canonicalize(runtime_path).map_err(|_| RuntimeControlFailure::ImageUnavailable)?;
        if hash_bounded_file(&runtime_path, 1024 * 1024 * 1024)? != identity.engine_identity_digest
        {
            return Err(RuntimeControlFailure::ImageUnavailable);
        }
        let platform = self.command(
            &["info".into(), "--format".into(), "{{json .}}".into()],
            deadline,
            1024 * 1024,
        )?;
        if !platform.success {
            return Err(RuntimeControlFailure::ImageUnavailable);
        }
        let platform: serde_json::Value = serde_json::from_slice(&platform.stdout)
            .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        if platform
            .get("Runtimes")
            .and_then(serde_json::Value::as_object)
            .is_none_or(|runtimes| !runtimes.contains_key(runtime_key))
        {
            return Err(RuntimeControlFailure::ImageUnavailable);
        }
        let platform = serde_json::json!({
            "architecture": platform.get("Architecture"),
            "cgroup_driver": platform.get("CgroupDriver"),
            "cgroup_version": platform.get("CgroupVersion"),
            "driver": platform.get("Driver"),
            "kernel_version": platform.get("KernelVersion"),
            "operating_system": platform.get("OperatingSystem"),
            "os_type": platform.get("OSType"),
            "runtime": {
                "path": platform.pointer(&format!("/Runtimes/{runtime_key}/path")),
                "runtime_args": platform.pointer(&format!("/Runtimes/{runtime_key}/runtimeArgs")),
            },
        });
        if canonical_hash(&platform).map_err(|_| RuntimeControlFailure::InvalidObservation)?
            != identity.platform_identity_digest
        {
            return Err(RuntimeControlFailure::ImageUnavailable);
        }
        let output = self.command(
            &[
                "image".into(),
                "inspect".into(),
                "--format".into(),
                "{{json .}}".into(),
                config_image_id.into(),
            ],
            deadline,
            1024 * 1024,
        )?;
        if !output.success {
            return Err(RuntimeControlFailure::ImageUnavailable);
        }
        let value: serde_json::Value = serde_json::from_slice(&output.stdout)
            .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        if value.get("Id").and_then(serde_json::Value::as_str) != Some(config_image_id) {
            return Err(RuntimeControlFailure::ImageUnavailable);
        }
        Ok(())
    }

    fn require_offline_cache(
        &self,
        root: &std::path::Path,
        inventory_digest: &str,
    ) -> Result<(), RuntimeControlFailure> {
        let canonical = canonical_directory(root)?;
        if canonical != root || !valid_sha256(inventory_digest) {
            return Err(RuntimeControlFailure::CacheUnavailable);
        }
        let manifest_path = canonical
            .parent()
            .ok_or(RuntimeControlFailure::CacheUnavailable)?
            .join("cache.sha256");
        let manifest = read_bounded(&manifest_path, 1024 * 1024)
            .map_err(|_| RuntimeControlFailure::CacheUnavailable)?;
        if sha256_bytes(&manifest) != inventory_digest {
            return Err(RuntimeControlFailure::CacheUnavailable);
        }
        validate_sha256_manifest(&canonical, &manifest)?;
        Ok(())
    }

    fn create_owned_container(
        &self,
        request: OwnedContainerCreate,
        deadline: Instant,
        invocation_cancelled: &AtomicBool,
        relay_cancelled: &AtomicBool,
    ) -> Result<(), RuntimeControlFailure> {
        require_available(deadline, invocation_cancelled, relay_cancelled)?;
        validate_owner(&request.owner)?;
        validate_container_name(&request.name)?;
        validate_docker_arguments(&request.arguments)?;
        if request.mounts.is_empty() || request.mounts.len() > 32 {
            return Err(RuntimeControlFailure::InvalidConfiguration);
        }
        let mut arguments = vec![
            "container".into(),
            "create".into(),
            "--name".into(),
            request.name.clone(),
        ];
        for (key, value) in owner_labels(&request.owner) {
            arguments.extend(["--label".into(), format!("{key}={value}")]);
        }
        for mount in &request.mounts {
            validate_owned_mount(mount)?;
            let mut specification = format!(
                "type=bind,src={},dst={}",
                mount.source.display(),
                mount.destination
            );
            if mount.readonly {
                specification.push_str(",readonly");
            }
            arguments.extend(["--mount".into(), specification]);
        }
        arguments.extend(request.arguments.iter().cloned());
        let output = self.command(&arguments, deadline, 1024 * 1024)?;
        if !output.success {
            return Err(RuntimeControlFailure::LaunchUnavailable);
        }
        let identifier = std::str::from_utf8(&output.stdout)
            .map_err(|_| RuntimeControlFailure::InvalidObservation)?
            .trim();
        if !valid_full_container_id(identifier) {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        if !owned_container_matches(self, &request.name, &request.owner, deadline)? {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        let mut owned = self
            .owned
            .lock()
            .map_err(|_| RuntimeControlFailure::CleanupUnsettled)?;
        let resources = owned.entry(request.owner).or_default();
        if resources
            .containers
            .iter()
            .any(|item| item == &request.name)
        {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        resources.containers.push(request.name);
        Ok(())
    }

    fn run_owned_container(
        &self,
        owner: &RuntimeOwner,
        name: &str,
        writable_roots: &[PathBuf],
        limits: &ContainerExecutionLimits,
        invocation_cancelled: &AtomicBool,
        relay_cancelled: &AtomicBool,
    ) -> Result<ObservedContainerExit, RuntimeControlFailure> {
        validate_owner(owner)?;
        validate_container_name(name)?;
        if !owned_container_matches(self, name, owner, limits.deadline)? {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        let roots = writable_roots
            .iter()
            .map(|root| {
                let canonical = canonical_directory(root)?;
                if &canonical != root {
                    return Err(RuntimeControlFailure::InvalidConfiguration);
                }
                Ok(canonical)
            })
            .collect::<Result<Vec<_>, _>>()?;
        let workspace_before_sha256 = combined_tree_digest(&roots, limits)?;
        let nonce = format!(
            "{:016x}",
            RUNTIME_FILE_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        );
        let stdout_path = self.runtime_root.join(format!(".container-{nonce}.stdout"));
        let stderr_path = self.runtime_root.join(format!(".container-{nonce}.stderr"));
        let stdout = create_output(&stdout_path)?;
        let stderr = create_output(&stderr_path)?;
        let mut child = Command::new(&self.docker_binary)
            .args(["container", "start", "--attach", name])
            .stdin(Stdio::null())
            .stdout(stdout)
            .stderr(stderr)
            .spawn()
            .map_err(|_| RuntimeControlFailure::LaunchUnavailable)?;
        let started = Instant::now();
        let operation_deadline = started
            .checked_add(Duration::from_millis(limits.operation_timeout_ms))
            .unwrap_or(limits.deadline);
        let mut measurements = Measurements::default();
        let mut forced = None;
        loop {
            if invocation_cancelled.load(Ordering::SeqCst) || relay_cancelled.load(Ordering::SeqCst)
            {
                stop_runtime_child(self, &mut child, name, limits.deadline);
                remove_outputs(&stdout_path, &stderr_path);
                return Err(RuntimeControlFailure::Cancelled);
            }
            if Instant::now() >= limits.deadline && limits.deadline < operation_deadline {
                stop_runtime_child(self, &mut child, name, limits.deadline);
                remove_outputs(&stdout_path, &stderr_path);
                return Err(RuntimeControlFailure::DeadlineExceeded);
            }
            if forced.is_none() && Instant::now() >= operation_deadline {
                forced = Some(RuntimeTermination::DeadlineExceeded);
            }
            if forced.is_none()
                && output_size(&stdout_path, &stderr_path)? > limits.output_bytes as u64
            {
                forced = Some(RuntimeTermination::OutputExceeded);
            }
            let usage = combined_tree_usage(&roots)?;
            measurements.written_bytes = measurements.written_bytes.max(usage.0);
            measurements.written_entries = measurements.written_entries.max(usage.1);
            if forced.is_none() && usage.0 > limits.disk_bytes {
                forced = Some(RuntimeTermination::DiskExceeded);
            }
            if forced.is_none() && usage.1 > limits.entries {
                forced = Some(RuntimeTermination::DiskExceeded);
            }
            if let Some(pid) = self.container_pid(name, limits.deadline) {
                if let Ok(sample) = sample_cgroup(pid) {
                    measurements.cgroup_samples = measurements.cgroup_samples.saturating_add(1);
                    measurements.cpu_time_ms = measurements.cpu_time_ms.max(sample.cpu_time_ms);
                    measurements.peak_memory_bytes =
                        measurements.peak_memory_bytes.max(sample.peak_memory_bytes);
                    measurements.peak_pids = measurements.peak_pids.max(sample.peak_pids);
                }
            }
            if forced.is_none() && measurements.cpu_time_ms > limits.cpu_time_ms {
                forced = Some(RuntimeTermination::CpuExceeded);
            }
            if forced.is_none() && measurements.peak_memory_bytes > limits.memory_bytes {
                forced = Some(RuntimeTermination::MemoryExceeded);
            }
            if forced.is_none() && measurements.peak_pids > limits.pids {
                forced = Some(RuntimeTermination::PidExceeded);
            }
            if forced.is_some() {
                self.kill_container(name, limits.deadline);
            }
            match child.try_wait() {
                Ok(Some(_)) => break,
                Ok(None) => thread::sleep(Duration::from_millis(10)),
                Err(_) => {
                    stop_runtime_child(self, &mut child, name, limits.deadline);
                    remove_outputs(&stdout_path, &stderr_path);
                    return Err(RuntimeControlFailure::LaunchUnavailable);
                }
            }
        }
        let state = self.container_state(name, limits.deadline)?;
        let elapsed_ms = elapsed_ms(started);
        let stdout = read_prefix(&stdout_path, limits.output_bytes)?;
        let stderr = read_prefix(
            &stderr_path,
            limits.output_bytes.saturating_sub(stdout.len()),
        )?;
        remove_outputs(&stdout_path, &stderr_path);
        let stdout =
            String::from_utf8(stdout).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        let stderr =
            String::from_utf8(stderr).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        let usage = combined_tree_usage(&roots)?;
        measurements.written_bytes = measurements.written_bytes.max(usage.0);
        measurements.written_entries = measurements.written_entries.max(usage.1);
        let workspace_after_sha256 = combined_tree_digest(&roots, limits)?;
        if measurements.cgroup_samples == 0 {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        let termination = forced.unwrap_or_else(|| {
            if state.oom_killed {
                RuntimeTermination::MemoryExceeded
            } else if state.exit_code.is_some_and(|code| code >= 128) {
                RuntimeTermination::Signalled
            } else {
                RuntimeTermination::Exited
            }
        });
        validate_measurement_overruns(&measurements, elapsed_ms, termination, limits)?;
        let signal = if termination == RuntimeTermination::Signalled {
            state.exit_code.and_then(|code| code.checked_sub(128))
        } else {
            None
        };
        Ok(ObservedContainerExit {
            termination,
            exit_code: state.exit_code,
            signal,
            stdout,
            stderr,
            elapsed_ms,
            cpu_time_ms: measurements.cpu_time_ms,
            peak_memory_bytes: measurements.peak_memory_bytes,
            peak_pids: measurements.peak_pids,
            written_bytes: measurements.written_bytes,
            written_entries: measurements.written_entries,
            measurement_method: "cgroup_v2_sampled_cpu_usage_memory_peak_pids_peak_and_owned_tree"
                .into(),
            workspace_before_sha256: Some(workspace_before_sha256),
            workspace_after_sha256: Some(workspace_after_sha256),
        })
    }

    fn load_single_owned_image(
        &self,
        owner: &RuntimeOwner,
        archive: &std::path::Path,
        expected_tag: &str,
        maximum_bytes: u64,
        deadline: Instant,
    ) -> Result<LoadedOwnedImage, RuntimeControlFailure> {
        validate_owner(owner)?;
        validate_image_tag(expected_tag)?;
        let canonical =
            fs::canonicalize(archive).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        if canonical != archive {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        let metadata = fs::symlink_metadata(&canonical)
            .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        if !metadata.file_type().is_file() || metadata.len() == 0 || metadata.len() > maximum_bytes
        {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        validate_single_image_archive(&canonical, expected_tag, maximum_bytes)?;
        if image_exists(self, expected_tag, deadline)? {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        {
            let mut owned = self
                .owned
                .lock()
                .map_err(|_| RuntimeControlFailure::CleanupUnsettled)?;
            owned
                .entry(owner.clone())
                .or_default()
                .images
                .push((expected_tag.into(), String::new()));
        }
        let output = self.command(
            &[
                "image".into(),
                "load".into(),
                "--input".into(),
                canonical.display().to_string(),
            ],
            deadline,
            1024 * 1024,
        )?;
        if !output.success {
            return Err(RuntimeControlFailure::LaunchUnavailable);
        }
        let inspected = self.command(
            &[
                "image".into(),
                "inspect".into(),
                "--format".into(),
                "{{.Id}}".into(),
                expected_tag.into(),
            ],
            deadline,
            4096,
        )?;
        let config_image_id = std::str::from_utf8(&inspected.stdout)
            .map_err(|_| RuntimeControlFailure::InvalidObservation)?
            .trim()
            .to_owned();
        if !inspected.success || !valid_sha256(&config_image_id) {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        let archive_sha256 = hash_bounded_file(&canonical, maximum_bytes)?;
        let mut owned = self
            .owned
            .lock()
            .map_err(|_| RuntimeControlFailure::CleanupUnsettled)?;
        let resources = owned
            .get_mut(owner)
            .ok_or(RuntimeControlFailure::CleanupUnsettled)?;
        let image = resources
            .images
            .iter_mut()
            .find(|item| item.0 == expected_tag)
            .ok_or(RuntimeControlFailure::CleanupUnsettled)?;
        image.1.clone_from(&config_image_id);
        Ok(LoadedOwnedImage {
            config_image_id,
            archive_sha256,
            archive_byte_count: metadata.len(),
        })
    }

    fn cleanup_owner(
        &self,
        owner: &RuntimeOwner,
        deadline: Instant,
    ) -> Result<(), RuntimeControlFailure> {
        validate_owner(owner)?;
        let resources = self
            .owned
            .lock()
            .map_err(|_| RuntimeControlFailure::CleanupUnsettled)?
            .remove(owner)
            .unwrap_or_default();
        for name in resources.containers.iter().rev() {
            if container_exists(self, name, deadline)? {
                if !owned_container_matches(self, name, owner, deadline)? {
                    return Err(RuntimeControlFailure::CleanupUnsettled);
                }
                let removed = self.command(
                    &[
                        "container".into(),
                        "rm".into(),
                        "--force".into(),
                        name.clone(),
                    ],
                    deadline,
                    64 * 1024,
                )?;
                if !removed.success || container_exists(self, name, deadline)? {
                    return Err(RuntimeControlFailure::CleanupUnsettled);
                }
            }
        }
        for (tag, identifier) in resources.images.iter().rev() {
            if image_exists(self, tag, deadline)? {
                if identifier.is_empty() {
                    return Err(RuntimeControlFailure::CleanupUnsettled);
                }
                let inspected = self.command(
                    &[
                        "image".into(),
                        "inspect".into(),
                        "--format".into(),
                        "{{.Id}}".into(),
                        tag.clone(),
                    ],
                    deadline,
                    4096,
                )?;
                if std::str::from_utf8(&inspected.stdout).ok().map(str::trim) != Some(identifier) {
                    return Err(RuntimeControlFailure::CleanupUnsettled);
                }
                let removed = self.command(
                    &["image".into(), "rm".into(), tag.clone()],
                    deadline,
                    64 * 1024,
                )?;
                if !removed.success || image_exists(self, tag, deadline)? {
                    return Err(RuntimeControlFailure::CleanupUnsettled);
                }
            }
        }
        Ok(())
    }
}

fn create_output(path: &std::path::Path) -> Result<File, RuntimeControlFailure> {
    OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(path)
        .map_err(|_| RuntimeControlFailure::LaunchUnavailable)
}

fn remove_outputs(stdout: &std::path::Path, stderr: &std::path::Path) {
    let _ = fs::remove_file(stdout);
    let _ = fs::remove_file(stderr);
}

fn output_size(
    stdout: &std::path::Path,
    stderr: &std::path::Path,
) -> Result<u64, RuntimeControlFailure> {
    let stdout = fs::metadata(stdout)
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?
        .len();
    let stderr = fs::metadata(stderr)
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?
        .len();
    stdout
        .checked_add(stderr)
        .ok_or(RuntimeControlFailure::CapacityExceeded)
}

fn read_bounded(path: &std::path::Path, maximum: usize) -> Result<Vec<u8>, RuntimeControlFailure> {
    let file = File::open(path).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    let mut bytes = Vec::new();
    file.take(maximum.saturating_add(1) as u64)
        .read_to_end(&mut bytes)
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    if bytes.len() > maximum {
        return Err(RuntimeControlFailure::CapacityExceeded);
    }
    Ok(bytes)
}

fn read_prefix(path: &std::path::Path, maximum: usize) -> Result<Vec<u8>, RuntimeControlFailure> {
    let file = File::open(path).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    let mut bytes = Vec::new();
    file.take(maximum as u64)
        .read_to_end(&mut bytes)
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    Ok(bytes)
}

fn canonical_directory(path: &std::path::Path) -> Result<PathBuf, RuntimeControlFailure> {
    let canonical =
        fs::canonicalize(path).map_err(|_| RuntimeControlFailure::InvalidConfiguration)?;
    let metadata = fs::symlink_metadata(&canonical)
        .map_err(|_| RuntimeControlFailure::InvalidConfiguration)?;
    if !metadata.file_type().is_dir() || metadata.file_type().is_symlink() {
        return Err(RuntimeControlFailure::InvalidConfiguration);
    }
    Ok(canonical)
}

fn validate_sha256_manifest(
    root: &std::path::Path,
    manifest: &[u8],
) -> Result<(), RuntimeControlFailure> {
    let text =
        std::str::from_utf8(manifest).map_err(|_| RuntimeControlFailure::CacheUnavailable)?;
    let mut expected = HashMap::new();
    for line in text.lines() {
        let (digest, relative) = line
            .split_once("  ")
            .ok_or(RuntimeControlFailure::CacheUnavailable)?;
        if digest.len() != 64
            || !digest
                .bytes()
                .all(|item| item.is_ascii_hexdigit() && !item.is_ascii_uppercase())
            || !relative.starts_with("./")
        {
            return Err(RuntimeControlFailure::CacheUnavailable);
        }
        let relative = std::path::Path::new(&relative[2..]);
        if relative.as_os_str().is_empty()
            || relative.is_absolute()
            || relative.components().any(|item| {
                !matches!(
                    item,
                    std::path::Component::Normal(_) | std::path::Component::CurDir
                )
            })
        {
            return Err(RuntimeControlFailure::CacheUnavailable);
        }
        if expected
            .insert(relative.to_owned(), digest.to_owned())
            .is_some()
        {
            return Err(RuntimeControlFailure::CacheUnavailable);
        }
    }
    if expected.is_empty() {
        return Err(RuntimeControlFailure::CacheUnavailable);
    }
    let mut actual = Vec::new();
    collect_regular_files(root, root, &mut actual, 100_000)?;
    if actual.len() != expected.len() {
        return Err(RuntimeControlFailure::CacheUnavailable);
    }
    for path in actual {
        let relative = path
            .strip_prefix(root)
            .map_err(|_| RuntimeControlFailure::CacheUnavailable)?;
        let expected_digest = expected
            .get(relative)
            .ok_or(RuntimeControlFailure::CacheUnavailable)?;
        if &hash_bounded_file(&path, u64::MAX)?[7..] != expected_digest {
            return Err(RuntimeControlFailure::CacheUnavailable);
        }
    }
    Ok(())
}

fn collect_regular_files(
    root: &std::path::Path,
    directory: &std::path::Path,
    files: &mut Vec<PathBuf>,
    maximum_entries: usize,
) -> Result<(), RuntimeControlFailure> {
    let mut entries = fs::read_dir(directory)
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    entries.sort_by_key(std::fs::DirEntry::file_name);
    for entry in entries {
        if files.len() >= maximum_entries {
            return Err(RuntimeControlFailure::CapacityExceeded);
        }
        let path = entry.path();
        if !path.starts_with(root) {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        let metadata =
            fs::symlink_metadata(&path).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        if metadata.file_type().is_symlink() {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        if metadata.file_type().is_dir() {
            collect_regular_files(root, &path, files, maximum_entries)?;
        } else if metadata.file_type().is_file() {
            files.push(path);
        } else {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
    }
    Ok(())
}

fn require_available(
    deadline: Instant,
    invocation_cancelled: &AtomicBool,
    relay_cancelled: &AtomicBool,
) -> Result<(), RuntimeControlFailure> {
    if invocation_cancelled.load(Ordering::SeqCst) || relay_cancelled.load(Ordering::SeqCst) {
        return Err(RuntimeControlFailure::Cancelled);
    }
    if Instant::now() >= deadline {
        return Err(RuntimeControlFailure::DeadlineExceeded);
    }
    Ok(())
}

fn validate_owner(owner: &RuntimeOwner) -> Result<(), RuntimeControlFailure> {
    if !valid_label_value(&owner.deployment_owner, 128)
        || !valid_sha256(&owner.request_digest)
        || !valid_label_value(&owner.attempt_id, 128)
        || !owner.trial_owner_id.starts_with("trial_")
        || !valid_label_value(&owner.trial_owner_id, 64)
    {
        return Err(RuntimeControlFailure::InvalidConfiguration);
    }
    Ok(())
}

fn valid_label_value(value: &str, maximum: usize) -> bool {
    !value.is_empty()
        && value.len() <= maximum
        && value
            .bytes()
            .all(|item| item.is_ascii_alphanumeric() || matches!(item, b'_' | b'-' | b'.' | b':'))
}

fn owner_labels(owner: &RuntimeOwner) -> [(&'static str, &str); 5] {
    [
        ("workstream.trial", "true"),
        ("workstream.trial.deployment-owner", &owner.deployment_owner),
        ("workstream.trial.request-digest", &owner.request_digest),
        ("workstream.trial.attempt-id", &owner.attempt_id),
        ("workstream.trial.owner-id", &owner.trial_owner_id),
    ]
}

fn validate_container_name(value: &str) -> Result<(), RuntimeControlFailure> {
    if value.is_empty()
        || value.len() > 128
        || !value
            .bytes()
            .all(|item| item.is_ascii_alphanumeric() || matches!(item, b'_' | b'-' | b'.'))
    {
        return Err(RuntimeControlFailure::InvalidConfiguration);
    }
    Ok(())
}

fn validate_docker_arguments(arguments: &[String]) -> Result<(), RuntimeControlFailure> {
    if arguments.is_empty()
        || arguments.len() > 256
        || arguments.iter().any(|item| {
            item.is_empty()
                || item.len() > 4096
                || item
                    .bytes()
                    .any(|byte| byte == 0 || byte == b'\n' || byte == b'\r')
        })
    {
        return Err(RuntimeControlFailure::InvalidConfiguration);
    }
    Ok(())
}

fn validate_owned_mount(mount: &OwnedBindMount) -> Result<(), RuntimeControlFailure> {
    let canonical =
        fs::canonicalize(&mount.source).map_err(|_| RuntimeControlFailure::InvalidConfiguration)?;
    if canonical != mount.source
        || mount.source.to_str().is_none_or(|value| {
            !value.starts_with('/')
                || value.contains(',')
                || value.contains('\n')
                || value.contains('\r')
        })
        || mount.destination.contains(',')
        || mount.destination.contains('\n')
        || mount.destination.contains('\r')
    {
        return Err(RuntimeControlFailure::InvalidConfiguration);
    }
    let accepted = match mount.class {
        OwnedMountClass::ProjectedContext => mount.readonly && mount.destination == "/workspace",
        OwnedMountClass::OfflineCache => mount.readonly && mount.destination == "/cache",
        OwnedMountClass::CandidateOutput => !mount.readonly && mount.destination == "/out",
        OwnedMountClass::TrialState => !mount.readonly && mount.destination == "/work/state",
        OwnedMountClass::VerifiedMaterial => {
            mount.readonly
                && mount
                    .destination
                    .strip_prefix("/work/input/")
                    .is_some_and(valid_relative_label)
        }
    };
    if !accepted {
        return Err(RuntimeControlFailure::InvalidConfiguration);
    }
    Ok(())
}

fn valid_relative_label(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 100
        && value
            .bytes()
            .all(|item| item.is_ascii_alphanumeric() || matches!(item, b'_' | b'-' | b'.'))
        && value != "."
        && value != ".."
}

fn valid_full_container_id(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|item| item.is_ascii_hexdigit() && !item.is_ascii_uppercase())
}

fn owned_container_matches(
    control: &DockerRuntimeControl,
    name: &str,
    owner: &RuntimeOwner,
    deadline: Instant,
) -> Result<bool, RuntimeControlFailure> {
    let output = control.command(
        &[
            "container".into(),
            "inspect".into(),
            "--format".into(),
            "{{json .}}".into(),
            name.into(),
        ],
        deadline,
        1024 * 1024,
    )?;
    if !output.success {
        return Ok(false);
    }
    let value: serde_json::Value = serde_json::from_slice(&output.stdout)
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    if value.get("Name").and_then(serde_json::Value::as_str) != Some(&format!("/{name}")) {
        return Ok(false);
    }
    Ok(owner_labels(owner).iter().all(|(key, expected)| {
        value
            .pointer(&format!(
                "/Config/Labels/{}",
                key.replace('~', "~0").replace('/', "~1")
            ))
            .and_then(serde_json::Value::as_str)
            == Some(*expected)
    }))
}

fn container_exists(
    control: &DockerRuntimeControl,
    name: &str,
    deadline: Instant,
) -> Result<bool, RuntimeControlFailure> {
    let output = control.command(
        &["container".into(), "inspect".into(), name.into()],
        deadline,
        64 * 1024,
    )?;
    Ok(output.success)
}

fn image_exists(
    control: &DockerRuntimeControl,
    tag: &str,
    deadline: Instant,
) -> Result<bool, RuntimeControlFailure> {
    let output = control.command(
        &["image".into(), "inspect".into(), tag.into()],
        deadline,
        64 * 1024,
    )?;
    Ok(output.success)
}

fn stop_runtime_child(
    control: &DockerRuntimeControl,
    child: &mut Child,
    name: &str,
    deadline: Instant,
) {
    control.kill_container(name, deadline);
    let _ = child.kill();
    let _ = child.wait();
}

fn elapsed_ms(started: Instant) -> u64 {
    u64::try_from(started.elapsed().as_millis()).unwrap_or(u64::MAX)
}

fn sample_cgroup(pid: u32) -> Result<Measurements, RuntimeControlFailure> {
    let cgroup = fs::read_to_string(format!("/proc/{pid}/cgroup"))
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    let relative = cgroup
        .lines()
        .find_map(|line| line.strip_prefix("0::"))
        .filter(|value| value.starts_with('/') && !value.contains(".."))
        .ok_or(RuntimeControlFailure::InvalidObservation)?;
    let root = std::path::Path::new("/sys/fs/cgroup").join(&relative[1..]);
    let cpu = fs::read_to_string(root.join("cpu.stat"))
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    let usage_usec = cpu
        .lines()
        .find_map(|line| line.strip_prefix("usage_usec "))
        .and_then(|value| value.parse::<u64>().ok())
        .ok_or(RuntimeControlFailure::InvalidObservation)?;
    let memory_current = read_u64(root.join("memory.current"))?;
    let memory_peak = read_u64(root.join("memory.peak")).unwrap_or(memory_current);
    let pids = read_u64(root.join("pids.peak"))?;
    Ok(Measurements {
        cgroup_samples: 1,
        cpu_time_ms: usage_usec / 1000,
        peak_memory_bytes: memory_current.max(memory_peak),
        peak_pids: pids,
        ..Measurements::default()
    })
}

fn read_u64(path: PathBuf) -> Result<u64, RuntimeControlFailure> {
    fs::read_to_string(path)
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?
        .trim()
        .parse()
        .map_err(|_| RuntimeControlFailure::InvalidObservation)
}

fn combined_tree_usage(roots: &[PathBuf]) -> Result<(u64, u64), RuntimeControlFailure> {
    let mut bytes = 0_u64;
    let mut entries = 0_u64;
    for root in roots {
        tree_usage(root, &mut bytes, &mut entries)?;
    }
    Ok((bytes, entries))
}

fn tree_usage(
    path: &std::path::Path,
    bytes: &mut u64,
    entries: &mut u64,
) -> Result<(), RuntimeControlFailure> {
    let metadata =
        fs::symlink_metadata(path).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    if metadata.file_type().is_symlink() {
        return Err(RuntimeControlFailure::InvalidObservation);
    }
    *entries = entries
        .checked_add(1)
        .ok_or(RuntimeControlFailure::CapacityExceeded)?;
    if metadata.file_type().is_file() {
        *bytes = bytes
            .checked_add(metadata.len())
            .ok_or(RuntimeControlFailure::CapacityExceeded)?;
    } else if metadata.file_type().is_dir() {
        let mut children = fs::read_dir(path)
            .map_err(|_| RuntimeControlFailure::InvalidObservation)?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        children.sort_by_key(std::fs::DirEntry::file_name);
        for child in children {
            tree_usage(&child.path(), bytes, entries)?;
        }
    } else {
        return Err(RuntimeControlFailure::InvalidObservation);
    }
    Ok(())
}

fn combined_tree_digest(
    roots: &[PathBuf],
    limits: &ContainerExecutionLimits,
) -> Result<String, RuntimeControlFailure> {
    let mut digest = Sha256::new();
    let (bytes, entries) = combined_tree_usage(roots)?;
    if bytes > limits.disk_bytes.saturating_add(limits.disk_overrun_bytes)
        || entries > limits.entries.saturating_add(limits.entries_overrun)
    {
        return Err(RuntimeControlFailure::CapacityExceeded);
    }
    for root in roots {
        hash_tree(root, root, &mut digest)?;
    }
    Ok(format!("sha256:{:x}", digest.finalize()))
}

fn hash_tree(
    root: &std::path::Path,
    path: &std::path::Path,
    digest: &mut Sha256,
) -> Result<(), RuntimeControlFailure> {
    let metadata =
        fs::symlink_metadata(path).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    let relative = path
        .strip_prefix(root)
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    let path_bytes = relative
        .to_str()
        .ok_or(RuntimeControlFailure::InvalidObservation)?
        .as_bytes();
    digest.update((path_bytes.len() as u64).to_be_bytes());
    digest.update(path_bytes);
    if metadata.file_type().is_dir() {
        digest.update(b"directory");
        let mut children = fs::read_dir(path)
            .map_err(|_| RuntimeControlFailure::InvalidObservation)?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        children.sort_by_key(std::fs::DirEntry::file_name);
        for child in children {
            hash_tree(root, &child.path(), digest)?;
        }
    } else if metadata.file_type().is_file() {
        digest.update(b"file");
        digest.update(metadata.len().to_be_bytes());
        let mut file = File::open(path).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        std::io::copy(&mut file, digest).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    } else {
        return Err(RuntimeControlFailure::InvalidObservation);
    }
    Ok(())
}

fn validate_measurement_overruns(
    measurements: &Measurements,
    elapsed: u64,
    termination: RuntimeTermination,
    limits: &ContainerExecutionLimits,
) -> Result<(), RuntimeControlFailure> {
    let within =
        |observed: u64, bound: u64, overrun: u64| observed <= bound.saturating_add(overrun);
    if !within(
        elapsed,
        limits.operation_timeout_ms,
        limits.wall_time_overrun_ms,
    ) || !within(
        measurements.cpu_time_ms,
        limits.cpu_time_ms,
        limits.cpu_time_overrun_ms,
    ) || !within(
        measurements.peak_memory_bytes,
        limits.memory_bytes,
        limits.memory_overrun_bytes,
    ) || !within(measurements.peak_pids, limits.pids, limits.pids_overrun)
        || !within(
            measurements.written_bytes,
            limits.disk_bytes,
            limits.disk_overrun_bytes,
        )
        || !within(
            measurements.written_entries,
            limits.entries,
            limits.entries_overrun,
        )
    {
        return Err(RuntimeControlFailure::InvalidObservation);
    }
    let crossed = match termination {
        RuntimeTermination::DeadlineExceeded => elapsed >= limits.operation_timeout_ms,
        RuntimeTermination::CpuExceeded => measurements.cpu_time_ms >= limits.cpu_time_ms,
        RuntimeTermination::MemoryExceeded => measurements.peak_memory_bytes >= limits.memory_bytes,
        RuntimeTermination::PidExceeded => measurements.peak_pids >= limits.pids,
        RuntimeTermination::DiskExceeded => {
            measurements.written_bytes >= limits.disk_bytes
                || measurements.written_entries >= limits.entries
        }
        RuntimeTermination::OutputExceeded => true,
        RuntimeTermination::Exited | RuntimeTermination::Signalled => true,
    };
    if !crossed {
        return Err(RuntimeControlFailure::InvalidObservation);
    }
    Ok(())
}

fn validate_image_tag(value: &str) -> Result<(), RuntimeControlFailure> {
    let suffix = value
        .strip_prefix("workstream-trial:")
        .ok_or(RuntimeControlFailure::InvalidConfiguration)?;
    if !valid_relative_label(suffix) {
        return Err(RuntimeControlFailure::InvalidConfiguration);
    }
    Ok(())
}

fn validate_single_image_archive(
    archive: &std::path::Path,
    expected_tag: &str,
    maximum_bytes: u64,
) -> Result<(), RuntimeControlFailure> {
    let mut file = File::open(archive).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    let length = file
        .metadata()
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?
        .len();
    if length == 0 || length > maximum_bytes {
        return Err(RuntimeControlFailure::InvalidObservation);
    }
    let mut offset = 0_u64;
    let mut manifest = None;
    let mut paths = HashSet::new();
    while offset.saturating_add(512) <= length {
        file.seek(SeekFrom::Start(offset))
            .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        let mut header = [0_u8; 512];
        file.read_exact(&mut header)
            .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
        if header.iter().all(|byte| *byte == 0) {
            break;
        }
        validate_tar_checksum(&header)?;
        let name = tar_text(&header[0..100])?;
        let prefix = tar_text(&header[345..500])?;
        let path = if prefix.is_empty() {
            name
        } else {
            format!("{prefix}/{name}")
        };
        if path.starts_with('/') || path.split('/').any(|part| part == "..") {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        if !paths.insert(path.clone()) || path == "repositories" {
            return Err(RuntimeControlFailure::InvalidObservation);
        }
        let size = tar_octal(&header[124..136])?;
        let data = offset
            .checked_add(512)
            .ok_or(RuntimeControlFailure::InvalidObservation)?;
        let padded = size
            .checked_add(511)
            .map(|value| value / 512 * 512)
            .ok_or(RuntimeControlFailure::InvalidObservation)?;
        offset = data
            .checked_add(padded)
            .filter(|value| *value <= length)
            .ok_or(RuntimeControlFailure::InvalidObservation)?;
        if path == "manifest.json" {
            if manifest.is_some() || size > 1024 * 1024 {
                return Err(RuntimeControlFailure::InvalidObservation);
            }
            file.seek(SeekFrom::Start(data))
                .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
            let mut bytes = vec![0_u8; size as usize];
            file.read_exact(&mut bytes)
                .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
            manifest = Some(bytes);
        }
    }
    let manifest = manifest.ok_or(RuntimeControlFailure::InvalidObservation)?;
    let entries: Vec<serde_json::Value> =
        serde_json::from_slice(&manifest).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    if entries.len() != 1 {
        return Err(RuntimeControlFailure::InvalidObservation);
    }
    let entry = entries.first().unwrap();
    let tags = entry
        .get("RepoTags")
        .and_then(serde_json::Value::as_array)
        .ok_or(RuntimeControlFailure::InvalidObservation)?;
    let config = entry
        .get("Config")
        .and_then(serde_json::Value::as_str)
        .ok_or(RuntimeControlFailure::InvalidObservation)?;
    let layers = entry
        .get("Layers")
        .and_then(serde_json::Value::as_array)
        .ok_or(RuntimeControlFailure::InvalidObservation)?;
    let valid_config = valid_sha256(config)
        || (config.len() == 69
            && config.ends_with(".json")
            && config[..64]
                .bytes()
                .all(|item| item.is_ascii_hexdigit() && !item.is_ascii_uppercase()));
    if tags.len() != 1
        || tags[0].as_str() != Some(expected_tag)
        || !valid_config
        || !paths.contains(config)
        || layers.is_empty()
        || layers.iter().any(|layer| {
            layer.as_str().is_none_or(|path| {
                path.starts_with('/')
                    || path.split('/').any(|part| part == "..")
                    || !paths.contains(path)
            })
        })
    {
        return Err(RuntimeControlFailure::InvalidObservation);
    }
    Ok(())
}

fn validate_tar_checksum(header: &[u8; 512]) -> Result<(), RuntimeControlFailure> {
    let expected = tar_octal(&header[148..156])?;
    let actual: u64 = header
        .iter()
        .enumerate()
        .map(|(index, byte)| {
            if (148..156).contains(&index) {
                u64::from(b' ')
            } else {
                u64::from(*byte)
            }
        })
        .sum();
    if actual != expected {
        return Err(RuntimeControlFailure::InvalidObservation);
    }
    Ok(())
}

fn tar_text(bytes: &[u8]) -> Result<String, RuntimeControlFailure> {
    let end = bytes
        .iter()
        .position(|byte| *byte == 0)
        .unwrap_or(bytes.len());
    let value = std::str::from_utf8(&bytes[..end])
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    Ok(value.to_owned())
}

fn tar_octal(bytes: &[u8]) -> Result<u64, RuntimeControlFailure> {
    let text = std::str::from_utf8(bytes)
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?
        .trim_matches(|character| character == '\0' || character == ' ');
    u64::from_str_radix(text, 8).map_err(|_| RuntimeControlFailure::InvalidObservation)
}

fn hash_bounded_file(
    path: &std::path::Path,
    maximum_bytes: u64,
) -> Result<String, RuntimeControlFailure> {
    let mut file = File::open(path).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    let metadata = file
        .metadata()
        .map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    if metadata.len() > maximum_bytes {
        return Err(RuntimeControlFailure::CapacityExceeded);
    }
    let mut digest = Sha256::new();
    std::io::copy(&mut file, &mut digest).map_err(|_| RuntimeControlFailure::InvalidObservation)?;
    Ok(format!("sha256:{:x}", digest.finalize()))
}

fn sha256_bytes(value: &[u8]) -> String {
    format!("sha256:{:x}", Sha256::digest(value))
}

#[derive(Clone, Debug)]
pub(crate) struct DockerTrialConfiguration {
    pub(crate) identity: SandboxBackendIdentity,
    pub(crate) deployment_owner: String,
    pub(crate) request_digest: String,
    pub(crate) attempt_id: String,
    pub(crate) runtime_key: String,
    pub(crate) builder_image_id: String,
    pub(crate) offline_cache_root: PathBuf,
    pub(crate) maximum_candidate_archive_bytes: u64,
    pub(crate) candidate_uid: u32,
    pub(crate) candidate_gid: u32,
}

pub(crate) struct DockerTrialBackend<C: RuntimeControl> {
    config: DockerTrialConfiguration,
    pub(crate) control: C,
}

impl<C: RuntimeControl> DockerTrialBackend<C> {
    pub(crate) fn new(
        config: DockerTrialConfiguration,
        control: C,
    ) -> Result<Self, SandboxFailure> {
        if config.identity.child_runtime != "runsc"
            || config.identity.child_host_uds != "none"
            || config.runtime_key.is_empty()
            || config.runtime_key.len() > 100
            || !config
                .runtime_key
                .bytes()
                .all(|item| item.is_ascii_alphanumeric() || matches!(item, b'_' | b'-' | b'.'))
            || !valid_sha256(&config.builder_image_id)
            || config.builder_image_id != config.identity.builder_image_digest
            || !config.offline_cache_root.is_absolute()
            || config.maximum_candidate_archive_bytes == 0
            || config.candidate_uid == 0
            || config.candidate_gid == 0
        {
            return Err(infrastructure(TrialRelayFailure::InvalidRequest));
        }
        Ok(Self { config, control })
    }

    fn owner(&self, trial_owner_id: &str) -> RuntimeOwner {
        RuntimeOwner {
            deployment_owner: self.config.deployment_owner.clone(),
            request_digest: self.config.request_digest.clone(),
            attempt_id: self.config.attempt_id.clone(),
            trial_owner_id: trial_owner_id.to_owned(),
        }
    }

    fn limits(
        &self,
        resources: &crate::trial_relay::TrialResources,
        timeout_ms: u64,
        output_bytes: usize,
        overruns: &SandboxEnforcementOverruns,
        deadline: Instant,
    ) -> ContainerExecutionLimits {
        ContainerExecutionLimits {
            deadline,
            operation_timeout_ms: timeout_ms,
            cpu_time_ms: resources.cpu_time_ms,
            wall_time_overrun_ms: overruns.wall_time_ms,
            cpu_time_overrun_ms: overruns.cpu_time_ms,
            memory_bytes: resources.memory_bytes,
            memory_overrun_bytes: overruns.memory_bytes,
            pids: resources.pids,
            pids_overrun: overruns.pids,
            disk_bytes: resources.disk_bytes,
            disk_overrun_bytes: overruns.disk_bytes,
            entries: resources.maximum_entries,
            entries_overrun: overruns.entries,
            output_bytes,
        }
    }

    fn common_create_arguments(
        &self,
        resources: &crate::trial_relay::TrialResources,
    ) -> Vec<String> {
        vec![
            "--runtime".into(),
            self.config.runtime_key.clone(),
            "--network".into(),
            "none".into(),
            "--cap-drop".into(),
            "ALL".into(),
            "--security-opt".into(),
            "no-new-privileges".into(),
            "--pids-limit".into(),
            resources.pids.to_string(),
            "--memory".into(),
            resources.memory_bytes.to_string(),
            "--memory-swap".into(),
            resources.memory_bytes.to_string(),
            "--cpus".into(),
            format!("{:.3}", resources.cpu_quota_millis as f64 / 1000.0),
        ]
    }
}

impl<C: RuntimeControl> TrialSandboxBackend for DockerTrialBackend<C> {
    fn identity(&self) -> SandboxBackendIdentity {
        self.config.identity.clone()
    }

    fn build(
        &self,
        request: &SandboxBuildRequest,
        deadline: Instant,
        invocation_cancelled: &AtomicBool,
        relay_cancelled: &AtomicBool,
    ) -> Result<SandboxBuildResult, SandboxFailure> {
        self.control
            .require_image(
                &self.config.builder_image_id,
                &self.config.identity,
                &self.config.runtime_key,
                deadline,
            )
            .map_err(runtime_failure)?;
        self.control
            .require_offline_cache(
                &self.config.offline_cache_root,
                &self.config.identity.offline_cache_digest,
            )
            .map_err(runtime_failure)?;
        let owner = self.owner(&request.owner_id);
        let name = format!("ws-trial-{}-build", request.owner_id);
        let mut arguments = self.common_create_arguments(&request.resources);
        arguments.extend([
            "--user".into(),
            "0:0".into(),
            "--cap-add".into(),
            "CHOWN".into(),
            "--cap-add".into(),
            "DAC_OVERRIDE".into(),
            "--cap-add".into(),
            "FOWNER".into(),
            "--cap-add".into(),
            "SYS_CHROOT".into(),
            self.config.builder_image_id.clone(),
            format!(
                "--dockerfile=/workspace/{}/{}",
                request.context_relative, request.dockerfile_relative
            ),
            format!("--context=dir:///workspace/{}", request.context_relative),
            "--cache=true".into(),
            "--cache-dir=/cache".into(),
            "--cache-run-layers=false".into(),
            "--cache-copy-layers=false".into(),
            "--no-push".into(),
            "--no-push-cache".into(),
            "--tar-path=/out/candidate.tar".into(),
            format!("--destination={}", request.destination),
            "--force".into(),
            "--log-format=text".into(),
        ]);
        self.control
            .create_owned_container(
                OwnedContainerCreate {
                    owner: owner.clone(),
                    name: name.clone(),
                    arguments,
                    mounts: vec![
                        owned_mount(
                            &request.context_root,
                            "/workspace",
                            true,
                            OwnedMountClass::ProjectedContext,
                        )?,
                        owned_mount(
                            &self.config.offline_cache_root,
                            "/cache",
                            true,
                            OwnedMountClass::OfflineCache,
                        )?,
                        owned_mount(
                            request
                                .output_archive
                                .parent()
                                .ok_or_else(|| infrastructure(TrialRelayFailure::InvalidRequest))?,
                            "/out",
                            false,
                            OwnedMountClass::CandidateOutput,
                        )?,
                    ],
                },
                deadline,
                invocation_cancelled,
                relay_cancelled,
            )
            .map_err(runtime_failure)?;
        let observed = self
            .control
            .run_owned_container(
                &owner,
                &name,
                &[request.output_archive.parent().unwrap().to_owned()],
                &self.limits(
                    &request.resources,
                    request.timeout_ms,
                    request.maximum_output_bytes,
                    &request.enforcement_overruns,
                    deadline,
                ),
                invocation_cancelled,
                relay_cancelled,
            )
            .map_err(runtime_failure)?;
        let mut observation = build_observation(observed)?;
        if observation.outcome == TrialOperationOutcome::Succeeded {
            let loaded = self
                .control
                .load_single_owned_image(
                    &owner,
                    &request.output_archive,
                    &request.destination,
                    self.config.maximum_candidate_archive_bytes,
                    deadline,
                )
                .map_err(runtime_failure)?;
            observation.candidate_image_digest = Some(loaded.config_image_id);
            observation.candidate_archive_digest = Some(loaded.archive_sha256);
            observation.written_bytes = observation.written_bytes.max(loaded.archive_byte_count);
        }
        Ok(SandboxBuildResult { observation })
    }

    fn run_step(
        &self,
        request: &SandboxStepRequest,
        operation_order: u32,
        deadline: Instant,
        invocation_cancelled: &AtomicBool,
        relay_cancelled: &AtomicBool,
    ) -> Result<SandboxStepResult, SandboxFailure> {
        let owner = self.owner(&request.owner_id);
        let slot_digest = Sha256::digest(request.slot_id.as_bytes());
        let slot_digest = format!("{slot_digest:x}");
        let name = format!("ws-trial-{}-{}", request.owner_id, &slot_digest[..16]);
        let mut arguments = self.common_create_arguments(&request.resources);
        let user = format!(
            "{}:{}",
            self.config.candidate_uid, self.config.candidate_gid
        );
        let working_directory = if request.working_directory == "." {
            "/work/state".to_owned()
        } else {
            format!("/work/state/{}", request.working_directory)
        };
        arguments.extend([
            "--read-only".into(),
            "--user".into(),
            user,
            "--workdir".into(),
            working_directory,
            "--tmpfs".into(),
            "/tmp:rw,noexec,nosuid,nodev,size=16777216".into(),
        ]);
        let mut mounts = vec![owned_mount(
            &request.workspace_root,
            "/work/state",
            false,
            OwnedMountClass::TrialState,
        )?];
        for (role, path) in &request.visible_roles {
            mounts.push(owned_mount(
                path,
                &format!("/work/input/{role}"),
                true,
                OwnedMountClass::VerifiedMaterial,
            )?);
        }
        arguments.extend([
            "--entrypoint".into(),
            request.command[0].clone(),
            request.candidate_image_digest.clone(),
        ]);
        arguments.extend(request.command.iter().skip(1).cloned());
        self.control
            .create_owned_container(
                OwnedContainerCreate {
                    owner: owner.clone(),
                    name: name.clone(),
                    arguments,
                    mounts,
                },
                deadline,
                invocation_cancelled,
                relay_cancelled,
            )
            .map_err(runtime_failure)?;
        let observed = self
            .control
            .run_owned_container(
                &owner,
                &name,
                std::slice::from_ref(&request.workspace_root),
                &self.limits(
                    &request.resources,
                    request.timeout_ms,
                    request.maximum_output_bytes,
                    &request.enforcement_overruns,
                    deadline,
                ),
                invocation_cancelled,
                relay_cancelled,
            )
            .map_err(runtime_failure)?;
        Ok(SandboxStepResult {
            observation: step_observation(request, operation_order, observed)?,
        })
    }

    fn cleanup(&self, owner_id: &str, deadline: Instant) -> Result<(), SandboxFailure> {
        self.control
            .cleanup_owner(&self.owner(owner_id), deadline)
            .map_err(runtime_failure)
    }
}

fn build_observation(
    value: ObservedContainerExit,
) -> Result<TrialBuildObservation, SandboxFailure> {
    let outcome = operation_outcome(&value)?;
    Ok(TrialBuildObservation {
        outcome,
        exit_code: value.exit_code,
        signal: value.signal,
        stdout_sha256: sha256_text(&value.stdout),
        stderr_sha256: sha256_text(&value.stderr),
        stdout: value.stdout,
        stderr: value.stderr,
        candidate_image_digest: None,
        candidate_archive_digest: None,
        elapsed_ms: value.elapsed_ms,
        cpu_time_ms: value.cpu_time_ms,
        peak_memory_bytes: value.peak_memory_bytes,
        peak_pids: value.peak_pids,
        written_bytes: value.written_bytes,
        written_entries: value.written_entries,
        measurement_method: value.measurement_method,
    })
}

fn step_observation(
    request: &SandboxStepRequest,
    order: u32,
    value: ObservedContainerExit,
) -> Result<TrialStepObservation, SandboxFailure> {
    let outcome = operation_outcome(&value)?;
    Ok(TrialStepObservation {
        slot_id: request.slot_id.clone(),
        operation_order: order,
        workspace_identity: format!("workspace_{}", request.slot_id),
        visible_role_inventory_digests: request.visible_role_inventory_digests.clone(),
        outcome,
        exit_code: value.exit_code,
        signal: value.signal,
        stdout_sha256: sha256_text(&value.stdout),
        stderr_sha256: sha256_text(&value.stderr),
        stdout: value.stdout,
        stderr: value.stderr,
        workspace_before_sha256: value
            .workspace_before_sha256
            .ok_or_else(|| infrastructure(TrialRelayFailure::ImplementationUnavailable))?,
        workspace_after_sha256: value
            .workspace_after_sha256
            .ok_or_else(|| infrastructure(TrialRelayFailure::ImplementationUnavailable))?,
        elapsed_ms: value.elapsed_ms,
        cpu_time_ms: value.cpu_time_ms,
        peak_memory_bytes: value.peak_memory_bytes,
        peak_pids: value.peak_pids,
        written_bytes: value.written_bytes,
        written_entries: value.written_entries,
        measurement_method: value.measurement_method,
    })
}

fn operation_outcome(
    value: &ObservedContainerExit,
) -> Result<TrialOperationOutcome, SandboxFailure> {
    let outcome = match value.termination {
        RuntimeTermination::Exited if value.exit_code == Some(0) && value.signal.is_none() => {
            TrialOperationOutcome::Succeeded
        }
        RuntimeTermination::Exited if value.exit_code.is_some_and(|code| code != 0) => {
            TrialOperationOutcome::ExitNonzero
        }
        RuntimeTermination::Signalled => TrialOperationOutcome::Signalled,
        RuntimeTermination::DeadlineExceeded => TrialOperationOutcome::DeadlineExceeded,
        RuntimeTermination::CpuExceeded => TrialOperationOutcome::CpuExceeded,
        RuntimeTermination::MemoryExceeded => TrialOperationOutcome::MemoryExceeded,
        RuntimeTermination::PidExceeded => TrialOperationOutcome::PidExceeded,
        RuntimeTermination::DiskExceeded => TrialOperationOutcome::DiskExceeded,
        RuntimeTermination::OutputExceeded => TrialOperationOutcome::OutputExceeded,
        _ => return Err(infrastructure(TrialRelayFailure::ImplementationUnavailable)),
    };
    Ok(outcome)
}

fn owned_mount(
    source: &std::path::Path,
    destination: &str,
    readonly: bool,
    class: OwnedMountClass,
) -> Result<OwnedBindMount, SandboxFailure> {
    let source_text = source
        .to_str()
        .filter(|value| value.starts_with('/') && !value.contains(',') && !value.contains('\n'))
        .ok_or_else(|| infrastructure(TrialRelayFailure::InvalidRequest))?;
    if source_text.contains('\r')
        || !destination.starts_with('/')
        || destination.contains(',')
        || destination.contains('\n')
        || destination.contains('\r')
    {
        return Err(infrastructure(TrialRelayFailure::InvalidRequest));
    }
    Ok(OwnedBindMount {
        source: source.to_owned(),
        destination: destination.to_owned(),
        readonly,
        class,
    })
}

fn runtime_failure(value: RuntimeControlFailure) -> SandboxFailure {
    #[cfg(test)]
    eprintln!("trial runtime control failure: {value:?}");
    match value {
        RuntimeControlFailure::DeadlineExceeded => {
            infrastructure(TrialRelayFailure::DeadlineExceeded)
        }
        RuntimeControlFailure::Cancelled => infrastructure(TrialRelayFailure::Cancelled),
        RuntimeControlFailure::CapacityExceeded => {
            infrastructure(TrialRelayFailure::CapacityExceeded)
        }
        RuntimeControlFailure::CleanupUnsettled => SandboxFailure {
            code: TrialRelayFailure::CleanupUnsettled,
            cleanup_unsettled: true,
        },
        _ => infrastructure(TrialRelayFailure::ImplementationUnavailable),
    }
}

fn infrastructure(code: TrialRelayFailure) -> SandboxFailure {
    SandboxFailure {
        code,
        cleanup_unsettled: false,
    }
}

fn valid_sha256(value: &str) -> bool {
    value.len() == 71
        && value.starts_with("sha256:")
        && value[7..]
            .bytes()
            .all(|item| item.is_ascii_digit() || (b'a'..=b'f').contains(&item))
}

fn sha256_text(value: &str) -> String {
    format!("sha256:{:x}", Sha256::digest(value.as_bytes()))
}
