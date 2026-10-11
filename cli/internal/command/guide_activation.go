package command

import (
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addGuideActivation(guide *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	var input, key string
	activate := &cobra.Command{
		Use: "activate PROJECT_ID GUIDE_ID", Short: "Activate exactly selected, separately approved guide policies", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			body, err := readJSONInput(input)
			if err != nil {
				return err
			}
			result, err := apiClient.ActivateGuide(cmd.Context(), args[0], args[1], body, key)
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			return writeTaskContextFields(stdout, []contextField{{"Guide activation receipt", result.Raw}})
		},
	}
	activate.Flags().StringVar(&input, "input", "", "Required public activation JSON with exact inspected selections (at most 1MiB)")
	activate.Flags().StringVar(&key, "idempotency-key", "", "Required caller-owned UUID; retain with unchanged input for manual replay")
	guide.AddCommand(activate)
}
