package command

import (
	"crypto/rand"
	"encoding/json"
	"errors"
	"io"
	"os"

	"github.com/Flow-Research/workstream/cli/internal/api"
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
				info, err := os.Lstat(directory)
				if err != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
					return errors.New("download directory must be an existing real directory")
				}
				root, err := os.OpenRoot(directory)
				if err != nil {
					return errors.New("cannot open download directory")
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

func downloadGuide(cmd *cobra.Command, client *api.Client, root *os.Root, taskID string, document api.TaskGuideDocument) error {
	name := document.Filename()
	if _, err := root.Lstat(name); !os.IsNotExist(err) {
		return errors.New("download target already exists or is inaccessible")
	}
	temporary := ".workstream-guide-" + rand.Text()
	file, err := root.OpenFile(temporary, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		return errors.New("cannot create private guide download")
	}
	defer root.Remove(temporary)
	defer file.Close()
	if err := client.DownloadGuideDocument(cmd.Context(), taskID, document, file); err != nil {
		return err
	}
	if err := file.Sync(); err != nil {
		return errors.New("cannot persist guide download")
	}
	if err := file.Close(); err != nil {
		return errors.New("cannot close guide download")
	}
	// A hard link publishes atomically without replacing an existing file or
	// following a symlink. Root confines both names even if the directory moves.
	if err := root.Link(temporary, name); err != nil {
		return errors.New("cannot publish guide download without overwrite")
	}
	return nil
}
