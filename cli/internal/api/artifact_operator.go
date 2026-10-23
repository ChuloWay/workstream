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
	"unicode/utf8"
)

const artifactOperatorPath = "/api/v1/operator/artifacts"

// These projections contain public diagnosis facts, never provider coordinates.
// Server-owned states remain observations, not client-side lifecycle decisions.
type ArtifactBinding struct {
	ID                  string   `json:"id"`
	ContentID           string   `json:"content_id"`
	ProjectID           string   `json:"project_id"`
	ResourceType        string   `json:"resource_type"`
	ResourceID          string   `json:"resource_id"`
	LogicalRole         string   `json:"logical_role"`
	ScopeVersion        *big.Int `json:"scope_version"`
	SupersedesBindingID *string  `json:"supersedes_binding_id"`
	CreatedAt           string   `json:"created_at"`
}

type ArtifactReplica struct {
	ID                string  `json:"id"`
	ContentID         string  `json:"content_id"`
	VerificationState string  `json:"verification_state"`
	AvailabilityState string  `json:"availability_state"`
	IntegrityState    string  `json:"integrity_state"`
	LastReconciledAt  *string `json:"last_reconciled_at"`
	CreatedAt         string  `json:"created_at"`
	UpdatedAt         string  `json:"updated_at"`
}

type ArtifactReceipt struct {
	ID                  string   `json:"id"`
	ReceiptType         string   `json:"receipt_type"`
	ReplicaID           string   `json:"replica_id"`
	Outcome             string   `json:"outcome"`
	Replayed            *bool    `json:"replayed,omitempty"`
	AttemptNumber       *big.Int `json:"attempt_number,omitempty"`
	ExecutionGeneration *big.Int `json:"execution_generation,omitempty"`
	VerificationJobID   *string  `json:"verification_job_id,omitempty"`
	CreatedAt           string   `json:"created_at"`
}

type ArtifactVerificationJob struct {
	ID                      string   `json:"id"`
	ReplicaID               string   `json:"replica_id"`
	ParentVerificationJobID *string  `json:"parent_verification_job_id"`
	Status                  string   `json:"status"`
	AttemptCount            *big.Int `json:"attempt_count"`
	MaximumAttempts         *big.Int `json:"maximum_attempts"`
	NextRunAt               *string  `json:"next_run_at"`
	CASVersion              *big.Int `json:"cas_version"`
	TerminalResultCode      *string  `json:"terminal_result_code"`
	TerminalAt              *string  `json:"terminal_at"`
	ReceiptID               *string  `json:"receipt_id"`
	CreatedAt               string   `json:"created_at"`
	UpdatedAt               string   `json:"updated_at"`
}

type ArtifactRecoveryAttempt struct {
	ID                          string   `json:"id"`
	ProjectID                   string   `json:"project_id"`
	TaskID                      *string  `json:"task_id"`
	SubmissionID                *string  `json:"submission_id"`
	SourceVerificationJobID     string   `json:"source_verification_job_id"`
	SourceVerificationJobStatus string   `json:"source_verification_job_status"`
	RetryVerificationJobID      string   `json:"retry_verification_job_id"`
	RetryVerificationJobStatus  string   `json:"retry_verification_job_status"`
	ParentRecoveryAttemptID     *string  `json:"parent_recovery_attempt_id"`
	Status                      string   `json:"status"`
	TerminalResultCode          *string  `json:"terminal_result_code"`
	InitiationAuditEventID      string   `json:"initiation_audit_event_id"`
	TerminalAuditEventID        *string  `json:"terminal_audit_event_id"`
	CASVersion                  *big.Int `json:"cas_version"`
	CreatedAt                   string   `json:"created_at"`
	TerminalAt                  *string  `json:"terminal_at"`
	UpdatedAt                   string   `json:"updated_at"`
}

type ArtifactAuditEvent struct {
	ID            string  `json:"id"`
	EntityType    string  `json:"entity_type"`
	EntityID      string  `json:"entity_id"`
	EventType     string  `json:"event_type"`
	FromStatus    *string `json:"from_status"`
	ToStatus      *string `json:"to_status"`
	Reason        *string `json:"reason"`
	OccurredAt    *string `json:"occurred_at"`
	CreatedAt     string  `json:"created_at"`
	RequestID     *string `json:"request_id"`
	CorrelationID *string `json:"correlation_id"`
}

type ArtifactAdmissionUsage struct {
	ScopeType            string   `json:"scope_type"`
	ScopeID              string   `json:"scope_id"`
	CountedBytes         *big.Int `json:"counted_bytes"`
	LimitBytes           *big.Int `json:"limit_bytes"`
	RemainingBytes       *big.Int `json:"remaining_bytes"`
	ConfiguredLimitBytes *big.Int `json:"configured_limit_bytes"`
	UnboundReadyCount    *big.Int `json:"unbound_ready_count"`
	UnboundReadyBytes    *big.Int `json:"unbound_ready_bytes"`
	StaleCount           *big.Int `json:"stale_count"`
	StaleBytes           *big.Int `json:"stale_bytes"`
	CASVersion           *big.Int `json:"cas_version"`
	UpdatedAt            string   `json:"updated_at"`
}

type ArtifactReadiness struct {
	Backend         string          `json:"backend"`
	ProviderProfile *string         `json:"provider_profile"`
	Configured      *bool           `json:"configured"`
	Active          *bool           `json:"active"`
	Status          string          `json:"status"`
	Prerequisites   map[string]bool `json:"prerequisites"`
}

type ArtifactRetryReceipt struct {
	RecoveryAttemptID       string `json:"recovery_attempt_id"`
	SourceVerificationJobID string `json:"source_verification_job_id"`
	RetryVerificationJobID  string `json:"retry_verification_job_id"`
	Replayed                *bool  `json:"replayed"`
}

type ArtifactPage[T any] struct {
	Items      []T     `json:"items"`
	NextCursor *string `json:"next_cursor"`
}

type ArtifactRetryInput struct {
	ProjectID                   string
	TaskID                      string
	SubmissionID                *string
	Reason                      string
	ClientIdempotencyKey        string
	ExpectedSourceJobCASVersion string
}

func invalidArtifactResponse() error { return &Failure{Code: "invalid_api_response"} }

func artifactSelector(label, value string) (string, error) {
	if !validUUID(value) || len(value) > 100 {
		return "", errors.New(label + " must be a UUID")
	}
	return url.PathEscape(value), nil
}

func artifactPageQuery(limit int, cursor *string, extra url.Values) (string, error) {
	query, err := taskPageQuery(limit, cursor)
	if err != nil {
		return "", err
	}
	values, _ := url.ParseQuery(query)
	for key, entries := range extra {
		for _, entry := range entries {
			values.Add(key, entry)
		}
	}
	return values.Encode(), nil
}

func artifactPageRead[T any](c *Client, ctx context.Context, path, query string, limit int, cursorMayBeOmitted bool, validate func(json.RawMessage, *T) bool) (Result[ArtifactPage[T]], error) {
	var result Result[ArtifactPage[T]]
	var raw json.RawMessage
	var items []json.RawMessage
	var err error
	if cursorMayBeOmitted {
		// The receipts route alone excludes null response fields. Its final page
		// omits next_cursor, while every other ART list retains the canonical key.
		raw, err = c.requestWithResponseLimit(ctx, http.MethodGet, path, query, nil, "", http.StatusOK, maxSubmissionReadBytes)
		if err == nil {
			var envelope struct {
				Items      []json.RawMessage `json:"items"`
				NextCursor *string           `json:"next_cursor"`
			}
			_, err = contextObject(raw, &envelope, []string{"items"}, nil)
			if err != nil || envelope.Items == nil || len(envelope.Items) > limit ||
				(envelope.NextCursor != nil && (!validTaskCursor(*envelope.NextCursor) || len(envelope.Items) == 0)) || !c.safeMutationResponse(raw) {
				err = invalidArtifactResponse()
			}
			items = envelope.Items
		}
	} else {
		raw, _, items, err = c.readPage(ctx, path, query, limit)
	}
	if err != nil {
		return result, err
	}
	var page ArtifactPage[T]
	if jsonv2.Unmarshal(raw, &page, jsonv2.RejectUnknownMembers(true)) != nil || len(page.Items) != len(items) {
		return result, invalidArtifactResponse()
	}
	for index := range page.Items {
		if !validate(items[index], &page.Items[index]) {
			return result, invalidArtifactResponse()
		}
	}
	return Result[ArtifactPage[T]]{Raw: raw, Value: page}, nil
}

func artifactObject[T any](c *Client, ctx context.Context, path string, validate func(json.RawMessage, *T) bool) (Result[T], error) {
	var result Result[T]
	raw, err := c.request(ctx, http.MethodGet, path, "", nil)
	if err != nil {
		return result, err
	}
	var value T
	if !validate(raw, &value) || !c.safeMutationResponse(raw) {
		return result, invalidArtifactResponse()
	}
	return Result[T]{Raw: raw, Value: value}, nil
}

func artifactText(value string) bool { return value != "" && utf8.ValidString(value) }

var artifactBindingTypes = []string{"project", "project_guide", "guide_source_snapshot", "guide_source_snapshot_item", "task", "submission", "checker_run"}
var artifactAuditTypes = []string{"artifact_binding", "artifact_content", "artifact_replica", "artifact_receipt", "artifact_verification_job", "artifact_recovery_attempt"}

func (c *Client) ArtifactBindings(ctx context.Context, resourceType, resourceID string, limit int, cursor *string) (Result[ArtifactPage[ArtifactBinding]], error) {
	var result Result[ArtifactPage[ArtifactBinding]]
	if !oneOf(resourceType, artifactBindingTypes...) {
		return result, errors.New("RESOURCE_TYPE is not a supported artifact binding resource")
	}
	if _, err := artifactSelector("RESOURCE_ID", resourceID); err != nil {
		return result, err
	}
	query, err := artifactPageQuery(limit, cursor, url.Values{"resource_type": {resourceType}, "resource_id": {resourceID}})
	if err != nil {
		return result, err
	}
	return artifactPageRead(c, ctx, artifactOperatorPath+"/bindings", query, limit, false, func(raw json.RawMessage, value *ArtifactBinding) bool {
		fields, err := contextObject(raw, value, []string{"id", "content_id", "project_id", "resource_type", "resource_id", "logical_role", "scope_version", "created_at"}, nil)
		return err == nil && requiredNullable(fields, "supersedes_binding_id") && validUUID(value.ID) && validUUID(value.ContentID) && validUUID(value.ProjectID) &&
			value.ResourceType == resourceType && sameUUID(value.ResourceID, resourceID) && (resourceType != "project" || sameUUID(value.ProjectID, resourceID)) &&
			artifactText(value.LogicalRole) && nonNegative(value.ScopeVersion) && value.ScopeVersion.Sign() > 0 &&
			optionalUUID(value.SupersedesBindingID) && validTime(value.CreatedAt)
	})
}

func (c *Client) ArtifactReplicas(ctx context.Context, contentID string, limit int, cursor *string) (Result[ArtifactPage[ArtifactReplica]], error) {
	var result Result[ArtifactPage[ArtifactReplica]]
	selector, err := artifactSelector("CONTENT_ID", contentID)
	if err != nil {
		return result, err
	}
	query, err := artifactPageQuery(limit, cursor, nil)
	if err != nil {
		return result, err
	}
	return artifactPageRead(c, ctx, artifactOperatorPath+"/contents/"+selector+"/replicas", query, limit, false, func(raw json.RawMessage, value *ArtifactReplica) bool {
		fields, err := contextObject(raw, value, []string{"id", "content_id", "verification_state", "availability_state", "integrity_state", "created_at", "updated_at"}, nil)
		return err == nil && requiredNullable(fields, "last_reconciled_at") && validUUID(value.ID) && sameUUID(value.ContentID, contentID) &&
			artifactText(value.VerificationState) && artifactText(value.AvailabilityState) && artifactText(value.IntegrityState) &&
			optionalTime(value.LastReconciledAt) && validTime(value.CreatedAt) && validTime(value.UpdatedAt)
	})
}

func (c *Client) ArtifactReceipts(ctx context.Context, replicaID string, limit int, cursor *string) (Result[ArtifactPage[ArtifactReceipt]], error) {
	var result Result[ArtifactPage[ArtifactReceipt]]
	selector, err := artifactSelector("REPLICA_ID", replicaID)
	if err != nil {
		return result, err
	}
	query, err := artifactPageQuery(limit, cursor, nil)
	if err != nil {
		return result, err
	}
	return artifactPageRead(c, ctx, artifactOperatorPath+"/replicas/"+selector+"/receipts", query, limit, true, func(raw json.RawMessage, value *ArtifactReceipt) bool {
		_, err := contextObject(raw, value, []string{"id", "receipt_type", "replica_id", "outcome", "created_at"}, nil)
		return err == nil && validUUID(value.ID) && sameUUID(value.ReplicaID, replicaID) && oneOf(value.ReceiptType, "put", "put_observation", "verification") &&
			artifactText(value.Outcome) && validTime(value.CreatedAt) && optionalUUID(value.VerificationJobID) &&
			(value.AttemptNumber == nil || value.AttemptNumber.Sign() >= 0) &&
			(value.ExecutionGeneration == nil || value.ExecutionGeneration.Sign() >= 0)
	})
}

func (c *Client) ArtifactVerificationJob(ctx context.Context, jobID string) (Result[ArtifactVerificationJob], error) {
	var result Result[ArtifactVerificationJob]
	selector, err := artifactSelector("JOB_ID", jobID)
	if err != nil {
		return result, err
	}
	return artifactObject(c, ctx, artifactOperatorPath+"/verification-jobs/"+selector, func(raw json.RawMessage, value *ArtifactVerificationJob) bool {
		fields, err := contextObject(raw, value, []string{"id", "replica_id", "status", "attempt_count", "maximum_attempts", "cas_version", "created_at", "updated_at"}, nil)
		return err == nil && requiredNullable(fields, "parent_verification_job_id", "next_run_at", "terminal_result_code", "terminal_at", "receipt_id") &&
			sameUUID(value.ID, jobID) && validUUID(value.ReplicaID) && optionalUUID(value.ParentVerificationJobID) && optionalUUID(value.ReceiptID) &&
			artifactText(value.Status) && nonNegative(value.AttemptCount, value.MaximumAttempts, value.CASVersion) &&
			value.MaximumAttempts.Sign() > 0 && optionalTime(value.NextRunAt) && optionalTime(value.TerminalAt) &&
			validTime(value.CreatedAt) && validTime(value.UpdatedAt)
	})
}

func (c *Client) ArtifactRecoveryAttempt(ctx context.Context, attemptID string) (Result[ArtifactRecoveryAttempt], error) {
	var result Result[ArtifactRecoveryAttempt]
	selector, err := artifactSelector("ATTEMPT_ID", attemptID)
	if err != nil {
		return result, err
	}
	return artifactObject(c, ctx, artifactOperatorPath+"/recovery-attempts/"+selector, func(raw json.RawMessage, value *ArtifactRecoveryAttempt) bool {
		fields, err := contextObject(raw, value, []string{"id", "project_id", "source_verification_job_id", "source_verification_job_status", "retry_verification_job_id", "retry_verification_job_status", "status", "initiation_audit_event_id", "cas_version", "created_at", "updated_at"}, nil)
		return err == nil && requiredNullable(fields, "task_id", "submission_id", "parent_recovery_attempt_id", "terminal_result_code", "terminal_audit_event_id", "terminal_at") &&
			sameUUID(value.ID, attemptID) && validUUID(value.ProjectID) && validUUID(value.SourceVerificationJobID) && validUUID(value.RetryVerificationJobID) &&
			!sameUUID(value.ID, value.SourceVerificationJobID) && !sameUUID(value.ID, value.RetryVerificationJobID) &&
			!sameUUID(value.SourceVerificationJobID, value.RetryVerificationJobID) &&
			validUUID(value.InitiationAuditEventID) && optionalUUID(value.TaskID) && optionalUUID(value.SubmissionID) &&
			optionalUUID(value.ParentRecoveryAttemptID) && optionalUUID(value.TerminalAuditEventID) &&
			artifactText(value.SourceVerificationJobStatus) && artifactText(value.RetryVerificationJobStatus) && artifactText(value.Status) &&
			nonNegative(value.CASVersion) && validTime(value.CreatedAt) && validTime(value.UpdatedAt) && optionalTime(value.TerminalAt)
	})
}

func (c *Client) ArtifactAuditEvents(ctx context.Context, resourceType, resourceID string, limit int, cursor *string) (Result[ArtifactPage[ArtifactAuditEvent]], error) {
	var result Result[ArtifactPage[ArtifactAuditEvent]]
	if !oneOf(resourceType, artifactAuditTypes...) {
		return result, errors.New("RESOURCE_TYPE is not a supported artifact audit resource")
	}
	if _, err := artifactSelector("RESOURCE_ID", resourceID); err != nil {
		return result, err
	}
	query, err := artifactPageQuery(limit, cursor, url.Values{"resource_type": {resourceType}, "resource_id": {resourceID}})
	if err != nil {
		return result, err
	}
	return artifactPageRead(c, ctx, artifactOperatorPath+"/audit-events", query, limit, false, func(raw json.RawMessage, value *ArtifactAuditEvent) bool {
		fields, err := contextObject(raw, value, []string{"id", "entity_type", "entity_id", "event_type", "created_at"}, nil)
		return err == nil && requiredNullable(fields, "from_status", "to_status", "reason", "occurred_at", "request_id", "correlation_id") &&
			validUUID(value.ID) && value.EntityType == resourceType && sameUUID(value.EntityID, resourceID) && artifactText(value.EventType) &&
			validTime(value.CreatedAt) && optionalTime(value.OccurredAt) && optionalUUID(value.RequestID) && optionalUUID(value.CorrelationID)
	})
}

func (c *Client) ArtifactAdmissionUsage(ctx context.Context, projectID string, taskID *string, limit int, cursor *string) (Result[ArtifactPage[ArtifactAdmissionUsage]], error) {
	var result Result[ArtifactPage[ArtifactAdmissionUsage]]
	if _, err := artifactSelector("PROJECT_ID", projectID); err != nil {
		return result, err
	}
	if taskID != nil {
		if _, err := artifactSelector("TASK_ID", *taskID); err != nil {
			return result, err
		}
	}
	extra := url.Values{"project_id": {projectID}}
	if taskID != nil {
		extra.Set("task_id", *taskID)
	}
	query, err := artifactPageQuery(limit, cursor, extra)
	if err != nil {
		return result, err
	}
	return artifactPageRead(c, ctx, artifactOperatorPath+"/admission-usage", query, limit, false, func(raw json.RawMessage, value *ArtifactAdmissionUsage) bool {
		fields, err := contextObject(raw, value, []string{"scope_type", "scope_id", "counted_bytes", "limit_bytes", "remaining_bytes", "unbound_ready_count", "unbound_ready_bytes", "stale_count", "stale_bytes", "cas_version", "updated_at"}, nil)
		if err != nil || !requiredNullable(fields, "configured_limit_bytes") || !oneOf(value.ScopeType, "deployment", "project", "task") || !artifactText(value.ScopeID) ||
			!nonNegative(value.CountedBytes, value.LimitBytes, value.RemainingBytes, value.UnboundReadyCount, value.UnboundReadyBytes, value.StaleCount, value.StaleBytes, value.CASVersion) ||
			(value.ConfiguredLimitBytes != nil && value.ConfiguredLimitBytes.Sign() < 0) || !validTime(value.UpdatedAt) {
			return false
		}
		switch value.ScopeType {
		case "project":
			return sameUUID(value.ScopeID, projectID)
		case "task":
			return taskID != nil && sameUUID(value.ScopeID, *taskID)
		default:
			return true
		}
	})
}

func (c *Client) ArtifactReadiness(ctx context.Context) (Result[ArtifactReadiness], error) {
	return artifactObject(c, ctx, artifactOperatorPath+"/readiness", func(raw json.RawMessage, value *ArtifactReadiness) bool {
		fields, err := contextObject(raw, value, []string{"backend", "configured", "active", "status", "prerequisites"}, nil)
		if err != nil || !requiredNullable(fields, "provider_profile") || !artifactText(value.Backend) || !artifactText(value.Status) ||
			value.Configured == nil || value.Active == nil || value.Prerequisites == nil ||
			(value.ProviderProfile != nil && !artifactText(*value.ProviderProfile)) {
			return false
		}
		var prerequisites map[string]*bool
		if jsonv2.Unmarshal(fields["prerequisites"], &prerequisites) != nil || prerequisites == nil || len(prerequisites) != len(value.Prerequisites) {
			return false
		}
		for name, present := range prerequisites {
			if !artifactText(name) || present == nil {
				return false
			}
		}
		return true
	})
}

func artifactRetryFailure(err error) error {
	var failure *Failure
	if errors.As(err, &failure) && failure.OutcomeUnknown {
		copy := *failure
		copy.RecoveryHint = "artifact retry outcome unknown; inspect the exact recovery/job as observation only, then manually replay only the unchanged job, project, task, optional submission, reason, idempotency key and source CAS version"
		return &copy
	}
	return err
}

func (c *Client) RetryArtifactVerification(ctx context.Context, jobID string, input ArtifactRetryInput) (Result[ArtifactRetryReceipt], error) {
	var result Result[ArtifactRetryReceipt]
	selector, err := artifactSelector("JOB_ID", jobID)
	if err != nil {
		return result, err
	}
	for label, value := range map[string]string{"PROJECT_ID": input.ProjectID, "TASK_ID": input.TaskID, "--idempotency-key": input.ClientIdempotencyKey} {
		if _, err := artifactSelector(label, value); err != nil {
			return result, err
		}
	}
	if input.SubmissionID != nil {
		if _, err := artifactSelector("SUBMISSION_ID", *input.SubmissionID); err != nil {
			return result, err
		}
	}
	if !utf8.ValidString(input.Reason) || strings.TrimSpace(input.Reason) == "" || utf8.RuneCountInString(input.Reason) > 1000 {
		return result, errors.New("--reason must contain 1–1000 characters and not be blank")
	}
	cas, ok := new(big.Int).SetString(input.ExpectedSourceJobCASVersion, 10)
	if !ok || cas.Sign() < 0 || strings.HasPrefix(input.ExpectedSourceJobCASVersion, "+") || strings.TrimSpace(input.ExpectedSourceJobCASVersion) != input.ExpectedSourceJobCASVersion {
		return result, errors.New("--expected-source-job-cas-version must be a nonnegative integer")
	}
	// Pydantic accepts a JSON integer. Preserve arbitrarily large exact values.
	casValue := json.Number(cas.String())
	body, err := json.Marshal(struct {
		ProjectID                   string      `json:"project_id"`
		TaskID                      string      `json:"task_id"`
		SubmissionID                *string     `json:"submission_id"`
		Reason                      string      `json:"reason"`
		ClientIdempotencyKey        string      `json:"client_idempotency_key"`
		ExpectedSourceJobCASVersion json.Number `json:"expected_source_job_cas_version"`
	}{input.ProjectID, input.TaskID, input.SubmissionID, input.Reason, input.ClientIdempotencyKey, casValue})
	if err != nil {
		return result, errors.New("invalid artifact retry body")
	}
	raw, err := c.requestWithKey(ctx, http.MethodPost, artifactOperatorPath+"/verification-jobs/"+selector+"/retry", "", body, input.ClientIdempotencyKey, http.StatusAccepted)
	if err != nil {
		return result, artifactRetryFailure(err)
	}
	var value ArtifactRetryReceipt
	_, err = contextObject(raw, &value, []string{"recovery_attempt_id", "source_verification_job_id", "retry_verification_job_id", "replayed"}, nil)
	if err != nil || !validUUID(value.RecoveryAttemptID) || !sameUUID(value.SourceVerificationJobID, jobID) ||
		!validUUID(value.RetryVerificationJobID) || sameUUID(value.RecoveryAttemptID, value.SourceVerificationJobID) ||
		sameUUID(value.RecoveryAttemptID, value.RetryVerificationJobID) || sameUUID(value.SourceVerificationJobID, value.RetryVerificationJobID) ||
		value.Replayed == nil || !c.safeMutationResponse(raw) {
		return result, artifactRetryFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true})
	}
	return Result[ArtifactRetryReceipt]{Raw: raw, Value: value}, nil
}
