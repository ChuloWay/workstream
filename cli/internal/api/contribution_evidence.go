package api

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"math/big"
	"mime"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"
)

const maxContributionBytes = 32 * 1024 * 1024

type ContributionFilters struct {
	Project, Type, From, Before string
}

type ContributionEvidence struct {
	ExportedAt string               `json:"exported_at"`
	Items      []ContributionRecord `json:"items"`
}

type ContributionRecord struct {
	ID                 string              `json:"contribution_id"`
	Project            string              `json:"project_id"`
	Task               string              `json:"task_id"`
	Submission         string              `json:"submission_id"`
	Contributor        string              `json:"contributor_id"`
	DisplayName        *string             `json:"contributor_display_name"`
	Type               string              `json:"contribution_type"`
	Review             *string             `json:"source_review_id"`
	Lease              *string             `json:"source_review_lease_id"`
	Acceptance         *string             `json:"source_final_acceptance_id"`
	Assignment         *string             `json:"source_task_assignment_id"`
	ArtifactHash       string              `json:"artifact_hash"`
	Policy             string              `json:"contribution_policy_version_id"`
	PolicyNumber       *big.Int            `json:"policy_version_number"`
	RecordedAt         string              `json:"recorded_at"`
	AcceptedAt         *string             `json:"accepted_at"`
	AcceptanceSource   *string             `json:"acceptance_source"`
	AcceptanceReview   *string             `json:"acceptance_review_id"`
	AcceptanceManifest *string             `json:"acceptance_routing_manifest_id"`
	TaskTitle          string              `json:"task_title"`
	SourceType         string              `json:"source_type"`
	SourceRef          *string             `json:"source_ref"`
	ExternalTask       *string             `json:"external_task_id"`
	Awards             []ContributionAward `json:"awards"`
}

type ContributionAward struct {
	ID         string `json:"award_id"`
	Definition string `json:"award_definition_id"`
	Instrument string `json:"instrument"`
	Unit       string `json:"unit"`
	Quantity   string `json:"quantity"`
}

var contributionRequired = []string{"contribution_id", "project_id", "task_id", "submission_id", "contributor_id", "contribution_type", "artifact_hash", "contribution_policy_version_id", "policy_version_number", "recorded_at", "task_title", "source_type", "awards"}
var contributionNullable = []string{"contributor_display_name", "source_review_id", "source_review_lease_id", "source_final_acceptance_id", "source_task_assignment_id", "accepted_at", "acceptance_source", "acceptance_review_id", "acceptance_routing_manifest_id", "source_ref", "external_task_id"}
var contributionQuantity = regexp.MustCompile(`^[0-9]+(?:\.[0-9]+)?$`)

// The backend owns selection and authority. Normalize time precision to the
// public Python datetime contract before sending and checking the same filters.
func (f *ContributionFilters) query(projectScope, csv bool) (string, string, error) {
	bad := errors.New("select a valid project UUID, contribution type and aware RFC3339 interval")
	if (projectScope && f.Project == "") || (f.Project != "" && (!validUUID(f.Project) || len(f.Project) > 100)) ||
		(f.Type != "" && f.Type != "accepted_submission" && f.Type != "completed_review") {
		return "", "", bad
	}
	for _, value := range []*string{&f.From, &f.Before} {
		if *value != "" {
			t, err := time.Parse(time.RFC3339Nano, *value)
			if err != nil {
				return "", "", bad
			}
			*value = t.UTC().Truncate(time.Microsecond).Format(time.RFC3339Nano)
		}
	}
	if f.From != "" && f.Before != "" {
		start, _ := time.Parse(time.RFC3339Nano, f.From)
		end, _ := time.Parse(time.RFC3339Nano, f.Before)
		if !start.Before(end) {
			return "", "", bad
		}
	}
	path := "/api/v1/actors/me/contributions"
	values := url.Values{"format": {"json"}}
	if projectScope {
		path = "/api/v1/projects/" + url.PathEscape(f.Project) + "/contributions/export"
	} else if f.Project != "" {
		values.Set("project_id", f.Project)
	}
	if csv {
		values.Set("format", "csv")
	}
	for key, value := range map[string]string{"contribution_type": f.Type, "recorded_from": f.From, "recorded_before": f.Before} {
		if value != "" {
			values.Set(key, value)
		}
	}
	return path, values.Encode(), nil
}

func (c *Client) Contributions(ctx context.Context, projectScope bool, filters ContributionFilters) (Result[ContributionEvidence], error) {
	var result Result[ContributionEvidence]
	path, query, err := filters.query(projectScope, false)
	if err != nil {
		return result, err
	}
	raw, err := c.requestWithResponseLimit(ctx, http.MethodGet, path, query, nil, "", http.StatusOK, maxContributionBytes)
	if err != nil {
		return result, err
	}
	var value ContributionEvidence
	fields, err := contextObject(raw, &value, []string{"exported_at", "items"}, nil)
	if err != nil || !validTime(value.ExportedAt) || !c.safeMutationResponse(raw) || validateContributionRecords(fields["items"], filters) != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	return Result[ContributionEvidence]{Raw: raw, Value: value}, nil
}

func (c *Client) ContributionCSV(ctx context.Context, projectScope bool, filters ContributionFilters) ([]byte, error) {
	path, query, err := filters.query(projectScope, true)
	if err != nil {
		return nil, err
	}
	response, err := c.openRequest(ctx, c.http, http.MethodGet, path, query, nil, "", "text/csv")
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, maxContributionBytes+1))
	if err != nil || len(body) > maxContributionBytes {
		return nil, &Failure{Code: "invalid_api_response"}
	}
	if response.StatusCode != http.StatusOK {
		return nil, c.responseFailure(http.MethodGet, response, body)
	}
	mediaType, params, err := mime.ParseMediaType(response.Header.Get("Content-Type"))
	if err != nil || mediaType != "text/csv" || (params["charset"] != "" && !strings.EqualFold(params["charset"], "utf-8")) || c.validateContributionCSV(body, filters) != nil {
		return nil, &Failure{Code: "invalid_api_response"}
	}
	return body, nil
}

func validateContributionRecords(raw json.RawMessage, filters ContributionFilters) error {
	bad := errors.New("invalid contribution evidence")
	var records []json.RawMessage
	if err := json.Unmarshal(raw, &records); err != nil || records == nil || len(records) > 1000 {
		return bad
	}
	seen, awards := make(map[[16]byte]bool), make(map[[16]byte]bool)
	var previousTime time.Time
	var previousID [16]byte
	for _, rawRecord := range records {
		var r ContributionRecord
		fields, err := contextObject(rawRecord, &r, contributionRequired, nil)
		if err != nil || !requiredNullable(fields, contributionNullable...) ||
			(filters.Project != "" && !sameUUID(r.Project, filters.Project)) || (filters.Type != "" && r.Type != filters.Type) ||
			r.PolicyNumber == nil || r.PolicyNumber.Sign() <= 0 || !contextPolicyDigest.MatchString(r.ArtifactHash) {
			return bad
		}
		for _, value := range []string{r.ID, r.Project, r.Task, r.Submission, r.Contributor, r.Policy} {
			if !validUUID(value) {
				return bad
			}
		}
		for _, value := range []*string{r.Review, r.Lease, r.Acceptance, r.Assignment, r.AcceptanceReview, r.AcceptanceManifest} {
			if value != nil && !validUUID(*value) {
				return bad
			}
		}
		accepted := r.Type == "accepted_submission"
		if (!accepted && r.Type != "completed_review") || (r.Review != nil) != !accepted || (r.Lease != nil) != !accepted ||
			(r.Acceptance != nil) != accepted || (r.Assignment != nil) != accepted || (r.AcceptedAt != nil) != accepted || (r.AcceptanceSource != nil) != accepted {
			return bad
		}
		if accepted {
			if !validTime(*r.AcceptedAt) || (*r.AcceptanceSource != "human_review" && *r.AcceptanceSource != "task_post_submit_route") ||
				(r.AcceptanceReview != nil) != (*r.AcceptanceSource == "human_review") || (r.AcceptanceManifest != nil) != (*r.AcceptanceSource == "task_post_submit_route") {
				return bad
			}
		} else if r.AcceptanceReview != nil || r.AcceptanceManifest != nil {
			return bad
		}
		stamp, err := time.Parse(time.RFC3339Nano, r.RecordedAt)
		id, _ := uuidIdentity(r.ID)
		from, _ := time.Parse(time.RFC3339Nano, filters.From)
		before, _ := time.Parse(time.RFC3339Nano, filters.Before)
		if err != nil || seen[id] || (len(seen) > 0 && (stamp.Before(previousTime) || (stamp.Equal(previousTime) && bytes.Compare(id[:], previousID[:]) <= 0))) ||
			(filters.From != "" && stamp.Before(from)) || (filters.Before != "" && !stamp.Before(before)) {
			return bad
		}
		seen[id], previousTime, previousID = true, stamp, id
		var rawAwards []json.RawMessage
		if err := json.Unmarshal(fields["awards"], &rawAwards); err != nil || rawAwards == nil || len(rawAwards) > 2 {
			return bad
		}
		instruments := make(map[string]bool)
		for _, rawAward := range rawAwards {
			var a ContributionAward
			_, err := contextObject(rawAward, &a, []string{"award_id", "award_definition_id", "instrument", "unit", "quantity"}, nil)
			awardID, valid := uuidIdentity(a.ID)
			if err != nil || !valid || awards[awardID] || instruments[a.Instrument] || !validUUID(a.Definition) ||
				(a.Instrument != "money" && a.Instrument != "project_points") || !validContributionQuantity(a.Quantity, a.Instrument) {
				return bad
			}
			awards[awardID], instruments[a.Instrument] = true, true
		}
	}
	return nil
}

// Validate the public fixed-point representation, not eligibility or payments.
func validContributionQuantity(value, instrument string) bool {
	if len(value) > 40 || !contributionQuantity.MatchString(value) {
		return false
	}
	parts := strings.Split(value, ".")
	if len(parts) == 2 && (len(parts[1]) > 18 || instrument == "project_points") {
		return false
	}
	number, ok := new(big.Rat).SetString(value)
	maximum, _ := new(big.Rat).SetString("100000000000000000000")
	return ok && number.Sign() > 0 && number.Cmp(maximum) < 0
}
