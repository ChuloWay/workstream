//! Digest-bound Docker/runsc backend for the generic trial engine.

use crate::trial_engine::{
    SandboxBackendIdentity, SandboxBuildRequest, SandboxBuildResult, SandboxEnforcementOverruns,
    SandboxFailure, SandboxStepRequest, SandboxStepResult, TrialSandboxBackend,
};
use crate::trial_relay::{
    TrialBuildObservation, TrialOperationOutcome, TrialRelayFailure, TrialStepObservation,
};
use sha2::{Digest, Sha256};
use std::path::PathBuf;
use std::sync::atomic::AtomicBool;
use std::time::Instant;

#[derive(Clone, Debug, PartialEq, Eq)]
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
        platform_identity_digest: &str,
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
                &self.config.identity.platform_identity_digest,
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
        let name = format!("ws-trial-{}-{}", request.owner_id, request.slot_id);
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
