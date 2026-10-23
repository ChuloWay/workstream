//! Trusted immutable trial authority resolved from flat locked-policy selectors.

use crate::trial_relay::{valid_profile, valid_sha256, valid_uuid, TrialProfile};
use serde::Deserialize;
use serde_json::Value;
use std::collections::HashSet;
use workstream_checker_sdk::{canonical_hash, ValidatedRequest};

const MANIFEST_PROTOCOL: &str = "workstream.trial_authority_manifest.v1";
const MAXIMUM_MANIFEST_BYTES: usize = 4 * 1024 * 1024;

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct TrialAuthorityManifest {
    protocol_version: String,
    entries: Vec<TrialProfile>,
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
        let mut selectors = HashSet::new();
        let mut bindings = HashSet::new();
        for profile in &manifest.entries {
            let selector = selector_from_profile(profile);
            if !valid_profile(profile)
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
        }
        Ok(Self {
            entries: manifest.entries,
        })
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
    }
}
