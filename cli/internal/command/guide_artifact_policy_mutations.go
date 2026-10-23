package command

import (
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addGuideArtifactPolicyMutations(artifact *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	var createInput, createKey string
	create := &cobra.Command{
		Use: "create PROJECT_ID GUIDE_ID", Short: "Create a manual draft after authoritative finalized setup (not compiled approval)", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			body, err := readJSONInput(createInput)
			if err != nil {
				return err
			}
			result, err := apiClient.CreateManualArtifactPolicy(cmd.Context(), args[0], args[1], body, createKey)
			return writeGuideInspection(stdout, *output, "Manual artifact-policy draft (not effective policy or activation)", result, err)
		},
	}
	create.Flags().StringVar(&createInput, "input", "", "Required public manual policy create JSON file (at most 1MiB)")
	create.Flags().StringVar(&createKey, "idempotency-key", "", "Required caller-owned UUID; retain with unchanged input for manual replay")

	var updateInput, updateKey string
	update := &cobra.Command{
		Use: "update PROJECT_ID GUIDE_ID POLICY_ID", Short: "Append a manual draft successor with exact predecessor hash (not approval)", Args: cobra.ExactArgs(3),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			body, err := readJSONInput(updateInput)
			if err != nil {
				return err
			}
			result, err := apiClient.UpdateManualArtifactPolicy(cmd.Context(), args[0], args[1], args[2], body, updateKey)
			return writeGuideInspection(stdout, *output, "Manual artifact-policy successor (not effective policy or activation)", result, err)
		},
	}
	update.Flags().StringVar(&updateInput, "input", "", "Required public manual policy update JSON file (at most 1MiB; include expected_policy_hash)")
	update.Flags().StringVar(&updateKey, "idempotency-key", "", "Required caller-owned UUID; retain with unchanged input for manual replay")
	artifact.AddCommand(create, update)
}
