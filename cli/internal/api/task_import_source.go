package api

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/url"

	"github.com/Flow-Research/workstream/cli/internal/taskimport"
)

// TaskImportSource reports retained JSON byte custody, never Task creation.
type TaskImportSource struct {
	SourceID  string `json:"source_id"`
	ProjectID string `json:"project_id"`
	SHA256    string `json:"sha256"`
	ByteCount int    `json:"byte_count"`
	MediaType string `json:"media_type"`
	Status    string `json:"status"`
	CreatedAt string `json:"created_at"`
}

func taskImportSourcePath(project string) string {
	return "/api/v1/projects/" + url.PathEscape(project) + "/task-import-sources"
}

// DeclareTaskImportSource commits only the exact original JSON SHA/byte count.
// Source upload and atomic Task import remain separate explicit commands.
func (c *Client) DeclareTaskImportSource(ctx context.Context, project string, body []byte, key string) (Result[TaskImportSource], error) {
	var result Result[TaskImportSource]
	if !validUUID(project) || !validUUID(key) || len(project) > 100 || len(key) > 100 {
		return result, errors.New("PROJECT_ID and --idempotency-key must be UUIDs")
	}
	commitment, err := taskimport.ValidateJSON(body)
	if err != nil {
		return result, err
	}
	request, err := json.Marshal(struct {
		SHA256    string `json:"sha256"`
		ByteCount int    `json:"byte_count"`
	}{commitment.SHA256, commitment.ByteCount})
	if err != nil {
		return result, err
	}
	raw, err := c.requestWithKey(ctx, http.MethodPost, taskImportSourcePath(project), "", request, key, http.StatusCreated)
	if err != nil {
		return result, taskImportSourceFailure(err, "declare")
	}
	result, err = c.decodeTaskImportSource(raw, project, "")
	if err != nil || result.Value.SHA256 != commitment.SHA256 || result.Value.ByteCount != commitment.ByteCount {
		return Result[TaskImportSource]{}, taskImportSourceFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true}, "declare")
	}
	return result, nil
}

// UploadTaskImportSource sends the unchanged validated JSON once to the explicit
// retained source. It does not declare a source or create/screen/release Tasks.
func (c *Client) UploadTaskImportSource(ctx context.Context, project, source string, body []byte) (Result[TaskImportSource], error) {
	var result Result[TaskImportSource]
	if !validUUID(project) || !validUUID(source) || len(project) > 100 || len(source) > 100 {
		return result, errors.New("PROJECT_ID and SOURCE_ID must be UUIDs")
	}
	commitment, err := taskimport.ValidateJSON(body)
	if err != nil {
		return result, err
	}
	raw, err := c.requestWithKey(ctx, http.MethodPut, taskImportSourcePath(project)+"/"+url.PathEscape(source)+"/content", "", body, "", http.StatusOK)
	if err != nil {
		return result, taskImportSourceFailure(err, "upload")
	}
	result, err = c.decodeTaskImportSource(raw, project, source)
	if err != nil || result.Value.SHA256 != commitment.SHA256 || result.Value.ByteCount != commitment.ByteCount {
		return Result[TaskImportSource]{}, taskImportSourceFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true}, "upload")
	}
	return result, nil
}

func (c *Client) TaskImportSourceStatus(ctx context.Context, project, source string) (Result[TaskImportSource], error) {
	var result Result[TaskImportSource]
	if !validUUID(project) || !validUUID(source) || len(project) > 100 || len(source) > 100 {
		return result, errors.New("PROJECT_ID and SOURCE_ID must be UUIDs")
	}
	raw, err := c.request(ctx, http.MethodGet, taskImportSourcePath(project)+"/"+url.PathEscape(source), "", nil)
	if err != nil {
		return result, err
	}
	return c.decodeTaskImportSource(raw, project, source)
}

func (c *Client) decodeTaskImportSource(raw json.RawMessage, project, source string) (Result[TaskImportSource], error) {
	var value TaskImportSource
	_, err := contextObject(raw, &value, []string{"source_id", "project_id", "sha256", "byte_count", "media_type", "status", "created_at"}, nil)
	status := map[string]bool{
		"declared": true, "prepared": true, "put_in_flight": true, "acknowledgement_unknown": true,
		"object_confirmed": true, "absent_replay_required": true, "integrity_mismatch": true,
		"provider_unavailable": true, "conflict": true, "verified": true, "missing": true,
	}
	if err != nil || !validUUID(value.SourceID) || !sameUUID(value.ProjectID, project) ||
		(source != "" && !sameUUID(value.SourceID, source)) || !contextPolicyDigest.MatchString(value.SHA256) ||
		value.ByteCount < 1 || value.ByteCount > taskimport.MaxBytes || value.MediaType != "application/json" ||
		!status[value.Status] || !validTime(value.CreatedAt) {
		return Result[TaskImportSource]{}, &Failure{Code: "invalid_api_response"}
	}
	for _, metadata := range []string{value.SourceID, value.ProjectID, value.SHA256, value.MediaType, value.Status, value.CreatedAt} {
		if !c.safeMetadata(metadata) || sameUUID(metadata, c.token) {
			return Result[TaskImportSource]{}, &Failure{Code: "invalid_api_response"}
		}
	}
	return Result[TaskImportSource]{Raw: raw, Value: value}, nil
}

func taskImportSourceFailure(err error, operation string) error {
	var failure *Failure
	if errors.As(err, &failure) && failure.OutcomeUnknown {
		if operation == "declare" {
			failure.RecoveryHint = "source declaration outcome unknown; manually replay only the unchanged project, JSON file bytes and idempotency key"
		} else {
			failure.RecoveryHint = "source upload outcome unknown; inspect source-status, then manually replay only the unchanged project, source and JSON file bytes"
		}
	}
	return err
}
