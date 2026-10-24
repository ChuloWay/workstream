package command

import (
	"fmt"
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addProjectCatalogue(project *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	var page pageFlags
	cmd := &cobra.Command{
		Use: "list", Short: "List one minimal project catalogue page under system authority", Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			query := page.query(cmd)
			result, err := apiClient.ProjectCatalogue(cmd.Context(), query.Limit, query.Cursor)
			if err != nil || *output == "json" {
				return jsonOrError(stdout, result.Raw, err)
			}
			for _, item := range result.Value.Items {
				if _, err := fmt.Fprintf(stdout, "Project: %s\nName: %s\nStatus: %s\n",
					safeText(item.ProjectID), safeText(item.Name), safeText(item.Status)); err != nil {
					return err
				}
			}
			_, err = fmt.Fprintf(stdout, "Next cursor: %s\n", optional(result.Value.NextCursor))
			return err
		},
	}
	page.bind(cmd, 50)
	project.AddCommand(cmd)
}
