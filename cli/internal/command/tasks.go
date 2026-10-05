package command

import (
	"fmt"
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addTaskReads(project *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	var limit int
	var cursor string
	tasks := &cobra.Command{
		Use: "tasks PROJECT_ID", Short: "List one page of tasks under project-manager authority", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			var continuation *string
			if cmd.Flags().Changed("cursor") {
				continuation = &cursor
			}
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.Tasks(cmd.Context(), args[0], limit, continuation)
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			if _, err := fmt.Fprintf(stdout, "Project: %s\nTasks: %d\n", safeText(result.Value.ProjectID), len(result.Value.Items)); err != nil {
				return err
			}
			for _, task := range result.Value.Items {
				if err := writeTaskSummary(stdout, task); err != nil {
					return err
				}
			}
			_, err = fmt.Fprintf(stdout, "Next cursor: %s\n", optional(result.Value.NextCursor))
			return err
		},
	}
	tasks.Flags().IntVar(&limit, "limit", 50, "Page size (1–100; keep unchanged when continuing)")
	tasks.Flags().StringVar(&cursor, "cursor", "", "Opaque next cursor from the previous page")
	project.AddCommand(tasks)
	project.AddCommand(&cobra.Command{
		Use: "task PROJECT_ID TASK_ID", Short: "Inspect a task under project-manager authority", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.Task(cmd.Context(), args[0], args[1])
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			t := result.Value
			if err := writeTaskSummary(stdout, t.TaskSummary); err != nil {
				return err
			}
			_, err = fmt.Fprintf(stdout,
				"Description: %s\nAcceptance criteria: %s\nRejection criteria: %s\nSource type: %s\nSource reference: %s\nSource hash: %s\nImport batch: %s\nExternal task: %s\nCreated by: %s\nAssigned to: %s\n",
				safeText(t.Description), optional(t.AcceptanceCriteria), optional(t.RejectionCriteria), safeText(t.SourceType),
				optional(t.SourceRef), optional(t.SourcePayloadHash), optional(t.ImportBatchID), optional(t.ExternalTaskID), safeText(t.CreatedBy), optional(t.AssignedTo))
			return err
		},
	})
}

func writeTaskSummary(w io.Writer, t api.TaskSummary) error {
	minutes := "—"
	if t.EstimatedTimeMinutes != nil {
		minutes = fmt.Sprint(*t.EstimatedTimeMinutes)
	}
	_, err := fmt.Fprintf(w,
		"Task: %s\nProject: %s\nTitle: %s\nStatus: %s\nType: %s\nDifficulty: %s\nSkills: %s\nEstimated minutes: %s\nDeadline: %s\nCreated: %s\nUpdated: %s\n",
		safeText(t.TaskID), safeText(t.ProjectID), safeText(t.Title), safeText(t.Status), optional(t.TaskType), optional(t.Difficulty),
		list(t.SkillTags), minutes, optional(t.DeadlineAt), safeText(t.CreatedAt), safeText(t.UpdatedAt))
	return err
}
