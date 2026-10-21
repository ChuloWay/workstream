package command

import (
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addProjectContributorCandidates(roles *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	var limit int
	var cursor string
	cmd := &cobra.Command{
		Use: "candidates PROJECT_ID", Short: "Discover one authorized page of potential grant targets (not qualification)", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			var selectedCursor *string
			if cmd.Flags().Changed("cursor") {
				selectedCursor = &cursor
			}
			result, err := apiClient.ProjectContributorCandidates(cmd.Context(), args[0], limit, selectedCursor)
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			return writeTaskContextFields(stdout, []contextField{
				{"Project", args[0]}, {"Contributor candidates (not qualification or authority)", result.Value.Items}, {"Next cursor", result.Value.NextCursor},
			})
		},
	}
	cmd.Flags().IntVar(&limit, "limit", 50, "Page size (1–100; keep unchanged when continuing)")
	cmd.Flags().StringVar(&cursor, "cursor", "", "Opaque continuation; keep project and limit unchanged")
	roles.AddCommand(cmd)
}
