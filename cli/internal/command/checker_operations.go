package command

import (
	"fmt"
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addCheckerOperations(root *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	operations := &cobra.Command{Use: "operations", Short: "Explicit system Operator operations"}
	checker := &cobra.Command{Use: "checker", Short: "External checker registration and terminal recovery"}
	registry := &cobra.Command{Use: "registry", Short: "Immutable external-checker registry; publication does not enable execution"}

	var input, registerKey string
	register := &cobra.Command{
		Use: "register", Short: "Publish one exact digest-pinned checker specification", Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			if input == "" || registerKey == "" {
				return commandError{"invalid_arguments", "--input and --idempotency-key are required"}
			}
			body, err := readJSONInput(input)
			if err != nil {
				return err
			}
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.RegisterExternalChecker(cmd.Context(), body, registerKey)
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeSafeJSON(stdout, result.Raw)
			}
			return writeTaskContextFields(stdout, []contextField{{"Registered external checker (not enabled)", result.Raw}})
		},
	}
	register.Flags().StringVar(&input, "input", "", "Required closed registry specification JSON file (at most 1 MiB)")
	register.Flags().StringVar(&registerKey, "idempotency-key", "", "Required caller-owned UUID; reuse unchanged for manual replay")
	registry.AddCommand(register)
	registry.AddCommand(&cobra.Command{
		Use: "read ENTRY_ID", Short: "Read one exact immutable registry entry with current Operator authority", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.ReadExternalChecker(cmd.Context(), args[0])
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeSafeJSON(stdout, result.Raw)
			}
			return writeTaskContextFields(stdout, []contextField{{"External checker registry entry (not enabled)", result.Raw}})
		},
	})
	checker.AddCommand(registry)

	var limit int
	var cursor string
	sources := &cobra.Command{
		Use: "retry-sources PROJECT_ID", Short: "List one page of known-terminal checker infrastructure failures", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.CheckerRetrySources(cmd.Context(), args[0], limit, cursor)
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeSafeJSON(stdout, result.Raw)
			}
			return writeTaskContextFields(stdout, []contextField{{"Checker retry sources (not authority for a later retry)", result.Raw}})
		},
	}
	sources.Flags().IntVar(&limit, "limit", 50, "Page size, 1..100")
	sources.Flags().StringVar(&cursor, "cursor", "", "Opaque continuation from this exact project page")
	checker.AddCommand(sources)

	var reason, retryKey string
	retry := &cobra.Command{
		Use: "retry PROJECT_ID SOURCE_RUN_ID", Short: "Explicitly retry one finalized infrastructure-failed run", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			if !cmd.Flags().Changed("reason") || retryKey == "" || !api.ValidCheckerRetryReason(reason) {
				return commandError{"invalid_arguments", "--reason (1..500 characters without ASCII controls) and --idempotency-key are required"}
			}
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.RetryChecker(cmd.Context(), args[0], args[1], reason, retryKey)
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeSafeJSON(stdout, result.Raw)
			}
			_, err = fmt.Fprint(stdout, "Checker retry receipt (not acceptance): ")
			if err != nil {
				return err
			}
			return writeSafeJSON(stdout, result.Raw)
		},
	}
	retry.Flags().StringVar(&reason, "reason", "", "Required operator explanation (1..500 characters)")
	retry.Flags().StringVar(&retryKey, "idempotency-key", "", "Required caller-owned UUID; reuse with exact source and reason for manual replay")
	checker.AddCommand(retry)
	operations.AddCommand(checker)
	root.AddCommand(operations)
}
