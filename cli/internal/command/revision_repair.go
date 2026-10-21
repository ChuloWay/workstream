package command

import (
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addRevisionRepair(task *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	var key, reason, parentID, parentSHA, manifestID string
	cmd := &cobra.Command{
		Use: "repair-revision PROJECT_ID TASK_ID", Short: "Explicitly repair the current revision context under fresh project-manager authority", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			if !cmd.Flags().Changed("reason") || !cmd.Flags().Changed("idempotency-key") {
				return commandError{"invalid_arguments", "--reason and --idempotency-key are required"}
			}
			parent := cmd.Flags().Changed("parent-preparation-id") || cmd.Flags().Changed("parent-preparation-sha256")
			manifest := cmd.Flags().Changed("routing-manifest-id")
			if parent == manifest || (parent && (!cmd.Flags().Changed("parent-preparation-id") || !cmd.Flags().Changed("parent-preparation-sha256"))) {
				return commandError{"invalid_arguments", "select either an exact parent preparation ID and sha256, or one routing manifest UUID"}
			}
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.RepairRevisionContext(cmd.Context(), args[0], args[1], key, api.RevisionRepairInput{
				ParentPreparationID: parentID, ParentPreparationSHA256: parentSHA,
				RoutingManifestID: manifestID, Reason: reason,
			})
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			return writeTaskContextFields(stdout, []contextField{{"Revision repair result (server disposition, not new authority)", result.Value}})
		},
	}
	cmd.Flags().StringVar(&key, "idempotency-key", "", "Required caller-owned UUID for unchanged manual replay")
	cmd.Flags().StringVar(&reason, "reason", "", "Required explanation for this exact repair")
	cmd.Flags().StringVar(&parentID, "parent-preparation-id", "", "Exact blocked preparation UUID")
	cmd.Flags().StringVar(&parentSHA, "parent-preparation-sha256", "", "Exact lowercase sha256 digest of blocked preparation")
	cmd.Flags().StringVar(&manifestID, "routing-manifest-id", "", "Missing-root routing manifest UUID (instead of parent pair)")
	task.AddCommand(cmd)
}
