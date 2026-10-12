package command

import (
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addManagerTaskWrites(task *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	var input, createKey string
	create := &cobra.Command{
		Use: "create PROJECT_ID", Short: "Create one draft task under current project-manager authority", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			body, err := readJSONInput(input)
			if err != nil {
				return err
			}
			result, err := apiClient.CreateTask(cmd.Context(), args[0], body, createKey)
			if err != nil {
				return err
			}
			return writeManagerTask(stdout, *output, result)
		},
	}
	create.Flags().StringVar(&input, "input", "", "Required public TaskCreate JSON file (at most 1MiB)")
	create.Flags().StringVar(&createKey, "idempotency-key", "", "Required caller-owned UUID for unchanged manual replay")
	task.AddCommand(create)
	for _, action := range []string{"screen", "release"} {
		var key, reason string
		cmd := &cobra.Command{
			Use: action + " PROJECT_ID TASK_ID", Short: action + " one task under current project-manager authority", Args: cobra.ExactArgs(2),
			RunE: func(cmd *cobra.Command, args []string) error {
				apiClient, err := client()
				if err != nil {
					return err
				}
				var note *string
				if cmd.Flags().Changed("reason") {
					note = &reason
				}
				result, err := apiClient.PrepareTask(cmd.Context(), args[0], args[1], action, key, note)
				if err != nil {
					return err
				}
				return writeManagerTask(stdout, *output, result)
			},
		}
		cmd.Flags().StringVar(&key, "idempotency-key", "", "Required caller-owned UUID for unchanged manual replay")
		cmd.Flags().StringVar(&reason, "reason", "", "Explicit transition reason (required by the backend for release)")
		task.AddCommand(cmd)
	}
}

func writeManagerTask(stdout io.Writer, output string, result api.Result[api.ManagerTask]) error {
	if output == "json" {
		return writeJSON(stdout, result.Raw)
	}
	return writeTaskContextFields(stdout, []contextField{{"Manager task receipt", result.Raw}})
}
