package command

import (
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addGuideConfiguration(guide *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	var editInput, editKey string
	edit := &cobra.Command{
		Use: "edit PROJECT_ID GUIDE_ID", Short: "Edit mutable summary fields on an exact draft guide", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			body, err := readJSONInput(editInput)
			if err != nil {
				return err
			}
			result, err := apiClient.EditGuide(cmd.Context(), args[0], args[1], body, editKey)
			if err != nil || *output == "json" {
				return jsonOrError(stdout, result.Raw, err)
			}
			return writeTaskContextFields(stdout, []contextField{{"Draft guide edit", result.Value}})
		},
	}
	edit.Flags().StringVar(&editInput, "input", "", "Required regular public guide edit JSON file (at most 1MiB)")
	edit.Flags().StringVar(&editKey, "idempotency-key", "", "Required caller-owned UUID; retain with unchanged input for manual replay")
	guide.AddCommand(edit)

	addGuidePolicyCommand(guide, client, output, stdout, "review")
	addGuidePolicyCommand(guide, client, output, stdout, "revision")
}

func addGuidePolicyCommand(guide *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer, kind string) {
	var input, key, ifMatch string
	set := &cobra.Command{
		Use: "set-" + kind + "-policy PROJECT_ID GUIDE_ID", Short: "Set exact draft-guide " + kind + " policy with a caller-owned precondition", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			body, err := readJSONInput(input)
			if err != nil {
				return err
			}
			var result api.Result[api.PolicyConfigured]
			if kind == "review" {
				result, err = apiClient.ConfigureReviewPolicy(cmd.Context(), args[0], args[1], body, key, ifMatch)
			} else {
				result, err = apiClient.ConfigureRevisionPolicy(cmd.Context(), args[0], args[1], body, key, ifMatch)
			}
			if err != nil || *output == "json" {
				return jsonOrError(stdout, result.Raw, err)
			}
			return writeTaskContextFields(stdout, []contextField{{"Selected " + kind + " policy", result.Value}})
		},
	}
	set.Flags().StringVar(&input, "input", "", "Required regular public "+kind+" policy JSON file (at most 1MiB)")
	set.Flags().StringVar(&key, "idempotency-key", "", "Required caller-owned UUID; retain with unchanged input and If-Match for manual replay")
	set.Flags().StringVar(&ifMatch, "if-match", "", "Required exact selected-policy ETag, or quoted no-current-policy sentinel")
	guide.AddCommand(set)
}
