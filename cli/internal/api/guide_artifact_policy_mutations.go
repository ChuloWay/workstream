package api

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"strings"
	"unicode/utf8"
)

type manualArtifactPolicyCreateInput struct {
	SourceSnapshotID string          `json:"source_snapshot_id"`
	PolicyVersion    string          `json:"policy_version"`
	PolicyBody       json.RawMessage `json:"policy_body"`
	ChangeSummary    *string         `json:"change_summary"`
}

type manualArtifactPolicyUpdateInput struct {
	ExpectedPolicyHash     string          `json:"expected_policy_hash"`
	SuccessorPolicyVersion string          `json:"successor_policy_version"`
	PolicyBody             json.RawMessage `json:"policy_body"`
	ChangeSummary          *string         `json:"change_summary"`
}

func validManualPolicyVersion(version string) bool {
	return version != "" && version == strings.TrimSpace(version) &&
		utf8.RuneCountInString(version) <= 50 && !strings.HasPrefix(strings.ToLower(version), "agent-")
}

func validManualPolicySummary(summary *string) bool {
	return summary == nil || utf8.RuneCountInString(*summary) <= 2000
}

func manualPolicyInput(body json.RawMessage, create bool) (string, string, *string, bool) {
	if len(body) == 0 || len(body) > MaxGuideInputBytes {
		return "", "", nil, false
	}
	if create {
		var input manualArtifactPolicyCreateInput
		if _, err := contextObject(body, &input, []string{"source_snapshot_id", "policy_version", "policy_body"}, nil); err != nil ||
			!validUUID(input.SourceSnapshotID) || !validManualPolicyVersion(input.PolicyVersion) ||
			!inspectPolicyBodyInput(input.PolicyBody) || !validManualPolicySummary(input.ChangeSummary) {
			return "", "", nil, false
		}
		return input.SourceSnapshotID, input.PolicyVersion, input.ChangeSummary, true
	}
	var input manualArtifactPolicyUpdateInput
	fields, err := contextObject(body, &input, []string{"expected_policy_hash", "successor_policy_version"}, nil)
	if err != nil || !policyHash.MatchString(input.ExpectedPolicyHash) ||
		!validManualPolicyVersion(input.SuccessorPolicyVersion) || !validManualPolicySummary(input.ChangeSummary) {
		return "", "", nil, false
	}
	if _, present := fields["policy_body"]; present && !inspectPolicyBodyInput(input.PolicyBody) {
		return "", "", nil, false
	}
	return input.ExpectedPolicyHash, input.SuccessorPolicyVersion, input.ChangeSummary, true
}

func inspectPolicyBodyInput(raw json.RawMessage) bool {
	var body map[string]json.RawMessage
	return json.Unmarshal(raw, &body) == nil && body != nil
}

func validManualPolicyResponse(fields inspectionObject, version string, summary *string, predecessor string, create bool) bool {
	responseVersion, versionOK := inspectString(fields, "policy_version")
	status, statusOK := inspectString(fields, "lifecycle_status")
	derivation, derivationOK := inspectString(fields, "derivation_source")
	var actualSummary *string
	if json.Unmarshal(fields["change_summary"], &actualSummary) != nil ||
		!versionOK || responseVersion != version || !statusOK || status != "draft" ||
		!derivationOK || derivation != "manual_admin_derivation" ||
		string(fields["derivation_agent_name"]) != "null" ||
		string(fields["derivation_agent_version"]) != "null" ||
		string(fields["approved_by_role"]) != "null" ||
		string(fields["approved_by_actor"]) != "null" ||
		string(fields["approved_at"]) != "null" ||
		(create && !sameOptionalString(actualSummary, summary)) ||
		(!create && summary != nil && !sameOptionalString(actualSummary, summary)) {
		return false
	}
	if create {
		return string(fields["supersedes_policy_id"]) == "null"
	}
	selected, ok := inspectID(fields, "supersedes_policy_id")
	return ok && sameUUID(selected, predecessor)
}

// CreateManualArtifactPolicy asks the backend to create a manual draft against
// its current authoritative setup lineage. It never approves the draft.
func (c *Client) CreateManualArtifactPolicy(ctx context.Context, project, guide string, body json.RawMessage, key string) (Result[json.RawMessage], error) {
	var result Result[json.RawMessage]
	if !validPolicyMutationSelectors(project, guide, "", key) {
		return result, errors.New("project, guide and --idempotency-key must be UUIDs")
	}
	snapshot, version, summary, ok := manualPolicyInput(body, true)
	if !ok {
		return result, errors.New("--input must contain a bounded public manual artifact-policy create request")
	}
	path, _ := guideInspectionPath(project, guide, "/submission-artifact-policies")
	raw, err := c.requestWithResponseLimit(ctx, http.MethodPost, path, "", body, key, http.StatusCreated, maxGuideInspectionBytes)
	if err != nil {
		return result, manualPolicyMutationFailure(err)
	}
	fields, valid := validateArtifactPolicy(raw, project, guide, "")
	responseSnapshot, snapshotOK := inspectID(fields, "source_snapshot_id")
	if !valid || !snapshotOK || !sameUUID(responseSnapshot, snapshot) ||
		!validManualPolicyResponse(fields, version, summary, "", true) || !c.safeMutationResponse(raw) {
		return result, manualPolicyMutationFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true})
	}
	return Result[json.RawMessage]{Raw: raw, Value: raw}, nil
}

// UpdateManualArtifactPolicy selects one exact manual predecessor. The server
// owns the current-draft and expected-hash compare-and-swap decision.
func (c *Client) UpdateManualArtifactPolicy(ctx context.Context, project, guide, predecessor string, body json.RawMessage, key string) (Result[json.RawMessage], error) {
	var result Result[json.RawMessage]
	if !validPolicyMutationSelectors(project, guide, predecessor, key) {
		return result, errors.New("project, guide, policy and --idempotency-key must be UUIDs")
	}
	_, version, summary, ok := manualPolicyInput(body, false)
	if !ok {
		return result, errors.New("--input must contain a bounded public manual artifact-policy update request")
	}
	path, _ := guideInspectionPath(project, guide, "/submission-artifact-policies/"+url.PathEscape(predecessor))
	raw, err := c.requestWithResponseLimit(ctx, http.MethodPatch, path, "", body, key, http.StatusOK, maxGuideInspectionBytes)
	if err != nil {
		return result, manualPolicyMutationFailure(err)
	}
	fields, valid := validateArtifactPolicy(raw, project, guide, "")
	if !valid || !validManualPolicyResponse(fields, version, summary, predecessor, false) || !c.safeMutationResponse(raw) {
		return result, manualPolicyMutationFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true})
	}
	return Result[json.RawMessage]{Raw: raw, Value: raw}, nil
}

func validPolicyMutationSelectors(project, guide, policy, key string) bool {
	for _, id := range []string{project, guide, key} {
		if !validUUID(id) || len(id) > 100 {
			return false
		}
	}
	return policy == "" || validUUID(policy) && len(policy) <= 100
}

func manualPolicyMutationFailure(err error) error {
	var failure *Failure
	if errors.As(err, &failure) && failure.OutcomeUnknown {
		failure.RecoveryHint = "manual artifact-policy write outcome unknown; manually replay only the unchanged project, guide, policy (if selected), input file contents and idempotency key"
	}
	return err
}
