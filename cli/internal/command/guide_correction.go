package command

import (
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addGuideCorrection(guide *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	var input, key string
	correct := &cobra.Command{
		Use: "correct PROJECT_ID GUIDE_ID COMPILATION_ID", Short: "Save a correction of an exact guide proposal (does not dispatch)", Args: cobra.ExactArgs(3),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			body, err := readJSONInput(input)
			if err != nil {
				return err
			}
			result, err := apiClient.CorrectGuideProposal(cmd.Context(), args[0], args[1], args[2], body, key)
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			return writeTaskContextFields(stdout, []contextField{{"Saved guide correction (not dispatched or activated)", result.Raw}})
		},
	}
	correct.Flags().StringVar(&input, "input", "", "Required public correction JSON file containing inspected target and reason (at most 1MiB)")
	correct.Flags().StringVar(&key, "idempotency-key", "", "Required caller-owned UUID; retain with unchanged input for manual replay")
	var saved string
	dispatch := &cobra.Command{
		Use: "dispatch-correction PROJECT_ID GUIDE_ID COMPILATION_ID", Short: "Explicitly dispatch a saved correction; report status, not completion", Args: cobra.ExactArgs(3),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			receipt, err := readJSONInput(saved)
			if err != nil {
				return err
			}
			result, err := apiClient.DispatchGuideCorrection(cmd.Context(), args[0], args[1], args[2], receipt)
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			return writeTaskContextFields(stdout, []contextField{{"Correction dispatch status (not completion or activation)", result.Raw}})
		},
	}
	dispatch.Flags().StringVar(&saved, "input", "", "Required saved GuideProposalCorrectionReceipt JSON file (at most 1MiB); no new idempotency key")
	guide.AddCommand(correct, dispatch)
}
