package command

import (
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

// admin is deliberately separate from caller-owned whoami/profile operations.
// Each read or explicit write uses one public API operation; backend AUTH
// decides afresh and a prior read never authorizes a later write.
func addAdminInspection(root *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	admin := &cobra.Command{Use: "admin", Short: "Read evidence and make explicit administrative decisions"}
	actor := &cobra.Command{Use: "actor", Short: "Read and explicitly manage one exact actor profile"}
	actor.AddCommand(&cobra.Command{
		Use: "show ACTOR_ID", Short: "Read one actor's privacy-bounded administrative profile", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.AdminActor(cmd.Context(), args[0])
			if err != nil || *output == "json" {
				return jsonOrError(stdout, result.Raw, err)
			}
			return writeTaskContextFields(stdout, []contextField{{"Actor profile (not authority)", result.Raw}})
		},
	})
	actor.AddCommand(&cobra.Command{
		Use: "identity-links ACTOR_ID", Short: "Read the actor's one current privacy-bounded identity link", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.AdminIdentityLink(cmd.Context(), args[0])
			if err != nil || *output == "json" {
				return jsonOrError(stdout, result.Raw, err)
			}
			return writeTaskContextFields(stdout, []contextField{{"Identity link (not authority)", result.Raw}})
		},
	})
	addAdminGrantRead(actor, client, output, stdout, true)
	admin.AddCommand(actor)
	grants := addAdminGrantRead(admin, client, output, stdout, false)
	addAdminMutations(admin, actor, grants, client, output, stdout)
	admin.AddCommand(&cobra.Command{
		Use: "permissions", Short: "Read the public permission catalogue", Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.AdminPermissions(cmd.Context())
			if err != nil || *output == "json" {
				return jsonOrError(stdout, result.Raw, err)
			}
			return writeTaskContextFields(stdout, []contextField{{"Permission catalogue (not authority)", result.Raw}})
		},
	})
	admin.AddCommand(&cobra.Command{
		Use: "role-definitions", Short: "Read the public administrative role definitions", Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.AdminRoleDefinitions(cmd.Context())
			if err != nil || *output == "json" {
				return jsonOrError(stdout, result.Raw, err)
			}
			return writeTaskContextFields(stdout, []contextField{{"Role definitions (not authority)", result.Raw}})
		},
	})
	root.AddCommand(admin)
}

func addAdminGrantRead(parent *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer, actor bool) *cobra.Command {
	var scope, project, status, cursor string
	var limit int
	command := &cobra.Command{
		Use: "role-grants", Short: "Read one scope-filtered administrative grant page, not current authority",
		RunE: func(cmd *cobra.Command, args []string) error {
			query := api.AdminGrantQuery{Scope: scope, Limit: limit}
			if cmd.Flags().Changed("project-id") {
				query.ProjectID = &project
			}
			if cmd.Flags().Changed("status") {
				query.Status = &status
			}
			if cmd.Flags().Changed("cursor") {
				query.Cursor = &cursor
			}
			apiClient, err := client()
			if err != nil {
				return err
			}
			var selected *string
			if actor {
				selected = &args[0]
			}
			result, err := apiClient.AdminRoleGrants(cmd.Context(), selected, query)
			if err != nil || *output == "json" {
				return jsonOrError(stdout, result.Raw, err)
			}
			return writeTaskContextFields(stdout, []contextField{{"Grant history (not authority)", result.Raw}})
		},
	}
	if actor {
		command.Use += " ACTOR_ID"
		command.Args = cobra.ExactArgs(1)
	} else {
		command.Args = cobra.NoArgs
	}
	command.Flags().StringVar(&scope, "scope", "", "Required system or project scope")
	command.Flags().StringVar(&project, "project-id", "", "Required exact project UUID for project scope only")
	command.Flags().StringVar(&status, "status", "", "active, revoked or all (default: active)")
	command.Flags().IntVar(&limit, "limit", 50, "Page size, 1–100")
	command.Flags().StringVar(&cursor, "cursor", "", "Opaque next cursor from the prior page")
	parent.AddCommand(command)
	return command
}
