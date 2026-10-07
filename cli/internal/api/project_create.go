package api

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"unicode/utf8"
)

// ProjectCreate preserves omission versus explicit empty description. The API
// owns project identity, creation authority, replay and draft lifecycle.
type ProjectCreate struct {
	Name        string  `json:"name"`
	Slug        string  `json:"slug"`
	Description *string `json:"description,omitempty"`
}

func (c *Client) CreateProject(ctx context.Context, input ProjectCreate, key string) (Result[Project], error) {
	var result Result[Project]
	if !validUUID(key) || len(key) > 100 {
		return result, errors.New("--idempotency-key must be a UUID")
	}
	if !validProjectText(input.Name, 200) || !validProjectText(input.Slug, 120) ||
		(input.Description != nil && (!utf8.ValidString(*input.Description) || strings.ContainsRune(*input.Description, '\x00'))) {
		return result, errors.New("project fields must be valid UTF-8 without NUL; name and slug are limited to 200 and 120 characters")
	}
	body, err := json.Marshal(input)
	if err != nil || len(body) > maxUpdateBytes {
		return result, errors.New("project request exceeds the request size limit")
	}
	raw, err := c.requestWithKey(ctx, http.MethodPost, "/api/v1/projects", "", body, key, http.StatusCreated)
	if err != nil {
		return result, projectCreateFailure(err)
	}
	project, err := decodeProject(raw)
	if err != nil || project.Metadata == nil {
		return result, projectCreateFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true})
	}
	return Result[Project]{Raw: raw, Value: project}, nil
}

func validProjectText(value string, maxCharacters int) bool {
	return utf8.ValidString(value) && !strings.ContainsRune(value, '\x00') && utf8.RuneCountInString(value) <= maxCharacters
}

func projectCreateFailure(err error) error {
	var failure *Failure
	if errors.As(err, &failure) && failure.OutcomeUnknown {
		failure.RecoveryHint = "project creation outcome unknown; replay only the unchanged name, slug, description and idempotency key"
	}
	return err
}
