package api

import (
	"context"
	"encoding/json"
)

// ProjectCatalogueEntry is discovery metadata, not project membership or authority.
type ProjectCatalogueEntry struct {
	ProjectID string `json:"project_id"`
	Name      string `json:"name"`
	Status    string `json:"status"`
}

type ProjectCataloguePage struct {
	Items      []ProjectCatalogueEntry `json:"items"`
	NextCursor *string                 `json:"next_cursor"`
}

// ProjectCatalogue reads one page under current backend system authority.
func (c *Client) ProjectCatalogue(ctx context.Context, limit int, cursor *string) (Result[ProjectCataloguePage], error) {
	var result Result[ProjectCataloguePage]
	query, err := taskPageQuery(limit, cursor)
	if err != nil {
		return result, err
	}
	raw, fields, items, err := c.readPage(ctx, "/api/v1/projects", query, limit)
	if err != nil {
		return result, err
	}
	page := ProjectCataloguePage{Items: make([]ProjectCatalogueEntry, 0, len(items))}
	if json.Unmarshal(fields["next_cursor"], &page.NextCursor) != nil {
		return result, &Failure{Code: "invalid_api_response"}
	}
	seen := make(map[[16]byte]bool, len(items))
	for _, item := range items {
		var project ProjectCatalogueEntry
		_, decodeErr := contextObject(item, &project, []string{"project_id", "name", "status"}, nil)
		identity, valid := uuidIdentity(project.ProjectID)
		if decodeErr != nil || !valid || seen[identity] || project.Name == "" ||
			!oneOf(project.Status, "draft", "active", "paused", "archived") {
			return result, &Failure{Code: "invalid_api_response"}
		}
		seen[identity] = true
		page.Items = append(page.Items, project)
	}
	return Result[ProjectCataloguePage]{Raw: raw, Value: page}, nil
}
