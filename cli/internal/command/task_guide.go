package command

import (
	"encoding/json"
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/Flow-Research/workstream/cli/internal/download"
	"github.com/spf13/cobra"
)

func addTaskGuide(task *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	var directory string
	cmd := &cobra.Command{
		Use: "guide TASK_ID", Short: "List or download the assigned task's locked guide originals", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.WorkContext(cmd.Context(), args[0])
			if err != nil {
				return err
			}
			if !result.Value.Lifecycle.AssignedToCurrentActor {
				return &api.Failure{Code: "task_assignment_required"}
			}
			if directory != "" {
				root, err := download.OpenRoot(directory)
				if err != nil {
					return err
				}
				defer root.Close()
				for _, document := range result.Value.GuideDocuments {
					if err := downloadGuide(cmd, apiClient, root, result.Value.Task.TaskID, document); err != nil {
						return err
					}
				}
			}
			if *output == "json" {
				body, err := json.Marshal(result.Value.GuideDocuments)
				if err != nil {
					return err
				}
				return writeJSON(stdout, body)
			}
			return writeTaskContextFields(stdout, []contextField{{"Guide documents", result.Value.GuideDocuments}})
		},
	}
	cmd.Flags().StringVar(&directory, "download", "", "Download verified originals into an existing directory (never overwrite)")
	task.AddCommand(cmd)
}

func downloadGuide(cmd *cobra.Command, client *api.Client, root *download.Root, taskID string, document api.TaskGuideDocument) error {
	name := document.Filename()
	stage, err := root.Stage(name)
	if err != nil {
		return err
	}
	defer stage.Abort()
	if err := client.DownloadGuideDocument(cmd.Context(), taskID, document, stage); err != nil {
		return err
	}
	if err := stage.Seal(); err != nil {
		return err
	}
	return stage.Publish()
}
