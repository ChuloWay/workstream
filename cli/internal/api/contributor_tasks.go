package api

import (
	"context"
	"errors"
	"net/http"
	"net/url"
)

// ReadyTaskSummary is the public contributor projection, not management facts.
type ReadyTaskSummary struct {
	TaskID               string   `json:"task_id"`
	ProjectID            string   `json:"project_id"`
	Title                string   `json:"title"`
	TaskType             *string  `json:"task_type"`
	Difficulty           *string  `json:"difficulty"`
	SkillTags            []string `json:"skill_tags"`
	EstimatedTimeMinutes *int     `json:"estimated_time_minutes"`
	CreatedAt            string   `json:"created_at"`
}

type ReadyTaskPage struct {
	ProjectID  string
	Items      []ReadyTaskSummary
	NextCursor *string
}

// ContributorTaskDetail excludes management-only source and actor metadata.
type ContributorTaskDetail struct {
	TaskSummary
	Description        string  `json:"description"`
	AcceptanceCriteria *string `json:"acceptance_criteria"`
	RejectionCriteria  *string `json:"rejection_criteria"`
}

func (c *Client) ReadyTasks(ctx context.Context, project string, limit int, cursor *string) (Result[ReadyTaskPage], error) {
	var result Result[ReadyTaskPage]
	path, err := taskProjectPath(project)
	if err != nil {
		return result, err
	}
	query, err := taskPageQuery(limit, cursor)
	if err != nil {
		return result, err
	}
	raw, err := c.request(ctx, http.MethodGet, path+"/ready", query, nil)
	if err != nil {
		return result, err
	}
	page, err := decodeTaskPage(raw, project, limit)
	if err != nil {
		return result, err
	}
	value := ReadyTaskPage{ProjectID: page.ProjectID, Items: make([]ReadyTaskSummary, 0, len(page.Items)), NextCursor: page.NextCursor}
	seen := make(map[[16]byte]bool)
	selected, _ := uuidIdentity(project)
	for _, item := range page.Items {
		var task ReadyTaskSummary
		err := decodeTaskFields(item, &task,
			[]string{"task_id", "project_id", "title", "created_at"},
			[]string{"task_type", "difficulty", "estimated_time_minutes", "skill_tags"})
		id, validID := uuidIdentity(task.TaskID)
		returned, validProject := uuidIdentity(task.ProjectID)
		if err != nil || !validID || !validProject || returned != selected ||
			!validTime(task.CreatedAt) || seen[id] {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[id] = true
		value.Items = append(value.Items, task)
	}
	return Result[ReadyTaskPage]{Raw: raw, Value: value}, nil
}

func (c *Client) ContributorTask(ctx context.Context, selector string) (Result[ContributorTaskDetail], error) {
	var result Result[ContributorTaskDetail]
	selected, valid := uuidIdentity(selector)
	if !valid || len(selector) > 100 {
		return result, errors.New("TASK_ID must be a UUID")
	}
	raw, err := c.request(ctx, http.MethodGet, "/api/v1/tasks/"+url.PathEscape(selector), "", nil)
	if err != nil {
		return result, err
	}
	var value ContributorTaskDetail
	err = decodeTaskFields(raw, &value,
		[]string{"task_id", "project_id", "title", "description", "status", "created_at", "updated_at"},
		[]string{"skill_tags"})
	returned, valid := uuidIdentity(value.TaskID)
	if err != nil || !valid || returned != selected || !validTask(value.TaskSummary, value.ProjectID) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[ContributorTaskDetail]{Raw: raw, Value: value}, nil
}
