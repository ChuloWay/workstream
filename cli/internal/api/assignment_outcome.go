package api

import (
	"encoding/json"
	"errors"
)

// AssignmentOutcome describes closed work even when the task has been claimed again.
type AssignmentOutcome struct {
	AssignmentID string `json:"assignment_id"`
	SubmissionID string `json:"submission_id"`
	Status       string `json:"status"`
	StatusReason string `json:"status_reason"`
	ClosedAt     string `json:"closed_at"`
	NextAction   string `json:"next_action"`
}

func validateAssignmentOutcome(raw json.RawMessage) error {
	var value AssignmentOutcome
	_, err := contextObject(raw, &value, []string{
		"assignment_id", "submission_id", "status", "status_reason", "closed_at", "next_action",
	}, nil)
	if err != nil || !validUUID(value.AssignmentID) || !validUUID(value.SubmissionID) ||
		!validTime(value.ClosedAt) || value.NextAction != "none" ||
		!((value.Status == "revision_exhausted" && value.StatusReason == "revision_limit_reached") ||
			(value.Status == "revision_expired" && value.StatusReason == "revision_deadline_expired")) {
		return errors.New("invalid terminal assignment outcome")
	}
	return nil
}
