package command

import (
	"bufio"
	"crypto/rand"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"unicode"
	"unicode/utf16"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addContributionEvidence(root, project *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	for _, scoped := range []bool{false, true} {
		var filters api.ContributionFilters
		var destination string
		cmd := &cobra.Command{Use: "contributions", Short: "Read complete earned contribution evidence (not payment status)", Args: cobra.NoArgs}
		if scoped {
			cmd.Use = "contributions PROJECT_ID"
			cmd.Args = cobra.ExactArgs(1)
		} else {
			cmd.Flags().StringVar(&filters.Project, "project", "", "Filter your own contributions by project UUID")
		}
		cmd.Flags().StringVar(&filters.Type, "type", "", "Filter accepted_submission or completed_review evidence")
		cmd.Flags().StringVar(&filters.From, "recorded-from", "", "Inclusive RFC3339 recorded time")
		cmd.Flags().StringVar(&filters.Before, "recorded-before", "", "Exclusive RFC3339 recorded time")
		cmd.Flags().StringVar(&destination, "csv", "", "Save exact server CSV to a new private file; never overwrite")
		cmd.RunE = func(cmd *cobra.Command, args []string) error {
			for _, flag := range []string{"project", "type", "recorded-from", "recorded-before", "csv"} {
				if f := cmd.Flags().Lookup(flag); f != nil && f.Changed && f.Value.String() == "" {
					return commandError{"invalid_arguments", "explicit filters and CSV path must not be empty"}
				}
			}
			if scoped {
				filters.Project = args[0]
			}
			apiClient, err := client()
			if err != nil {
				return err
			}
			if destination != "" {
				if err := publishContributionCSV(destination, func(writer io.Writer) error {
					return apiClient.ContributionCSV(cmd.Context(), scoped, filters, writer)
				}); err != nil {
					return err
				}
				if *output == "json" {
					return writeJSON(stdout, json.RawMessage(`{"format":"csv","saved":true}`))
				}
				_, err = io.WriteString(stdout, "Contribution CSV saved (earned evidence, not payment status).\n")
				return err
			}
			staged, err := stageContributionJSON(func(writer io.Writer) error {
				return apiClient.Contributions(cmd.Context(), scoped, filters, writer)
			})
			if err != nil {
				return err
			}
			defer os.Remove(staged.Name())
			defer staged.Close()
			if *output == "json" {
				return writeSafeContributionJSON(stdout, staged)
			}
			if _, err := io.WriteString(stdout, "Contributions (earned evidence, not payment status): "); err != nil {
				return err
			}
			return writeSafeContributionJSON(stdout, staged)
		}
		if scoped {
			project.AddCommand(cmd)
		} else {
			root.AddCommand(cmd)
		}
	}
}

type contributionOutputWriter struct {
	destination io.Writer
	failure     error
}

func (w *contributionOutputWriter) Write(value []byte) (int, error) {
	written, err := w.destination.Write(value)
	if err == nil && written != len(value) {
		err = io.ErrShortWrite
	}
	if err != nil && w.failure == nil {
		w.failure = err
	}
	return written, err
}

func stageContributionJSON(write func(io.Writer) error) (*os.File, error) {
	file, err := os.CreateTemp("", ".workstream-contributions-")
	if err != nil {
		return nil, commandError{"file_io_error", "cannot create private contribution output"}
	}
	cleanup := func() {
		file.Close()
		os.Remove(file.Name())
	}
	tracked := &contributionOutputWriter{destination: file}
	if err := write(tracked); err != nil {
		cleanup()
		if tracked.failure != nil {
			return nil, commandError{"file_io_error", "cannot stage contribution output"}
		}
		return nil, err
	}
	if _, err := file.Seek(0, io.SeekStart); err != nil {
		cleanup()
		return nil, commandError{"file_io_error", "cannot read complete contribution output"}
	}
	return file, nil
}

func writeSafeContributionJSON(destination io.Writer, source io.Reader) error {
	reader := bufio.NewReader(source)
	writer := bufio.NewWriter(destination)
	for {
		r, _, err := reader.ReadRune()
		if err == io.EOF {
			if err := writer.WriteByte('\n'); err != nil {
				return err
			}
			return writer.Flush()
		}
		if err != nil {
			return err
		}
		if r >= 0x7f && (unicode.IsControl(r) || unicode.Is(unicode.Cf, r)) {
			if r <= 0xffff {
				if _, err := fmt.Fprintf(writer, "\\u%04x", r); err != nil {
					return err
				}
			} else {
				hi, lo := utf16.EncodeRune(r)
				if _, err := fmt.Fprintf(writer, "\\u%04x\\u%04x", hi, lo); err != nil {
					return err
				}
			}
		} else if _, err := writer.WriteRune(r); err != nil {
			return err
		}
	}
}

func publishContributionCSV(destination string, write func(io.Writer) error) error {
	root, err := os.OpenRoot(filepath.Dir(destination))
	if err != nil {
		return commandError{"invalid_arguments", "cannot open CSV destination directory"}
	}
	defer root.Close()
	name := filepath.Base(destination)
	if _, err := root.Lstat(name); !os.IsNotExist(err) {
		return commandError{"invalid_arguments", "CSV destination exists or is inaccessible"}
	}
	temporary := ".workstream-contributions-" + rand.Text()
	file, err := root.OpenFile(temporary, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		return commandError{"file_io_error", "cannot create private contribution CSV"}
	}
	defer root.Remove(temporary)
	defer file.Close()
	tracked := &contributionOutputWriter{destination: file}
	if err := write(tracked); err != nil {
		if tracked.failure == nil {
			return err
		}
		return commandError{"file_io_error", "cannot write contribution CSV"}
	}
	if err := file.Sync(); err != nil {
		return commandError{"file_io_error", "cannot persist contribution CSV"}
	}
	if err := file.Close(); err != nil {
		return commandError{"file_io_error", "cannot close contribution CSV"}
	}
	if err := root.Link(temporary, name); err != nil {
		return commandError{"file_io_error", "cannot publish contribution CSV without overwrite"}
	}
	return nil
}
