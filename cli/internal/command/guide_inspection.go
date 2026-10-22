package command

import (
	"encoding/json"
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

// addGuideInspection keeps administrative observations under the existing
// project/guide namespace. No read is a preflight or later-write authority.
func addGuideInspection(project, guide *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	project.AddCommand(&cobra.Command{
		Use: "active-guide PROJECT_ID", Short: "Inspect the backend's current active-guide policy chain (not later-write authority)", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.ActiveGuide(cmd.Context(), args[0])
			return writeGuideInspection(stdout, *output, "Current active-guide context (not later-write authority)", result, err)
		},
	})
	sufficiency := &cobra.Command{Use: "sufficiency", Short: "Inspect reports, record human diagnostics, or acknowledge eligible warnings (not approval or activation)"}
	sufficiency.AddCommand(&cobra.Command{
		Use: "list PROJECT_ID GUIDE_ID", Short: "Inspect the newest 100 canonical reports; exact show reaches older retained IDs", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.GuideSufficiencyReports(cmd.Context(), args[0], args[1])
			return writeGuideInspection(stdout, *output, "Retained sufficiency reports (newest 100, not readiness)", result, err)
		},
	}, &cobra.Command{
		Use: "show PROJECT_ID GUIDE_ID REPORT_ID", Short: "Inspect one exact retained sufficiency report", Args: cobra.ExactArgs(3),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.GuideSufficiencyReport(cmd.Context(), args[0], args[1], args[2])
			return writeGuideInspection(stdout, *output, "Retained sufficiency report (not readiness)", result, err)
		},
	})
	addGuideSufficiencyMutations(sufficiency, client, output, stdout)
	guide.AddCommand(sufficiency)
	artifact := &cobra.Command{Use: "artifact-policy", Short: "Inspect policy or deliberately create/update a manual draft (not approval or activation)"}
	artifact.AddCommand(&cobra.Command{
		Use: "list PROJECT_ID GUIDE_ID", Short: "Inspect the newest 100 canonical policies; exact show reaches older retained IDs", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.GuideArtifactPolicies(cmd.Context(), args[0], args[1])
			return writeGuideInspection(stdout, *output, "Retained artifact policies (newest 100, not approval)", result, err)
		},
	}, &cobra.Command{
		Use: "show PROJECT_ID GUIDE_ID POLICY_ID", Short: "Inspect one exact retained submission artifact policy", Args: cobra.ExactArgs(3),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.GuideArtifactPolicy(cmd.Context(), args[0], args[1], args[2])
			return writeGuideInspection(stdout, *output, "Retained artifact policy (not current authority)", result, err)
		},
	}, &cobra.Command{
		Use: "effective PROJECT_ID GUIDE_ID", Short: "Inspect the current approved effective submission artifact policy", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.GuideEffectiveArtifactPolicy(cmd.Context(), args[0], args[1])
			return writeGuideInspection(stdout, *output, "Current effective artifact policy (not later-write authority)", result, err)
		},
	})
	addGuideArtifactPolicyMutations(artifact, client, output, stdout)
	guide.AddCommand(artifact)
	guide.AddCommand(&cobra.Command{
		Use: "pre-submit-policy PROJECT_ID GUIDE_ID", Short: "Inspect the current compiled pre-submit checker summary", Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.GuidePreSubmitPolicy(cmd.Context(), args[0], args[1])
			return writeGuideInspection(stdout, *output, "Current pre-submit checker summary (not later-write authority)", result, err)
		},
	})
}

func writeGuideInspection(stdout io.Writer, output, label string, result api.Result[json.RawMessage], err error) error {
	if err != nil {
		return err
	}
	if output == "json" {
		return writeJSON(stdout, result.Raw)
	}
	return writeTaskContextFields(stdout, []contextField{{label, result.Raw}})
}
