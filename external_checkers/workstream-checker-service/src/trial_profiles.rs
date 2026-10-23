//! Trusted immutable trial authority resolved from flat locked-policy selectors.

use crate::trial_relay::{
    valid_profile, valid_sha256, valid_uuid, TrialMaterialProjectionProfile, TrialProfile,
    TrialSlotProfile,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashSet;
use workstream_checker_sdk::{canonical_hash, ValidatedRequest};

const MANIFEST_PROTOCOL: &str = "workstream.trial_authority_manifest.v1";
const MAXIMUM_MANIFEST_BYTES: usize = 4 * 1024 * 1024;

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct TrialAuthorityManifest {
    protocol_version: String,
    entries: Vec<TrialAuthorityEntry>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct TrialAuthorityEntry {
    registry_entry_id: String,
    registry_entry_digest: String,
    checker_image_digest: String,
    configuration_sha256: String,
    profile: RuntimeProfile,
    projection: ExecutionProjection,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct RuntimeProfile {
    schema_version: String,
    selector: ProfileSelector,
    runtime: String,
    isolation_mode: String,
    outer_host_uds: String,
    child_host_uds: String,
    outer_runtime_config_digest: String,
    child_runtime_config_digest: String,
    engine_identity_digest: String,
    platform: String,
    platform_identity_digest: String,
    builder_image_digest: String,
    offline_cache_digest: String,
    approved_base_digests: Vec<String>,
    permitted_source_roles: Vec<String>,
    permitted_material_roles: Vec<String>,
    permitted_operations: Vec<String>,
    permitted_state_retention_outcomes: Vec<String>,
    builder_capabilities: Vec<String>,
    child_capabilities: Vec<String>,
    child_network: String,
    child_runs_as_non_root: bool,
    limits: RuntimeLimits,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct ProfileSelector {
    profile_id: String,
    profile_version: u32,
    profile_digest: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct RuntimeLimits {
    maximum_total_timeout_ms: u64,
    maximum_build_timeout_ms: u64,
    maximum_step_timeout_ms: u64,
    maximum_steps: usize,
    maximum_cpu_quota_millis: u64,
    maximum_cpu_time_ms: u64,
    maximum_wall_time_overrun_ms: u64,
    maximum_cpu_time_overrun_ms: u64,
    maximum_memory_bytes: u64,
    maximum_swap_bytes: u64,
    maximum_memory_overrun_bytes: u64,
    maximum_pids: u64,
    maximum_pids_overrun: u64,
    maximum_disk_bytes: u64,
    maximum_disk_overrun_bytes: u64,
    maximum_entries: u64,
    maximum_entries_overrun: u64,
    maximum_step_output_bytes: usize,
    maximum_observation_bytes: usize,
    maximum_receipt_bytes: usize,
    maximum_frame_bytes: usize,
    maximum_response_bytes: usize,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct ExecutionProjection {
    selector: ProjectionSelector,
    trial_kind: String,
    material_projections: Vec<TrialMaterialProjectionProfile>,
    allowed_material_roles: Vec<String>,
    build_context_roles: Vec<String>,
    slot_templates: Vec<TrialSlotProfile>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct ProjectionSelector {
    projection_id: String,
    projection_version: u32,
    projection_digest: String,
}

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
struct Selector {
    profile_id: String,
    profile_version: u32,
    profile_digest: String,
    projection_id: String,
    projection_version: u32,
    projection_digest: String,
}

impl TrialAuthorityEntry {
    fn into_profile(self) -> Result<TrialProfile, &'static str> {
        let profile_digest = payload_digest(&self.profile, "profile_digest")?;
        let projection_digest = payload_digest(&self.projection, "projection_digest")?;
        let limits = self.profile.limits.clone();
        if self.profile.schema_version != "workstream.trial_execution_profile.v1"
            || self.profile.runtime != "runsc"
            || self.profile.isolation_mode != "gvisor"
            || self.profile.outer_host_uds != "open"
            || self.profile.child_host_uds != "none"
            || self.profile.child_network != "none"
            || !self.profile.child_runs_as_non_root
            || self.profile.builder_capabilities
                != ["CHOWN", "DAC_OVERRIDE", "FOWNER", "SYS_CHROOT"]
            || !self.profile.child_capabilities.is_empty()
            || self.profile.permitted_operations != ["run"]
            || profile_digest != self.profile.selector.profile_digest
            || projection_digest != self.projection.selector.projection_digest
            || limits.maximum_memory_bytes != limits.maximum_swap_bytes
            || limits.maximum_build_timeout_ms > limits.maximum_total_timeout_ms
            || limits.maximum_step_timeout_ms > limits.maximum_total_timeout_ms
            || limits.maximum_receipt_bytes > 1024 * 1024
            || self.profile.permitted_material_roles.is_empty()
            || self.profile.permitted_source_roles.is_empty()
            || self.profile.permitted_state_retention_outcomes.is_empty()
            || !self
                .projection
                .allowed_material_roles
                .iter()
                .all(|role| self.profile.permitted_material_roles.contains(role))
            || !self.projection.material_projections.iter().all(|material| {
                self.profile
                    .permitted_source_roles
                    .contains(&material.source_role)
            })
            || !self.projection.slot_templates.iter().all(|slot| {
                slot.retain_state_after.iter().all(|outcome| {
                    self.profile
                        .permitted_state_retention_outcomes
                        .contains(outcome)
                })
            })
            || !valid_uuid(&self.registry_entry_id)
            || !valid_sha256(&self.registry_entry_digest)
            || !valid_sha256(&self.checker_image_digest)
            || !valid_sha256(&self.configuration_sha256)
            || !valid_sha256(&self.profile.outer_runtime_config_digest)
        {
            return Err("trial authority manifest entry invalid");
        }
        Ok(TrialProfile {
            profile_id: self.profile.selector.profile_id,
            profile_version: self.profile.selector.profile_version,
            profile_digest: self.profile.selector.profile_digest,
            projection_id: self.projection.selector.projection_id,
            projection_version: self.projection.selector.projection_version,
            projection_digest: self.projection.selector.projection_digest,
            trial_kind: self.projection.trial_kind,
            registry_entry_id: self.registry_entry_id,
            registry_entry_digest: self.registry_entry_digest,
            checker_image_digest: self.checker_image_digest,
            configuration_sha256: self.configuration_sha256,
            engine_identity_digest: self.profile.engine_identity_digest,
            child_runtime: self.profile.runtime,
            child_runtime_config_digest: self.profile.child_runtime_config_digest,
            child_host_uds: self.profile.child_host_uds,
            platform: self.profile.platform,
            platform_identity_digest: self.profile.platform_identity_digest,
            builder_image_digest: self.profile.builder_image_digest,
            offline_cache_digest: self.profile.offline_cache_digest,
            approved_base_digests: self.profile.approved_base_digests,
            source_material_roles: self.profile.permitted_source_roles,
            material_projections: self.projection.material_projections,
            build_context_roles: self.projection.build_context_roles,
            allowed_material_roles: self.projection.allowed_material_roles,
            slot_templates: self.projection.slot_templates,
            maximum_frame_bytes: limits.maximum_frame_bytes,
            maximum_response_bytes: limits.maximum_response_bytes,
            maximum_steps: limits.maximum_steps,
            maximum_build_timeout_ms: limits.maximum_build_timeout_ms,
            maximum_step_timeout_ms: limits.maximum_step_timeout_ms,
            maximum_step_output_bytes: limits.maximum_step_output_bytes,
            maximum_observation_bytes: limits.maximum_observation_bytes,
            maximum_receipt_bytes: limits.maximum_receipt_bytes,
            maximum_cpu_quota_millis: limits.maximum_cpu_quota_millis,
            maximum_cpu_time_ms: limits.maximum_cpu_time_ms,
            maximum_wall_time_overrun_ms: limits.maximum_wall_time_overrun_ms,
            maximum_cpu_time_overrun_ms: limits.maximum_cpu_time_overrun_ms,
            maximum_memory_bytes: limits.maximum_memory_bytes,
            maximum_memory_overrun_bytes: limits.maximum_memory_overrun_bytes,
            maximum_disk_bytes: limits.maximum_disk_bytes,
            maximum_disk_overrun_bytes: limits.maximum_disk_overrun_bytes,
            maximum_entries: limits.maximum_entries,
            maximum_entries_overrun: limits.maximum_entries_overrun,
            maximum_pids: limits.maximum_pids,
            maximum_pids_overrun: limits.maximum_pids_overrun,
        })
    }
}

fn payload_digest<T: Serialize>(value: &T, digest_key: &str) -> Result<String, &'static str> {
    let mut value = serde_json::to_value(value).map_err(|_| "trial authority manifest invalid")?;
    value
        .get_mut("selector")
        .and_then(Value::as_object_mut)
        .and_then(|selector| selector.remove(digest_key))
        .ok_or("trial authority manifest invalid")?;
    canonical_hash(&value).map_err(|_| "trial authority manifest invalid")
}

#[derive(Debug)]
pub(crate) struct TrialProfileCatalog {
    entries: Vec<TrialProfile>,
}

impl TrialProfileCatalog {
    pub(crate) fn from_bytes(bytes: &[u8], expected_digest: &str) -> Result<Self, &'static str> {
        if bytes.is_empty()
            || bytes.len() > MAXIMUM_MANIFEST_BYTES
            || !valid_sha256(expected_digest)
        {
            return Err("trial authority manifest invalid");
        }
        let value: Value =
            serde_json::from_slice(bytes).map_err(|_| "trial authority manifest invalid")?;
        if canonical_hash(&value).map_err(|_| "trial authority manifest invalid")?
            != expected_digest
        {
            return Err("trial authority manifest digest differs");
        }
        let manifest: TrialAuthorityManifest =
            serde_json::from_value(value).map_err(|_| "trial authority manifest invalid")?;
        if manifest.protocol_version != MANIFEST_PROTOCOL || manifest.entries.is_empty() {
            return Err("trial authority manifest invalid");
        }
        let mut entries = Vec::with_capacity(manifest.entries.len());
        let mut selectors = HashSet::new();
        let mut bindings = HashSet::new();
        for entry in manifest.entries {
            let profile = entry.into_profile()?;
            let selector = selector_from_profile(&profile);
            if !valid_profile(&profile)
                || !selectors.insert(selector)
                || !bindings.insert((
                    profile.registry_entry_id.clone(),
                    profile.registry_entry_digest.clone(),
                    profile.checker_image_digest.clone(),
                    profile.configuration_sha256.clone(),
                ))
            {
                return Err("trial authority manifest entry invalid");
            }
            entries.push(profile);
        }
        Ok(Self { entries })
    }

    pub(crate) fn resolve(
        &self,
        request: &ValidatedRequest,
    ) -> Result<Option<&TrialProfile>, &'static str> {
        let configuration = request
            .value
            .get("configuration")
            .and_then(Value::as_object)
            .ok_or("trial selectors invalid")?;
        let selected = selector_from_configuration(configuration)?;
        let Some(selected) = selected else {
            return Ok(None);
        };
        if request.phase != "post_submit" {
            return Err("trial selectors outside POST");
        }
        let matches = self
            .entries
            .iter()
            .filter(|profile| {
                selector_from_profile(profile) == selected
                    && profile.registry_entry_id == request.registry_entry_id
                    && profile.registry_entry_digest == request.registry_entry_digest
                    && profile.checker_image_digest == request.image_digest
                    && profile.configuration_sha256 == request.configuration_digest
            })
            .collect::<Vec<_>>();
        match matches.as_slice() {
            [profile] => Ok(Some(*profile)),
            _ => Err("trial authority unavailable"),
        }
    }
}

fn selector_from_profile(profile: &TrialProfile) -> Selector {
    Selector {
        profile_id: profile.profile_id.clone(),
        profile_version: profile.profile_version,
        profile_digest: profile.profile_digest.clone(),
        projection_id: profile.projection_id.clone(),
        projection_version: profile.projection_version,
        projection_digest: profile.projection_digest.clone(),
    }
}

fn selector_from_configuration(
    configuration: &serde_json::Map<String, Value>,
) -> Result<Option<Selector>, &'static str> {
    const KEYS: [&str; 6] = [
        "trial_profile_id",
        "trial_profile_version",
        "trial_profile_digest",
        "trial_projection_id",
        "trial_projection_version",
        "trial_projection_digest",
    ];
    let present = KEYS
        .iter()
        .filter(|key| configuration.contains_key(**key))
        .count();
    if configuration
        .keys()
        .any(|key| key.starts_with("trial_") && !KEYS.contains(&key.as_str()))
    {
        return Err("trial selectors invalid");
    }
    if present == 0 {
        return if configuration.contains_key("trial_execution") {
            Err("nested trial authority forbidden")
        } else {
            Ok(None)
        };
    }
    if present != KEYS.len() || configuration.contains_key("trial_execution") {
        return Err("trial selectors incomplete");
    }
    let string = |key| {
        configuration
            .get(key)
            .and_then(Value::as_str)
            .map(str::to_owned)
            .ok_or("trial selector invalid")
    };
    let version = |key| {
        configuration
            .get(key)
            .and_then(Value::as_u64)
            .and_then(|value| u32::try_from(value).ok())
            .filter(|value| *value > 0)
            .ok_or("trial selector invalid")
    };
    let selector = Selector {
        profile_id: string("trial_profile_id")?,
        profile_version: version("trial_profile_version")?,
        profile_digest: string("trial_profile_digest")?,
        projection_id: string("trial_projection_id")?,
        projection_version: version("trial_projection_version")?,
        projection_digest: string("trial_projection_digest")?,
    };
    if !valid_uuid(&selector.profile_id)
        || !valid_sha256(&selector.profile_digest)
        || !valid_uuid(&selector.projection_id)
        || !valid_sha256(&selector.projection_digest)
    {
        return Err("trial selector invalid");
    }
    Ok(Some(selector))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn flat_selector_parser_rejects_partial_nested_and_wrong_types() {
        let mut value = serde_json::json!({});
        assert_eq!(
            selector_from_configuration(value.as_object().unwrap()),
            Ok(None)
        );
        value["trial_profile_id"] = Value::String("018f6f49-66b8-7d2a-bf4d-0e2eeaa00001".into());
        assert_eq!(
            selector_from_configuration(value.as_object().unwrap()),
            Err("trial selectors incomplete")
        );
        value = serde_json::json!({"trial_execution": {}});
        assert_eq!(
            selector_from_configuration(value.as_object().unwrap()),
            Err("nested trial authority forbidden")
        );
        value = serde_json::json!({"trial_future_authority": "forbidden"});
        assert_eq!(
            selector_from_configuration(value.as_object().unwrap()),
            Err("trial selectors invalid")
        );
    }
}
