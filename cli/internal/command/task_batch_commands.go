package command

import (
	"fmt"
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addTaskBatchCommands(batch *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	var importKey string
	importCommand := &cobra.Command{
		Use: "import PROJECT_ID SOURCE_ID", Short: "Import every retained JSON row into DRAFT; does not screen or release", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.ImportTaskBatch(cmd.Context(), args[0], args[1], importKey)
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			if err := writeTaskBatchCreation(stdout, result.Value); err != nil {
				return err
			}
			for index, task := range result.Value.Tasks {
				if _, err := fmt.Fprintf(stdout, "Row %d: %s | %s | original %s\n", index, task.ID, safeText(task.ExternalTaskID), task.Status); err != nil {
					return err
				}
			}
			return nil
		},
	}
	importCommand.Flags().StringVar(&importKey, "idempotency-key", "", "Required caller UUID; retain unchanged source and key for manual replay")
	batch.AddCommand(importCommand)
	batch.AddCommand(&cobra.Command{
		Use: "status PROJECT_ID BATCH_ID", Short: "Read complete native membership, original creation and separate current states", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.TaskBatchStatus(cmd.Context(), args[0], args[1])
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			if err := writeTaskBatchCreation(stdout, result.Value.Creation); err != nil {
				return err
			}
			for _, task := range result.Value.CurrentTasks {
				if _, err := fmt.Fprintf(stdout, "Row %d: %s | current %s\n", task.RowIndex, task.TaskID, safeText(task.Status)); err != nil {
					return err
				}
			}
			return nil
		},
	})
	for _, operation := range []string{"screen", "release"} {
		var key, reason string
		command := &cobra.Command{
			Use: operation + " PROJECT_ID BATCH_ID", Short: "Explicitly " + operation + " every native member atomically", Args: cobra.ExactArgs(2),
			RunE: func(cmd *cobra.Command, args []string) error {
				apiClient, err := client()
				if err != nil {
					return err
				}
				var decision *string
				if cmd.Flags().Changed("reason") {
					decision = &reason
				}
				result, err := apiClient.TransitionTaskBatch(cmd.Context(), args[0], args[1], operation, key, decision)
				if err != nil {
					return err
				}
				if *output == "json" {
					return writeJSON(stdout, result.Raw)
				}
				value := result.Value
				if _, err := fmt.Fprintf(stdout, "Batch: %s\nProject: %s\nOperation: %s\nTasks: %d\n", value.BatchID, value.ProjectID, value.Operation, value.RowCount); err != nil {
					return err
				}
				for _, task := range value.Tasks {
					if _, err := fmt.Fprintf(stdout, "Row %d: %s | %s | guide %s\n", task.RowIndex, task.TaskID, task.Status, safeText(task.LockedGuideVersion)); err != nil {
						return err
					}
				}
				return nil
			},
		}
		command.Flags().StringVar(&key, "idempotency-key", "", "Required caller UUID; manual unchanged-key replay requires every member still matches its original post-state")
		command.Flags().StringVar(&reason, "reason", "", "At most 1000 UTF-8 characters; release requires a nonblank decision reason")
		batch.AddCommand(command)
	}
}

func writeTaskBatchCreation(stdout io.Writer, value api.TaskImportBatch) error {
	_, err := fmt.Fprintf(stdout, "Batch: %s\nProject: %s\nSource: %s\nSHA-256: %s\nJSON bytes: %d\nTasks: %d\nOriginal state: draft\n", value.BatchID, value.ProjectID, value.SourceID, value.SHA256, value.ByteCount, value.RowCount)
	return err
}
