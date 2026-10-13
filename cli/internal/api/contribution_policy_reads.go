package api

import (
	"context"
	"encoding/json"
	"errors"
	"math/big"
	"net/http"
	"net/url"
	"strings"
)

type ContributionPolicySelection struct {
	ProjectID                 string  `json:"project_id"`
	ContributionPolicyID      string  `json:"contribution_policy_id"`
	CurrentPublishedVersionID *string `json:"current_published_version_id"`
	OpenDraftVersionID        *string `json:"open_draft_version_id"`
}

// A view is retained Finance history, not permission, publication or readiness.
type ContributionPolicyVersion struct {
	ProjectID                   string                   `json:"project_id"`
	ContributionPolicyID        string                   `json:"contribution_policy_id"`
	Name                        string                   `json:"name"`
	PolicyStatus                string                   `json:"policy_status"`
	ContributionPolicyVersionID string                   `json:"contribution_policy_version_id"`
	VersionNumber               *big.Int                 `json:"version_number"`
	VersionStatus               string                   `json:"version_status"`
	Rules                       []ContributionPolicyRule `json:"rules"`
}

type ContributionPolicyRule struct {
	RuleID           string                         `json:"rule_id"`
	ContributionType string                         `json:"contribution_type"`
	CompensationMode string                         `json:"compensation_mode"`
	Definitions      []ContributionPolicyDefinition `json:"definitions"`
}

type ContributionPolicyDefinition struct {
	DefinitionID     string `json:"definition_id"`
	InstrumentType   string `json:"instrument_type"`
	UnitCode         string `json:"unit_code"`
	Quantity         string `json:"quantity"`
	AdapterBindingID string `json:"adapter_binding_id"`
}

func contributionPolicyPath(project string) (string, error) {
	if !validUUID(project) || len(project) > 100 {
		return "", errors.New("PROJECT_ID must be a UUID")
	}
	return "/api/v1/projects/" + url.PathEscape(project) + "/contribution-policies", nil
}

func (c *Client) CurrentContributionPolicy(ctx context.Context, project string) (Result[ContributionPolicySelection], error) {
	var result Result[ContributionPolicySelection]
	path, err := contributionPolicyPath(project)
	if err != nil {
		return result, err
	}
	raw, err := c.request(ctx, http.MethodGet, path+"/current", "", nil)
	if err != nil {
		return result, err
	}
	var value ContributionPolicySelection
	fields, err := contextObject(raw, &value, []string{"project_id", "contribution_policy_id"}, nil)
	if err != nil || !requiredNullable(fields, "current_published_version_id", "open_draft_version_id") ||
		!sameUUID(value.ProjectID, project) || !validUUID(value.ContributionPolicyID) || !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	for _, id := range []*string{value.CurrentPublishedVersionID, value.OpenDraftVersionID} {
		if id != nil && !validUUID(*id) {
			return result, &Failure{Code: "invalid_api_response"}
		}
	}
	if (value.CurrentPublishedVersionID == nil && value.OpenDraftVersionID == nil) ||
		(value.CurrentPublishedVersionID != nil && value.OpenDraftVersionID != nil && sameUUID(*value.CurrentPublishedVersionID, *value.OpenDraftVersionID)) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[ContributionPolicySelection]{Raw: raw, Value: value}, nil
}

func (c *Client) ContributionPolicy(ctx context.Context, project, policy string, version *string) (Result[ContributionPolicyVersion], error) {
	var result Result[ContributionPolicyVersion]
	path, err := contributionPolicyPath(project)
	if err != nil {
		return result, err
	}
	if !validUUID(policy) || len(policy) > 100 || (version != nil && (!validUUID(*version) || len(*version) > 100)) {
		return result, errors.New("POLICY_ID and an explicit --version must be UUIDs")
	}
	query := ""
	if version != nil {
		query = url.Values{"version_id": {*version}}.Encode()
	}
	raw, err := c.request(ctx, http.MethodGet, path+"/"+url.PathEscape(policy), query, nil)
	if err != nil {
		return result, err
	}
	var value ContributionPolicyVersion
	fields, err := contextObject(raw, &value, []string{
		"project_id", "contribution_policy_id", "name", "policy_status", "contribution_policy_version_id", "version_number", "version_status", "rules",
	}, nil)
	if err != nil || !sameUUID(value.ProjectID, project) || !sameUUID(value.ContributionPolicyID, policy) ||
		!validUUID(value.ContributionPolicyVersionID) || (version != nil && !sameUUID(value.ContributionPolicyVersionID, *version)) ||
		strings.TrimSpace(value.Name) == "" || value.VersionNumber == nil || value.VersionNumber.Sign() <= 0 ||
		(value.PolicyStatus != "draft" && value.PolicyStatus != "active" && value.PolicyStatus != "retired") ||
		(value.VersionStatus != "draft" && value.VersionStatus != "published" && value.VersionStatus != "retired") ||
		value.Rules == nil || len(value.Rules) > 2 || !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	var rules []json.RawMessage
	if err := json.Unmarshal(fields["rules"], &rules); err != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	seenRules, seenDefinitions := make(map[[16]byte]bool), make(map[[16]byte]bool)
	seenTypes := make(map[string]bool)
	for index, rawRule := range rules {
		rule := &value.Rules[index]
		members, err := contextObject(rawRule, rule, []string{"rule_id", "contribution_type", "compensation_mode", "definitions"}, nil)
		id, valid := uuidIdentity(rule.RuleID)
		if err != nil || !valid || seenRules[id] || seenTypes[rule.ContributionType] ||
			(rule.ContributionType != "accepted_submission" && rule.ContributionType != "completed_review") ||
			(rule.CompensationMode != "unpaid" && rule.CompensationMode != "compensated") || rule.Definitions == nil || len(rule.Definitions) > 2 {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seenRules[id], seenTypes[rule.ContributionType] = true, true
		var definitions []json.RawMessage
		if err := json.Unmarshal(members["definitions"], &definitions); err != nil {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seenInstruments := make(map[string]bool)
		for index, rawDefinition := range definitions {
			definition := &rule.Definitions[index]
			_, err := contextObject(rawDefinition, definition, []string{"definition_id", "instrument_type", "unit_code", "quantity", "adapter_binding_id"}, nil)
			id, valid := uuidIdentity(definition.DefinitionID)
			award := CompensationAward{Instrument: definition.InstrumentType, Unit: definition.UnitCode, Quantity: definition.Quantity}
			if err != nil || !valid || seenDefinitions[id] || !validUUID(definition.AdapterBindingID) ||
				!validCompensationAward(award) || seenInstruments[definition.InstrumentType] {
				return result, &Failure{Code: "invalid_api_response"}
			}
			seenDefinitions[id], seenInstruments[definition.InstrumentType] = true, true
		}
	}
	return Result[ContributionPolicyVersion]{Raw: raw, Value: value}, nil
}
