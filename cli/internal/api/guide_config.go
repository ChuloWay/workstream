package api

import (
	"context"
	"encoding/json"
	"errors"
	"math/big"
	"reflect"
	"strings"
	"unicode"
)

// GuideEdited is the public draft-guide PATCH result, not an activation receipt.
type GuideEdited struct {
	ID                          string         `json:"id"`
	ProjectID                   string         `json:"project_id"`
	Version                     string         `json:"version"`
	Status                      string         `json:"status"`
	ChangeSummary               *string        `json:"change_summary"`
	TaskExamples                []GuideExample `json:"task_examples"`
	TaskExamplesHash            *string        `json:"task_examples_hash"`
	ContributionPolicyID        *string        `json:"contribution_policy_id"`
	ContributionPolicyVersionID *string        `json:"contribution_policy_version_id"`
	ActivationOperationID       *string        `json:"activation_operation_id"`
	ApprovedBy                  *string        `json:"approved_by"`
	EffectiveAt                 *string        `json:"effective_at"`
	CreatedBy                   string         `json:"created_by"`
	CreatedAt                   string         `json:"created_at"`
	UpdatedAt                   string         `json:"updated_at"`
	SupersededAt                *string        `json:"superseded_at"`
}

type guideEditInput struct {
	ChangeSummary *string `json:"change_summary"`
}

type reviewPolicyInput struct {
	HumanReviewRequired              *bool    `json:"human_review_required"`
	ReviewPreferenceWindowSeconds    *big.Int `json:"review_preference_window_seconds"`
	ReviewLeaseDurationSeconds       *big.Int `json:"review_lease_duration_seconds"`
	MaxActiveReviewLeasesPerReviewer *big.Int `json:"max_active_review_leases_per_reviewer"`
	SelfReviewAllowed                *bool    `json:"self_review_allowed"`
	RejectPolicy                     *string  `json:"reject_policy"`
	FindingEvidenceRequirement       *string  `json:"finding_evidence_requirement"`
	RequiresSecondReview             *bool    `json:"requires_second_review"`
	AllowedDecisions                 []string `json:"allowed_decisions"`
	MinimumFindingFields             []string `json:"minimum_finding_fields"`
}

type revisionPolicyInput struct {
	MaxRevisionRounds         *big.Int `json:"max_revision_rounds"`
	RevisionDeadlineHours     *big.Int `json:"revision_deadline_hours"`
	AllowedResubmissionStates []string `json:"allowed_resubmission_states"`
	ReviewerReassignmentRule  *string  `json:"reviewer_reassignment_rule"`
}

type PolicyConfigured struct {
	ID                               string   `json:"id"`
	ProjectID                        string   `json:"project_id"`
	GuideVersion                     string   `json:"guide_version"`
	PolicyGeneration                 *big.Int `json:"policy_generation"`
	PolicyHash                       string   `json:"policy_hash"`
	SemanticsStatus                  string   `json:"semantics_status"`
	SupersedesPolicyID               *string  `json:"supersedes_policy_id"`
	HumanReviewRequired              *bool    `json:"human_review_required,omitempty"`
	SemanticsFormat                  *string  `json:"semantics_format,omitempty"`
	ReviewPreferenceWindowSeconds    *big.Int `json:"review_preference_window_seconds,omitempty"`
	ReviewLeaseDurationSeconds       *big.Int `json:"review_lease_duration_seconds,omitempty"`
	MaxActiveReviewLeasesPerReviewer *big.Int `json:"max_active_review_leases_per_reviewer,omitempty"`
	SelfReviewAllowed                *bool    `json:"self_review_allowed,omitempty"`
	RejectPolicy                     *string  `json:"reject_policy,omitempty"`
	FindingEvidenceRequirement       *string  `json:"finding_evidence_requirement,omitempty"`
	RequiresSecondReview             *bool    `json:"requires_second_review,omitempty"`
	AllowedDecisions                 []string `json:"allowed_decisions,omitempty"`
	MinimumFindingFields             []string `json:"minimum_finding_fields,omitempty"`
	MaxRevisionRounds                *big.Int `json:"max_revision_rounds,omitempty"`
	RevisionDeadlineHours            *big.Int `json:"revision_deadline_hours,omitempty"`
	AllowedResubmissionStates        []string `json:"allowed_resubmission_states,omitempty"`
	ReviewerReassignmentRule         *string  `json:"reviewer_reassignment_rule,omitempty"`
	CreatedAt                        string   `json:"created_at"`
}

func guideConfigSelectors(project, guide, key string) (string, error) {
	path, err := guidePath(project, guide)
	if err != nil || !validUUID(key) || len(key) > 100 {
		return "", errors.New("PROJECT_ID, GUIDE_ID and --idempotency-key must be UUIDs")
	}
	return path, nil
}

func configInputFields(body json.RawMessage, value any, required, arrays []string) (map[string]json.RawMessage, error) {
	if len(body) == 0 || len(body) > MaxGuideInputBytes {
		return nil, errors.New("invalid input size")
	}
	return contextObject(body, value, required, arrays)
}

func presentNonNull(fields map[string]json.RawMessage, names ...string) bool {
	for _, name := range names {
		if raw, present := fields[name]; present && strings.TrimSpace(string(raw)) == "null" {
			return false
		}
	}
	return true
}

func (c *Client) EditGuide(ctx context.Context, project, guide string, body json.RawMessage, key string) (Result[GuideEdited], error) {
	var result Result[GuideEdited]
	path, err := guideConfigSelectors(project, guide, key)
	if err != nil {
		return result, err
	}
	var input guideEditInput
	fields, err := configInputFields(body, &input, nil, nil)
	if err != nil {
		return result, errors.New("--input must contain a bounded public guide edit")
	}
	raw, err := c.requestWithCanonicalPatch(ctx, path, body, key, maxGuideResponseBytes)
	if err != nil {
		return result, guideConfigFailure(err, false)
	}
	var value GuideEdited
	returned, err := contextObject(raw, &value, []string{"id", "project_id", "version", "status", "created_by", "created_at", "updated_at", "task_examples"}, nil)
	if err != nil || !requiredNullable(returned, "change_summary", "task_examples_hash", "contribution_policy_id",
		"contribution_policy_version_id", "activation_operation_id", "approved_by", "effective_at", "superseded_at") ||
		!validUUID(value.ID) || !sameUUID(value.ID, guide) || !sameUUID(value.ProjectID, project) || value.Version == "" ||
		value.Status != "draft" || !validUUID(value.CreatedBy) || !validTime(value.CreatedAt) || !validTime(value.UpdatedAt) ||
		value.TaskExamplesHash == nil || !policyHash.MatchString(*value.TaskExamplesHash) ||
		value.ContributionPolicyID != nil || value.ContributionPolicyVersionID != nil || value.ActivationOperationID != nil ||
		value.ApprovedBy != nil || value.EffectiveAt != nil || value.SupersededAt != nil ||
		!c.safeMutationResponse(raw) {
		return result, guideConfigFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true}, false)
	}
	if _, err := decodeGuideExamples(returned["task_examples"]); err != nil {
		return result, guideConfigFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true}, false)
	}
	if _, supplied := fields["change_summary"]; supplied && !reflect.DeepEqual(value.ChangeSummary, input.ChangeSummary) {
		return result, guideConfigFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true}, false)
	}
	return Result[GuideEdited]{Raw: raw, Value: value}, nil
}

func validIfMatchHeader(value string) bool {
	if value == "" || len(value) > 256 {
		return false
	}
	for _, r := range value {
		if r < ' ' || r > '~' || unicode.IsControl(r) {
			return false
		}
	}
	return true
}

// policyPredecessor checks receipt lineage only after a successful public PUT.
// The backend remains the authority for admissible If-Match spelling.
func policyPredecessor(value string) (*string, *big.Int, bool) {
	if value == `"no-current-policy"` {
		return nil, big.NewInt(1), true
	}
	if len(value) < 3 || value[0] != '"' || value[len(value)-1] != '"' {
		return nil, nil, false
	}
	parts := strings.Split(value[1:len(value)-1], ".")
	if len(parts) != 3 || !validUUID(parts[0]) || len(parts[2]) != 64 {
		return nil, nil, false
	}
	for _, r := range parts[2] {
		if (r < '0' || r > '9') && (r < 'a' || r > 'f') {
			return nil, nil, false
		}
	}
	generation, ok := new(big.Int).SetString(parts[1], 10)
	if !ok || generation.Sign() <= 0 || parts[1] != generation.String() {
		return nil, nil, false
	}
	return &parts[0], generation.Add(generation, big.NewInt(1)), true
}

func (c *Client) ConfigureReviewPolicy(ctx context.Context, project, guide string, body json.RawMessage, key, ifMatch string) (Result[PolicyConfigured], error) {
	return c.configurePolicy(ctx, project, guide, body, key, ifMatch, "review")
}

func (c *Client) ConfigureRevisionPolicy(ctx context.Context, project, guide string, body json.RawMessage, key, ifMatch string) (Result[PolicyConfigured], error) {
	return c.configurePolicy(ctx, project, guide, body, key, ifMatch, "revision")
}

func (c *Client) configurePolicy(ctx context.Context, project, guide string, body json.RawMessage, key, ifMatch, kind string) (Result[PolicyConfigured], error) {
	var result Result[PolicyConfigured]
	path, err := guideConfigSelectors(project, guide, key)
	if err != nil {
		return result, err
	}
	if !validIfMatchHeader(ifMatch) {
		return result, errors.New("--if-match must be a bounded, control-free public policy selector")
	}
	var fields map[string]json.RawMessage
	var review reviewPolicyInput
	var revision revisionPolicyInput
	if kind == "review" {
		fields, err = configInputFields(body, &review, []string{"review_preference_window_seconds", "review_lease_duration_seconds"},
			[]string{"allowed_decisions", "minimum_finding_fields"})
		if err == nil && (!presentNonNull(fields, "human_review_required", "max_active_review_leases_per_reviewer", "self_review_allowed",
			"reject_policy", "finding_evidence_requirement", "requires_second_review", "allowed_decisions", "minimum_finding_fields") ||
			review.ReviewPreferenceWindowSeconds == nil || review.ReviewLeaseDurationSeconds == nil) {
			err = errors.New("invalid review input")
		}
	} else {
		fields, err = configInputFields(body, &revision, []string{"max_revision_rounds", "revision_deadline_hours"},
			[]string{"allowed_resubmission_states"})
		if err == nil && (!presentNonNull(fields, "allowed_resubmission_states") || revision.MaxRevisionRounds == nil || revision.RevisionDeadlineHours == nil) {
			err = errors.New("invalid revision input")
		}
	}
	if err != nil {
		return result, errors.New("--input must contain a bounded public " + kind + " policy")
	}
	raw, err := c.requestWithIfMatch(ctx, path+"/"+kind+"-policy", body, key, ifMatch, maxGuideResponseBytes)
	if err != nil {
		return result, guideConfigFailure(err, true)
	}
	var value PolicyConfigured
	base := []string{"id", "project_id", "guide_version", "policy_generation", "policy_hash", "semantics_status", "created_at"}
	var arrays []string
	if kind == "review" {
		base = append(base, "human_review_required", "semantics_format", "review_preference_window_seconds", "review_lease_duration_seconds",
			"max_active_review_leases_per_reviewer", "self_review_allowed", "reject_policy", "finding_evidence_requirement",
			"requires_second_review", "allowed_decisions", "minimum_finding_fields")
		arrays = []string{"allowed_decisions", "minimum_finding_fields"}
	} else {
		base = append(base, "max_revision_rounds", "revision_deadline_hours", "allowed_resubmission_states")
		arrays = []string{"allowed_resubmission_states"}
	}
	returned, err := contextObject(raw, &value, base, arrays)
	predecessor, generation, lineageOK := policyPredecessor(ifMatch)
	if err != nil || !lineageOK || unexpectedPolicyFields(returned, kind) || !requiredNullable(returned, "supersedes_policy_id") ||
		(kind == "revision" && !requiredNullable(returned, "reviewer_reassignment_rule")) ||
		!validUUID(value.ID) || !sameUUID(value.ProjectID, project) || value.GuideVersion == "" ||
		value.PolicyGeneration == nil || value.PolicyGeneration.Cmp(generation) != 0 ||
		!policyHash.MatchString(value.PolicyHash) || value.SemanticsStatus != "complete" || !validTime(value.CreatedAt) ||
		!optionalUUID(value.SupersedesPolicyID) || !sameOptionalUUID(value.SupersedesPolicyID, predecessor) ||
		!c.safeMutationResponse(raw) {
		return result, guideConfigFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true}, true)
	}
	if kind == "review" {
		if !validConfiguredReview(value, review, fields) {
			return result, guideConfigFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true}, true)
		}
	} else if !validConfiguredRevision(value, revision, fields) {
		return result, guideConfigFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true}, true)
	}
	return Result[PolicyConfigured]{Raw: raw, Value: value}, nil
}

func unexpectedPolicyFields(fields map[string]json.RawMessage, kind string) bool {
	other := []string{"max_revision_rounds", "revision_deadline_hours", "allowed_resubmission_states", "reviewer_reassignment_rule"}
	if kind == "revision" {
		other = []string{"human_review_required", "semantics_format", "review_preference_window_seconds", "review_lease_duration_seconds",
			"max_active_review_leases_per_reviewer", "self_review_allowed", "reject_policy", "finding_evidence_requirement",
			"requires_second_review", "allowed_decisions", "minimum_finding_fields"}
	}
	for _, name := range other {
		if _, present := fields[name]; present {
			return true
		}
	}
	return false
}

func sameOptionalUUID(left, right *string) bool {
	if left == nil || right == nil {
		return left == nil && right == nil
	}
	return sameUUID(*left, *right)
}

func sameBigInt(left, right *big.Int) bool {
	return left != nil && right != nil && left.Cmp(right) == 0
}

func validConfiguredReview(value PolicyConfigured, input reviewPolicyInput, fields map[string]json.RawMessage) bool {
	if value.HumanReviewRequired == nil || value.SemanticsFormat == nil || *value.SemanticsFormat != "v2" ||
		value.ReviewPreferenceWindowSeconds == nil || value.ReviewPreferenceWindowSeconds.Sign() <= 0 ||
		value.ReviewLeaseDurationSeconds == nil || value.ReviewLeaseDurationSeconds.Sign() <= 0 ||
		value.MaxActiveReviewLeasesPerReviewer == nil || value.MaxActiveReviewLeasesPerReviewer.Cmp(big.NewInt(1)) != 0 ||
		value.SelfReviewAllowed == nil || *value.SelfReviewAllowed || value.RejectPolicy == nil || *value.RejectPolicy != "close_task" ||
		value.FindingEvidenceRequirement == nil || !oneOf(*value.FindingEvidenceRequirement, "optional", "required_for_blocking", "required_for_all") ||
		value.RequiresSecondReview == nil || *value.RequiresSecondReview ||
		value.AllowedDecisions == nil || value.MinimumFindingFields == nil ||
		!sameBigInt(value.ReviewPreferenceWindowSeconds, input.ReviewPreferenceWindowSeconds) ||
		!sameBigInt(value.ReviewLeaseDurationSeconds, input.ReviewLeaseDurationSeconds) {
		return false
	}
	for _, decision := range value.AllowedDecisions {
		if !oneOf(decision, "accept", "needs_revision", "reject") {
			return false
		}
	}
	if _, present := fields["human_review_required"]; present && *value.HumanReviewRequired != *input.HumanReviewRequired {
		return false
	}
	if _, present := fields["max_active_review_leases_per_reviewer"]; present && !sameBigInt(value.MaxActiveReviewLeasesPerReviewer, input.MaxActiveReviewLeasesPerReviewer) {
		return false
	}
	if _, present := fields["self_review_allowed"]; present && *value.SelfReviewAllowed != *input.SelfReviewAllowed {
		return false
	}
	if _, present := fields["reject_policy"]; present && *value.RejectPolicy != *input.RejectPolicy {
		return false
	}
	if _, present := fields["finding_evidence_requirement"]; present && *value.FindingEvidenceRequirement != *input.FindingEvidenceRequirement {
		return false
	}
	if _, present := fields["requires_second_review"]; present && *value.RequiresSecondReview != *input.RequiresSecondReview {
		return false
	}
	if _, present := fields["allowed_decisions"]; present && !reflect.DeepEqual(value.AllowedDecisions, input.AllowedDecisions) {
		return false
	}
	if _, present := fields["minimum_finding_fields"]; present && !reflect.DeepEqual(value.MinimumFindingFields, input.MinimumFindingFields) {
		return false
	}
	return true
}

func validConfiguredRevision(value PolicyConfigured, input revisionPolicyInput, fields map[string]json.RawMessage) bool {
	if value.MaxRevisionRounds == nil || value.MaxRevisionRounds.Sign() < 0 ||
		value.RevisionDeadlineHours == nil || value.RevisionDeadlineHours.Sign() <= 0 ||
		!sameBigInt(value.MaxRevisionRounds, input.MaxRevisionRounds) || !sameBigInt(value.RevisionDeadlineHours, input.RevisionDeadlineHours) ||
		len(value.AllowedResubmissionStates) != 1 || value.AllowedResubmissionStates[0] != "needs_revision" {
		return false
	}
	if _, present := fields["allowed_resubmission_states"]; present && !reflect.DeepEqual(value.AllowedResubmissionStates, input.AllowedResubmissionStates) {
		return false
	}
	if _, present := fields["reviewer_reassignment_rule"]; present && !reflect.DeepEqual(value.ReviewerReassignmentRule, input.ReviewerReassignmentRule) {
		return false
	}
	return true
}

func guideConfigFailure(err error, policy bool) error {
	var failure *Failure
	if errors.As(err, &failure) && failure.OutcomeUnknown {
		if policy {
			failure.RecoveryHint = "policy write outcome unknown; inspect the exact guide, then deliberately replay only unchanged project, guide, input, If-Match and idempotency key"
		} else {
			failure.RecoveryHint = "guide edit outcome unknown; inspect the exact guide, then deliberately replay only unchanged project, guide, input and idempotency key"
		}
	}
	return err
}
