package command

import (
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addGuideSufficiencyMutations(sufficiency *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	var createInput, createKey string
	create := &cobra.Command{
		Use: "create PROJECT_ID GUIDE_ID", Short: "Record a human sufficiency diagnostic for the current draft source snapshot (not compiled setup)", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			body, err := readJSONInput(createInput)
			if err != nil {
				return err
			}
			result, err := apiClient.CreateGuideSufficiencyReport(cmd.Context(), args[0], args[1], body, createKey)
			return writeGuideInspection(stdout, *output, "Human sufficiency diagnostic (not compiled setup or approval)", result, err)
		},
	}
	create.Flags().StringVar(&createInput, "input", "", "Required public sufficiency-report JSON file (at most 1MiB)")
	create.Flags().StringVar(&createKey, "idempotency-key", "", "Required caller-owned UUID; retain with unchanged input for manual replay")

	var acknowledgeInput, acknowledgeKey string
	acknowledge := &cobra.Command{
		Use: "acknowledge-warnings PROJECT_ID GUIDE_ID REPORT_ID", Short: "Explicitly acknowledge one sufficiency report's warnings (not policy approval)", Args: cobra.ExactArgs(3),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			body, err := readJSONInput(acknowledgeInput)
			if err != nil {
				return err
			}
			result, err := apiClient.AcknowledgeGuideSufficiencyWarnings(cmd.Context(), args[0], args[1], args[2], body, acknowledgeKey)
			return writeGuideInspection(stdout, *output, "Human warning acknowledgement (not compilation or activation)", result, err)
		},
	}
	acknowledge.Flags().StringVar(&acknowledgeInput, "input", "", "Required public warning-acknowledgement JSON file (at most 1MiB; {} for no note)")
	acknowledge.Flags().StringVar(&acknowledgeKey, "idempotency-key", "", "Required caller-owned UUID; retain with unchanged input for manual replay")
	sufficiency.AddCommand(create, acknowledge)
}
