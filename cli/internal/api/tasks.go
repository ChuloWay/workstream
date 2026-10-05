package api

import (
	"context"
	"encoding/json"
	jsonv2 "encoding/json/v2"
	"errors"
	"net/http"
	"net/url"
	"strconv"
	"unicode/utf8"
)

type TaskSummary struct {
	TaskID               string   `json:"task_id"`
	ProjectID            string   `json:"project_id"`
	Title                string   `json:"title"`
	TaskType             *string  `json:"task_type"`
	Difficulty           *string  `json:"difficulty"`
	SkillTags            []string `json:"skill_tags"`
	EstimatedTimeMinutes *int     `json:"estimated_time_minutes"`
	Status               string   `json:"status"`
	DeadlineAt           *string  `json:"deadline_at"`
	CreatedAt            string   `json:"created_at"`
	UpdatedAt            string   `json:"updated_at"`
}

type TaskDetail struct {
	TaskSummary
	Description        string  `json:"description"`
	AcceptanceCriteria *string `json:"acceptance_criteria"`
	RejectionCriteria  *string `json:"rejection_criteria"`
	SourceType         string  `json:"source_type"`
	SourceRef          *string `json:"source_ref"`
	SourcePayloadHash  *string `json:"source_payload_hash"`
	ImportBatchID      *string `json:"import_batch_id"`
	ExternalTaskID     *string `json:"external_task_id"`
	CreatedBy          string  `json:"created_by"`
	AssignedTo         *string `json:"assigned_to"`
}

type TaskPage struct {
	ProjectID  string
	Items      []TaskSummary
	NextCursor *string
}

func taskProjectPath(selector string) (string, error) {
	if _, ok := uuidIdentity(selector); !ok || len(selector) > 100 {
		return "", errors.New("PROJECT_ID must be a UUID")
	}
	return "/api/v1/projects/" + url.PathEscape(selector) + "/tasks", nil
}

func (c *Client) Tasks(ctx context.Context, project string, limit int, cursor *string) (Result[TaskPage], error) {
	var result Result[TaskPage]
	path, err := taskProjectPath(project)
	if err != nil {
		return result, err
	}
	if limit < 1 || limit > 100 || (cursor != nil && !validTaskCursor(*cursor)) {
		return result, errors.New("limit must be 1–100; cursor must contain 1–512 valid UTF-8 characters")
	}
	query := url.Values{"limit": {strconv.Itoa(limit)}}
	if cursor != nil {
		query.Set("cursor", *cursor)
	}
	raw, err := c.request(ctx, http.MethodGet, path, query.Encode(), nil)
	if err != nil {
		return result, err
	}
	var page struct {
		ProjectID  string            `json:"project_id"`
		Items      []json.RawMessage `json:"items"`
		NextCursor *string           `json:"next_cursor"`
	}
	err = decode(raw, &page, []string{"project_id", "items", "next_cursor"}, nil)
	selected, _ := uuidIdentity(project)
	returned, valid := uuidIdentity(page.ProjectID)
	if err != nil || !valid || selected != returned || page.Items == nil || len(page.Items) > limit ||
		(page.NextCursor != nil && (!validTaskCursor(*page.NextCursor) || len(page.Items) == 0)) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	value := TaskPage{ProjectID: page.ProjectID, Items: make([]TaskSummary, 0, len(page.Items)), NextCursor: page.NextCursor}
	seen := make(map[[16]byte]bool)
	for _, item := range page.Items {
		var task TaskSummary
		if err := decodeTask(item, &task, false); err != nil || !validTask(task, project) {
			return result, &Failure{Code: "invalid_api_response"}
		}
		id, _ := uuidIdentity(task.TaskID)
		if seen[id] {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[id] = true
		value.Items = append(value.Items, task)
	}
	return Result[TaskPage]{Raw: raw, Value: value}, nil
}

func (c *Client) Task(ctx context.Context, project, selector string) (Result[TaskDetail], error) {
	var result Result[TaskDetail]
	path, err := taskProjectPath(project)
	selected, valid := uuidIdentity(selector)
	if err != nil {
		return result, err
	}
	if !valid || len(selector) > 100 {
		return result, errors.New("TASK_ID must be a UUID")
	}
	raw, err := c.request(ctx, http.MethodGet, path+"/"+url.PathEscape(selector), "", nil)
	if err != nil {
		return result, err
	}
	var value TaskDetail
	err = decodeTask(raw, &value, true)
	returned, valid := uuidIdentity(value.TaskID)
	_, validCreator := uuidIdentity(value.CreatedBy)
	validAssignment := true
	if value.AssignedTo != nil {
		_, validAssignment = uuidIdentity(*value.AssignedTo)
	}
	if err != nil || !validTask(value.TaskSummary, project) || !valid || selected != returned || !validCreator || !validAssignment {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[TaskDetail]{Raw: raw, Value: value}, nil
}

func validTaskCursor(cursor string) bool {
	return cursor != "" && utf8.ValidString(cursor) && utf8.RuneCountInString(cursor) <= 512
}

func validTask(task TaskSummary, project string) bool {
	selected, _ := uuidIdentity(project)
	returned, validProject := uuidIdentity(task.ProjectID)
	_, validID := uuidIdentity(task.TaskID)
	return validID && validProject && selected == returned && task.SkillTags != nil &&
		validTime(task.CreatedAt) && validTime(task.UpdatedAt) &&
		(task.DeadlineAt == nil || validTime(*task.DeadlineAt))
}

func decodeTask(raw json.RawMessage, value any, detail bool) error {
	strings := []string{"task_id", "project_id", "title", "status", "created_at", "updated_at"}
	required := append([]string{}, strings...)
	required = append(required, "skill_tags")
	if detail {
		strings = append(strings, "description", "source_type", "created_by")
		required = append(required, "description", "source_type", "created_by")
	} else {
		required = append(required, "task_type", "difficulty", "estimated_time_minutes", "deadline_at")
	}
	var fields map[string]json.RawMessage
	if err := jsonv2.Unmarshal(raw, &fields); err != nil || fields == nil {
		return errors.New("invalid task object")
	}
	for _, key := range strings {
		var field *string
		if err := jsonv2.Unmarshal(fields[key], &field); err != nil || field == nil {
			return errors.New("invalid required task string")
		}
	}
	return decode(raw, value, required, []string{"skill_tags"})
}
