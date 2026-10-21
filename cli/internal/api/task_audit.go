package api

import (
	"bytes"
	"context"
	"encoding/json"
	jsonv2 "encoding/json/v2"
	"errors"
	"math/big"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

// AuditTaskLockedContext contains only the Audit Authority's historical
// references. The manager-only policy-body summary is not part of this route.
type AuditTaskLockedContext struct {
	TaskID                                             string   `json:"task_id"`
	ProjectID                                          string   `json:"project_id"`
	LockedGuideVersion                                 string   `json:"locked_guide_version"`
	LockedGuideSourceSnapshotID                        string   `json:"locked_guide_source_snapshot_id"`
	LockedGuideSourceSnapshotHash                      string   `json:"locked_guide_source_snapshot_hash"`
	LockedEffectiveProjectSubmissionArtifactPolicyID   string   `json:"locked_effective_project_submission_artifact_policy_id"`
	LockedEffectiveProjectSubmissionArtifactPolicyHash string   `json:"locked_effective_project_submission_artifact_policy_hash"`
	LockedPreSubmitCheckerPolicyID                     string   `json:"locked_pre_submit_checker_policy_id"`
	LockedPreSubmitCheckerBundleHash                   string   `json:"locked_pre_submit_checker_bundle_hash"`
	LockedPostSubmitCheckerPolicyID                    string   `json:"locked_post_submit_checker_policy_id"`
	LockedPostSubmitCheckerPolicyVersion               string   `json:"locked_post_submit_checker_policy_version"`
	LockedPostSubmitCheckerPolicyHash                  string   `json:"locked_post_submit_checker_policy_hash"`
	LockedReviewPolicyID                               string   `json:"locked_review_policy_id"`
	LockedReviewPolicyGeneration                       *big.Int `json:"locked_review_policy_generation"`
	LockedReviewPolicyHash                             string   `json:"locked_review_policy_hash"`
	LockedRevisionPolicyID                             string   `json:"locked_revision_policy_id"`
	LockedRevisionPolicyGeneration                     *big.Int `json:"locked_revision_policy_generation"`
	LockedRevisionPolicyHash                           string   `json:"locked_revision_policy_hash"`
	LockedContributionPolicyVersionID                  string   `json:"locked_contribution_policy_version_id"`
}

var auditLockedFields = []string{
	"task_id", "project_id", "locked_guide_version", "locked_guide_source_snapshot_id",
	"locked_guide_source_snapshot_hash", "locked_effective_project_submission_artifact_policy_id",
	"locked_effective_project_submission_artifact_policy_hash", "locked_pre_submit_checker_policy_id",
	"locked_pre_submit_checker_bundle_hash", "locked_post_submit_checker_policy_id",
	"locked_post_submit_checker_policy_version", "locked_post_submit_checker_policy_hash",
	"locked_review_policy_id", "locked_review_policy_generation", "locked_review_policy_hash",
	"locked_revision_policy_id", "locked_revision_policy_generation", "locked_revision_policy_hash",
	"locked_contribution_policy_version_id",
}

type AuditTaskEvent struct {
	EventID                 string  `json:"event_id"`
	EventType               string  `json:"event_type"`
	FromStatus              *string `json:"from_status"`
	ToStatus                *string `json:"to_status"`
	ActorID                 string  `json:"actor_id"`
	CreatedAt               string  `json:"created_at"`
	AssignmentID            *string `json:"assignment_id"`
	AuthorizationDecisionID *string `json:"authorization_decision_id"`
}

// AuditTaskCursor is the backend's four-field JSON position, not an authority
// token. Every continuation makes a new authorized request.
type AuditTaskCursor struct {
	ProjectID string `json:"project_id"`
	TaskID    string `json:"task_id"`
	CreatedAt string `json:"created_at"`
	EventID   string `json:"event_id"`
}

type AuditTaskEvidencePage struct {
	ProjectID  string           `json:"project_id"`
	TaskID     string           `json:"task_id"`
	Items      []AuditTaskEvent `json:"items"`
	NextCursor *AuditTaskCursor `json:"next_cursor"`
}

func auditTaskPath(project, task, suffix string) (string, error) {
	if !submissionSelector(project) || !submissionSelector(task) {
		return "", errors.New("PROJECT_ID and TASK_ID must be UUIDs")
	}
	return "/api/v1/audit/projects/" + url.PathEscape(project) + "/tasks/" + url.PathEscape(task) + suffix, nil
}

func invalidAuditResponse() error { return &Failure{Code: "invalid_api_response"} }

func (c *Client) AuditLockedContext(ctx context.Context, project, task string) (Result[AuditTaskLockedContext], error) {
	var result Result[AuditTaskLockedContext]
	path, err := auditTaskPath(project, task, "/locked-context")
	if err != nil {
		return result, err
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet, path, "", nil, "", http.StatusOK, maxSubmissionReadBytes)
	if err != nil {
		return result, err
	}
	var value AuditTaskLockedContext
	_, err = contextObject(raw, &value, auditLockedFields, nil)
	if err != nil || !sameUUID(value.ProjectID, project) || !sameUUID(value.TaskID, task) ||
		strings.TrimSpace(value.LockedGuideVersion) == "" || strings.TrimSpace(value.LockedPostSubmitCheckerPolicyVersion) == "" ||
		!positive(value.LockedReviewPolicyGeneration, value.LockedRevisionPolicyGeneration) || !c.safeMutationResponse(raw) {
		return result, invalidAuditResponse()
	}
	for _, id := range []string{
		value.LockedGuideSourceSnapshotID, value.LockedEffectiveProjectSubmissionArtifactPolicyID,
		value.LockedPreSubmitCheckerPolicyID, value.LockedPostSubmitCheckerPolicyID,
		value.LockedReviewPolicyID, value.LockedRevisionPolicyID, value.LockedContributionPolicyVersionID,
	} {
		if !validUUID(id) {
			return result, invalidAuditResponse()
		}
	}
	for _, digest := range []string{
		value.LockedGuideSourceSnapshotHash, value.LockedEffectiveProjectSubmissionArtifactPolicyHash,
		value.LockedPreSubmitCheckerBundleHash, value.LockedPostSubmitCheckerPolicyHash,
		value.LockedReviewPolicyHash, value.LockedRevisionPolicyHash,
	} {
		if !contextPolicyDigest.MatchString(digest) {
			return result, invalidAuditResponse()
		}
	}
	return Result[AuditTaskLockedContext]{Raw: raw, Value: value}, nil
}

func positive(values ...*big.Int) bool {
	for _, value := range values {
		if value == nil || value.Sign() <= 0 {
			return false
		}
	}
	return true
}

// Python's datetime used by the audit API cannot represent year zero. Check
// the parsed timestamp's stated local year, not its UTC-converted year.
func validAuditTime(value string) bool {
	parsed, err := time.Parse(time.RFC3339Nano, value)
	return err == nil && parsed.Year() >= 1 && parsed.Year() <= 9999
}

func auditCursor(raw string, project, task string) error {
	if !validTaskCursor(raw) {
		return errors.New("cursor must be backend next_cursor JSON of at most 512 characters")
	}
	var cursor AuditTaskCursor
	_, err := contextObject(json.RawMessage(raw), &cursor,
		[]string{"project_id", "task_id", "created_at", "event_id"}, nil)
	if err != nil || !sameUUID(cursor.ProjectID, project) || !sameUUID(cursor.TaskID, task) ||
		!validAuditTime(cursor.CreatedAt) || !validUUID(cursor.EventID) {
		return errors.New("cursor must be backend next_cursor JSON for this project and task")
	}
	return nil
}

func validAuditEvent(raw json.RawMessage, value AuditTaskEvent) bool {
	var ignored AuditTaskEvent
	fields, err := contextObject(raw, &ignored, []string{"event_id", "event_type", "actor_id", "created_at"}, nil)
	if err != nil || !requiredNullable(fields, "from_status", "to_status", "assignment_id", "authorization_decision_id") ||
		!validUUID(value.EventID) || !validAuditTime(value.CreatedAt) ||
		!optionalUUID(value.AssignmentID) || !optionalUUID(value.AuthorizationDecisionID) {
		return false
	}
	if oneOf(value.EventType, "TaskCreated", "TaskScreened", "TaskReleased") {
		return value.AssignmentID == nil && value.AuthorizationDecisionID != nil
	}
	return (value.AssignmentID == nil) == (value.AuthorizationDecisionID == nil)
}

func (c *Client) AuditEvidence(ctx context.Context, project, task string, limit int, cursor *string) (Result[AuditTaskEvidencePage], error) {
	var result Result[AuditTaskEvidencePage]
	path, err := auditTaskPath(project, task, "/evidence")
	if err != nil {
		return result, err
	}
	if limit < 1 || limit > 100 {
		return result, errors.New("limit must be 1–100")
	}
	query := url.Values{"limit": {strconv.Itoa(limit)}}
	if cursor != nil {
		if err := auditCursor(*cursor, project, task); err != nil {
			return result, err
		}
		query.Set("cursor", *cursor)
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet, path, query.Encode(), nil, "", http.StatusOK, maxSubmissionReadBytes)
	if err != nil {
		return result, err
	}
	var page AuditTaskEvidencePage
	fields, err := contextObject(raw, &page, []string{"project_id", "task_id", "items"}, nil)
	if err != nil || !requiredNullable(fields, "next_cursor") || page.Items == nil || len(page.Items) > limit ||
		!sameUUID(page.ProjectID, project) || !sameUUID(page.TaskID, task) || !c.safeMutationResponse(raw) {
		return result, invalidAuditResponse()
	}
	var items []json.RawMessage
	if jsonv2.Unmarshal(fields["items"], &items) != nil || items == nil {
		return result, invalidAuditResponse()
	}
	var previousTime time.Time
	var previousID [16]byte
	for index, item := range items {
		value := page.Items[index]
		if !validAuditEvent(item, value) {
			return result, invalidAuditResponse()
		}
		created, _ := time.Parse(time.RFC3339Nano, value.CreatedAt)
		id, _ := uuidIdentity(value.EventID)
		if index > 0 && (created.Before(previousTime) || created.Equal(previousTime) && bytes.Compare(id[:], previousID[:]) <= 0) {
			return result, invalidAuditResponse()
		}
		previousTime, previousID = created, id
	}
	if page.NextCursor != nil {
		var checked AuditTaskCursor
		cursorFields, cursorErr := contextObject(fields["next_cursor"], &checked,
			[]string{"project_id", "task_id", "created_at", "event_id"}, nil)
		if cursorErr != nil || len(cursorFields) != 4 || len(items) == 0 ||
			!sameUUID(page.NextCursor.ProjectID, project) || !sameUUID(page.NextCursor.TaskID, task) ||
			!sameUUID(page.NextCursor.EventID, page.Items[len(page.Items)-1].EventID) || !validAuditTime(page.NextCursor.CreatedAt) {
			return result, invalidAuditResponse()
		}
		cursorTime, _ := time.Parse(time.RFC3339Nano, page.NextCursor.CreatedAt)
		if !cursorTime.Equal(previousTime) {
			return result, invalidAuditResponse()
		}
	}
	return Result[AuditTaskEvidencePage]{Raw: raw, Value: page}, nil
}
