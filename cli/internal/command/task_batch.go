package command

import (
	"encoding/json"
	"fmt"
	"io"
	"os"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/Flow-Research/workstream/cli/internal/taskimport"
	"github.com/spf13/cobra"
)

func addTaskBatch(project *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	batch := &cobra.Command{Use: "task-batch", Short: "Explicit task import, screening and release operations"}
	addTaskBatchCSV(batch, output, stdout)
	addTaskBatchSources(batch, client, output, stdout)
	addTaskBatchCommands(batch, client, output, stdout)
	project.AddCommand(batch)
}

func addTaskBatchCSV(batch *cobra.Command, output *string, stdout io.Writer) {
	var input, destination, label string
	convert := &cobra.Command{
		Use: "convert-csv", Short: "Convert local CSV briefs to uploadable JSON without contacting the server", Args: cobra.NoArgs,
		RunE: func(_ *cobra.Command, _ []string) error {
			if *output != "text" && *output != "json" {
				return commandError{"invalid_output", "--output must be text or json"}
			}
			if destination == "" {
				return commandError{"invalid_arguments", "--out must name a new JSON file"}
			}
			file, err := openTaskBatchInput(input)
			if err != nil {
				return err
			}
			defer file.Close()
			converted, err := taskimport.ConvertCSV(file, label)
			if err != nil {
				return commandError{"invalid_task_import_csv", err.Error()}
			}
			if err := writeNewTaskBatchJSON(destination, converted.Bytes); err != nil {
				return err
			}
			if *output == "json" {
				raw, err := json.Marshal(struct {
					JSONPath  string `json:"json_path"`
					SHA256    string `json:"sha256"`
					ByteCount int    `json:"byte_count"`
					RowCount  int    `json:"row_count"`
				}{destination, converted.SHA256, converted.ByteCount, converted.RowCount})
				if err != nil {
					return err
				}
				return writeJSON(stdout, raw)
			}
			_, err = fmt.Fprintf(stdout, "JSON file: %s\nSHA-256: %s\nJSON bytes: %d\nTasks: %d\n", safeText(destination), converted.SHA256, converted.ByteCount, converted.RowCount)
			return err
		},
	}
	convert.Flags().StringVar(&input, "input", "", "Required regular UTF-8 CSV file, at most 8MiB")
	convert.Flags().StringVar(&destination, "out", "", "Required new JSON file; existing files are never overwritten")
	convert.Flags().StringVar(&label, "label", "", "Optional batch display label, at most 255 characters")
	batch.AddCommand(convert)
}

func openTaskBatchInput(path string) (*os.File, error) {
	bad := commandError{"invalid_arguments", "--input must be a readable regular file of 1..8388608 bytes"}
	info, err := os.Stat(path)
	if err != nil || !info.Mode().IsRegular() || info.Size() < 1 || info.Size() > taskimport.MaxBytes {
		return nil, bad
	}
	file, err := os.Open(path)
	if err != nil {
		return nil, bad
	}
	info, err = file.Stat()
	if err != nil || !info.Mode().IsRegular() || info.Size() < 1 || info.Size() > taskimport.MaxBytes {
		file.Close()
		return nil, bad
	}
	return file, nil
}

func writeNewTaskBatchJSON(path string, body []byte) error {
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if err != nil {
		return commandError{"invalid_arguments", "--out must name a writable new file; existing files are never overwritten"}
	}
	written, writeErr := file.Write(body)
	closeErr := file.Close()
	if writeErr != nil || closeErr != nil || written != len(body) {
		// This command created the file and has not published a commitment.
		// Remove only its incomplete local conversion output.
		os.Remove(path)
		return commandError{"task_import_output_failed", "could not write complete JSON output"}
	}
	return nil
}
