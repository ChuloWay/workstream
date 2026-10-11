package api

import (
	"context"
	"encoding/json"
	"errors"
	"math/big"
	"net/http"
	"net/url"
)

// GuideActivationInput contains manager-selected public facts, not readiness.
type GuideActivationInput struct {
	Target                                PostPolicyTarget     `json:"target"`
	PostApprovalOperationID               string               `json:"post_approval_operation_id"`
	PostApprovalOutputDigest              string               `json:"post_approval_output_digest"`
	GuideMutationGeneration               *big.Int             `json:"guide_mutation_generation"`
	Review                                GuidePolicySelection `json:"review"`
	Revision                              GuidePolicySelection `json:"revision"`
	ContributionPolicyID                  string               `json:"contribution_policy_id"`
	ContributionPolicyVersionID           string               `json:"contribution_policy_version_id"`
	ExpectedPreviousActiveGuideID         *string              `json:"expected_previous_active_guide_id"`
	ExpectedPreviousActiveGuideGeneration *big.Int             `json:"expected_previous_active_guide_generation"`
}

type GuideActivationCommand struct {
	GuideActivationInput
	IdempotencyKey string `json:"idempotency_key"`
}

type GuideActivationContribution struct {
	ProjectID                   string   `json:"project_id"`
	ContributionPolicyID        string   `json:"contribution_policy_id"`
	ContributionPolicyVersionID string   `json:"contribution_policy_version_id"`
	Purpose                     string   `json:"purpose"`
	VersionNumber               *big.Int `json:"version_number"`
	RulesAndDefinitionsDigest   string   `json:"rules_and_definitions_digest"`
	AdapterBindingIDs           []string `json:"adapter_binding_ids"`
}

type GuideActivationReceipt struct {
	OperationID          string                      `json:"operation_id"`
	Command              GuideActivationCommand      `json:"command"`
	Contribution         GuideActivationContribution `json:"contribution"`
	ActivationGeneration *big.Int                    `json:"activation_generation"`
	EffectiveAt          string                      `json:"effective_at"`
	PriorProjectStatus   string                      `json:"prior_project_status"`
}

func (c *Client) ActivateGuide(ctx context.Context, project, guide string, body json.RawMessage, key string) (Result[GuideActivationReceipt], error) {
	var result Result[GuideActivationReceipt]
	for _, id := range []string{project, guide, key} {
		if !validUUID(id) || len(id) > 100 {
			return result, errors.New("project, guide and --idempotency-key must be UUIDs")
		}
	}
	var input GuideActivationInput
	if len(body) == 0 || len(body) > MaxGuideInputBytes || decodeGuideActivationInput(body, &input, false) != nil ||
		!sameUUID(input.Target.Proposal.ProjectID, project) || !sameUUID(input.Target.Proposal.GuideID, guide) {
		return result, errors.New("--input must contain the bounded public activation request with exact selections for the chosen project and guide")
	}
	raw, err := c.requestWithKey(ctx, http.MethodPost,
		"/api/v1/projects/"+url.PathEscape(project)+"/guides/"+url.PathEscape(guide)+"/activate", "", body, key, http.StatusOK)
	if err != nil {
		return result, guideActivationFailure(err)
	}
	var value GuideActivationReceipt
	fields, err := contextObject(raw, &value, []string{"operation_id", "command", "contribution", "activation_generation", "effective_at", "prior_project_status"}, nil)
	identity, valid := uuidIdentity(value.OperationID)
	if err != nil || !valid || identity[6]>>4 != 7 || identity[8]&0xc0 != 0x80 ||
		decodeGuideActivationInput(fields["command"], &value.Command.GuideActivationInput, true) != nil ||
		!sameUUID(value.Command.IdempotencyKey, key) || !sameGuideActivationInput(value.Command.GuideActivationInput, input) ||
		value.ActivationGeneration.Cmp(new(big.Int).Add(input.GuideMutationGeneration, big.NewInt(1))) != 0 ||
		!validTime(value.EffectiveAt) || (value.PriorProjectStatus != "draft" && value.PriorProjectStatus != "active") ||
		validateActivationContribution(fields["contribution"], &value.Contribution, input) != nil || !c.safeMutationResponse(raw) {
		return result, guideActivationFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true})
	}
	return Result[GuideActivationReceipt]{Raw: raw, Value: value}, nil
}

func decodeGuideActivationInput(raw json.RawMessage, value *GuideActivationInput, command bool) error {
	required := []string{"target", "post_approval_operation_id", "post_approval_output_digest", "guide_mutation_generation", "review", "revision", "contribution_policy_id", "contribution_policy_version_id"}
	var fields map[string]json.RawMessage
	var err error
	if command {
		var echoed GuideActivationCommand
		fields, err = contextObject(raw, &echoed, append(required, "idempotency_key"), nil)
		*value = echoed.GuideActivationInput
		if !validUUID(echoed.IdempotencyKey) {
			return errors.New("invalid activation replay identity")
		}
	} else {
		fields, err = contextObject(raw, value, required, nil)
	}
	if err != nil || !requiredNullable(fields, "expected_previous_active_guide_id", "expected_previous_active_guide_generation") ||
		decodePostPolicyTarget(fields["target"], &value.Target) != nil ||
		!validUUID(value.PostApprovalOperationID) || !contextPolicyDigest.MatchString(value.PostApprovalOutputDigest) || value.GuideMutationGeneration.Sign() <= 0 ||
		validateGuidePolicySelection(fields["review"], &value.Review) != nil || validateGuidePolicySelection(fields["revision"], &value.Revision) != nil ||
		!validUUID(value.ContributionPolicyID) || !validUUID(value.ContributionPolicyVersionID) {
		return errors.New("invalid activation selections")
	}
	// The public input permits a retained predecessor with a null generation.
	// Do not replace its asymmetric rule with the display context's pair rule.
	previous, generation := value.ExpectedPreviousActiveGuideID, value.ExpectedPreviousActiveGuideGeneration
	if (previous == nil && generation != nil) || (generation != nil && generation.Sign() <= 0) ||
		(previous != nil && (!validUUID(*previous) || sameUUID(*previous, value.Target.Proposal.GuideID))) {
		return errors.New("invalid activation predecessor")
	}
	return nil
}

func sameGuideActivationInput(a, b GuideActivationInput) bool {
	if !samePostPolicyTarget(a.Target, b.Target) || !sameUUID(a.PostApprovalOperationID, b.PostApprovalOperationID) ||
		a.PostApprovalOutputDigest != b.PostApprovalOutputDigest || a.GuideMutationGeneration.Cmp(b.GuideMutationGeneration) != 0 ||
		!sameUUID(a.ContributionPolicyID, b.ContributionPolicyID) || !sameUUID(a.ContributionPolicyVersionID, b.ContributionPolicyVersionID) ||
		(a.ExpectedPreviousActiveGuideID == nil) != (b.ExpectedPreviousActiveGuideID == nil) ||
		(a.ExpectedPreviousActiveGuideID != nil && !sameUUID(*a.ExpectedPreviousActiveGuideID, *b.ExpectedPreviousActiveGuideID)) ||
		(a.ExpectedPreviousActiveGuideGeneration == nil) != (b.ExpectedPreviousActiveGuideGeneration == nil) ||
		(a.ExpectedPreviousActiveGuideGeneration != nil && a.ExpectedPreviousActiveGuideGeneration.Cmp(b.ExpectedPreviousActiveGuideGeneration) != 0) {
		return false
	}
	for i, selected := range []GuidePolicySelection{a.Review, a.Revision} {
		other := []GuidePolicySelection{b.Review, b.Revision}[i]
		if !sameUUID(selected.PolicyID, other.PolicyID) || selected.Generation.Cmp(other.Generation) != 0 || selected.PolicyHash != other.PolicyHash {
			return false
		}
	}
	return true
}

func validateActivationContribution(raw json.RawMessage, value *GuideActivationContribution, input GuideActivationInput) error {
	_, err := contextObject(raw, value, []string{"project_id", "contribution_policy_id", "contribution_policy_version_id", "purpose", "version_number", "rules_and_definitions_digest", "adapter_binding_ids"}, []string{"adapter_binding_ids"})
	if err != nil || !sameUUID(value.ProjectID, input.Target.Proposal.ProjectID) || !sameUUID(value.ContributionPolicyID, input.ContributionPolicyID) ||
		!sameUUID(value.ContributionPolicyVersionID, input.ContributionPolicyVersionID) || value.Purpose != "guide_activation" ||
		value.VersionNumber.Sign() <= 0 || !contextPolicyDigest.MatchString(value.RulesAndDefinitionsDigest) {
		return errors.New("invalid activation contribution binding")
	}
	for _, id := range value.AdapterBindingIDs {
		if !validUUID(id) {
			return errors.New("invalid activation adapter identity")
		}
	}
	return nil
}

func guideActivationFailure(err error) error {
	var failure *Failure
	if errors.As(err, &failure) && failure.OutcomeUnknown {
		failure.RecoveryHint = "guide activation outcome unknown; replay only the unchanged project, guide, input file contents and idempotency key"
	}
	return err
}
