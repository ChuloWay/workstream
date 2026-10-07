package command

import (
	"fmt"
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addProjectCreate(project *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	var name, slug, description, key string
	create := &cobra.Command{
		Use: "create", Short: "Create a draft project shell (not an approved guide)", Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			if !cmd.Flags().Changed("name") || !cmd.Flags().Changed("slug") {
				return commandError{"invalid_arguments", "--name and --slug are required"}
			}
			input := api.ProjectCreate{Name: name, Slug: slug}
			if cmd.Flags().Changed("description") {
				input.Description = &description
			}
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.CreateProject(cmd.Context(), input, key)
			if err != nil {
				return err
			}
			return writeProject(stdout, *output, result)
		},
	}
	create.Flags().StringVar(&name, "name", "", "Project name (at most 200 characters)")
	create.Flags().StringVar(&slug, "slug", "", "Project slug (at most 120 characters; preserved unchanged)")
	create.Flags().StringVar(&description, "description", "", "Optional project description")
	create.Flags().StringVar(&key, "idempotency-key", "", "Required caller-owned UUID; retain with unchanged fields for manual replay")
	project.AddCommand(create)
}

func writeProject(w io.Writer, output string, result api.Result[api.Project]) error {
	if output == "json" {
		return writeJSON(w, result.Raw)
	}
	p := result.Value
	if _, err := fmt.Fprintf(w, "Project: %s\nName: %s\nStatus: %s\n",
		safeText(p.ID), safeText(p.Name), safeText(p.Status)); err != nil {
		return err
	}
	if p.Metadata != nil {
		_, err := fmt.Fprintf(w, "Slug: %s\nDescription: %s\nCreated: %s\nUpdated: %s\n",
			safeText(p.Metadata.Slug), optional(p.Metadata.Description),
			safeText(p.Metadata.CreatedAt), safeText(p.Metadata.UpdatedAt))
		return err
	}
	return nil
}
