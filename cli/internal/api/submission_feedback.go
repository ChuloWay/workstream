package api

import (
	"encoding/json"
	"errors"
	"math/big"
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
	for _, item := range details.Results {
		var discriminator struct {
			Source string `json:"source"`
			Status string `json:"status"`
		}
		if json.Unmarshal(item, &discriminator) != nil {
			return nil, bad
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
					return nil, bad
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
					return nil, bad
				}
				if check.Status == "failed" {
					if check.Failure == nil || *check.Failure == "" || check.Count.Sign() <= 0 {
						return nil, bad
					}
				} else if (check.Status != "passed" && check.Status != "not_run") || check.Failure != nil || check.Count.Sign() != 0 {
					return nil, bad
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
				(external.Status != "passed" && external.Status != "failed") || external.Findings == nil || len(external.Findings) > 256 {
				return nil, bad
			}
			for _, f := range external.Findings {
				var finding struct {
					Code    string  `json:"code"`
					Level   string  `json:"level"`
					Message string  `json:"message"`
					Path    *string `json:"path"`
				}
				fields, e := contextObject(f, &finding, []string{"code", "level", "message"}, nil)
				if e != nil || !requiredNullable(fields, "path") || finding.Code == "" || finding.Message == "" ||
					(finding.Level != "info" && finding.Level != "warning" && finding.Level != "error") {
					return nil, bad
				}
			}
		default:
			return nil, bad
		}
	}
	return envelope.Error.Details, nil
}
