package command

import (
	"fmt"
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addContributorTaskWrites(task *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	for _, action := range []string{"claim", "start"} {
		var key, reason string
		cmd := &cobra.Command{
			Use: action + " TASK_ID --idempotency-key UUID", Short: action + " a task under current Submitter authority", Args: cobra.ExactArgs(1),
			RunE: func(cmd *cobra.Command, args []string) error {
				var note *string
				if cmd.Flags().Changed("reason") {
					note = &reason
				}
				apiClient, err := client()
				if err != nil {
					return err
				}
				if action == "start" {
					result, err := apiClient.StartTask(cmd.Context(), args[0], key, note)
					if err != nil {
						return err
					}
					if *output == "json" {
						return writeJSON(stdout, result.Raw)
					}
					return writeMutationTask(stdout, result.Value)
				}
				result, err := apiClient.ClaimTask(cmd.Context(), args[0], key, note)
				if err != nil {
					return err
				}
				if *output == "json" {
					return writeJSON(stdout, result.Raw)
				}
				if err := writeMutationTask(stdout, result.Value.Task); err != nil {
					return err
				}
				a := result.Value.Assignment
				_, err = fmt.Fprintf(stdout, "Assignment: %s\nAssignment task: %s\nAssignment project: %s\nSubmitter policy: %s\nContributor: %s\nAssigned by: %s\nAssigned at: %s\nAccepted at: %s\nReleased at: %s\nAssignment status: %s\n",
					safeText(a.ID), safeText(a.TaskID), safeText(a.ProjectID), safeText(a.SubmitterContributionPolicyVersionID), safeText(a.ContributorID), safeText(a.AssignedBy), safeText(a.AssignedAt), safeText(a.AcceptedAt), optional(a.ReleasedAt), safeText(a.Status))
				return err
			},
		}
		cmd.Flags().StringVar(&key, "idempotency-key", "", "Caller-supplied UUID; retain it for an exact manual retry")
		cmd.Flags().StringVar(&reason, "reason", "", "Optional transition reason (at most 1000 characters)")
		task.AddCommand(cmd)
	}
}

func writeMutationTask(w io.Writer, t api.MutationTask) error {
	if err := writeTaskSummary(w, api.TaskSummary{
		TaskID: t.ID, ProjectID: t.ProjectID, Title: t.Title, TaskType: t.TaskType,
		Difficulty: t.Difficulty, SkillTags: t.SkillTags, EstimatedTimeMinutes: t.EstimatedTimeMinutes,
		Status: t.Status, DeadlineAt: t.DeadlineAt, CreatedAt: t.CreatedAt, UpdatedAt: t.UpdatedAt,
	}); err != nil {
		return err
	}
	_, err := fmt.Fprintf(w, "Description: %s\nAcceptance criteria: %s\nRejection criteria: %s\nSource type: %s\nContribution policy: %s\nGuide version: %s\nReview policy: %s\nReview generation: %d\nReview hash: %s\nRevision policy: %s\nRevision generation: %d\nRevision hash: %s\nPayment policy: %s\nBase amount: %s\nCurrency: %s\nPayout type: %s\n",
		safeText(t.Description), optional(t.AcceptanceCriteria), optional(t.RejectionCriteria), safeText(t.SourceType), safeText(t.LockedContributionPolicyVersionID), safeText(t.LockedGuideVersion), safeText(t.LockedReviewPolicyID), t.LockedReviewPolicyGeneration, safeText(t.LockedReviewPolicyHash), safeText(t.LockedRevisionPolicyID), t.LockedRevisionPolicyGeneration, safeText(t.LockedRevisionPolicyHash), optional(t.LockedPaymentPolicyVersion), optional(t.BaseAmount), optional(t.Currency), optional(t.PayoutType))
	return err
}
