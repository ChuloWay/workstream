package api

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
)

// ProjectRoleGrant is a current observation of retained history, not authority.
type ProjectRoleGrant struct {
	ID                        string              `json:"id"`
	ProjectID                 string              `json:"project_id"`
	ActorProfileID            string              `json:"actor_profile_id"`
	Role                      string              `json:"role"`
	Status                    string              `json:"status"`
	Version                   int                 `json:"version"`
	GrantMethod               string              `json:"grant_method"`
	QualificationSnapshot     ProjectRoleSnapshot `json:"qualification_snapshot"`
	GrantedByActorProfileID   string              `json:"granted_by_actor_profile_id"`
	GrantedByAdminRoleGrantID string              `json:"granted_by_admin_role_grant_id"`
	GrantedAt                 string              `json:"granted_at"`
	GrantReason               string              `json:"grant_reason"`
	RevokedByActorProfileID   *string             `json:"revoked_by_actor_profile_id"`
	RevokedAt                 *string             `json:"revoked_at"`
	RevokedReason             *string             `json:"revoked_reason"`
}

type ProjectRoleSnapshot struct {
	roleQualification
	ID                         string `json:"id"`
	RequestedRole              string `json:"requested_role"`
	CapturedByActorProfileID   string `json:"captured_by_actor_profile_id"`
	CapturedByAdminRoleGrantID string `json:"captured_by_admin_role_grant_id"`
	CapturedAt                 string `json:"captured_at"`
}

type ProjectRolePage struct {
	Items      []ProjectRoleGrant `json:"items"`
	NextCursor *string            `json:"next_cursor"`
}

// Qualification-bearing pages can exceed the small JSON response envelope.
const maxProjectRoleReadBytes = 2 * 1024 * 1024

func (c *Client) ProjectRoles(ctx context.Context, project string, limit int, cursor, status, role *string) (Result[ProjectRolePage], error) {
	var result Result[ProjectRolePage]
	if !validUUID(project) || len(project) > 100 ||
		(status != nil && *status != "active" && *status != "revoked") ||
		(role != nil && !validProjectRole(*role)) {
		return result, errors.New("select a project UUID, active/revoked status and submitter/reviewer role")
	}
	query, err := taskPageQuery(limit, cursor)
	if err != nil {
		return result, err
	}
	if status != nil {
		query += "&status=" + url.QueryEscape(*status)
	}
	if role != nil {
		query += "&role=" + url.QueryEscape(*role)
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet, "/api/v1/projects/"+url.PathEscape(project)+"/role-grants", query, nil, "", http.StatusOK, maxProjectRoleReadBytes)
	if err != nil {
		return result, err
	}
	var page ProjectRolePage
	fields, err := contextObject(raw, &page, []string{"items"}, nil)
	if err != nil || !requiredNullable(fields, "next_cursor") || page.Items == nil || len(page.Items) > limit ||
		(page.NextCursor != nil && (!validTaskCursor(*page.NextCursor) || len(page.Items) == 0)) || !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	var items []json.RawMessage
	if err := json.Unmarshal(fields["items"], &items); err != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	seen := make(map[[16]byte]bool)
	for index, item := range items {
		value := &page.Items[index]
		if validateProjectRoleGrant(item, value, project) != nil ||
			(status != nil && value.Status != *status) || (role != nil && value.Role != *role) {
			return result, &Failure{Code: "invalid_api_response"}
		}
		identity, _ := uuidIdentity(value.ID)
		if seen[identity] {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[identity] = true
	}
	return Result[ProjectRolePage]{Raw: raw, Value: page}, nil
}

func (c *Client) ProjectRole(ctx context.Context, project, grant string) (Result[ProjectRoleGrant], error) {
	var result Result[ProjectRoleGrant]
	if !validUUID(project) || len(project) > 100 || !validUUID(grant) || len(grant) > 100 {
		return result, errors.New("PROJECT_ID and GRANT_ID must be UUIDs")
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet, "/api/v1/projects/"+url.PathEscape(project)+"/role-grants/"+url.PathEscape(grant), "", nil, "", http.StatusOK, maxProjectRoleReadBytes)
	if err != nil {
		return result, err
	}
	var value ProjectRoleGrant
	if validateProjectRoleGrant(raw, &value, project) != nil || !sameUUID(value.ID, grant) || !c.safeMutationResponse(raw) {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[ProjectRoleGrant]{Raw: raw, Value: value}, nil
}

func validateProjectRoleGrant(raw json.RawMessage, value *ProjectRoleGrant, project string) error {
	fields, err := contextObject(raw, value, []string{
		"id", "project_id", "actor_profile_id", "role", "status", "version", "grant_method", "qualification_snapshot",
		"granted_by_actor_profile_id", "granted_by_admin_role_grant_id", "granted_at", "grant_reason",
	}, nil)
	if err != nil || !requiredNullable(fields, "revoked_by_actor_profile_id", "revoked_at", "revoked_reason") ||
		!validUUID(value.ID) || !sameUUID(value.ProjectID, project) || !validUUID(value.ActorProfileID) ||
		!validUUID(value.GrantedByActorProfileID) || !validUUID(value.GrantedByAdminRoleGrantID) ||
		!validProjectRole(value.Role) || value.GrantMethod != "manual" || !validTime(value.GrantedAt) || !validRoleReason(value.GrantReason) {
		return errors.New("invalid project grant")
	}
	snapshot := &value.QualificationSnapshot
	members, err := contextObject(fields["qualification_snapshot"], snapshot, []string{
		"id", "requested_role", "skills_snapshot", "reputation_snapshot", "prior_project_work_refs", "external_expertise_refs",
		"captured_by_actor_profile_id", "captured_by_admin_role_grant_id", "captured_at",
	}, []string{"prior_project_work_refs", "external_expertise_refs"})
	if err != nil || !validUUID(snapshot.ID) || snapshot.RequestedRole != value.Role ||
		!sameUUID(snapshot.CapturedByActorProfileID, value.GrantedByActorProfileID) ||
		!sameUUID(snapshot.CapturedByAdminRoleGrantID, value.GrantedByAdminRoleGrantID) ||
		!validTime(snapshot.CapturedAt) || validateRoleQualification(members, &snapshot.roleQualification) != nil {
		return errors.New("invalid qualification snapshot")
	}
	switch value.Status {
	case "active":
		if value.Version == 1 && value.RevokedByActorProfileID == nil && value.RevokedAt == nil && value.RevokedReason == nil {
			return nil
		}
	case "revoked":
		if value.Version == 2 && value.RevokedByActorProfileID != nil && validUUID(*value.RevokedByActorProfileID) &&
			value.RevokedAt != nil && validTime(*value.RevokedAt) && value.RevokedReason != nil && validRoleReason(*value.RevokedReason) {
			return nil
		}
	}
	return errors.New("invalid project grant lifecycle")
}
