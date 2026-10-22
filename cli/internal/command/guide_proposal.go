package command

import (
	"encoding/json"
	"fmt"
	"io"
	"math/big"
	"strings"

	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/spf13/cobra"
)

func addGuideProposal(guide *cobra.Command, client func() (*api.Client, error), output *string, stdout io.Writer) {
	guide.AddCommand(&cobra.Command{
		Use: "proposal PROJECT_ID GUIDE_ID COMPILATION_ID", Short: "Inspect an exact finalized proposal (does not approve or activate)", Args: cobra.ExactArgs(3),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiClient, err := client()
			if err != nil {
				return err
			}
			result, err := apiClient.GuideProposal(cmd.Context(), args[0], args[1], args[2])
			if err != nil {
				return err
			}
			if *output == "json" {
				return writeJSON(stdout, result.Raw)
			}
			return writeGuideProposal(stdout, result.Value)
		},
	})
}

func writeGuideProposal(stdout io.Writer, proposal api.GuideProposal) error {
	var text strings.Builder
	line := func(format string, values ...any) {
		for index, value := range values {
			if stringValue, ok := value.(string); ok {
				values[index] = safeText(stringValue)
			}
		}
		fmt.Fprintf(&text, format, values...)
	}
	status := "not recorded"
	if proposal.CurrentApprovalOperationID != nil {
		status = "recorded"
	}
	policyStatus := nullableText(proposal.ArtifactPolicyStatus, "none")
	line("Guide proposal (inspection only)\n")
	line("Status: %s | Current: %t | Intake policy: %s | Approval: %s\n", proposal.Result.Status, proposal.Current, policyStatus, status)
	line("Approval operation: %s | Approval output digest: %s\n", nullableText(proposal.CurrentApprovalOperationID, "none"), nullableText(proposal.CurrentApprovalOutputDigest, "none"))
	line("Project: %s | Guide: %s (%s) | Compilation: %s\n", proposal.Target.ProjectID, proposal.Target.GuideID, proposal.Target.GuideVersion, proposal.Target.CompilationID)
	line("Target digest: %s | Post-submit policy: %s | Warning hashes: %d\n", proposal.TargetDigest, nullableText(proposal.PostSubmitPolicyID, "none"), len(proposal.WarningHashes))

	line("\nFindings (%d)\n", len(proposal.Result.Findings))
	if len(proposal.Result.Findings) == 0 {
		line("  None\n")
	}
	for _, finding := range proposal.Result.Findings {
		line("  [%s] %s: %s%s\n", finding.Severity, finding.Code, finding.Message, proposalEvidenceText(finding.EvidenceRefs))
	}

	writeProposalPolicy(&text, proposal.Result.SubmissionArtifactPolicy)
	groups := []struct {
		title        string
		dispositions map[string]bool
	}{
		{"PRE requirements", map[string]bool{"supported_pre_submit": true, "pre_submit_capability_gap": true}},
		{"POST requirements", map[string]bool{"supported_post_submit": true, "post_submit_capability_gap": true}},
		{"Non-checker requirements", map[string]bool{
			"platform_covered": true, "human_review": true, "project_lifecycle_policy": true,
			"guide_blocker": true, "informational": true,
		}},
	}
	for _, group := range groups {
		count := 0
		for _, requirement := range proposal.Result.Requirements {
			if group.dispositions[requirement.Disposition] {
				count++
			}
		}
		line("\n%s (%d)\n", group.title, count)
		if count == 0 {
			line("  None\n")
			continue
		}
		for _, requirement := range proposal.Result.Requirements {
			if group.dispositions[requirement.Disposition] {
				writeProposalRequirement(&text, requirement, proposal.Result.PreSubmitBindings, proposal.Result.PostSubmitBindings)
			}
		}
	}

	line("\nCapability suggestions (%d)\n", len(proposal.Result.CapabilitySuggestions))
	for _, suggestion := range proposal.Result.CapabilitySuggestions {
		line("  %s [%s] %s: %s%s\n", suggestion.RequirementID, suggestion.Stage, suggestion.Title, suggestion.Rationale, proposalEvidenceText(suggestion.EvidenceRefs))
	}
	if len(proposal.Result.CapabilitySuggestions) == 0 {
		line("  None\n")
	}
	line("\nSetup notes (%d)\n", len(proposal.Result.SetupNotes))
	for _, note := range proposal.Result.SetupNotes {
		line("  - %s\n", note)
	}
	if len(proposal.Result.SetupNotes) == 0 {
		line("  None\n")
	}
	_, err := io.WriteString(stdout, text.String())
	return err
}

func writeProposalPolicy(text *strings.Builder, policy *api.ProposalIntakePolicy) {
	line := func(format string, values ...any) {
		for index, value := range values {
			if stringValue, ok := value.(string); ok {
				values[index] = safeText(stringValue)
			}
		}
		fmt.Fprintf(text, format, values...)
	}
	line("\nSubmission artifact policy\n")
	if policy == nil {
		line("  None\n")
		return
	}
	line("  Packaging: %s\n", policy.Packaging)
	line("  Maximum file size: %s\n", nullableInteger(policy.MaximumFileSizeBytes))
	line("  Maximum package size: %s\n", nullableInteger(policy.MaximumPackageSizeBytes))
	line("  Maximum archive size: %s\n", nullableInteger(policy.MaximumArchiveSizeBytes))
	line("  Maximum archive entries: %s\n", nullableInteger(policy.MaximumArchiveEntries))
	line("  Allowed storage schemes: %s\n", proposalList(policy.AllowedStorageSchemes))
	line("  Required artifacts: %s\n", proposalList(policy.RequiredArtifacts))
	line("  Forbidden artifacts: %s\n", proposalList(policy.ForbiddenArtifacts))
	line("  Required evidence: %s\n", proposalList(policy.RequiredEvidence))
	line("  Attestation terms: %s\n", proposalList(policy.AttestationTerms))
}

func writeProposalRequirement(text *strings.Builder, requirement api.ProposalRequirement, pre []api.ProposalPreBinding, post []api.ProposalPostBinding) {
	line := func(format string, values ...any) {
		for index, value := range values {
			if stringValue, ok := value.(string); ok {
				values[index] = safeText(stringValue)
			}
		}
		fmt.Fprintf(text, format, values...)
	}
	line("  %s [%s]%s\n", requirement.RequirementID, requirement.Disposition, proposalEvidenceText(requirement.EvidenceRefs))
	line("    Requirement: %s\n", requirement.Statement)
	line("    Classification rationale: %s\n", nullableText(requirement.ClassificationRationale, "not recorded (retained proposal)"))
	if requirement.PlatformCoverage != nil {
		line("    Platform coverage: %s %s (%s)\n", requirement.PlatformCoverage.CapabilityID, requirement.PlatformCoverage.CapabilityVersion, requirement.PlatformCoverage.Stage)
	}
	for _, binding := range pre {
		if binding.RequirementID == requirement.RequirementID {
			writeProposalBinding(text, binding.CapabilityID, binding.CapabilityVersion, binding.Stage, binding.Parameters)
		}
	}
	for _, binding := range post {
		if binding.RequirementID == requirement.RequirementID {
			writeProposalBinding(text, binding.CapabilityID, binding.CapabilityVersion, binding.Stage, binding.Parameters)
		}
	}
	if requirement.CheckSpecification == nil {
		line("    Check specification: not recorded\n")
		return
	}
	spec := requirement.CheckSpecification
	line("    Check: %s | %s | maximum %s seconds\n", spec.EvaluationMethod, spec.ExecutionMode, spec.MaximumDurationSeconds.String())
	line("    Stage rationale: %s\n", spec.StageRationale)
	line("    Inputs\n")
	for _, input := range spec.Inputs {
		path := ""
		if input.RelativePath != nil {
			path = " path=" + *input.RelativePath
		}
		line("      - %s (%s)%s: %s\n", input.InputID, input.Kind, path, input.Purpose)
	}
	writeProposalStrings(text, "Check steps", spec.CheckSteps)
	writeProposalStrings(text, "Pass conditions", spec.PassConditions)
	line("    Failure findings\n")
	for _, finding := range spec.FailureFindings {
		line("      - [%s] %s when %s: %s\n", finding.Level, finding.Code, finding.Condition, finding.Message)
	}
	writeProposalStrings(text, "Positive tests", spec.PositiveTests)
	line("    Negative tests\n")
	for _, test := range spec.NegativeTests {
		line("      - %s (%s): %s; findings: %s\n", test.Name, test.ExpectedVerdict, test.Scenario, proposalList(test.ExpectedFindingCodes))
	}
	line("    Runtime dependencies\n")
	if len(spec.RuntimeDependencies) == 0 {
		line("      None\n")
	}
	for _, dependency := range spec.RuntimeDependencies {
		line("      - %s (%s, %s; unavailable=%s): %s\n", dependency.DependencyID, dependency.Kind, dependency.Provisioning, dependency.UnavailableCode, dependency.Purpose)
	}
	line("    Infrastructure failures\n")
	for _, failure := range spec.InfrastructureFailures {
		line("      - %s: %s\n", failure.Code, failure.Condition)
	}
}

func writeProposalBinding(text *strings.Builder, capabilityID, version, stage string, parameters []api.ProposalParameter) {
	fmt.Fprintf(text, "    Binding: %s %s (%s)", safeText(capabilityID), safeText(version), safeText(stage))
	if len(parameters) == 0 {
		text.WriteString("\n")
		return
	}
	text.WriteString("; parameters: ")
	for index, parameter := range parameters {
		if index > 0 {
			text.WriteString(", ")
		}
		fmt.Fprintf(text, "%s=%s", safeText(parameter.Name), safeText(string(parameter.Value)))
	}
	text.WriteString("\n")
}

func writeProposalStrings(text *strings.Builder, title string, values []string) {
	fmt.Fprintf(text, "    %s\n", title)
	for _, value := range values {
		fmt.Fprintf(text, "      - %s\n", safeText(value))
	}
}

func proposalEvidenceText(evidence []api.ProposalEvidence) string {
	if len(evidence) == 0 {
		return ""
	}
	values := make([]string, 0, len(evidence))
	for _, reference := range evidence {
		location := "document " + reference.DocumentNumber.String()
		if reference.StartPage != nil {
			location += ", page " + reference.StartPage.String()
			if reference.EndPage != nil && reference.EndPage.Cmp(reference.StartPage) != 0 {
				location += "-" + reference.EndPage.String()
			}
		}
		if reference.Section != nil {
			location += ", section " + safeText(*reference.Section)
		}
		values = append(values, location)
	}
	return " [evidence: " + strings.Join(values, "; ") + "]"
}

func nullableText(value *string, fallback string) string {
	if value == nil {
		return fallback
	}
	return *value
}

func nullableInteger(value *big.Int) string {
	if value == nil {
		return "none (platform limit applies)"
	}
	return value.String()
}

func proposalList(values []string) string {
	if len(values) == 0 {
		return "none"
	}
	encoded, _ := json.Marshal(values)
	return string(encoded)
}
