package api

import (
	"context"
	"encoding/json"
	"errors"
	"net/url"
	"strconv"
)

// ProjectPageQuery selects one page of a project-wide management list. The
// server binds every continuation to the same filters and limit. Outcome
// filters preparations only.
type ProjectPageQuery struct {
	Limit   int
	Cursor  *string
	Outcome *string
}

// ProjectPreparation is one contributor's preparation with finding counts only.
type ProjectPreparation struct {
	PreparationSummary
	ActorProfileID string `json:"actor_profile_id"`
}

type ProjectPreparationPage struct {
	Items  []ProjectPreparation `json:"items"`
	Cursor *string              `json:"next_cursor"`
}

var preparationOutcomes = []string{"pending", "passed", "failed", "infrastructure_failed"}

func (q ProjectPageQuery) encode() (string, error) {
	if q.Limit < 1 || q.Limit > 100 || (q.Cursor != nil && !validTaskCursor(*q.Cursor)) ||
		(q.Outcome != nil && !oneOf(*q.Outcome, preparationOutcomes...)) {
		return "", errors.New("limit must be 1–100; cursor 1–512 characters; outcome pending, passed, failed or infrastructure_failed")
	}
	query := url.Values{"limit": {strconv.Itoa(q.Limit)}}
	if q.Cursor != nil {
		query.Set("cursor", *q.Cursor)
	}
	if q.Outcome != nil {
		query.Set("outcome", *q.Outcome)
	}
	return query.Encode(), nil
}

// ProjectPreparations lists every contributor's ZIP preparations in one project, newest first.
func (c *Client) ProjectPreparations(ctx context.Context, project string, q ProjectPageQuery) (Result[ProjectPreparationPage], error) {
	var result Result[ProjectPreparationPage]
	path, err := projectReadPath(project, "/submission-bundle-preparations")
	if err != nil {
		return result, err
	}
	query, err := q.encode()
	if err != nil {
		return result, err
	}
	raw, fields, items, err := c.readPage(ctx, path, query, q.Limit)
	if err != nil {
		return result, err
	}
	page := ProjectPreparationPage{Items: make([]ProjectPreparation, 0, len(items))}
	if json.Unmarshal(fields["next_cursor"], &page.Cursor) != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	seen := map[[16]byte]bool{}
	for _, item := range items {
		var value ProjectPreparation
		itemFields, err := contextObject(item, &value, []string{"preparation_id", "task_id", "assignment_id", "outcome", "state", "archive_sha256", "archive_byte_count", "created_at", "actor_profile_id"}, nil)
		id, _ := uuidIdentity(value.PreparationID)
		if err != nil || !validPreparation(itemFields, value.PreparationSummary) || !validUUID(value.ActorProfileID) || seen[id] ||
			(q.Outcome != nil && value.Outcome != *q.Outcome) {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[id] = true
		page.Items = append(page.Items, value)
	}
	return Result[ProjectPreparationPage]{Raw: raw, Value: page}, nil
}
