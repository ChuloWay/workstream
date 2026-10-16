package api

import (
	"encoding/json"
	"errors"
	"math/big"
	"strconv"
)

// Only this fixed public PRE projection may enter error details. Never echo a
// raw error envelope, arbitrary exception data or storage/provider coordinates.
func preparationFeedback(raw json.RawMessage) (json.RawMessage, error) {
	bad := errors.New("invalid pre-submission feedback")
	var envelope struct {
		Error struct {
			Details json.RawMessage `json:"details"`
		} `json:"error"`
	}
	if json.Unmarshal(raw, &envelope) != nil {
		return nil, bad
	}
	var details struct {
		Status   string            `json:"status"`
		Eligible bool              `json:"eligible_to_submit"`
		Results  []json.RawMessage `json:"results"`
	}
	_, err := contextObject(envelope.Error.Details, &details, []string{"status", "eligible_to_submit", "results"}, nil)
	if err != nil || details.Status != "failed" || details.Eligible || details.Results == nil {
		return nil, bad
	}
	if !validPreSubmissionResults(details.Results, false) {
		return nil, bad
	}
	return envelope.Error.Details, nil
}

// validPreSubmissionResults checks the fixed public PRE projection shared by a
// blocked preparation's error details and an admitted preparation's receipt.
// An admitted attempt cannot carry a failed check or an error finding.
func validPreSubmissionResults(results []json.RawMessage, admitted bool) bool {
	var err error
	for _, item := range results {
		var discriminator struct {
			Source string `json:"source"`
			Status string `json:"status"`
		}
		if json.Unmarshal(item, &discriminator) != nil {
			return false
		}
		switch discriminator.Source {
		case "workstream_default":
			if discriminator.Status == "warning" {
				var warning struct {
					Source string `json:"source"`
					Status string `json:"status"`
					Code   string `json:"warning_code"`
				}
				_, err = contextObject(item, &warning, []string{"source", "status", "warning_code"}, nil)
				if err != nil || warning.Code == "" {
					return false
				}
			} else {
				var check struct {
					Source  string   `json:"source"`
					Status  string   `json:"status"`
					ID      string   `json:"check_id"`
					Failure *string  `json:"failure_code"`
					Count   *big.Int `json:"finding_count"`
				}
				fields, e := contextObject(item, &check, []string{"source", "status", "check_id", "finding_count"}, nil)
				if e != nil || !requiredNullable(fields, "failure_code") || check.ID == "" || check.Count == nil || check.Count.Sign() < 0 {
					return false
				}
				if admitted && check.Status != "passed" {
					return false
				}
				if check.Status == "failed" {
					if check.Failure == nil || *check.Failure == "" || check.Count.Sign() <= 0 {
						return false
					}
				} else if (check.Status != "passed" && check.Status != "not_run") || check.Failure != nil || check.Count.Sign() != 0 {
					return false
				}
			}
		case "project_external_checker":
			var external struct {
				Source      string            `json:"source"`
				Requirement string            `json:"requirement_id"`
				Registry    string            `json:"registry_entry_id"`
				Digest      string            `json:"registry_entry_digest"`
				Status      string            `json:"status"`
				Findings    []json.RawMessage `json:"findings"`
			}
			_, err = contextObject(item, &external, []string{"source", "requirement_id", "registry_entry_id", "registry_entry_digest", "status", "findings"}, nil)
			if err != nil || external.Requirement == "" || !validUUID(external.Registry) || !policyHash.MatchString(external.Digest) ||
				(external.Status != "passed" && external.Status != "failed") || external.Findings == nil || len(external.Findings) > 256 ||
				(admitted && external.Status != "passed") {
				return false
			}
			for _, f := range external.Findings {
				var finding struct {
					CheckID string  `json:"check_id"`
					Code    string  `json:"code"`
					Level   string  `json:"level"`
					Message string  `json:"message"`
					Path    *string `json:"path"`
					Line    *int64  `json:"line"`
				}
				fields, e := contextObject(f, &finding, []string{"check_id", "code", "level", "message"}, nil)
				if e != nil || !requiredNullable(fields, "path", "line") || finding.CheckID == "" || finding.Code == "" ||
					finding.Message == "" || (finding.Line != nil && (finding.Path == nil || *finding.Line < 1)) {
					return false
				}
				switch finding.Level {
				case "info", "warning", "coverage_incomplete":
				case "error":
					if admitted {
						return false
					}
				default:
					return false
				}
			}
		default:
			return false
		}
	}
	return true
}

// IntakeFeedbackLines renders an admitted attempt's nonblocking findings for
// people; passed checks are omitted. The values were validated on receipt.
func IntakeFeedbackLines(results []json.RawMessage) []string {
	var lines []string
	for _, item := range results {
		var result struct {
			Source   string `json:"source"`
			Status   string `json:"status"`
			Warning  string `json:"warning_code"`
			Findings []struct {
				CheckID string  `json:"check_id"`
				Level   string  `json:"level"`
				Message string  `json:"message"`
				Path    *string `json:"path"`
				Line    *int64  `json:"line"`
			} `json:"findings"`
		}
		if json.Unmarshal(item, &result) != nil {
			continue
		}
		if result.Source == "workstream_default" && result.Status == "warning" {
			lines = append(lines, "warning "+result.Warning)
		}
		for _, finding := range result.Findings {
			location := ""
			if finding.Path != nil {
				location = " " + *finding.Path
				if finding.Line != nil {
					location += ":" + strconv.FormatInt(*finding.Line, 10)
				}
			}
			lines = append(lines, finding.Level+" "+finding.CheckID+location+": "+finding.Message)
		}
	}
	return lines
}
