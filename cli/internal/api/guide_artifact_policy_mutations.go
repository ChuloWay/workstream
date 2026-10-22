package api

import (
	"bytes"
	"context"
	"encoding/json"
	jsonv2 "encoding/json/v2"
	"errors"
	"net/http"
	"net/url"
	"reflect"
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
	return version != "" && version == pythonStrip(version) &&
		utf8.RuneCountInString(version) <= 50 && !strings.HasPrefix(strings.ToLower(version), "agent-")
}

func validManualPolicySummary(summary *string) bool {
	return summary == nil || utf8.RuneCountInString(*summary) <= 2000
}

func manualPolicyInput(body json.RawMessage, create bool) (string, string, *string, json.RawMessage, bool) {
	if len(body) == 0 || len(body) > MaxGuideInputBytes {
		return "", "", nil, nil, false
	}
	if create {
		var input manualArtifactPolicyCreateInput
		if _, err := contextObject(body, &input, []string{"source_snapshot_id", "policy_version", "policy_body"}, nil); err != nil ||
			!validUUID(input.SourceSnapshotID) || !validManualPolicyVersion(input.PolicyVersion) ||
			!inspectPolicyBodyInput(input.PolicyBody) || !validManualPolicySummary(input.ChangeSummary) {
			return "", "", nil, nil, false
		}
		return input.SourceSnapshotID, input.PolicyVersion, input.ChangeSummary, input.PolicyBody, true
	}
	var input manualArtifactPolicyUpdateInput
	fields, err := contextObject(body, &input, []string{"expected_policy_hash", "successor_policy_version"}, nil)
	if err != nil || !policyHash.MatchString(input.ExpectedPolicyHash) ||
		!validManualPolicyVersion(input.SuccessorPolicyVersion) || !validManualPolicySummary(input.ChangeSummary) {
		return "", "", nil, nil, false
	}
	if _, present := fields["policy_body"]; present && !bytes.Equal(bytes.TrimSpace(input.PolicyBody), []byte("null")) && !inspectPolicyBodyInput(input.PolicyBody) {
		return "", "", nil, nil, false
	}
	if bytes.Equal(bytes.TrimSpace(input.PolicyBody), []byte("null")) {
		return input.ExpectedPolicyHash, input.SuccessorPolicyVersion, input.ChangeSummary, nil, true
	}
	return input.ExpectedPolicyHash, input.SuccessorPolicyVersion, input.ChangeSummary, input.PolicyBody, true
}

func inspectPolicyBodyInput(raw json.RawMessage) bool {
	var body map[string]json.RawMessage
	return jsonv2.Unmarshal(raw, &body) == nil && body != nil
}

// Compare only explicitly supplied policy content. The backend owns defaults,
// canonical rule order and set normalization; the CLI must not accept a
// successful write receipt that silently substitutes requested content.
func policyBodyReflectsInput(inputRaw, responseRaw json.RawMessage) bool {
	if len(inputRaw) == 0 {
		return true // omitted or explicit null PATCH inherits the predecessor
	}
	decode := func(raw json.RawMessage) (any, bool) {
		var checked any
		if jsonv2.Unmarshal(raw, &checked) != nil {
			return nil, false
		}
		decoder := json.NewDecoder(bytes.NewReader(raw))
		decoder.UseNumber()
		var value any
		return value, decoder.Decode(&value) == nil
	}
	input, inputOK := decode(inputRaw)
	response, responseOK := decode(responseRaw)
	inputFields, inputObject := input.(map[string]any)
	responseFields, responseObject := response.(map[string]any)
	if !inputOK || !responseOK || !inputObject || !responseObject {
		return false
	}
	for key, expected := range inputFields {
		actual, present := responseFields[key]
		if !present {
			return false
		}
		switch key {
		case "required_artifacts", "required_evidence", "forbidden_artifacts":
			identity := "key"
			if key == "forbidden_artifacts" {
				identity = "pattern"
			}
			if !policyRuleListReflectsInput(expected, actual, identity) {
				return false
			}
		case "attestation_terms", "allowed_storage_schemes":
			if !policyStringSetReflectsInput(expected, actual) {
				return false
			}
		default:
			if !policyValueReflectsInput(expected, actual) {
				return false
			}
		}
	}
	return true
}

func policyValueReflectsInput(expected, actual any) bool {
	switch value := expected.(type) {
	case map[string]any:
		returned, ok := actual.(map[string]any)
		if !ok {
			return false
		}
		for key, member := range value {
			actualMember, present := returned[key]
			if !present || !policyValueReflectsInput(member, actualMember) {
				return false
			}
		}
		return true
	case []any:
		returned, ok := actual.([]any)
		if !ok || len(value) != len(returned) {
			return false
		}
		for index, member := range value {
			if !policyValueReflectsInput(member, returned[index]) {
				return false
			}
		}
		return true
	default:
		if number, ok := expected.(json.Number); ok {
			// Reuse the existing precision-aware JSON number identity used by
			// checker receipts. Python may parse 1e3 and persist it as 1000.
			wanted, wantedErr := checkerParsedIdentity(number)
			returned, returnedErr := checkerParsedIdentity(actual)
			return wantedErr == nil && returnedErr == nil && reflect.DeepEqual(wanted, returned)
		}
		return reflect.DeepEqual(expected, actual)
	}
}

func policyRuleListReflectsInput(expected, actual any, identity string) bool {
	wanted, wantedOK := expected.([]any)
	returned, returnedOK := actual.([]any)
	if !wantedOK || !returnedOK || len(wanted) != len(returned) {
		return false
	}
	byIdentity := make(map[string]map[string]any, len(returned))
	for _, member := range returned {
		rule, ok := member.(map[string]any)
		if !ok {
			return false
		}
		id, ok := rule[identity].(string)
		if !ok || id == "" || byIdentity[id] != nil {
			return false
		}
		byIdentity[id] = rule
	}
	for _, member := range wanted {
		rule, ok := member.(map[string]any)
		if !ok {
			return false
		}
		id, ok := rule[identity].(string)
		if !ok || !policyValueReflectsInput(rule, byIdentity[id]) {
			return false
		}
	}
	return true
}

func policyStringSetReflectsInput(expected, actual any) bool {
	wanted, wantedOK := expected.([]any)
	returned, returnedOK := actual.([]any)
	if !wantedOK || !returnedOK {
		return false
	}
	toSet := func(values []any) (map[string]bool, bool) {
		set := make(map[string]bool, len(values))
		for _, member := range values {
			value, ok := member.(string)
			if !ok {
				return nil, false
			}
			set[value] = true
		}
		return set, true
	}
	wantedSet, wantedValid := toSet(wanted)
	returnedSet, returnedValid := toSet(returned)
	if !wantedValid || !returnedValid || len(wantedSet) != len(returnedSet) {
		return false
	}
	for value := range wantedSet {
		if !returnedSet[value] {
			return false
		}
	}
	return true
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
	snapshot, version, summary, requestedPolicyBody, ok := manualPolicyInput(body, true)
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
		!validManualPolicyResponse(fields, version, summary, "", true) ||
		!policyBodyReflectsInput(requestedPolicyBody, fields["policy_body"]) || !c.safeMutationResponse(raw) {
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
	_, version, summary, requestedPolicyBody, ok := manualPolicyInput(body, false)
	if !ok {
		return result, errors.New("--input must contain a bounded public manual artifact-policy update request")
	}
	path, _ := guideInspectionPath(project, guide, "/submission-artifact-policies/"+url.PathEscape(predecessor))
	raw, err := c.requestWithCanonicalPatch(ctx, path, body, key, maxGuideInspectionBytes)
	if err != nil {
		return result, manualPolicyMutationFailure(err)
	}
	fields, valid := validateArtifactPolicy(raw, project, guide, "")
	if !valid || !validManualPolicyResponse(fields, version, summary, predecessor, false) ||
		!policyBodyReflectsInput(requestedPolicyBody, fields["policy_body"]) || !c.safeMutationResponse(raw) {
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
