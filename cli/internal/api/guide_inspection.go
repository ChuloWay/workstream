package api

import (
	"context"
	"encoding/json"
	jsonv2 "encoding/json/v2"
	"errors"
	"math/big"
	"net/http"
	"net/url"
	"strings"
)

// These two historical collections are server-capped at the newest 100 rows.
// They have no cursor contract; older known IDs use the exact show operation.
const maxGuideInspectionBytes = 16 * 1024 * 1024

type inspectionObject map[string]json.RawMessage

func inspectObject(raw json.RawMessage, required []string, nullable ...[]string) (inspectionObject, bool) {
	var fields inspectionObject
	if jsonv2.Unmarshal(raw, &fields) != nil || fields == nil {
		return nil, false
	}
	allowed := make(map[string]bool, len(required))
	for _, key := range required {
		allowed[key] = true
		value, found := fields[key]
		if !found || string(value) == "null" {
			return nil, false
		}
	}
	if len(nullable) > 0 {
		for _, key := range nullable[0] {
			allowed[key] = true
			if _, found := fields[key]; !found {
				return nil, false
			}
		}
	}
	for key := range fields {
		if !allowed[key] {
			return nil, false
		}
	}
	return fields, true
}

func inspectString(fields inspectionObject, name string) (string, bool) {
	var value string
	if json.Unmarshal(fields[name], &value) != nil {
		return "", false
	}
	return value, strings.TrimSpace(value) != ""
}

func inspectNonblank(fields inspectionObject, name string) bool {
	_, valid := inspectString(fields, name)
	return valid
}

func inspectID(fields inspectionObject, name string) (string, bool) {
	value, valid := inspectString(fields, name)
	return value, valid && validUUID(value)
}

func inspectOptionalID(fields inspectionObject, name string) bool {
	if string(fields[name]) == "null" {
		return true
	}
	_, valid := inspectID(fields, name)
	return valid
}

func inspectHash(fields inspectionObject, name string) (string, bool) {
	value, valid := inspectString(fields, name)
	return value, valid && policyHash.MatchString(value)
}

func inspectOptionalHash(fields inspectionObject, name string) bool {
	if string(fields[name]) == "null" {
		return true
	}
	_, valid := inspectHash(fields, name)
	return valid
}

func inspectTime(fields inspectionObject, name string) bool {
	value, valid := inspectString(fields, name)
	return valid && validTime(value)
}

func inspectOptionalTime(fields inspectionObject, name string) bool {
	return string(fields[name]) == "null" || inspectTime(fields, name)
}

func inspectInteger(fields inspectionObject, name string, minimum int64) bool {
	value, ok := new(big.Int).SetString(string(fields[name]), 10)
	return ok && value.Cmp(big.NewInt(minimum)) >= 0
}

func inspectOptionalInteger(fields inspectionObject, name string, minimum int64) bool {
	return string(fields[name]) == "null" || inspectInteger(fields, name, minimum)
}

func inspectBool(fields inspectionObject, name string) bool {
	var value bool
	return (string(fields[name]) == "true" || string(fields[name]) == "false") && json.Unmarshal(fields[name], &value) == nil
}

func inspectArray(fields inspectionObject, name string, max int) ([]json.RawMessage, bool) {
	var entries []json.RawMessage
	if json.Unmarshal(fields[name], &entries) != nil {
		return nil, false
	}
	return entries, entries != nil && len(entries) <= max
}

func inspectStringArray(fields inspectionObject, name string) bool {
	entries, valid := inspectArray(fields, name, maxGuideInspectionBytes)
	if !valid {
		return false
	}
	for _, entry := range entries {
		var item string
		if string(entry) == "null" || json.Unmarshal(entry, &item) != nil {
			return false
		}
	}
	return true
}

func inspectLiteralArray(fields inspectionObject, name string, max int, allowed ...string) bool {
	entries, valid := inspectArray(fields, name, max)
	if !valid || len(entries) == 0 {
		return false
	}
	for _, entry := range entries {
		var item string
		if json.Unmarshal(entry, &item) != nil || !oneOf(item, allowed...) {
			return false
		}
	}
	return true
}

func inspectLiteral(fields inspectionObject, name string, allowed ...string) bool {
	value, valid := inspectString(fields, name)
	return valid && oneOf(value, allowed...)
}

func inspectDictionary(fields inspectionObject, name string) bool {
	var value map[string]json.RawMessage
	return jsonv2.Unmarshal(fields[name], &value) == nil && value != nil
}

func inspectGuideLink(fields inspectionObject, project, guide string) (string, string, bool) {
	projectID, projectOK := inspectID(fields, "project_id")
	guideID, guideOK := inspectID(fields, "guide_id")
	version, versionOK := inspectString(fields, "guide_version")
	return version, projectID, projectOK && guideOK && versionOK && sameUUID(projectID, project) && sameUUID(guideID, guide)
}

func inspectSnapshotLink(fields inspectionObject) (string, string, bool) {
	id, idOK := inspectID(fields, "source_snapshot_id")
	hash, hashOK := inspectHash(fields, "source_snapshot_hash")
	return id, hash, idOK && hashOK
}

func validateSufficiency(raw json.RawMessage, project, guide, selected string) (inspectionObject, bool) {
	fields, ok := inspectObject(raw, []string{"id", "project_id", "guide_id", "guide_version", "source_snapshot_id", "source_snapshot_hash", "status", "findings", "created_by", "created_at"}, []string{"summary", "agent_name", "agent_version", "project_setup_run_id", "setup_generation", "agent_material_sha256", "agent_material_byte_count", "warnings_acknowledged_by_role", "warnings_acknowledged_by_actor", "warnings_acknowledged_at", "acknowledgement_note"})
	if !ok {
		return nil, false
	}
	id, idOK := inspectID(fields, "id")
	_, _, linkOK := inspectGuideLink(fields, project, guide)
	_, _, snapshotOK := inspectSnapshotLink(fields)
	status, statusOK := inspectString(fields, "status")
	findings, findingsOK := inspectArray(fields, "findings", 100)
	for _, finding := range findings {
		var item map[string]json.RawMessage
		if json.Unmarshal(finding, &item) != nil || item == nil {
			findingsOK = false
		}
	}
	return fields, idOK && (selected == "" || sameUUID(id, selected)) && linkOK && snapshotOK && statusOK && oneOf(status, "passed", "blocked", "passed_with_warnings") && findingsOK && inspectStringValue(fields, "created_by") && inspectTime(fields, "created_at") && inspectOptionalStringOrNull(fields, "summary", "agent_name", "agent_version", "warnings_acknowledged_by_role", "warnings_acknowledged_by_actor", "acknowledgement_note") && inspectOptionalID(fields, "project_setup_run_id") && inspectOptionalInteger(fields, "setup_generation", 1) && inspectOptionalHash(fields, "agent_material_sha256") && inspectOptionalInteger(fields, "agent_material_byte_count", 0) && inspectOptionalTime(fields, "warnings_acknowledged_at")
}

func inspectStringValue(fields inspectionObject, name string) bool {
	var value string
	return string(fields[name]) != "null" && json.Unmarshal(fields[name], &value) == nil
}

func inspectOptionalStringOrNull(fields inspectionObject, names ...string) bool {
	for _, name := range names {
		if string(fields[name]) != "null" && !inspectStringValue(fields, name) {
			return false
		}
	}
	return true
}

func validateArtifactPolicy(raw json.RawMessage, project, guide, selected string) (inspectionObject, bool) {
	fields, ok := inspectObject(raw, []string{"id", "project_id", "guide_id", "guide_version", "source_snapshot_id", "source_snapshot_hash", "policy_version", "lifecycle_status", "policy_body", "policy_hash", "derivation_source", "source_material_refs", "created_by", "created_at", "updated_at"}, []string{"derivation_agent_name", "derivation_agent_version", "approved_by_role", "approved_by_actor", "approved_at", "supersedes_policy_id", "superseded_at", "change_summary"})
	if !ok {
		return nil, false
	}
	id, idOK := inspectID(fields, "id")
	_, _, linkOK := inspectGuideLink(fields, project, guide)
	_, _, snapshotOK := inspectSnapshotLink(fields)
	status, statusOK := inspectString(fields, "lifecycle_status")
	return fields, idOK && (selected == "" || sameUUID(id, selected)) && linkOK && snapshotOK && inspectStringValue(fields, "policy_version") && statusOK && oneOf(status, "draft", "approved", "superseded") && inspectDictionary(fields, "policy_body") && inspectHashValue(fields, "policy_hash") && inspectStringValue(fields, "derivation_source") && inspectStringArray(fields, "source_material_refs") && inspectStringValue(fields, "created_by") && inspectTime(fields, "created_at") && inspectTime(fields, "updated_at") && inspectOptionalStringOrNull(fields, "derivation_agent_name", "derivation_agent_version", "approved_by_role", "approved_by_actor", "change_summary") && inspectOptionalTime(fields, "approved_at") && inspectOptionalID(fields, "supersedes_policy_id") && inspectOptionalTime(fields, "superseded_at")
}

func inspectHashValue(fields inspectionObject, name string) bool {
	_, ok := inspectHash(fields, name)
	return ok
}

func validateEffectivePolicy(raw json.RawMessage, project, guide string) (inspectionObject, bool) {
	fields, ok := inspectObject(raw, []string{"id", "project_id", "guide_id", "guide_version", "source_snapshot_id", "source_snapshot_hash", "submission_artifact_policy_id", "submission_artifact_policy_hash", "lifecycle_status", "merge_algorithm_version", "effective_policy", "effective_policy_hash", "created_by", "created_at"}, []string{"supersedes_effective_policy_id", "superseded_at"})
	if !ok {
		return nil, false
	}
	_, idOK := inspectID(fields, "id")
	_, _, linkOK := inspectGuideLink(fields, project, guide)
	_, _, snapshotOK := inspectSnapshotLink(fields)
	status, statusOK := inspectString(fields, "lifecycle_status")
	_, submissionOK := inspectID(fields, "submission_artifact_policy_id")
	return fields, idOK && linkOK && snapshotOK && submissionOK && inspectHashValue(fields, "submission_artifact_policy_hash") && statusOK && status == "approved" && inspectStringValue(fields, "merge_algorithm_version") && inspectDictionary(fields, "effective_policy") && inspectHashValue(fields, "effective_policy_hash") && inspectStringValue(fields, "created_by") && inspectTime(fields, "created_at") && inspectOptionalID(fields, "supersedes_effective_policy_id") && inspectOptionalTime(fields, "superseded_at")
}

func validatePreSubmitPolicy(raw json.RawMessage, project, guide string, active bool) (inspectionObject, bool) {
	mandatory := []string{"id", "project_id", "guide_id", "guide_version", "source_snapshot_id", "source_snapshot_hash", "effective_policy_id", "effective_policy_hash", "lifecycle_status", "checker_names", "created_by", "created_at"}
	optional := []string{"compiler_version", "compiled_bundle_hash", "supersedes_pre_submit_checker_policy_id", "superseded_at"}
	if active {
		mandatory = append(mandatory, "checker_configs")
	}
	fields, ok := inspectObject(raw, mandatory, optional)
	if !ok {
		return nil, false
	}
	_, idOK := inspectID(fields, "id")
	_, _, linkOK := inspectGuideLink(fields, project, guide)
	_, _, snapshotOK := inspectSnapshotLink(fields)
	_, effectiveOK := inspectID(fields, "effective_policy_id")
	status, statusOK := inspectString(fields, "lifecycle_status")
	return fields, idOK && linkOK && snapshotOK && effectiveOK && inspectHashValue(fields, "effective_policy_hash") && statusOK && status == "compiled" && inspectStringArray(fields, "checker_names") && inspectStringValue(fields, "created_by") && inspectTime(fields, "created_at") && inspectOptionalStringOrNull(fields, "compiler_version") && inspectHashValue(fields, "compiled_bundle_hash") && inspectOptionalID(fields, "supersedes_pre_submit_checker_policy_id") && inspectOptionalTime(fields, "superseded_at") && (!active || inspectDictionary(fields, "checker_configs"))
}

func validateActiveAssociated(raw json.RawMessage, name, project, guideVersion string) bool {
	var required, nullable []string
	switch name {
	case "post_submit_checker_policy":
		required = []string{"id", "project_id", "guide_version", "required_checkers", "warning_checkers", "blocking_severities", "lifecycle_status", "created_at"}
		nullable = []string{"policy_hash", "projection_operation_id", "approval_operation_id", "approved_at"}
	case "review_policy":
		required = []string{"id", "project_id", "guide_version", "policy_generation", "human_review_required", "semantics_format", "semantics_status", "requires_second_review", "allowed_decisions", "minimum_finding_fields", "created_at"}
		nullable = []string{"policy_hash", "supersedes_policy_id", "review_preference_window_seconds", "review_lease_duration_seconds", "max_active_review_leases_per_reviewer", "self_review_allowed", "reject_policy", "finding_evidence_requirement"}
	case "revision_policy":
		required = []string{"id", "project_id", "guide_version", "policy_generation", "semantics_status", "max_revision_rounds", "revision_deadline_hours", "allowed_resubmission_states", "created_at"}
		nullable = []string{"policy_hash", "supersedes_policy_id", "reviewer_reassignment_rule"}
	default:
		return false
	}
	entry, valid := inspectObject(raw, required, nullable)
	if !valid {
		return false
	}
	entryProject, projectOK := inspectID(entry, "project_id")
	entryVersion, versionOK := inspectString(entry, "guide_version")
	if _, idOK := inspectID(entry, "id"); !idOK || !projectOK || !sameUUID(entryProject, project) || !versionOK || entryVersion != guideVersion || !inspectTime(entry, "created_at") {
		return false
	}
	switch name {
	case "post_submit_checker_policy":
		status, statusOK := inspectString(entry, "lifecycle_status")
		return statusOK && status == "approved" && inspectStringArray(entry, "required_checkers") && inspectStringArray(entry, "warning_checkers") && inspectStringArray(entry, "blocking_severities") && inspectHashValue(entry, "policy_hash") && inspectIDValue(entry, "projection_operation_id") && inspectIDValue(entry, "approval_operation_id") && inspectTime(entry, "approved_at")
	case "review_policy":
		format, formatOK := inspectString(entry, "semantics_format")
		status, statusOK := inspectString(entry, "semantics_status")
		return inspectInteger(entry, "policy_generation", 1) && inspectHashValue(entry, "policy_hash") && inspectBool(entry, "human_review_required") && formatOK && oneOf(format, "v1", "v2") && (format != "v1" || string(entry["human_review_required"]) == "true") && statusOK && status == "complete" && inspectOptionalID(entry, "supersedes_policy_id") && inspectInteger(entry, "review_preference_window_seconds", 1) && inspectInteger(entry, "review_lease_duration_seconds", 1) && string(entry["max_active_review_leases_per_reviewer"]) == "1" && string(entry["self_review_allowed"]) == "false" && inspectLiteral(entry, "reject_policy", "close_task") && inspectLiteral(entry, "finding_evidence_requirement", "optional", "required_for_blocking", "required_for_all") && string(entry["requires_second_review"]) == "false" && inspectLiteralArray(entry, "allowed_decisions", maxGuideInspectionBytes, "accept", "needs_revision", "reject") && inspectStringArray(entry, "minimum_finding_fields")
	case "revision_policy":
		status, statusOK := inspectString(entry, "semantics_status")
		return inspectInteger(entry, "policy_generation", 1) && inspectHashValue(entry, "policy_hash") && statusOK && status == "complete" && inspectOptionalID(entry, "supersedes_policy_id") && inspectInteger(entry, "max_revision_rounds", 0) && inspectInteger(entry, "revision_deadline_hours", 1) && inspectLiteralArray(entry, "allowed_resubmission_states", 1, "needs_revision") && inspectOptionalStringOrNull(entry, "reviewer_reassignment_rule")
	}
	return false
}

func inspectIDValue(fields inspectionObject, name string) bool {
	_, valid := inspectID(fields, name)
	return valid
}

func guideInspectionPath(project, guide, suffix string) (string, error) {
	path, err := guidePath(project, guide)
	if err != nil {
		return "", err
	}
	return path + suffix, nil
}

func (c *Client) guideInspection(ctx context.Context, path string) (json.RawMessage, error) {
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet, path, "", nil, "", http.StatusOK, maxGuideInspectionBytes)
	if err != nil {
		return nil, err
	}
	if !c.safeMutationResponse(raw) {
		return nil, &Failure{Code: "invalid_api_response"}
	}
	return raw, nil
}

func (c *Client) GuideSufficiencyReports(ctx context.Context, project, guide string) (Result[json.RawMessage], error) {
	var result Result[json.RawMessage]
	path, err := guideInspectionPath(project, guide, "/sufficiency-reports")
	if err != nil {
		return result, err
	}
	raw, err := c.guideInspection(ctx, path)
	if err != nil {
		return result, err
	}
	var entries []json.RawMessage
	if json.Unmarshal(raw, &entries) != nil || entries == nil || len(entries) > 100 {
		return result, &Failure{Code: "invalid_api_response"}
	}
	seen := map[[16]byte]bool{}
	for _, entry := range entries {
		fields, ok := validateSufficiency(entry, project, guide, "")
		if !ok {
			return result, &Failure{Code: "invalid_api_response"}
		}
		id, _ := inspectID(fields, "id")
		key, _ := uuidIdentity(id)
		if seen[key] {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[key] = true
	}
	return Result[json.RawMessage]{Raw: raw, Value: raw}, nil
}

func (c *Client) GuideSufficiencyReport(ctx context.Context, project, guide, report string) (Result[json.RawMessage], error) {
	var result Result[json.RawMessage]
	if !validUUID(report) || len(report) > 100 {
		return result, errors.New("REPORT_ID must be a UUID")
	}
	path, err := guideInspectionPath(project, guide, "/sufficiency-reports/"+url.PathEscape(report))
	if err != nil {
		return result, err
	}
	raw, err := c.guideInspection(ctx, path)
	if err != nil {
		return result, err
	}
	if _, ok := validateSufficiency(raw, project, guide, report); !ok {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[json.RawMessage]{Raw: raw, Value: raw}, nil
}

func (c *Client) GuideArtifactPolicies(ctx context.Context, project, guide string) (Result[json.RawMessage], error) {
	var result Result[json.RawMessage]
	path, err := guideInspectionPath(project, guide, "/submission-artifact-policies")
	if err != nil {
		return result, err
	}
	raw, err := c.guideInspection(ctx, path)
	if err != nil {
		return result, err
	}
	var entries []json.RawMessage
	if json.Unmarshal(raw, &entries) != nil || entries == nil || len(entries) > 100 {
		return result, &Failure{Code: "invalid_api_response"}
	}
	seen := map[[16]byte]bool{}
	for _, entry := range entries {
		fields, ok := validateArtifactPolicy(entry, project, guide, "")
		if !ok {
			return result, &Failure{Code: "invalid_api_response"}
		}
		id, _ := inspectID(fields, "id")
		key, _ := uuidIdentity(id)
		if seen[key] {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[key] = true
	}
	return Result[json.RawMessage]{Raw: raw, Value: raw}, nil
}

func (c *Client) GuideArtifactPolicy(ctx context.Context, project, guide, policy string) (Result[json.RawMessage], error) {
	var result Result[json.RawMessage]
	if !validUUID(policy) || len(policy) > 100 {
		return result, errors.New("POLICY_ID must be a UUID")
	}
	path, err := guideInspectionPath(project, guide, "/submission-artifact-policies/"+url.PathEscape(policy))
	if err != nil {
		return result, err
	}
	raw, err := c.guideInspection(ctx, path)
	if err != nil {
		return result, err
	}
	if _, ok := validateArtifactPolicy(raw, project, guide, policy); !ok {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[json.RawMessage]{Raw: raw, Value: raw}, nil
}

func (c *Client) GuideEffectiveArtifactPolicy(ctx context.Context, project, guide string) (Result[json.RawMessage], error) {
	var result Result[json.RawMessage]
	path, err := guideInspectionPath(project, guide, "/effective-submission-artifact-policy")
	if err != nil {
		return result, err
	}
	raw, err := c.guideInspection(ctx, path)
	if err != nil {
		return result, err
	}
	if _, ok := validateEffectivePolicy(raw, project, guide); !ok {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[json.RawMessage]{Raw: raw, Value: raw}, nil
}

func (c *Client) GuidePreSubmitPolicy(ctx context.Context, project, guide string) (Result[json.RawMessage], error) {
	var result Result[json.RawMessage]
	path, err := guideInspectionPath(project, guide, "/pre-submit-checker-policy")
	if err != nil {
		return result, err
	}
	raw, err := c.guideInspection(ctx, path)
	if err != nil {
		return result, err
	}
	if _, ok := validatePreSubmitPolicy(raw, project, guide, false); !ok {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[json.RawMessage]{Raw: raw, Value: raw}, nil
}

// ActiveGuide is a current backend projection, not a local readiness calculation.
func (c *Client) ActiveGuide(ctx context.Context, project string) (Result[json.RawMessage], error) {
	var result Result[json.RawMessage]
	path, err := projectReadPath(project, "/active-guide")
	if err != nil {
		return result, err
	}
	raw, err := c.guideInspection(ctx, path)
	if err != nil {
		return result, err
	}
	fields, ok := inspectObject(raw, []string{"guide", "guide_source_snapshot", "guide_sufficiency_report", "submission_artifact_policy", "effective_submission_artifact_policy", "pre_submit_checker_policy", "post_submit_checker_policy", "review_policy", "revision_policy"})
	if !ok {
		return result, &Failure{Code: "invalid_api_response"}
	}
	guide, ok := inspectObject(fields["guide"], []string{"id", "project_id", "version", "status", "created_by", "created_at", "updated_at"}, []string{"change_summary", "task_examples", "task_examples_hash", "approved_by", "effective_at", "superseded_at", "contribution_policy_id", "contribution_policy_version_id", "activation_operation_id"})
	if !ok {
		return result, &Failure{Code: "invalid_api_response"}
	}
	guideID, idOK := inspectID(guide, "id")
	guideProject, projectOK := inspectID(guide, "project_id")
	guideVersion, versionOK := inspectString(guide, "version")
	status, statusOK := inspectString(guide, "status")
	if !idOK || !projectOK || !sameUUID(guideProject, project) || !versionOK || !statusOK || status != "active" || !inspectIDValue(guide, "activation_operation_id") || !inspectOptionalID(guide, "contribution_policy_id") || !inspectOptionalID(guide, "contribution_policy_version_id") || !inspectNonblank(guide, "approved_by") || !inspectTime(guide, "created_at") || !inspectTime(guide, "updated_at") || !inspectTime(guide, "effective_at") || !inspectOptionalTime(guide, "superseded_at") {
		return result, &Failure{Code: "invalid_api_response"}
	}
	snapshot, ok := inspectObject(fields["guide_source_snapshot"], []string{"id", "project_id", "guide_id", "guide_version", "manifest_schema_version", "manifest_json", "bundle_hash", "captured_by", "captured_at", "items"})
	if !ok {
		return result, &Failure{Code: "invalid_api_response"}
	}
	snapshotID, snapshotOK := inspectID(snapshot, "id")
	snapshotHash, hashOK := inspectHash(snapshot, "bundle_hash")
	snapshotVersion, _, snapshotLinkOK := inspectGuideLink(snapshot, project, guideID)
	items, itemsOK := inspectArray(snapshot, "items", 100)
	if !snapshotOK || !hashOK || !snapshotLinkOK || snapshotVersion != guideVersion || !itemsOK || !inspectDictionary(snapshot, "manifest_json") || !inspectStringValue(snapshot, "manifest_schema_version") || !inspectStringValue(snapshot, "captured_by") || !inspectTime(snapshot, "captured_at") {
		return result, &Failure{Code: "invalid_api_response"}
	}
	for _, item := range items {
		entry, valid := inspectObject(item, []string{"id", "source_snapshot_id", "item_order", "source_kind", "source_label", "ingestion_adapter", "created_at"}, []string{"media_type"})
		itemID, itemOK := inspectID(entry, "id")
		itemSnapshot, itemSnapshotOK := inspectID(entry, "source_snapshot_id")
		if !valid || !itemOK || itemID == "" || !itemSnapshotOK || !sameUUID(itemSnapshot, snapshotID) || !inspectInteger(entry, "item_order", 0) || !inspectStringValue(entry, "source_kind") || !inspectStringValue(entry, "source_label") || !inspectStringValue(entry, "ingestion_adapter") || !inspectOptionalStringOrNull(entry, "media_type") || !inspectTime(entry, "created_at") {
			return result, &Failure{Code: "invalid_api_response"}
		}
	}
	rows := []struct {
		name     string
		validate func(json.RawMessage, string, string) (inspectionObject, bool)
	}{
		{"guide_sufficiency_report", func(raw json.RawMessage, p, g string) (inspectionObject, bool) {
			return validateSufficiency(raw, p, g, "")
		}},
		{"submission_artifact_policy", func(raw json.RawMessage, p, g string) (inspectionObject, bool) {
			return validateArtifactPolicy(raw, p, g, "")
		}},
		{"effective_submission_artifact_policy", validateEffectivePolicy},
		{"pre_submit_checker_policy", func(raw json.RawMessage, p, g string) (inspectionObject, bool) {
			return validatePreSubmitPolicy(raw, p, g, true)
		}},
	}
	chain := map[string]inspectionObject{}
	for _, row := range rows {
		entry, valid := row.validate(fields[row.name], project, guideID)
		if !valid {
			return result, &Failure{Code: "invalid_api_response"}
		}
		version, _, _ := inspectGuideLink(entry, project, guideID)
		id, hash, _ := inspectSnapshotLink(entry)
		if version != guideVersion || !sameUUID(id, snapshotID) || hash != snapshotHash {
			return result, &Failure{Code: "invalid_api_response"}
		}
		chain[row.name] = entry
	}
	submission := chain["submission_artifact_policy"]
	sufficiency := chain["guide_sufficiency_report"]
	effective := chain["effective_submission_artifact_policy"]
	pre := chain["pre_submit_checker_policy"]
	submissionID, _ := inspectID(submission, "id")
	effectiveID, _ := inspectID(effective, "id")
	submissionHash, _ := inspectHash(submission, "policy_hash")
	effectiveHash, _ := inspectHash(effective, "effective_policy_hash")
	effectiveSubmissionID, _ := inspectID(effective, "submission_artifact_policy_id")
	preEffectiveID, _ := inspectID(pre, "effective_policy_id")
	preSubmissionHash, _ := inspectHash(effective, "submission_artifact_policy_hash")
	preEffectiveHash, _ := inspectHash(pre, "effective_policy_hash")
	sufficiencyStatus, _ := inspectString(sufficiency, "status")
	submissionStatus, _ := inspectString(submission, "lifecycle_status")
	if !oneOf(sufficiencyStatus, "passed", "passed_with_warnings") || submissionStatus != "approved" || !inspectLiteral(submission, "approved_by_role", "admin", "project_manager") || !inspectNonblank(submission, "approved_by_actor") || !inspectTime(submission, "approved_at") || !sameUUID(effectiveSubmissionID, submissionID) || !sameUUID(preEffectiveID, effectiveID) || preSubmissionHash != submissionHash || preEffectiveHash != effectiveHash {
		return result, &Failure{Code: "invalid_api_response"}
	}
	for _, name := range []string{"post_submit_checker_policy", "review_policy", "revision_policy"} {
		if !validateActiveAssociated(fields[name], name, project, guideVersion) {
			return result, &Failure{Code: "invalid_api_response"}
		}
	}
	return Result[json.RawMessage]{Raw: raw, Value: raw}, nil
}
