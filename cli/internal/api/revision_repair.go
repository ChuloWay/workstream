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

// RevisionRepairInput selects one exact backend-owned revision source. These
// fields are caller assertions, not cached permission or eligibility facts.
type RevisionRepairInput struct {
	ParentPreparationID     string
	ParentPreparationSHA256 string
	RoutingManifestID       string
	Reason                  string
}

func (c *Client) RepairRevisionContext(ctx context.Context, project, task, key string, input RevisionRepairInput) (Result[RevisionContext], error) {
	var result Result[RevisionContext]
	if !validUUID(project) || len(project) > 100 || !validUUID(task) || len(task) > 100 {
		return result, errors.New("PROJECT_ID and TASK_ID must be UUIDs")
	}
	if !validUUID(key) || len(key) > 100 {
		return result, errors.New("--idempotency-key must be a UUID")
	}
	if !utf8.ValidString(input.Reason) || strings.TrimSpace(input.Reason) == "" ||
		utf8.RuneCountInString(input.Reason) > 1000 || len([]byte(strings.TrimSpace(input.Reason))) > 1000 {
		return result, errors.New("--reason must be nonblank and at most 1000 UTF-8 characters and bytes")
	}
	parent := input.ParentPreparationID != "" || input.ParentPreparationSHA256 != ""
	manifest := input.RoutingManifestID != ""
	if parent == manifest || (parent && (!validUUID(input.ParentPreparationID) || len(input.ParentPreparationID) > 100 ||
		!contextPolicyDigest.MatchString(input.ParentPreparationSHA256))) ||
		(manifest && (!validUUID(input.RoutingManifestID) || len(input.RoutingManifestID) > 100)) {
		return result, errors.New("select either an exact parent preparation ID and sha256, or one routing manifest UUID")
	}
	body := map[string]string{"reason": input.Reason}
	if parent {
		body["parent_preparation_id"] = input.ParentPreparationID
		body["parent_preparation_sha256"] = input.ParentPreparationSHA256
	} else {
		body["routing_manifest_id"] = input.RoutingManifestID
	}
	encoded, err := json.Marshal(body)
	if err != nil || len(encoded) > maxUpdateBytes {
		return result, errors.New("revision repair request exceeds the request size limit")
	}
	path := "/api/v1/projects/" + url.PathEscape(project) + "/tasks/" + url.PathEscape(task) + "/revision-context/repair"
	raw, err := c.requestWithResponseLimit(ctx, http.MethodPost, path, "", encoded, key, http.StatusOK, maxGuideContextResponseBytes)
	if err != nil {
		return result, revisionRepairFailure(err)
	}
	var value RevisionContext
	var fields map[string]json.RawMessage
	if validateRevisionContext(raw, &value) != nil || json.Unmarshal(raw, &fields) != nil ||
		!hasRepairNullableFields(fields) || !c.safeMutationResponse(raw) ||
		(parent && (value.PredecessorPreparationID == nil || !sameUUID(*value.PredecessorPreparationID, input.ParentPreparationID))) ||
		(manifest && !sameUUID(value.SourceRoutingManifestID, input.RoutingManifestID)) {
		return result, revisionRepairFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true})
	}
	return Result[RevisionContext]{Raw: raw, Value: value}, nil
}

func hasRepairNullableFields(fields map[string]json.RawMessage) bool {
	for _, name := range []string{"predecessor_preparation_id", "deadline_at", "remaining_microseconds", "direction", "target"} {
		if _, ok := fields[name]; !ok {
			return false
		}
	}
	return true
}

func revisionRepairFailure(err error) error {
	var failure *Failure
	if errors.As(err, &failure) && failure.OutcomeUnknown {
		failure.RecoveryHint = "revision repair outcome unknown; inspect project task (observation, not rollback proof); deliberately replay only the unchanged project, task, exact source, reason and idempotency key"
	}
	return err
}
