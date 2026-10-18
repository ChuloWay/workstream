package command

import (
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

// These project-scoped reads are distinct from the contributor task/submission
// commands. Every invocation asks the backend for fresh, exact authority.
func addManagerTaskEvidence(project *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	for _, kind := range []string{"task-requirements", "task-locked-context", "task-context"} {
		kind := kind
		cmd := &cobra.Command{Use: kind + " PROJECT_ID TASK_ID", Short: "Inspect exact manager task context under current project authority", Args: cobra.ExactArgs(2)}
		cmd.RunE = func(cmd *cobra.Command, args []string) error {
			c, err := client()
			if err != nil {
				return err
			}
			switch kind {
			case "task-requirements":
				result, err := c.ManagementRequirements(cmd.Context(), args[0], args[1])
				if err != nil {
					return err
				}
				if *output == "json" {
					return writeSafeJSON(stdout, result.Raw)
				}
				return writeTaskContextFields(stdout, []contextField{{"Manager submission requirements", result.Value}})
			case "task-locked-context":
				result, err := c.ManagementLockedContext(cmd.Context(), args[0], args[1])
				if err != nil {
					return err
				}
				if *output == "json" {
					return writeSafeJSON(stdout, result.Raw)
				}
				return writeTaskContextFields(stdout, []contextField{{"Locked manager context", result.Value}})
			default:
				result, err := c.ManagementWorkContext(cmd.Context(), args[0], args[1])
				if err != nil {
					return err
				}
				if *output == "json" {
					return writeSafeJSON(stdout, result.Raw)
				}
				return writeTaskContextFields(stdout, []contextField{{"Manager work context (not later authority)", result.Value}})
			}
		}
		project.AddCommand(cmd)
	}
	var taskLimit int
	var taskCursor string
	taskSubmissions := &cobra.Command{Use: "task-submissions PROJECT_ID TASK_ID", Short: "Read one page of a task's manager submission history", Args: cobra.ExactArgs(2)}
	taskSubmissions.Flags().IntVar(&taskLimit, "limit", 25, "Page size (1–100)")
	taskSubmissions.Flags().StringVar(&taskCursor, "cursor", "", "Opaque next cursor; no automatic pagination")
	taskSubmissions.RunE = func(cmd *cobra.Command, args []string) error {
		var cursor *string
		if cmd.Flags().Changed("cursor") {
			cursor = &taskCursor
		}
		c, err := client()
		if err != nil {
			return err
		}
		result, err := c.ManagementTaskSubmissions(cmd.Context(), args[0], args[1], taskLimit, cursor)
		if err != nil {
			return err
		}
		if *output == "json" {
			return writeSafeJSON(stdout, result.Raw)
		}
		return writeTaskContextFields(stdout, []contextField{{"Manager submission history", result.Value}})
	}
	project.AddCommand(taskSubmissions)
	project.AddCommand(&cobra.Command{Use: "submission PROJECT_ID SUBMISSION_ID", Short: "Read one exact manager Submission and its locked lineage", Args: cobra.ExactArgs(2), RunE: func(cmd *cobra.Command, args []string) error {
		c, err := client()
		if err != nil {
			return err
		}
		result, err := c.ManagementSubmission(cmd.Context(), args[0], args[1])
		if err != nil {
			return err
		}
		if *output == "json" {
			return writeSafeJSON(stdout, result.Raw)
		}
		return writeTaskContextFields(stdout, []contextField{{"Manager submission", result.Value}})
	}})
	var run, runCursor string
	var runLimit int
	checkerRuns := &cobra.Command{Use: "checker-runs PROJECT_ID SUBMISSION_ID", Short: "Read manager checker evidence, not acceptance", Args: cobra.ExactArgs(2)}
	checkerRuns.Flags().StringVar(&run, "run", "", "Exact checker-run UUID instead of a page")
	checkerRuns.Flags().IntVar(&runLimit, "limit", 25, "Page size (1–100)")
	checkerRuns.Flags().StringVar(&runCursor, "cursor", "", "Opaque next cursor; no automatic pagination")
	checkerRuns.RunE = func(cmd *cobra.Command, args []string) error {
		if cmd.Flags().Changed("run") && (run == "" || cmd.Flags().Changed("limit") || cmd.Flags().Changed("cursor")) {
			return commandError{"invalid_arguments", "--run requires a UUID and cannot be combined with pagination flags"}
		}
		var cursor *string
		if cmd.Flags().Changed("cursor") {
			cursor = &runCursor
		}
		c, err := client()
		if err != nil {
			return err
		}
		result, err := c.ManagementCheckerRuns(cmd.Context(), args[0], args[1], run, runLimit, cursor)
		if err != nil {
			return err
		}
		if *output == "json" {
			return writeSafeJSON(stdout, result.Raw)
		}
		return writeTaskContextFields(stdout, []contextField{{"Manager checker evidence (not acceptance)", result.Raw}})
	}
	project.AddCommand(checkerRuns)
}
