package command

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func writeArtifactObservation(w io.Writer, output, label string, raw json.RawMessage) error {
	if output == "json" {
		return writeSafeJSON(w, raw)
	}
	var pretty bytes.Buffer
	if err := json.Indent(&pretty, raw, "", "  "); err != nil {
		return &api.Failure{Code: "invalid_api_response"}
	}
	_, err := fmt.Fprintf(w, "%s (current observation, not later authority):\n%s\n", safeText(label), safeText(pretty.String()))
	return err
}

func addArtifactOperator(operations *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	artifact := &cobra.Command{Use: "artifact", Short: "Inspect public artifact custody and explicitly retry one verification job"}

	var bindingsPage pageFlags
	bindings := &cobra.Command{
		Use: "bindings RESOURCE_TYPE RESOURCE_ID", Short: "List exact-resource artifact bindings", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			page := bindingsPage.query(cmd)
			result, err := apiClient.ArtifactBindings(cmd.Context(), args[0], args[1], page.Limit, page.Cursor)
			if err != nil {
				return err
			}
			return writeArtifactObservation(stdout, *output, "Artifact bindings", result.Raw)
		},
	}
	bindingsPage.bind(bindings, 50)
	artifact.AddCommand(bindings)

	var replicasPage pageFlags
	replicas := &cobra.Command{
		Use: "replicas CONTENT_ID", Short: "List replicas for one content record without provider coordinates", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			page := replicasPage.query(cmd)
			result, err := apiClient.ArtifactReplicas(cmd.Context(), args[0], page.Limit, page.Cursor)
			if err != nil {
				return err
			}
			return writeArtifactObservation(stdout, *output, "Artifact replicas", result.Raw)
		},
	}
	replicasPage.bind(replicas, 50)
	artifact.AddCommand(replicas)

	var receiptsPage pageFlags
	receipts := &cobra.Command{
		Use: "receipts REPLICA_ID", Short: "List bounded put, observation and verification receipts", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			page := receiptsPage.query(cmd)
			result, err := apiClient.ArtifactReceipts(cmd.Context(), args[0], page.Limit, page.Cursor)
			if err != nil {
				return err
			}
			return writeArtifactObservation(stdout, *output, "Artifact receipts", result.Raw)
		},
	}
	receiptsPage.bind(receipts, 50)
	artifact.AddCommand(receipts)

	artifact.AddCommand(&cobra.Command{
		Use: "verification-job JOB_ID", Short: "Inspect one verification job and its source CAS version", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.ArtifactVerificationJob(cmd.Context(), args[0])
			if err != nil {
				return err
			}
			return writeArtifactObservation(stdout, *output, "Artifact verification job", result.Raw)
		},
	})

	artifact.AddCommand(&cobra.Command{
		Use: "recovery-attempt ATTEMPT_ID", Short: "Inspect one recovery chain without inferring its outcome", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.ArtifactRecoveryAttempt(cmd.Context(), args[0])
			if err != nil {
				return err
			}
			return writeArtifactObservation(stdout, *output, "Artifact recovery attempt", result.Raw)
		},
	})

	var auditPage pageFlags
	audit := &cobra.Command{
		Use: "audit-events RESOURCE_TYPE RESOURCE_ID", Short: "List audit facts for one exact artifact resource", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			page := auditPage.query(cmd)
			result, err := apiClient.ArtifactAuditEvents(cmd.Context(), args[0], args[1], page.Limit, page.Cursor)
			if err != nil {
				return err
			}
			return writeArtifactObservation(stdout, *output, "Artifact audit events", result.Raw)
		},
	}
	auditPage.bind(audit, 50)
	artifact.AddCommand(audit)

	var usagePage pageFlags
	var usageTask string
	usage := &cobra.Command{
		Use: "admission-usage PROJECT_ID", Short: "Inspect bounded admission usage for one project and optional task", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			var taskID *string
			if cmd.Flags().Changed("task-id") {
				taskID = &usageTask
			}
			apiClient, err := client()
			if err != nil {
				return err
			}
			page := usagePage.query(cmd)
			result, err := apiClient.ArtifactAdmissionUsage(cmd.Context(), args[0], taskID, page.Limit, page.Cursor)
			if err != nil {
				return err
			}
			return writeArtifactObservation(stdout, *output, "Artifact admission usage", result.Raw)
		},
	}
	usagePage.bind(usage, 50)
	usage.Flags().StringVar(&usageTask, "task-id", "", "Optional exact task in the selected project")
	artifact.AddCommand(usage)

	artifact.AddCommand(&cobra.Command{
		Use: "readiness", Short: "Inspect provider-neutral artifact readiness status only", Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.ArtifactReadiness(cmd.Context())
			if err != nil {
				return err
			}
			return writeArtifactObservation(stdout, *output, "Artifact readiness", result.Raw)
		},
	})

	var retryProject, retryTask, retrySubmission, retryReason, retryKey, retryCAS string
	retry := &cobra.Command{
		Use: "retry JOB_ID", Short: "Explicitly request one reasoned verification retry under current Operator authority", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			for _, name := range []string{"project-id", "task-id", "reason", "idempotency-key", "expected-source-job-cas-version"} {
				if !cmd.Flags().Changed(name) {
					return commandError{"invalid_arguments", "--" + name + " is required for artifact retry"}
				}
			}
			var submissionID *string
			if cmd.Flags().Changed("submission-id") {
				submissionID = &retrySubmission
			}
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.RetryArtifactVerification(cmd.Context(), args[0], api.ArtifactRetryInput{
				ProjectID: retryProject, TaskID: retryTask, SubmissionID: submissionID,
				Reason: retryReason, ClientIdempotencyKey: retryKey, ExpectedSourceJobCASVersion: retryCAS,
			})
			if err != nil {
				return err
			}
			return writeArtifactObservation(stdout, *output, "Artifact retry accepted; inspect recovery and job before inferring outcome", result.Raw)
		},
	}
	retry.Flags().StringVar(&retryProject, "project-id", "", "Required exact project bound to the source job")
	retry.Flags().StringVar(&retryTask, "task-id", "", "Required exact task bound to the source job")
	retry.Flags().StringVar(&retrySubmission, "submission-id", "", "Optional exact submission bound to the source job")
	retry.Flags().StringVar(&retryReason, "reason", "", "Required nonblank explanation (at most 1000 characters)")
	retry.Flags().StringVar(&retryKey, "idempotency-key", "", "Required caller-owned UUID; preserve it for manual unchanged-payload replay")
	retry.Flags().StringVar(&retryCAS, "expected-source-job-cas-version", "", "Required observed nonnegative source-job CAS version")
	artifact.AddCommand(retry)

	operations.AddCommand(artifact)
}
