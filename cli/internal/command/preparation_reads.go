package command

import (
	"fmt"
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

// projectPageFlags binds the shared project-list page flags; unset flags stay nil.
type projectPageFlags struct {
	limit           int
	cursor, outcome string
}

func (f *projectPageFlags) query(cmd *cobra.Command) api.ProjectPageQuery {
	q := api.ProjectPageQuery{Limit: f.limit}
	if cmd.Flags().Changed("cursor") {
		q.Cursor = &f.cursor
	}
	if cmd.Flags().Changed("outcome") {
		q.Outcome = &f.outcome
	}
	return q
}

func (f *projectPageFlags) bind(cmd *cobra.Command, outcome bool) {
	cmd.Flags().IntVar(&f.limit, "limit", 50, "Page size (1–100; keep unchanged when continuing)")
	cmd.Flags().StringVar(&f.cursor, "cursor", "", "Opaque next cursor from the previous page (same filters)")
	if outcome {
		cmd.Flags().StringVar(&f.outcome, "outcome", "", "pending, passed, failed or infrastructure_failed")
	}
}

// addProjectPreparationReads adds `project preparations PROJECT_ID` for Project Managers.
func addProjectPreparationReads(project *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	var page projectPageFlags
	preparations := &cobra.Command{Use: "preparations PROJECT_ID", Short: "List every contributor's ZIP preparations in a project, newest first (counts only, no findings)", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.ProjectPreparations(cmd.Context(), args[0], page.query(cmd))
			if err != nil || *output == "json" {
				return jsonOrError(stdout, result.Raw, err)
			}
			for _, p := range result.Value.Items {
				if _, err := fmt.Fprintf(stdout, "Contributor: %s\n", safeText(p.ActorProfileID)); err != nil {
					return err
				}
				if err := writePreparation(stdout, p.PreparationSummary); err != nil {
					return err
				}
			}
			_, err = fmt.Fprintf(stdout, "Next cursor: %s\n", optional(result.Value.Cursor))
			return err
		}}
	page.bind(preparations, true)
	project.AddCommand(preparations)
}
