package command

import (
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addProjectRoleMutations(project *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	roles := &cobra.Command{Use: "role-grant", Short: "Explicit project contributor-role decisions (not AdminRole grants)"}
	for _, action := range []string{"issue", "revoke"} {
		var input, key string
		use, count := "issue PROJECT_ID", 1
		if action == "revoke" {
			use, count = "revoke PROJECT_ID GRANT_ID", 2
		}
		cmd := &cobra.Command{
			Use: use, Short: action + " one exact-project Submitter/Reviewer grant through AUTH", Args: cobra.ExactArgs(count),
			RunE: func(cmd *cobra.Command, args []string) error {
				apiClient, err := client()
				if err != nil {
					return err
				}
				body, err := readJSONInput(input)
				if err != nil {
					return err
				}
				var result api.Result[api.ProjectRoleReceipt]
				if action == "issue" {
					result, err = apiClient.IssueProjectRole(cmd.Context(), args[0], body, key)
				} else {
					result, err = apiClient.RevokeProjectRole(cmd.Context(), args[0], args[1], body, key)
				}
				if err != nil {
					return err
				}
				if *output == "json" {
					return writeJSON(stdout, result.Raw)
				}
				return writeTaskContextFields(stdout, []contextField{{"Project role receipt (not cached authority)", result.Raw}})
			},
		}
		cmd.Flags().StringVar(&input, "input", "", "Required public decision JSON; qualification and reason are caller-supplied")
		cmd.Flags().StringVar(&key, "idempotency-key", "", "Required caller-owned UUID for unchanged manual replay")
		roles.AddCommand(cmd)
	}
	project.AddCommand(roles)
}
