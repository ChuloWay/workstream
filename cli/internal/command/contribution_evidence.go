package command

import (
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
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
					return errors.New("explicit filters and CSV path must not be empty")
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
				body, err := apiClient.ContributionCSV(cmd.Context(), scoped, filters)
				if err != nil {
					return err
				}
				if err := publishContributionCSV(destination, body); err != nil {
					return err
				}
				if *output == "json" {
					return writeJSON(stdout, json.RawMessage(`{"format":"csv","saved":true}`))
				}
				_, err = io.WriteString(stdout, "Contribution CSV saved (earned evidence, not payment status).\n")
				return err
			}
			result, err := apiClient.Contributions(cmd.Context(), scoped, filters)
			if err != nil {
				return err
			}
			if *output == "json" {
				// Preserve the JSON value, but never emit literal C1/bidi/format
				// controls supplied by arbitrary task titles or display names.
				var safe strings.Builder
				for _, r := range string(result.Raw) {
					if r >= 0x7f && (unicode.IsControl(r) || unicode.Is(unicode.Cf, r)) {
						if r <= 0xffff {
							fmt.Fprintf(&safe, "\\u%04x", r)
						} else {
							hi, lo := utf16.EncodeRune(r)
							fmt.Fprintf(&safe, "\\u%04x\\u%04x", hi, lo)
						}
					} else {
						safe.WriteRune(r)
					}
				}
				return writeJSON(stdout, json.RawMessage(safe.String()))
			}
			return writeTaskContextFields(stdout, []contextField{{"Contributions (earned evidence, not payment status)", result.Raw}})
		}
		if scoped {
			project.AddCommand(cmd)
		} else {
			root.AddCommand(cmd)
		}
	}
}

func publishContributionCSV(destination string, body []byte) error {
	root, err := os.OpenRoot(filepath.Dir(destination))
	if err != nil {
		return errors.New("cannot open CSV destination directory")
	}
	defer root.Close()
	name := filepath.Base(destination)
	if _, err := root.Lstat(name); !os.IsNotExist(err) {
		return errors.New("CSV destination exists or is inaccessible")
	}
	temporary := ".workstream-contributions-" + rand.Text()
	file, err := root.OpenFile(temporary, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		return errors.New("cannot create private contribution CSV")
	}
	defer root.Remove(temporary)
	defer file.Close()
	if _, err := file.Write(body); err != nil {
		return errors.New("cannot write contribution CSV")
	}
	if err := file.Sync(); err != nil {
		return errors.New("cannot persist contribution CSV")
	}
	if err := file.Close(); err != nil {
		return errors.New("cannot close contribution CSV")
	}
	if err := root.Link(temporary, name); err != nil {
		return errors.New("cannot publish contribution CSV without overwrite")
	}
	return nil
}
