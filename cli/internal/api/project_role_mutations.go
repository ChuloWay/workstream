package api

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"unicode"
)

// ProjectRoleReceipt is the public mutation observation, not cached authority.
type ProjectRoleReceipt struct {
	ID                      string `json:"id"`
	QualificationSnapshotID string `json:"qualification_snapshot_id"`
	ProjectID               string `json:"project_id"`
	ActorProfileID          string `json:"actor_profile_id"`
	Role                    string `json:"role"`
	Status                  string `json:"status"`
	Version                 int    `json:"version"`
}

type roleAvailability struct {
	Availability      string   `json:"availability"`
	ReferenceIDs      []string `json:"reference_ids"`
	UnavailableReason *string  `json:"unavailable_reason"`
}

type roleQualification struct {
	SkillsSnapshot        roleAvailability `json:"skills_snapshot"`
	ReputationSnapshot    roleAvailability `json:"reputation_snapshot"`
	PriorProjectWorkRefs  []string         `json:"prior_project_work_refs"`
	ExternalExpertiseRefs []string         `json:"external_expertise_refs"`
}

type projectRoleIssueInput struct {
	TargetActorProfileID string            `json:"target_actor_profile_id"`
	Role                 string            `json:"role"`
	Qualification        roleQualification `json:"qualification"`
	Reason               string            `json:"reason"`
}

var qualificationReference = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$`)

func validProjectRole(role string) bool { return role == "submitter" || role == "reviewer" }

func validRoleReason(reason string) bool {
	if len(reason) == 0 || len(reason) > 500 || strings.TrimSpace(reason) != reason {
		return false
	}
	for _, character := range reason {
		if unicode.Is(unicode.C, character) {
			return false
		}
	}
	return true
}

func validRoleReferences(refs []string) bool {
	if refs == nil || len(refs) > 20 {
		return false
	}
	for _, ref := range refs {
		if !qualificationReference.MatchString(ref) || strings.Contains(ref, "://") {
			return false
		}
	}
	return true
}

func decodeRoleQualification(raw json.RawMessage, value *roleQualification) error {
	fields, err := contextObject(raw, value, []string{"skills_snapshot", "reputation_snapshot", "prior_project_work_refs", "external_expertise_refs"}, []string{"prior_project_work_refs", "external_expertise_refs"})
	if err != nil {
		return err
	}
	return validateRoleQualification(fields, value)
}

// Read snapshots add provenance to these same qualification facts.
func validateRoleQualification(fields map[string]json.RawMessage, value *roleQualification) error {
	if value.PriorProjectWorkRefs == nil || len(value.PriorProjectWorkRefs) > 20 || !validRoleReferences(value.ExternalExpertiseRefs) {
		return errors.New("invalid qualification structure")
	}
	for _, id := range value.PriorProjectWorkRefs {
		if !validUUID(id) {
			return errors.New("invalid prior-work UUID")
		}
	}
	for _, item := range []struct {
		key   string
		value *roleAvailability
	}{{"skills_snapshot", &value.SkillsSnapshot}, {"reputation_snapshot", &value.ReputationSnapshot}} {
		members, err := contextObject(fields[item.key], item.value, []string{"availability", "reference_ids"}, []string{"reference_ids"})
		v := item.value
		if err != nil || !requiredNullable(members, "unavailable_reason") || !validRoleReferences(v.ReferenceIDs) {
			return errors.New("invalid qualification availability")
		}
		switch v.Availability {
		case "available":
			if len(v.ReferenceIDs) == 0 || v.UnavailableReason != nil {
				return errors.New("invalid available qualification")
			}
		case "unavailable":
			if len(v.ReferenceIDs) != 0 || v.UnavailableReason == nil || (*v.UnavailableReason != "not_collected" && *v.UnavailableReason != "source_unavailable" && *v.UnavailableReason != "no_record") {
				return errors.New("invalid unavailable qualification")
			}
		default:
			return errors.New("invalid qualification availability token")
		}
	}
	return nil
}

// IssueProjectRole sends one caller-supplied decision; only AUTH may grant it.
func (c *Client) IssueProjectRole(ctx context.Context, project string, body json.RawMessage, key string) (Result[ProjectRoleReceipt], error) {
	var input projectRoleIssueInput
	fields, err := contextObject(body, &input, []string{"target_actor_profile_id", "role", "qualification", "reason"}, nil)
	if len(body) == 0 || len(body) > MaxGuideInputBytes || err != nil || !validUUID(input.TargetActorProfileID) || !validProjectRole(input.Role) || !validRoleReason(input.Reason) || decodeRoleQualification(fields["qualification"], &input.Qualification) != nil {
		return Result[ProjectRoleReceipt]{}, errors.New("--input must contain the closed public role-issue decision and explicit qualification evidence")
	}
	result, err := c.projectRoleWrite(ctx, project, "", body, key)
	if err == nil && (!sameUUID(result.Value.ActorProfileID, input.TargetActorProfileID) || result.Value.Role != input.Role) {
		return Result[ProjectRoleReceipt]{}, roleMutationFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true})
	}
	return result, err
}

// RevokeProjectRole observes the server's actor/role without a preflight read.
func (c *Client) RevokeProjectRole(ctx context.Context, project, grant string, body json.RawMessage, key string) (Result[ProjectRoleReceipt], error) {
	var input struct {
		Reason string `json:"reason"`
	}
	if len(body) == 0 || len(body) > MaxGuideInputBytes {
		return Result[ProjectRoleReceipt]{}, errors.New("--input must contain a bounded public revocation reason")
	}
	if _, err := contextObject(body, &input, []string{"reason"}, nil); err != nil || !validRoleReason(input.Reason) || !validUUID(grant) || len(grant) > 100 {
		return Result[ProjectRoleReceipt]{}, errors.New("select a grant UUID and closed public revocation reason")
	}
	return c.projectRoleWrite(ctx, project, grant, body, key)
}

func (c *Client) projectRoleWrite(ctx context.Context, project, grant string, body json.RawMessage, key string) (Result[ProjectRoleReceipt], error) {
	var result Result[ProjectRoleReceipt]
	if !validUUID(project) || len(project) > 100 || !validUUID(key) || len(key) > 100 {
		return result, errors.New("PROJECT_ID and --idempotency-key must be UUIDs")
	}
	path := "/api/v1/projects/" + url.PathEscape(project) + "/role-grants"
	status, version, success := "active", 1, http.StatusCreated
	if grant != "" {
		path += "/" + url.PathEscape(grant) + "/revoke"
		status, version, success = "revoked", 2, http.StatusOK
	}
	raw, err := c.requestWithKey(ctx, http.MethodPost, path, "", body, key, success)
	if err != nil {
		return result, roleMutationFailure(err)
	}
	var value ProjectRoleReceipt
	_, err = contextObject(raw, &value, []string{"id", "qualification_snapshot_id", "project_id", "actor_profile_id", "role", "status", "version"}, nil)
	if err != nil || !validUUID(value.ID) || !validUUID(value.QualificationSnapshotID) || !validUUID(value.ActorProfileID) || !sameUUID(value.ProjectID, project) || (grant != "" && !sameUUID(value.ID, grant)) || !validProjectRole(value.Role) || value.Status != status || value.Version != version || !c.safeMutationResponse(raw) {
		return result, roleMutationFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true})
	}
	return Result[ProjectRoleReceipt]{Raw: raw, Value: value}, nil
}

func roleMutationFailure(err error) error {
	var failure *Failure
	if errors.As(err, &failure) && failure.OutcomeUnknown {
		failure.RecoveryHint = "project role outcome unknown; replay only the unchanged action, selectors, input file contents and idempotency key; a grant read is observation, not rollback proof"
	}
	return err
}
