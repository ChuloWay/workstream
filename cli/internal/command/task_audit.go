package command

import (
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

// Audit reads are separate from manager and contributor task projections.
func addTaskAudit(root *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	audit := &cobra.Command{Use: "audit", Short: "Read exact Audit Authority projections"}
	task := &cobra.Command{Use: "task", Short: "Read one project's task audit facts"}
	task.AddCommand(&cobra.Command{
		Use: "locked-context PROJECT_ID TASK_ID", Short: "Read immutable task policy lineage (not policy bodies)", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.AuditLockedContext(cmd.Context(), args[0], args[1])
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeSafeJSON(stdout, result.Raw)
			}
			return writeTaskContextFields(stdout, []contextField{{"Locked context", result.Value}})
		},
	})
	var limit int
	var cursor string
	evidence := &cobra.Command{
		Use: "evidence PROJECT_ID TASK_ID", Short: "Read one bounded page of task lifecycle evidence", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			var selected *string
			if cmd.Flags().Changed("cursor") {
				selected = &cursor
			}
			result, err := apiClient.AuditEvidence(cmd.Context(), args[0], args[1], limit, selected)
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeSafeJSON(stdout, result.Raw)
			}
			for _, event := range result.Value.Items {
				if err := writeTaskContextFields(stdout, []contextField{{"Event", event}}); err != nil {
					return err
				}
			}
			return writeTaskContextFields(stdout, []contextField{{"Next cursor", result.Value.NextCursor}})
		},
	}
	evidence.Flags().IntVar(&limit, "limit", 50, "Page size (1–100; keep unchanged when continuing)")
	evidence.Flags().StringVar(&cursor, "cursor", "", "JSON next_cursor from the previous page (same project and task)")
	task.AddCommand(evidence)
	audit.AddCommand(task)
	root.AddCommand(audit)
}
