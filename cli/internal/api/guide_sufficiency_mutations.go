package api

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"unicode/utf8"
)

type sufficiencyFindingInput struct {
	Severity string  `json:"severity"`
	Code     string  `json:"code"`
	Message  string  `json:"message"`
	Location *string `json:"location"`
}

type sufficiencyCreateInput struct {
	SourceSnapshotID string            `json:"source_snapshot_id"`
	Status           string            `json:"status"`
	Findings         []json.RawMessage `json:"findings"`
	Summary          *string           `json:"summary"`
}

type sufficiencyAcknowledgementInput struct {
	Note *string `json:"acknowledgement_note"`
}

func validSufficiencyInput(body json.RawMessage) (sufficiencyCreateInput, bool) {
	var input sufficiencyCreateInput
	if len(body) == 0 || len(body) > MaxGuideInputBytes {
		return input, false
	}
	fields, err := contextObject(body, &input, []string{"source_snapshot_id", "status"}, nil)
	if err != nil || len(input.SourceSnapshotID) > 36 || !validUUID(input.SourceSnapshotID) ||
		!oneOf(input.Status, "passed", "blocked", "passed_with_warnings") ||
		(input.Summary != nil && utf8.RuneCountInString(*input.Summary) > 2000) {
		return input, false
	}
	if _, found := fields["findings"]; found {
		findings, valid := inspectArray(fields, "findings", 100)
		if !valid {
			return input, false
		}
		input.Findings = findings
	}
	for _, raw := range input.Findings {
		var finding sufficiencyFindingInput
		if _, err := contextObject(raw, &finding, []string{"severity", "code", "message"}, nil); err != nil ||
			!oneOf(finding.Severity, "blocking_gap", "warning", "info") ||
			utf8.RuneCountInString(finding.Code) > 100 ||
			utf8.RuneCountInString(finding.Message) > 1000 ||
			(finding.Location != nil && utf8.RuneCountInString(*finding.Location) > 500) {
			return input, false
		}
	}
	return input, true
}

func validSufficiencyAcknowledgement(body json.RawMessage) (*string, bool) {
	if len(body) == 0 || len(body) > MaxGuideInputBytes {
		return nil, false
	}
	var input sufficiencyAcknowledgementInput
	if _, err := contextObject(body, &input, nil, nil); err != nil ||
		(input.Note != nil && utf8.RuneCountInString(*input.Note) > 1000) {
		return nil, false
	}
	return input.Note, true
}

// CreateGuideSufficiencyReport records a human diagnostic. The server alone
// decides whether the draft guide and source snapshot permit the write.
func (c *Client) CreateGuideSufficiencyReport(ctx context.Context, project, guide string, body json.RawMessage, key string) (Result[json.RawMessage], error) {
	var result Result[json.RawMessage]
	if !validUUID(project) || !validUUID(guide) || !validUUID(key) ||
		len(project) > 100 || len(guide) > 100 || len(key) > 100 {
		return result, errors.New("project, guide and --idempotency-key must be UUIDs")
	}
	input, ok := validSufficiencyInput(body)
	if !ok {
		return result, errors.New("--input must contain a bounded public sufficiency report for one source snapshot")
	}
	path, _ := guideInspectionPath(project, guide, "/sufficiency-reports")
	raw, err := c.requestWithResponseLimit(ctx, http.MethodPost, path, "", body, key, http.StatusCreated, maxGuideInspectionBytes)
	if err != nil {
		return result, sufficiencyMutationFailure(err)
	}
	fields, valid := validateSufficiency(raw, project, guide, "")
	responseSnapshot, snapshotValid := inspectID(fields, "source_snapshot_id")
	status, statusValid := inspectString(fields, "status")
	var summary *string
	if err := json.Unmarshal(fields["summary"], &summary); err != nil {
		valid = false
	}
	if !valid || !snapshotValid || !sameUUID(responseSnapshot, input.SourceSnapshotID) ||
		!statusValid || status != input.Status || !sameOptionalString(summary, input.Summary) ||
		!sameSufficiencyFindings(input.Findings, fields["findings"]) ||
		!manualSufficiencyProvenance(fields) || !c.safeMutationResponse(raw) {
		return result, sufficiencyMutationFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true})
	}
	return Result[json.RawMessage]{Raw: raw, Value: raw}, nil
}

func sameSufficiencyFindings(expected []json.RawMessage, raw json.RawMessage) bool {
	var actual []json.RawMessage
	if json.Unmarshal(raw, &actual) != nil || actual == nil || len(actual) != len(expected) {
		return false
	}
	for index, entry := range actual {
		var want, got sufficiencyFindingInput
		if _, err := contextObject(expected[index], &want, []string{"severity", "code", "message"}, nil); err != nil {
			return false
		}
		if _, err := contextObject(entry, &got, []string{"severity", "code", "message"}, nil); err != nil ||
			want.Severity != got.Severity || want.Code != got.Code || want.Message != got.Message ||
			!sameOptionalString(want.Location, got.Location) {
			return false
		}
	}
	return true
}

func manualSufficiencyProvenance(fields inspectionObject) bool {
	for _, field := range []string{
		"agent_name", "agent_version", "project_setup_run_id", "setup_generation",
		"agent_material_sha256", "agent_material_byte_count", "warnings_acknowledged_by_role",
		"warnings_acknowledged_by_actor", "warnings_acknowledged_at", "acknowledgement_note",
	} {
		if string(fields[field]) != "null" {
			return false
		}
	}
	return true
}

// AcknowledgeGuideSufficiencyWarnings records one explicit acknowledgement;
// it does not approve compilation, policy, or activation.
func (c *Client) AcknowledgeGuideSufficiencyWarnings(ctx context.Context, project, guide, report string, body json.RawMessage, key string) (Result[json.RawMessage], error) {
	var result Result[json.RawMessage]
	if !validUUID(project) || !validUUID(guide) || !validUUID(report) || !validUUID(key) ||
		len(project) > 100 || len(guide) > 100 || len(report) > 100 || len(key) > 100 {
		return result, errors.New("project, guide, report and --idempotency-key must be UUIDs")
	}
	note, ok := validSufficiencyAcknowledgement(body)
	if !ok {
		return result, errors.New("--input must contain a bounded public warning acknowledgement")
	}
	path, _ := guideInspectionPath(project, guide, "/sufficiency-reports/"+url.PathEscape(report)+"/acknowledge-warnings")
	raw, err := c.requestWithResponseLimit(ctx, http.MethodPost, path, "", body, key, http.StatusOK, maxGuideInspectionBytes)
	if err != nil {
		return result, sufficiencyMutationFailure(err)
	}
	fields, valid := validateSufficiency(raw, project, guide, report)
	role, roleValid := inspectString(fields, "warnings_acknowledged_by_role")
	_, actorValid := inspectID(fields, "warnings_acknowledged_by_actor")
	responseNote := fields["acknowledgement_note"]
	var actualNote *string
	if err := json.Unmarshal(responseNote, &actualNote); err != nil ||
		valid && (!roleValid || role != "project_manager" || !actorValid || !inspectTime(fields, "warnings_acknowledged_at") || !sameOptionalString(note, actualNote)) {
		valid = false
	}
	status, statusValid := inspectString(fields, "status")
	if !valid || !statusValid || status != "passed_with_warnings" || !c.safeMutationResponse(raw) {
		return result, sufficiencyMutationFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true})
	}
	return Result[json.RawMessage]{Raw: raw, Value: raw}, nil
}

func sameOptionalString(left, right *string) bool {
	if left == nil || right == nil {
		return left == nil && right == nil
	}
	return *left == *right
}

func sufficiencyMutationFailure(err error) error {
	var failure *Failure
	if errors.As(err, &failure) && failure.OutcomeUnknown {
		failure.RecoveryHint = "sufficiency write outcome unknown; manually replay only the unchanged project, guide, report (if selected), input file contents and idempotency key"
	}
	return err
}
