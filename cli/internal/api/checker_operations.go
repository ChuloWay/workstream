package api

import (
	"bytes"
	"context"
	"encoding/json"
	jsonv2 "encoding/json/v2"
	"errors"
	"math"
	"math/big"
	"net/http"
	"net/url"
	"reflect"
	"strconv"
	"strings"
	"unicode/utf8"
)

// CheckerRegistrySpec is the exact caller-selected immutable specification.
// Publication does not select or enable a checker for a guide.
type CheckerRegistrySpec struct {
	CapabilityID        string                        `json:"capability_id"`
	CapabilityVersion   string                        `json:"capability_version"`
	Phase               string                        `json:"phase"`
	ImageDigest         string                        `json:"image_digest"`
	ConfigurationSchema ExternalCheckerSchema         `json:"configuration_schema"`
	InputSchema         ExternalCheckerSchema         `json:"input_schema"`
	OutputSchema        ExternalCheckerSchema         `json:"output_schema"`
	Resources           ExternalCheckerResourceLimits `json:"resources"`
}

func checkerSpec(raw json.RawMessage) (CheckerRegistrySpec, error) {
	var value CheckerRegistrySpec
	fields, err := contextObject(raw, &value, []string{
		"capability_id", "capability_version", "phase", "image_digest", "configuration_schema", "input_schema", "output_schema", "resources",
	}, nil)
	if err != nil || !postPolicyIdentifier.MatchString(value.CapabilityID) || !postPolicySchemaVersion.MatchString(value.CapabilityVersion) ||
		(value.Phase != "pre_submit" && value.Phase != "post_submit") || !contextPolicyDigest.MatchString(value.ImageDigest) {
		return value, errors.New("invalid checker registry specification")
	}
	inputID := "external_checker_pre_submit_input"
	if value.Phase == "post_submit" {
		inputID = "external_checker_post_submit_input"
	}
	if validateExternalCheckerSchema(fields["configuration_schema"], &value.ConfigurationSchema, "") != nil ||
		validateExternalCheckerSchema(fields["input_schema"], &value.InputSchema, inputID) != nil ||
		validateExternalCheckerSchema(fields["output_schema"], &value.OutputSchema, "external_checker_result") != nil ||
		validateExternalCheckerResources(fields["resources"], &value.Resources) != nil {
		return value, errors.New("invalid checker registry specification")
	}
	return value, nil
}

func checkerEntry(raw json.RawMessage, selectedID, operationID string) (ExternalCheckerRegistryEntry, error) {
	var entry ExternalCheckerRegistryEntry
	fields, err := contextObject(raw, &entry, []string{
		"capability_id", "capability_version", "phase", "image_digest", "configuration_schema", "input_schema", "output_schema", "resources",
		"registry_entry_id", "entry_digest", "registration_operation_id", "registered_by_actor_profile_id", "authorization_decision_event_id", "created_at",
	}, nil)
	if err != nil || !validUUID(entry.RegistryEntryID) || !validUUID(entry.RegistrationOperationID) ||
		!validUUID(entry.RegisteredByActorProfileID) || !validUUID(entry.AuthorizationDecisionEventID) ||
		!validTime(entry.CreatedAt) || !contextPolicyDigest.MatchString(entry.EntryDigest) ||
		(selectedID != "" && !sameUUID(selectedID, entry.RegistryEntryID)) ||
		(operationID != "" && !sameUUID(operationID, entry.RegistrationOperationID)) {
		return entry, errors.New("invalid checker registry entry")
	}
	identity, _ := uuidIdentity(entry.RegistryEntryID)
	if identity[6]>>4 != 7 || identity[8]&0xc0 != 0x80 {
		return entry, errors.New("invalid checker registry entry ID")
	}
	specFields := map[string]json.RawMessage{}
	for _, key := range []string{"capability_id", "capability_version", "phase", "image_digest", "configuration_schema", "input_schema", "output_schema", "resources"} {
		specFields[key] = fields[key]
	}
	specRaw, _ := json.Marshal(specFields)
	if _, err := checkerSpec(specRaw); err != nil {
		return entry, err
	}
	return entry, nil
}

func checkerMutationFailure(err error, hint string) error {
	var failure *Failure
	if errors.As(err, &failure) && failure.OutcomeUnknown {
		copy := *failure
		copy.RecoveryHint = hint
		return &copy
	}
	return err
}

func (c *Client) RegisterExternalChecker(ctx context.Context, body json.RawMessage, key string) (Result[ExternalCheckerRegistryEntry], error) {
	var result Result[ExternalCheckerRegistryEntry]
	if !validUUID(key) || len(key) > 100 {
		return result, errors.New("--idempotency-key must be a UUID")
	}
	if len(body) == 0 || len(body) > MaxGuideInputBytes {
		return result, errors.New("--input must contain a bounded checker registry specification")
	}
	submitted, err := checkerSpec(body)
	if err != nil {
		return result, err
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodPost, "/api/v1/operations/external-checker-registry", "", body, key, http.StatusCreated, MaxGuideInputBytes)
	if err != nil {
		return result, checkerMutationFailure(err, "registration outcome unknown; inspect the exact entry if known, then manually replay the unchanged input and key")
	}
	entry, err := checkerEntry(raw, "", key)
	if err != nil || !c.safeMutationResponse(raw) {
		return result, checkerMutationFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true}, "registration outcome unknown; manually replay the unchanged input and key")
	}
	if !sameCheckerSpec(submitted, entry) {
		return result, checkerMutationFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true}, "registration outcome unknown; manually replay the unchanged input and key")
	}
	return Result[ExternalCheckerRegistryEntry]{Raw: raw, Value: entry}, nil
}

func sameCheckerSpec(spec CheckerRegistrySpec, entry ExternalCheckerRegistryEntry) bool {
	return spec.CapabilityID == entry.CapabilityID && spec.CapabilityVersion == entry.CapabilityVersion &&
		spec.Phase == entry.Phase && spec.ImageDigest == entry.ImageDigest &&
		sameCheckerSchema(spec.ConfigurationSchema, entry.ConfigurationSchema) &&
		sameCheckerSchema(spec.InputSchema, entry.InputSchema) && sameCheckerSchema(spec.OutputSchema, entry.OutputSchema) &&
		spec.Resources.CPUMillis.Cmp(entry.Resources.CPUMillis) == 0 &&
		spec.Resources.MemoryBytes.Cmp(entry.Resources.MemoryBytes) == 0 &&
		spec.Resources.DeadlineMillis.Cmp(entry.Resources.DeadlineMillis) == 0 &&
		spec.Resources.MaximumOutputBytes.Cmp(entry.Resources.MaximumOutputBytes) == 0
}

func sameCheckerSchema(left, right ExternalCheckerSchema) bool {
	if left.SchemaID != right.SchemaID || left.SchemaVersion != right.SchemaVersion || left.SchemaHash != right.SchemaHash {
		return false
	}
	// Compare the submitted and returned JSON values, not their formatting.
	// Canonical digest computation and JSON Schema validity remain backend-owned.
	submitted, leftErr := checkerDocumentIdentity(left.Document)
	returned, rightErr := checkerDocumentIdentity(right.Document)
	return leftErr == nil && rightErr == nil && reflect.DeepEqual(submitted, returned)
}

type checkerNumberIdentity string

func checkerDocumentIdentity(raw json.RawMessage) (any, error) {
	// The ordinary v2 `any` decoder loses integer precision above 2^53.
	// Preserve integer precision while comparing the decimal values that the
	// backend may persist through PostgreSQL JSONB. This is equality, not a
	// digest canonicalizer.
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var value any
	if err := decoder.Decode(&value); err != nil {
		return nil, err
	}
	return checkerParsedIdentity(value)
}

func checkerParsedIdentity(value any) (any, error) {
	switch item := value.(type) {
	case map[string]any:
		for key, child := range item {
			identity, err := checkerParsedIdentity(child)
			if err != nil {
				return nil, err
			}
			item[key] = identity
		}
	case []any:
		for index, child := range item {
			identity, err := checkerParsedIdentity(child)
			if err != nil {
				return nil, err
			}
			item[index] = identity
		}
	case json.Number:
		literal := item.String()
		if !strings.ContainsAny(literal, ".eE") {
			integer, ok := new(big.Int).SetString(literal, 10)
			if !ok {
				return nil, errors.New("invalid checker integer")
			}
			return checkerNumberIdentity(integer.String()), nil
		}
		floating, err := strconv.ParseFloat(literal, 64)
		if err != nil || math.IsNaN(floating) || math.IsInf(floating, 0) {
			return nil, errors.New("invalid checker float")
		}
		// Python's JSON float parser rounds to binary64 before PostgreSQL
		// stores its decimal form. Rat keeps the resulting decimal comparison
		// lossless, including 1e20 versus its integer spelling and signed zero.
		decimal := strconv.FormatFloat(floating, 'f', -1, 64)
		rational, ok := new(big.Rat).SetString(decimal)
		if !ok {
			return nil, errors.New("invalid checker float")
		}
		return checkerNumberIdentity(rational.RatString()), nil
	}
	return value, nil
}

func (c *Client) ReadExternalChecker(ctx context.Context, registryEntryID string) (Result[ExternalCheckerRegistryEntry], error) {
	var result Result[ExternalCheckerRegistryEntry]
	if !validUUID(registryEntryID) || len(registryEntryID) > 100 {
		return result, errors.New("ENTRY_ID must be a UUID")
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet, "/api/v1/operations/external-checker-registry/"+url.PathEscape(registryEntryID), "", nil, "", http.StatusOK, MaxGuideInputBytes)
	if err != nil {
		return result, err
	}
	entry, err := checkerEntry(raw, registryEntryID, "")
	if err != nil || !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[ExternalCheckerRegistryEntry]{Raw: raw, Value: entry}, nil
}

type CheckerRetrySource struct {
	ProjectID                string   `json:"project_id"`
	TaskID                   string   `json:"task_id"`
	SubmissionID             string   `json:"submission_id"`
	SubmissionVersion        *big.Int `json:"submission_version"`
	SourceRunID              string   `json:"source_run_id"`
	SourceRequestID          string   `json:"source_request_id"`
	SourceRequestDigest      string   `json:"source_request_digest"`
	SourceResultID           string   `json:"source_result_id"`
	SourceResultDigest       string   `json:"source_result_digest"`
	SourceFinalizeEvidenceID string   `json:"source_finalize_evidence_id"`
	SourceGeneration         *big.Int `json:"source_generation"`
	FailureCode              string   `json:"failure_code"`
}

type CheckerRetrySuccessor struct {
	RequestID     string   `json:"request_id"`
	RequestDigest string   `json:"request_digest"`
	RunID         string   `json:"run_id"`
	ResultID      string   `json:"result_id"`
	Generation    *big.Int `json:"generation"`
	EventID       string   `json:"event_id"`
	AuditEventID  string   `json:"audit_event_id"`
}

type CheckerRetrySourceItem struct {
	Source                  CheckerRetrySource              `json:"source"`
	RecoveryState           string                          `json:"recovery_state"`
	CreatedAt               string                          `json:"created_at"`
	CompletedAt             string                          `json:"completed_at"`
	RetryReceiptID          *string                         `json:"retry_receipt_id"`
	Successor               *CheckerRetrySuccessor          `json:"successor"`
	ModelRecoveryCandidates []CheckerModelRecoveryCandidate `json:"model_recovery_candidates"`
}

type CheckerRetrySourcePage struct {
	ProjectID  string                   `json:"project_id"`
	Items      []CheckerRetrySourceItem `json:"items"`
	NextCursor *string                  `json:"next_cursor"`
}

type CheckerRetryReceipt struct {
	ReceiptID               string                `json:"receipt_id"`
	Source                  CheckerRetrySource    `json:"source"`
	Successor               CheckerRetrySuccessor `json:"successor"`
	AuthorizationDecisionID string                `json:"authorization_decision_id"`
}

func validCheckerSource(raw json.RawMessage, source *CheckerRetrySource, project, run string) bool {
	_, err := contextObject(raw, source, []string{
		"project_id", "task_id", "submission_id", "submission_version", "source_run_id", "source_request_id", "source_request_digest", "source_result_id", "source_result_digest", "source_finalize_evidence_id", "source_generation", "failure_code",
	}, nil)
	if err != nil || !sameUUID(source.ProjectID, project) || (run != "" && !sameUUID(source.SourceRunID, run)) ||
		!boundedInteger(source.SubmissionVersion, 1, 2_147_483_647) || !boundedInteger(source.SourceGeneration, 1, 2_147_483_647) ||
		!contextPolicyDigest.MatchString(source.SourceRequestDigest) || !contextPolicyDigest.MatchString(source.SourceResultDigest) ||
		utf8.RuneCountInString(source.FailureCode) < 1 || utf8.RuneCountInString(source.FailureCode) > 100 {
		return false
	}
	for _, id := range []string{source.TaskID, source.SubmissionID, source.SourceRunID, source.SourceRequestID, source.SourceResultID, source.SourceFinalizeEvidenceID} {
		if !validUUID(id) {
			return false
		}
	}
	return true
}

func validCheckerSuccessor(raw json.RawMessage, successor *CheckerRetrySuccessor) bool {
	_, err := contextObject(raw, successor, []string{"request_id", "request_digest", "run_id", "result_id", "generation", "event_id", "audit_event_id"}, nil)
	if err != nil || !contextPolicyDigest.MatchString(successor.RequestDigest) || !boundedInteger(successor.Generation, 1, 2_147_483_647) {
		return false
	}
	for _, id := range []string{successor.RequestID, successor.RunID, successor.ResultID, successor.EventID, successor.AuditEventID} {
		if !validUUID(id) {
			return false
		}
	}
	return true
}

func validCheckerRetryLineage(source *CheckerRetrySource, successor *CheckerRetrySuccessor) bool {
	if source == nil || successor == nil || source.SourceGeneration == nil || successor.Generation == nil ||
		successor.Generation.Cmp(new(big.Int).Add(source.SourceGeneration, big.NewInt(1))) != 0 {
		return false
	}
	// A retry creates three new records. Reusing any source or successor
	// record identity would make the receipt claim a false lineage.
	seen := map[[16]byte]bool{}
	for _, id := range []string{
		source.SourceRequestID, source.SourceRunID, source.SourceResultID,
		successor.RequestID, successor.RunID, successor.ResultID,
	} {
		identity, valid := uuidIdentity(id)
		if !valid || seen[identity] {
			return false
		}
		seen[identity] = true
	}
	return true
}

func (c *Client) CheckerRetrySources(ctx context.Context, project string, limit int, cursor string) (Result[CheckerRetrySourcePage], error) {
	var result Result[CheckerRetrySourcePage]
	if !validUUID(project) || len(project) > 100 || limit < 1 || limit > 100 || len(cursor) > 512 {
		return result, errors.New("PROJECT_ID must be a UUID, --limit 1..100, and --cursor at most 512 bytes")
	}
	query := url.Values{"limit": {strconv.Itoa(limit)}}
	if cursor != "" {
		query.Set("cursor", cursor)
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet, "/api/v1/operations/projects/"+url.PathEscape(project)+"/checker-retry-sources", query.Encode(), nil, "", http.StatusOK, MaxGuideInputBytes)
	if err != nil {
		return result, err
	}
	var page CheckerRetrySourcePage
	fields, err := contextObject(raw, &page, []string{"project_id", "items"}, nil)
	if err != nil || !requiredNullable(fields, "next_cursor") || !sameUUID(page.ProjectID, project) || page.Items == nil || len(page.Items) > limit || !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	if page.NextCursor != nil && (*page.NextCursor == "" || len(*page.NextCursor) > 512) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	var itemRaw []json.RawMessage
	if jsonv2.Unmarshal(fields["items"], &itemRaw) != nil || len(itemRaw) != len(page.Items) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	seen := map[[16]byte]bool{}
	for i, item := range page.Items {
		var wire CheckerRetrySourceItem
		parts, err := contextObject(itemRaw[i], &wire, []string{"source", "recovery_state", "created_at", "completed_at", "model_recovery_candidates"}, nil)
		if err != nil || !requiredNullable(parts, "retry_receipt_id", "successor") ||
			!validCheckerSource(parts["source"], &item.Source, project, "") || !validTime(item.CreatedAt) || !validTime(item.CompletedAt) ||
			(item.RecoveryState != "eligible" && item.RecoveryState != "retried" && item.RecoveryState != "not_current") ||
			(item.RetryReceiptID == nil) != (item.Successor == nil) || (item.RecoveryState == "retried") != (item.RetryReceiptID != nil) {
			return result, &Failure{Code: "invalid_api_response"}
		}
		if !validCheckerModelRecoveryCandidates(parts["model_recovery_candidates"], &item) {
			return result, &Failure{Code: "invalid_api_response"}
		}
		if item.RetryReceiptID != nil {
			if !validUUID(*item.RetryReceiptID) || !validCheckerSuccessor(parts["successor"], item.Successor) ||
				!validCheckerRetryLineage(&item.Source, item.Successor) {
				return result, &Failure{Code: "invalid_api_response"}
			}
		}
		id, _ := uuidIdentity(item.Source.SourceRunID)
		if seen[id] {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[id] = true
	}
	return Result[CheckerRetrySourcePage]{Raw: raw, Value: page}, nil
}

func ValidCheckerRetryReason(reason string) bool {
	if !utf8.ValidString(reason) || utf8.RuneCountInString(reason) < 1 || utf8.RuneCountInString(reason) > 500 || strings.TrimSpace(reason) == "" {
		return false
	}
	for _, r := range reason {
		if r < 32 || r == 127 {
			return false
		}
	}
	return true
}

func (c *Client) RetryChecker(ctx context.Context, project, sourceRun, reason, key string) (Result[CheckerRetryReceipt], error) {
	var result Result[CheckerRetryReceipt]
	if !validUUID(project) || !validUUID(sourceRun) || len(project) > 100 || len(sourceRun) > 100 || !validUUID(key) || len(key) > 100 {
		return result, errors.New("PROJECT_ID, SOURCE_RUN_ID and --idempotency-key must be UUIDs")
	}
	if !ValidCheckerRetryReason(reason) {
		return result, errors.New("--reason must be 1..500 characters without ASCII controls")
	}
	body, _ := json.Marshal(struct {
		Reason string `json:"reason"`
	}{reason})
	path := "/api/v1/operations/projects/" + url.PathEscape(project) + "/checker-runs/" + url.PathEscape(sourceRun) + "/retry"
	raw, err := c.requestWithKey(ctx, http.MethodPost, path, "", body, key, http.StatusCreated)
	if err != nil {
		return result, checkerMutationFailure(err, "retry outcome unknown; manually replay the exact project, run, reason and key")
	}
	var receipt CheckerRetryReceipt
	fields, err := contextObject(raw, &receipt, []string{"receipt_id", "source", "successor", "authorization_decision_id"}, nil)
	if err != nil || !validUUID(receipt.ReceiptID) || !validUUID(receipt.AuthorizationDecisionID) ||
		!validCheckerSource(fields["source"], &receipt.Source, project, sourceRun) ||
		!validCheckerSuccessor(fields["successor"], &receipt.Successor) ||
		!validCheckerRetryLineage(&receipt.Source, &receipt.Successor) || !c.safeMutationResponse(raw) {
		return result, checkerMutationFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true}, "retry outcome unknown; manually replay the exact project, run, reason and key")
	}
	return Result[CheckerRetryReceipt]{Raw: raw, Value: receipt}, nil
}
