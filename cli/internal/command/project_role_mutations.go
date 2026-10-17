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
	addProjectRoleReads(roles, client, output, stdout)
	project.AddCommand(roles)
}

func addProjectRoleReads(roles *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	var limit int
	var cursor, status, role string
	list := &cobra.Command{
		Use: "list PROJECT_ID", Short: "Inspect one authorized page of retained project grants", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			selected := func(name string, value *string) *string {
				if cmd.Flags().Changed(name) {
					return value
				}
				return nil
			}
			result, err := apiClient.ProjectRoles(cmd.Context(), args[0], limit, selected("cursor", &cursor), selected("status", &status), selected("role", &role))
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			return writeTaskContextFields(stdout, []contextField{
				{"Project", args[0]}, {"Grant history (not authority)", result.Value.Items}, {"Next cursor", result.Value.NextCursor},
			})
		},
	}
	list.Flags().IntVar(&limit, "limit", 50, "Page size (1–100; keep unchanged when continuing)")
	list.Flags().StringVar(&cursor, "cursor", "", "Opaque continuation; keep project and filters unchanged")
	list.Flags().StringVar(&status, "status", "", "Optional active or revoked filter")
	list.Flags().StringVar(&role, "role", "", "Optional submitter or reviewer filter")
	roles.AddCommand(list, &cobra.Command{
		Use: "show PROJECT_ID GRANT_ID", Short: "Inspect one exact retained grant and its qualification history", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.ProjectRole(cmd.Context(), args[0], args[1])
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			return writeTaskContextFields(stdout, []contextField{{"Grant history (not authority)", result.Raw}})
		},
	})
}
