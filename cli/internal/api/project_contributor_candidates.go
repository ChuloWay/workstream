package api

import (
	"context"
	"encoding/json"
)

// ContributorCandidate is the backend's minimal project-scoped discovery row.
// It is not a qualification or a grant decision.
type ContributorCandidate struct {
	ActorProfileID string  `json:"actor_profile_id"`
	DisplayName    *string `json:"display_name"`
}

type ContributorCandidatePage struct {
	Items      []ContributorCandidate `json:"items"`
	NextCursor *string                `json:"next_cursor"`
}

// ProjectContributorCandidates reads one page under current backend authority.
func (c *Client) ProjectContributorCandidates(ctx context.Context, project string, limit int, cursor *string) (Result[ContributorCandidatePage], error) {
	var result Result[ContributorCandidatePage]
	path, err := projectReadPath(project, "/contributor-candidates")
	if err != nil {
		return result, err
	}
	query, err := taskPageQuery(limit, cursor)
	if err != nil {
		return result, err
	}
	raw, fields, items, err := c.readPage(ctx, path, query, limit)
	if err != nil {
		return result, err
	}
	page := ContributorCandidatePage{Items: make([]ContributorCandidate, 0, len(items))}
	if json.Unmarshal(fields["next_cursor"], &page.NextCursor) != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	seen := make(map[[16]byte]bool, len(items))
	for _, item := range items {
		var candidate ContributorCandidate
		members, decodeErr := contextObject(item, &candidate, []string{"actor_profile_id"}, nil)
		identity, valid := uuidIdentity(candidate.ActorProfileID)
		if decodeErr != nil || !requiredNullable(members, "display_name") || !valid || seen[identity] {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[identity] = true
		page.Items = append(page.Items, candidate)
	}
	return Result[ContributorCandidatePage]{Raw: raw, Value: page}, nil
}
