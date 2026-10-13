package command

import (
	"fmt"
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/Flow-Research/workstream/cli/internal/taskimport"
	"github.com/spf13/cobra"
)

func addTaskBatchSources(batch *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	var input, key string
	declare := &cobra.Command{
		Use: "source-declare PROJECT_ID", Short: "Declare exact JSON byte custody; does not upload or import", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			body, err := readTaskBatchJSON(input)
			if err != nil {
				return err
			}
			result, err := apiClient.DeclareTaskImportSource(cmd.Context(), args[0], body, key)
			if err != nil {
				return err
			}
			return writeTaskBatchSource(stdout, *output, result)
		},
	}
	declare.Flags().StringVar(&input, "input", "", "Required canonical UTF-8 JSON file, at most 8MiB; exact bytes determine the commitment")
	declare.Flags().StringVar(&key, "idempotency-key", "", "Required caller UUID; retain unchanged file and key for manual declaration replay")
	batch.AddCommand(declare)
	var uploadInput string
	upload := &cobra.Command{
		Use: "source-upload PROJECT_ID SOURCE_ID", Short: "Upload exact JSON once to a declared source; does not import", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			body, err := readTaskBatchJSON(uploadInput)
			if err != nil {
				return err
			}
			result, err := apiClient.UploadTaskImportSource(cmd.Context(), args[0], args[1], body)
			if err != nil {
				return err
			}
			return writeTaskBatchSource(stdout, *output, result)
		},
	}
	upload.Flags().StringVar(&uploadInput, "input", "", "Required unchanged canonical JSON file matching the source SHA/count, at most 8MiB")
	batch.AddCommand(upload)
	batch.AddCommand(&cobra.Command{
		Use: "source-status PROJECT_ID SOURCE_ID", Short: "Inspect retained JSON custody under current authority", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.TaskImportSourceStatus(cmd.Context(), args[0], args[1])
			if err != nil {
				return err
			}
			return writeTaskBatchSource(stdout, *output, result)
		},
	})
}

func readTaskBatchJSON(path string) ([]byte, error) {
	file, err := openTaskBatchInput(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	body, err := io.ReadAll(io.LimitReader(file, taskimport.MaxBytes+1))
	if err != nil || len(body) < 1 || len(body) > taskimport.MaxBytes {
		return nil, commandError{"invalid_arguments", "--input must contain 1..8388608 readable JSON bytes"}
	}
	return body, nil
}

func writeTaskBatchSource(stdout io.Writer, output string, result api.Result[api.TaskImportSource]) error {
	if output == "json" {
		return writeJSON(stdout, result.Raw)
	}
	value := result.Value
	_, err := fmt.Fprintf(stdout, "Source: %s\nProject: %s\nSHA-256: %s\nJSON bytes: %d\nStorage status: %s\n", safeText(value.SourceID), safeText(value.ProjectID), value.SHA256, value.ByteCount, safeText(value.Status))
	return err
}
