package api

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"strings"
	"unicode"
	"unicode/utf8"
)

// These are returned mutation receipts, never locally cached authorization.
type ServiceActorProvision struct {
	ActorProfileID     string `json:"actor_profile_id"`
	ServiceIdentity    string `json:"service_identity"`
	ActorStatus        string `json:"actor_status"`
	IdentityLinkStatus string `json:"identity_link_status"`
	ProvisioningMethod string `json:"provisioning_method"`
	CreatedAt          string `json:"created_at"`
	LinkedAt           string `json:"linked_at"`
}

type AdminLifecycleReceipt struct {
	ResourceType string `json:"resource_type"`
	ResourceID   string `json:"resource_id"`
	Version      *int   `json:"version"`
	HTTPStatus   int    `json:"http_status"`
}

type AdminGrantReceipt struct {
	ResourceType string `json:"resource_type"`
	ResourceID   string `json:"resource_id"`
	Version      int    `json:"version"`
	HTTPStatus   int    `json:"http_status"`
}

type serviceActorInput struct {
	ServiceIdentity string `json:"service_identity"`
	Subject         string `json:"subject"`
	Reason          string `json:"reason"`
}

type lifecycleInput struct {
	Reason string `json:"reason"`
}

type adminGrantIssueInput struct {
	TargetActorProfileID string  `json:"target_actor_profile_id"`
	Role                 string  `json:"role"`
	ScopeType            string  `json:"scope_type"`
	ScopeProjectID       *string `json:"scope_project_id"`
	Reason               string  `json:"reason"`
}

func validAdminMutationBody(body json.RawMessage, value any, required []string) error {
	if len(body) == 0 || len(body) > MaxGuideInputBytes || !utf8.Valid(body) {
		return errors.New("--input must contain a bounded UTF-8 public decision JSON object")
	}
	if _, err := contextObject(body, value, required, nil); err != nil {
		return errors.New("--input must contain the closed public decision fields")
	}
	return nil
}

func validAdminReason(reason string) bool {
	return utf8.ValidString(reason) && len(reason) >= 1 && len(reason) <= 500 && !strings.ContainsRune(reason, 0)
}

// Python str.strip treats these four ASCII separators as whitespace in
// addition to Unicode White_Space. Keep local input checks aligned with the
// public Pydantic validators; the backend still makes the final decision.
func pythonStrip(value string) string {
	return strings.TrimFunc(value, func(r rune) bool {
		return unicode.IsSpace(r) || (r >= '\x1c' && r <= '\x1f')
	})
}

func validLifecycleReason(reason string) bool {
	normalized := pythonStrip(reason)
	return utf8.ValidString(reason) && len(normalized) >= 1 && len(normalized) <= 500 && !strings.ContainsRune(reason, 0)
}

func adminMutationFailure(err error) error {
	var failure *Failure
	if errors.As(err, &failure) && failure.OutcomeUnknown {
		failure.RecoveryHint = "administrative write outcome unknown; inspect the exact resource as observation only, then deliberately replay only the unchanged action, selectors, input file bytes and idempotency key; do not infer authority from a read"
	}
	return err
}

func adminInvalidResponse() error {
	return adminMutationFailure(&Failure{Code: "invalid_api_response", OutcomeUnknown: true})
}

func validAdminKey(key string) bool { return validUUID(key) && len(key) <= 100 }

func (c *Client) ProvisionServiceActor(ctx context.Context, body json.RawMessage, key string) (Result[ServiceActorProvision], error) {
	var result Result[ServiceActorProvision]
	var input serviceActorInput
	if err := validAdminMutationBody(body, &input, []string{"service_identity", "subject", "reason"}); err != nil ||
		!validServiceIdentity(input.ServiceIdentity) || len(input.Subject) == 0 || len(input.Subject) > 200 ||
		pythonStrip(input.Subject) != input.Subject || strings.ContainsRune(input.Subject, 0) ||
		!utf8.ValidString(input.Subject) || !utf8.ValidString(input.Reason) || len(input.Reason) < 1 || len(input.Reason) > 500 ||
		!validAdminKey(key) {
		return result, errors.New("--input must contain a service identity, bounded subject and provision reason; --idempotency-key must be a UUID")
	}
	raw, err := c.requestWithKey(ctx, http.MethodPost, "/api/v1/service-actors", "", body, key, http.StatusCreated)
	if err != nil {
		return result, adminMutationFailure(err)
	}
	var value ServiceActorProvision
	_, err = contextObject(raw, &value, []string{"actor_profile_id", "service_identity", "actor_status", "identity_link_status", "provisioning_method", "created_at", "linked_at"}, nil)
	if err != nil || !validUUID(value.ActorProfileID) || value.ServiceIdentity != input.ServiceIdentity ||
		value.ActorStatus != "active" || value.IdentityLinkStatus != "active" ||
		value.ProvisioningMethod != "manual_service_provisioning" || !validTime(value.CreatedAt) ||
		!validTime(value.LinkedAt) || !c.safeMutationResponse(raw) {
		return result, adminInvalidResponse()
	}
	return Result[ServiceActorProvision]{Raw: raw, Value: value}, nil
}

func (c *Client) MutateAdminActor(ctx context.Context, actor, action string, body json.RawMessage, key string) (Result[AdminLifecycleReceipt], error) {
	var result Result[AdminLifecycleReceipt]
	if !oneOf(action, "suspend", "reactivate", "deactivate") || !validUUID(actor) || len(actor) > 100 {
		return result, errors.New("select an actor UUID and suspend, reactivate or deactivate")
	}
	return c.adminLifecycleWrite(ctx, "/api/v1/actors/"+url.PathEscape(actor)+"/"+action, actor, "actor_profile", body, key)
}

func (c *Client) MutateAdminIdentityLink(ctx context.Context, link, action string, body json.RawMessage, key string) (Result[AdminLifecycleReceipt], error) {
	var result Result[AdminLifecycleReceipt]
	if !oneOf(action, "revoke", "reactivate") || !validUUID(link) || len(link) > 100 {
		return result, errors.New("select an identity-link UUID and revoke or reactivate")
	}
	return c.adminLifecycleWrite(ctx, "/api/v1/actor-identity-links/"+url.PathEscape(link)+"/"+action, link, "actor_identity_link", body, key)
}

func (c *Client) adminLifecycleWrite(ctx context.Context, path, selector, resourceType string, body json.RawMessage, key string) (Result[AdminLifecycleReceipt], error) {
	var result Result[AdminLifecycleReceipt]
	var input lifecycleInput
	if err := validAdminMutationBody(body, &input, []string{"reason"}); err != nil || !validLifecycleReason(input.Reason) || !validAdminKey(key) {
		return result, errors.New("--input must contain a bounded lifecycle reason; --idempotency-key must be a UUID")
	}
	raw, err := c.requestWithKey(ctx, http.MethodPost, path, "", body, key, http.StatusOK)
	if err != nil {
		return result, adminMutationFailure(err)
	}
	var value AdminLifecycleReceipt
	_, err = contextObject(raw, &value, []string{"resource_type", "resource_id", "http_status"}, nil)
	if err != nil || value.ResourceType != resourceType || !sameUUID(value.ResourceID, selector) ||
		value.Version != nil || value.HTTPStatus != http.StatusOK || !c.safeMutationResponse(raw) {
		return result, adminInvalidResponse()
	}
	return Result[AdminLifecycleReceipt]{Raw: raw, Value: value}, nil
}

func (c *Client) IssueAdminGrant(ctx context.Context, body json.RawMessage, key string) (Result[AdminGrantReceipt], error) {
	var result Result[AdminGrantReceipt]
	var input adminGrantIssueInput
	if err := validAdminMutationBody(body, &input, []string{"target_actor_profile_id", "role", "scope_type", "reason"}); err != nil ||
		!validUUID(input.TargetActorProfileID) || !validAdminRole(input.Role) || !validAdminScope(input.ScopeType) ||
		(oneOf(input.Role, "access_administrator", "operator") && input.ScopeType != "system") ||
		(input.ScopeType == "project") != (input.ScopeProjectID != nil) ||
		(input.ScopeProjectID != nil && !validUUID(*input.ScopeProjectID)) ||
		!validAdminReason(input.Reason) || !validAdminKey(key) {
		return result, errors.New("--input must contain a target UUID, admin role, exact scope and reason; --idempotency-key must be a UUID")
	}
	return c.adminGrantWrite(ctx, "/api/v1/admin-role-grants", "", body, key, http.StatusCreated, 1)
}

func (c *Client) RevokeAdminGrant(ctx context.Context, grant string, body json.RawMessage, key string) (Result[AdminGrantReceipt], error) {
	var result Result[AdminGrantReceipt]
	var input lifecycleInput
	if !validUUID(grant) || len(grant) > 100 || validAdminMutationBody(body, &input, []string{"reason"}) != nil ||
		!validAdminReason(input.Reason) || !validAdminKey(key) {
		return result, errors.New("select a grant UUID, bounded public revocation reason and UUID idempotency key")
	}
	return c.adminGrantWrite(ctx, "/api/v1/admin-role-grants/"+url.PathEscape(grant)+"/revoke", grant, body, key, http.StatusOK, 2)
}

func (c *Client) adminGrantWrite(ctx context.Context, path, selector string, body json.RawMessage, key string, status, version int) (Result[AdminGrantReceipt], error) {
	var result Result[AdminGrantReceipt]
	raw, err := c.requestWithKey(ctx, http.MethodPost, path, "", body, key, status)
	if err != nil {
		return result, adminMutationFailure(err)
	}
	var value AdminGrantReceipt
	_, err = contextObject(raw, &value, []string{"resource_type", "resource_id", "version", "http_status"}, nil)
	if err != nil || value.ResourceType != "admin_role_grant" || !validUUID(value.ResourceID) ||
		(selector != "" && !sameUUID(value.ResourceID, selector)) || value.Version != version ||
		value.HTTPStatus != status || !c.safeMutationResponse(raw) {
		return result, adminInvalidResponse()
	}
	return Result[AdminGrantReceipt]{Raw: raw, Value: value}, nil
}
