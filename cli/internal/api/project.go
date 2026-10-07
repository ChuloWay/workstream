package api

import (
	"context"
	"encoding/json"
	jsonv2 "encoding/json/v2"
	"errors"
	"net/http"
	"net/url"
)

type ProjectIdentity struct {
	ID     string `json:"id"`
	Name   string `json:"name"`
	Status string `json:"status"`
}

type ProjectMetadata struct {
	Slug        string  `json:"slug"`
	Description *string `json:"description"`
	CreatedAt   string  `json:"created_at"`
	UpdatedAt   string  `json:"updated_at"`
}

// Project holds only the projection returned by the server. Metadata is absent
// for the contributor shape; its presence does not confer client-side authority.
type Project struct {
	ProjectIdentity
	Metadata *ProjectMetadata
}

func (c *Client) Project(ctx context.Context, selector string) (Result[Project], error) {
	var result Result[Project]
	_, valid := uuidIdentity(selector)
	if len(selector) > 100 || !valid {
		return result, errors.New("PROJECT_ID must be a UUID")
	}
	raw, err := c.request(ctx, http.MethodGet, "/api/v1/projects/"+url.PathEscape(selector), "", nil)
	if err != nil {
		return result, err
	}
	project, err := decodeProject(raw)
	if err != nil || !sameUUID(project.ID, selector) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[Project]{Raw: raw, Value: project}, nil
}

func decodeProject(raw json.RawMessage) (Project, error) {
	var project Project
	var fields map[string]json.RawMessage
	if err := jsonv2.Unmarshal(raw, &fields); err != nil || fields == nil {
		return project, &Failure{Code: "invalid_api_response"}
	}
	requiredStrings := []string{"id", "name", "status"}
	if len(fields) != 3 {
		requiredStrings = append(requiredStrings, "slug", "created_at", "updated_at")
	}
	for _, key := range requiredStrings {
		var value *string
		if err := jsonv2.Unmarshal(fields[key], &value); err != nil || value == nil {
			return project, &Failure{Code: "invalid_api_response"}
		}
	}
	var err error
	if len(fields) == 3 {
		err = decode(raw, &project.ProjectIdentity, requiredStrings, nil)
	} else {
		var full struct {
			ProjectIdentity
			ProjectMetadata
		}
		err = decode(raw, &full, append(requiredStrings, "description"), nil)
		if !validTime(full.CreatedAt) || !validTime(full.UpdatedAt) {
			return project, &Failure{Code: "invalid_api_response"}
		}
		project = Project{ProjectIdentity: full.ProjectIdentity, Metadata: &full.ProjectMetadata}
	}
	if err != nil || !validUUID(project.ID) {
		return project, &Failure{Code: "invalid_api_response"}
	}
	return project, nil
}
