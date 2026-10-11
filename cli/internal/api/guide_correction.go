package api

import (
	"context"
	"encoding/json"
	"errors"
	"math/big"
	"net/http"
	"net/url"
	"unicode/utf8"
)

type GuideCorrectionDispatch struct {
	CorrectionOperationID string   `json:"correction_operation_id"`
	SetupRunID            string   `json:"setup_run_id"`
	SetupGeneration       *big.Int `json:"setup_generation"`
	Status                string   `json:"status"`
}

func (c *Client) CorrectGuideProposal(ctx context.Context, project, guide, compilation string, body json.RawMessage, key string) (Result[GuideCorrection], error) {
	var result Result[GuideCorrection]
	for _, id := range []string{project, guide, compilation, key} {
		if !validUUID(id) || len(id) > 100 {
			return result, errors.New("project, guide, compilation and --idempotency-key must be UUIDs")
		}
	}
	var input struct {
		Target ProposalTarget `json:"target"`
		Reason string         `json:"reason"`
	}
	fields, err := contextObject(body, &input, []string{"target", "reason"}, nil)
	if len(body) == 0 || len(body) > MaxGuideInputBytes || err != nil ||
		utf8.RuneCountInString(input.Reason) < 1 || utf8.RuneCountInString(input.Reason) > 4000 ||
		validateProposalTarget(fields["target"], &input.Target) != nil ||
		!sameUUID(input.Target.ProjectID, project) || !sameUUID(input.Target.GuideID, guide) || !sameUUID(input.Target.CompilationID, compilation) {
		return result, errors.New("--input must contain the bounded public correction request with target and reason for the selected project, guide and compilation")
	}
	raw, err := c.requestWithKey(ctx, http.MethodPost, guideCorrectionPath(project, guide, compilation), "", body, key, http.StatusCreated)
	if err != nil {
		return result, guideCorrectionFailure(err, false)
	}
	value, err := c.decodeCorrectionReceipt(raw)
	if err != nil || value.SuccessorSetupGeneration.Cmp(new(big.Int).Add(input.Target.SetupGeneration, big.NewInt(1))) != 0 {
		return result, guideCorrectionFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true}, false)
	}
	return Result[GuideCorrection]{Raw: raw, Value: value}, nil
}

func (c *Client) DispatchGuideCorrection(ctx context.Context, project, guide, compilation string, receipt json.RawMessage) (Result[GuideCorrectionDispatch], error) {
	var result Result[GuideCorrectionDispatch]
	for _, id := range []string{project, guide, compilation} {
		if !validUUID(id) || len(id) > 100 {
			return result, errors.New("project, guide and compilation must be UUIDs")
		}
	}
	saved, err := c.decodeCorrectionReceipt(receipt)
	if len(receipt) == 0 || len(receipt) > MaxGuideInputBytes || err != nil {
		return result, errors.New("--input must contain the exact saved public guide correction receipt")
	}
	raw, err := c.requestWithKey(ctx, http.MethodPost,
		guideCorrectionPath(project, guide, compilation)+"/"+url.PathEscape(saved.OperationID)+"/dispatch",
		"", nil, "", http.StatusAccepted)
	if err != nil {
		return result, guideCorrectionFailure(err, true)
	}
	var value GuideCorrectionDispatch
	_, err = contextObject(raw, &value, []string{"correction_operation_id", "setup_run_id", "setup_generation", "status"}, nil)
	if err != nil || !sameUUID(value.CorrectionOperationID, saved.OperationID) || !sameUUID(value.SetupRunID, saved.SuccessorSetupRunID) ||
		value.SetupGeneration.Cmp(saved.SuccessorSetupGeneration) != 0 ||
		!c.safeMetadata(value.CorrectionOperationID) || !c.safeMetadata(value.SetupRunID) || !c.safeMetadata(value.Status) ||
		sameUUID(value.CorrectionOperationID, c.token) || sameUUID(value.SetupRunID, c.token) || sameUUID(value.Status, c.token) {
		return result, guideCorrectionFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true}, true)
	}
	return Result[GuideCorrectionDispatch]{Raw: raw, Value: value}, nil
}

func guideCorrectionPath(project, guide, compilation string) string {
	return "/api/v1/projects/" + url.PathEscape(project) + "/guides/" + url.PathEscape(guide) + "/compilations/" + url.PathEscape(compilation) + "/corrections"
}

func (c *Client) decodeCorrectionReceipt(raw json.RawMessage) (GuideCorrection, error) {
	var value GuideCorrection
	// The backend owns target/feedback digest computation. Check the closed
	// public receipt structure, not a second client-side business hash recipe.
	// Decode once to obtain the digest, then apply the canonical closed
	// validator (including duplicate-member rejection) to the original bytes.
	if json.Unmarshal(raw, &value) != nil || validateGuideCorrection(raw, &value, value.TargetDigest) != nil {
		return value, errors.New("invalid correction receipt")
	}
	for _, metadata := range []string{value.OperationID, value.SuccessorSetupRunID, value.TargetDigest, value.FeedbackHash} {
		if !c.safeMetadata(metadata) || sameUUID(metadata, c.token) {
			return value, errors.New("credential-reflecting correction receipt")
		}
	}
	return value, nil
}

func guideCorrectionFailure(err error, dispatch bool) error {
	var failure *Failure
	if errors.As(err, &failure) && failure.OutcomeUnknown {
		failure.RecoveryHint = "guide correction outcome unknown; replay only the unchanged project, guide, compilation, input file contents and idempotency key"
		if dispatch {
			failure.RecoveryHint = "correction dispatch outcome unknown; inspect setup status and manually redispatch only the unchanged project, guide, compilation and saved correction receipt"
		}
	}
	return err
}
