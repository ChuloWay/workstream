package command

import (
	"context"
	"encoding/json"
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

type adminWriteCall func(*api.Client, context.Context, []string, json.RawMessage, string) (json.RawMessage, error)

func adminWriteCommand(use, description string, count int, client func() (*api.Client, error), output *string, stdout io.Writer, call adminWriteCall) *cobra.Command {
	var input, key string
	cmd := &cobra.Command{
		Use: use, Short: description, Args: cobra.ExactArgs(count),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			body, err := readJSONInput(input)
			if err != nil {
				return err
			}
			raw, err := call(apiClient, cmd.Context(), args, body, key)
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, raw)
			}
			return writeTaskContextFields(stdout, []contextField{{"Administrative mutation receipt (not cached authority)", raw}})
		},
	}
	cmd.Flags().StringVar(&input, "input", "", "Required caller-authored public decision JSON file (at most 1MiB)")
	cmd.Flags().StringVar(&key, "idempotency-key", "", "Required caller-owned UUID; retain unchanged input and selectors for deliberate manual replay")
	return cmd
}

// #606 owns the single admin command root; these eight explicit writes only
// compose under it. No prior read, local grant or cached permission is trusted.
func addAdminMutations(admin, actor, grants *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	service := &cobra.Command{Use: "service-actor", Short: "Explicit controlled service-actor provisioning"}
	service.AddCommand(adminWriteCommand("provision", "Provision one fixed service identity and subject through current AUTH", 0, client, output, stdout,
		func(c *api.Client, ctx context.Context, _ []string, body json.RawMessage, key string) (json.RawMessage, error) {
			result, err := c.ProvisionServiceActor(ctx, body, key)
			return result.Raw, err
		}))
	admin.AddCommand(service)

	for _, action := range []string{"suspend", "reactivate", "deactivate"} {
		actor.AddCommand(adminWriteCommand(action+" ACTOR_ID", "Explicitly "+action+" one actor profile, not its identity link", 1, client, output, stdout,
			func(c *api.Client, ctx context.Context, args []string, body json.RawMessage, key string) (json.RawMessage, error) {
				result, err := c.MutateAdminActor(ctx, args[0], action, body, key)
				return result.Raw, err
			}))
	}

	link := &cobra.Command{Use: "identity-link", Short: "Explicit identity-link lifecycle writes, separate from actor profiles"}
	for _, action := range []string{"revoke", "reactivate"} {
		link.AddCommand(adminWriteCommand(action+" LINK_ID", "Explicitly "+action+" one identity link, not its actor profile", 1, client, output, stdout,
			func(c *api.Client, ctx context.Context, args []string, body json.RawMessage, key string) (json.RawMessage, error) {
				result, err := c.MutateAdminIdentityLink(ctx, args[0], action, body, key)
				return result.Raw, err
			}))
	}
	admin.AddCommand(link)

	grants.AddCommand(adminWriteCommand("issue", "Issue one administrative role grant (not a project contributor grant)", 0, client, output, stdout,
		func(c *api.Client, ctx context.Context, _ []string, body json.RawMessage, key string) (json.RawMessage, error) {
			result, err := c.IssueAdminGrant(ctx, body, key)
			return result.Raw, err
		}))
	grants.AddCommand(adminWriteCommand("revoke GRANT_ID", "Revoke one exact administrative role grant", 1, client, output, stdout,
		func(c *api.Client, ctx context.Context, args []string, body json.RawMessage, key string) (json.RawMessage, error) {
			result, err := c.RevokeAdminGrant(ctx, args[0], body, key)
			return result.Raw, err
		}))
}
