package tui

import (
	"fmt"
	"math/big"
	"strings"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/Flow-Research/workstream/cli/internal/api"
)

func (m *Model) heading() string {
	if m.picker {
		return "PROJECTS"
	}
	if !m.detail {
		return m.tab.String()
	}
	if m.tab == submissions {
		if m.section == 1 {
			return "FINDINGS"
		}
		return "SUBMISSION"
	}
	return [...]string{"TASK", "CONTEXT", "INTAKE", "GUIDE"}[m.section]
}

// fitText bounds a display label, never an exact identity or request selector.
// Callers pass text that has already crossed clean.
func fitText(value string, width int) string {
	if lipgloss.Width(value) <= width {
		return value
	}
	first, _, _ := strings.Cut(lipgloss.Wrap(value, max(1, width-3), ""), "\n")
	return first + "..."
}

func (m *Model) headerText() string {
	header := "WORKSTREAM / CONTRIBUTE / " + m.heading()
	if m.project != "" {
		header += "\nProject: " + fitText(m.clean(m.projectName), m.width-9) + "\nID: " + m.clean(m.project)
	}
	return header
}

func (m *Model) footerText() string {
	if m.guideMode == guideDestination {
		return "enter confirm | esc cancel | ctrl+c quit"
	}
	if m.guideMode == guideConfirm {
		return "y download | esc cancel | q quit"
	}
	if m.height < 16 {
		return "? keys | q quit"
	}
	if m.detail && m.tab == mine && m.section == 3 {
		return "arrows select | d download | tab section | esc back\nr refresh | c CLI | ? help | q quit"
	}
	if m.detail && m.tab == submissions && m.section == 1 {
		return "arrows scroll | n next | tab overview | esc back\nr refresh | c CLI | ? help | q quit"
	}
	return "arrows select/scroll | enter inspect | tab section | esc back\ng project | n next | r refresh | / local filter | c CLI | ? help | q quit"
}

func (m *Model) statusText() string {
	if m.detail && m.tab == submissions && m.section == 1 {
		count := 0
		if m.findings != nil {
			count = len(m.findings.Items)
		}
		status := fmt.Sprintf("page %d | fetched %d runs", m.findingsPage, count)
		if m.findingsCursor != "" {
			status += " | more available"
		}
		if !m.observed.IsZero() {
			status += " observed " + m.observed.Format("15:04:05")
		}
		return fitText(status, m.width)
	}
	status := fmt.Sprintf("page %d | fetched %d", m.page, len(m.rows))
	if m.width < 70 {
		status = fmt.Sprintf("page %d rows %d", m.page, len(m.rows))
	}
	if m.cursor != nil {
		if m.width < 70 {
			status += " more"
		} else {
			status += " | more available"
		}
	}
	if !m.observed.IsZero() {
		status += " observed " + m.observed.Format("15:04:05")
	}
	if m.filtering {
		return fitText("Filter fetched page only: "+m.clean(m.filter), m.width) + "\n" + fitText(status, m.width)
	} else if m.filter != "" {
		return fitText("local filter: "+m.clean(m.filter), m.width) + "\n" + fitText(status, m.width)
	}
	return fitText(status, m.width)
}

func (m *Model) View() tea.View {
	if m.closed {
		return tea.NewView("")
	}
	if m.tooSmall() {
		v := tea.NewView(lipgloss.Wrap("Resize to at least 40x10. q quit", max(1, m.width), ""))
		v.AltScreen = !m.plain
		return v
	}
	header := m.headerText()
	if !m.noColor {
		header = lipgloss.NewStyle().Foreground(lipgloss.Color("#69D7E3")).Render(header)
	}
	footer, status := m.footerText(), m.statusText()
	content := lipgloss.Wrap(header, m.width, "") + "\n" + m.viewport.View() + "\n" +
		lipgloss.Wrap(status, m.width, "") + "\n" + lipgloss.Wrap(footer, m.width, "")
	v := tea.NewView(content)
	v.AltScreen = !m.plain
	return v
}

func (m *Model) reflow() {
	if m.width < 1 || m.height < 1 {
		return
	}
	// Reserve wrapped status/help lines; never measure unescaped server text.
	reserved := lipgloss.Height(lipgloss.Wrap(m.headerText(), m.width, "")) +
		lipgloss.Height(lipgloss.Wrap(m.footerText(), m.width, "")) + 1 + lipgloss.Height(m.statusText())
	m.viewport.SetWidth(m.width)
	m.viewport.SetHeight(max(1, m.height-reserved))
	body := m.body()
	m.viewport.SetContent(lipgloss.Wrap(body, m.width, ""))
}

func (m *Model) body() string {
	if m.help {
		return "KEYBOARD HELP\nArrows select a row/document or scroll detail. Enter inspects one exact resource.\nTab: Ready/Mine/Submissions in lists; Overview/Context/Intake/Guide in active Mine detail; Overview/Findings in Submission detail.\nEsc returns or cancels destination/confirmation without a download. g fetches a fresh project picker.\nn fetches exactly one next findings/list page. r resets the current read; no polling.\n/ filters the fetched list page only; enter finishes, esc cancels.\nd enters a destination for one selected guide original; y confirms.\nc shows inert CLI arguments. q or Ctrl+C quits.\nChecker evidence is not acceptance. A read is not a reservation or authority.\n? or Esc closes help."
	}
	if m.handoff {
		return m.handoffText()
	}
	if m.failure != "" {
		return m.failure + "\nNo retained page or detail is available.\n" + m.failureHelp()
	}
	if m.loading {
		return "Loading..."
	}
	if !m.started {
		return "Waiting for terminal size..."
	}
	if m.detail {
		if m.width >= 100 && !m.plain {
			leftWidth := m.width / 3
			return lipgloss.JoinHorizontal(lipgloss.Top,
				lipgloss.NewStyle().Width(leftWidth).Render(m.listText(leftWidth)), " | ",
				lipgloss.NewStyle().Width(m.width-leftWidth-3).Render(lipgloss.Wrap(m.detailText(), m.width-leftWidth-3, "")))
		}
		return m.detailText()
	}
	list := m.listText(m.width)
	if m.width >= 100 && !m.plain && !m.picker {
		leftWidth := m.width/2 - 2
		return lipgloss.JoinHorizontal(lipgloss.Top,
			lipgloss.NewStyle().Width(leftWidth).Render(m.listText(leftWidth)),
			" | ", lipgloss.NewStyle().Width(m.width-leftWidth-3).Render("SELECTED TASK\nOpen to inspect.\nA summary is not full instructions or a reservation."))
	}
	return list
}

func (m *Model) failureHelp() string {
	if m.blocked {
		return "Session unavailable. Quit and supply a valid bearer through the existing environment.\n? help | q quit"
	}
	return "r explicit refresh | g fresh project picker | ? help | q quit"
}

func (m *Model) listText(width int) string {
	rows := m.visible()
	if len(rows) == 0 {
		return "No rows on this fetched page.\nThis is not a project-wide count."
	}
	var out strings.Builder
	// Keep the selected row in the list viewport without retaining other pages.
	first := max(0, m.selected-max(1, m.viewport.Height()-3))
	for i := first; i < len(rows); i++ {
		mark := "  "
		if i == m.selected {
			mark = "> "
		}
		status := m.clean(rows[i].status)
		available := max(1, width-lipgloss.Width(status)-5)
		title := m.clean(rows[i].title)
		title = fitText(title, available)
		fmt.Fprintf(&out, "%s%s [%s]\n", mark, title, status)
	}
	return out.String()
}

func number(v *big.Int) string {
	if v == nil {
		return "not supplied"
	}
	return v.String()
}

func (m *Model) detailText() string {
	var out strings.Builder
	line := func(label, value string) { out.WriteString(label + ": " + m.clean(value) + "\n") }
	optional := func(label string, value *string) {
		if value != nil {
			line(label, *value)
		}
	}
	if m.tab == submissions && m.section == 1 && m.findings != nil {
		return m.findingsText()
	}
	if m.submission != nil {
		v := m.submission
		line("Submission", v.ID)
		line("Task", v.Task)
		line("Stored outcome", v.Status)
		optional("Reason", v.StatusReason)
		line("Version", number(v.Version))
		line("Summary", v.Summary)
		line("Submitted", v.SubmittedAt)
		optional("Decided", v.DecidedAt)
		line("Blocking findings", number(v.FindingCounts.Blocking))
		line("Warning findings", number(v.FindingCounts.Warning))
		line("Coverage incomplete", number(v.FindingCounts.CoverageIncomplete))
		optional("Predecessor", v.Predecessor)
		for _, e := range v.Evidence {
			line("Evidence label", e.Label)
			line("Evidence ID", e.ID)
			line("Type", e.Type)
			line("Size", number(e.Size))
		}
		out.WriteString("Tab opens contributor-visible checker findings.\nStored observations do not predict acceptance or fulfillment.")
		return out.String()
	}
	if m.section == 3 && m.context != nil {
		return m.guideText()
	}
	if m.section == 1 && m.context != nil {
		v := m.context
		line("Task", v.Task.TaskID)
		line("Project", v.Project.ID)
		line("Guide", v.Guide.ID)
		line("Locked guide version", v.Guide.Version)
		line("Review policy", v.ReviewPolicy.PolicyID)
		line("Review policy generation", fmt.Sprint(v.ReviewPolicy.Generation))
		line("Review policy hash", v.ReviewPolicy.PolicyHash)
		line("Revision policy", v.RevisionPolicy.PolicyID)
		line("Revision policy generation", fmt.Sprint(v.RevisionPolicy.Generation))
		line("Revision policy hash", v.RevisionPolicy.PolicyHash)
		line("Contribution policy version", v.ContributionPolicyVersionID)
		line("Assigned to current actor", fmt.Sprint(v.Lifecycle.AssignedToCurrentActor))
		line("Observed action hints (not authority)", strings.Join(v.Lifecycle.NextActions, ", "))
		for _, d := range v.GuideDocuments {
			line("Document label", d.Label)
			line("Document ID", d.DocumentID)
			line("Media type", d.MediaType)
			line("Bytes", fmt.Sprint(d.ByteCount))
			line("SHA-256 (server metadata; bytes not downloaded)", d.SHA256)
		}
		if v.RevisionContext != nil {
			r := v.RevisionContext
			line("Revision preparation", r.PreparationID)
			line("Revision preparation digest", r.PreparationSHA256)
			line("Revision source Submission", r.SourceSubmissionID)
			line("Revision disposition", r.Disposition)
			line("Revision clock", r.ClockState)
			optional("Revision deadline", r.DeadlineAt)
		}
		return out.String()
	}
	if m.section == 2 && m.intake != nil {
		v := m.intake
		line("Task", v.TaskID)
		line("Project", v.ProjectID)
		line("Locked guide version", v.GuideVersion)
		line("Required packet fields", strings.Join(v.RequiredPacketFields, ", "))
		for _, a := range v.RequiredArtifacts {
			line("Artifact", a.Key)
			line("Path (text only)", a.Path)
			line("Required", fmt.Sprint(a.Required))
			line("Hash required", fmt.Sprint(a.HashRequired))
			optional("Description", a.Description)
		}
		for _, e := range v.RequiredEvidence {
			line("Evidence", e.Key)
			line("Label", e.Label)
			line("Required", fmt.Sprint(e.Required))
			line("Hash required", fmt.Sprint(e.HashRequired))
			optional("Description", e.Description)
		}
		for _, a := range v.ForbiddenArtifacts {
			line("Forbidden pattern", a.Pattern)
			optional("Reason", a.Reason)
			optional("Suggested fix", a.WorkerFacingFix)
			optional("Severity", a.Severity)
		}
		for _, term := range v.AttestationTerms {
			line("Attestation term", term)
		}
		line("Manifest required", fmt.Sprint(v.ManifestRequired))
		line("Artifact hash required", fmt.Sprint(v.ArtifactHashRequired))
		line("Hash algorithm", v.ArtifactHashAlgorithm)
		line("Allowed storage schemes", strings.Join(v.AllowedStorageSchemes, ", "))
		line("Allowed URI prefixes (text only)", strings.Join(v.StorageReferenceRules.AllowedURIPrefixes, ", "))
		line("Storage credentials allowed", fmt.Sprint(v.StorageReferenceRules.CredentialsAllowed))
		line("Storage query strings allowed", fmt.Sprint(v.StorageReferenceRules.QueryStringsAllowed))
		line("Storage fragments allowed", fmt.Sprint(v.StorageReferenceRules.FragmentsAllowed))
		line("Storage path traversal allowed", fmt.Sprint(v.StorageReferenceRules.PathTraversalAllowed))
		line("Maximum file bytes", number(v.MaximumFileSizeBytes))
		line("Maximum package bytes", number(v.MaximumPackageSizeBytes))
		line("Maximum archive bytes", number(v.MaximumArchiveSizeBytes))
		line("Maximum archive entries", number(v.MaximumArchiveEntries))
		line("Package required", fmt.Sprint(v.Packaging.PackageRequired))
		line("Allowed package formats", strings.Join(v.Packaging.AllowedPackageFormats, ", "))
		out.WriteString("Intake requirements are not a preparation or Submission.\nNo package is uploaded.")
		return out.String()
	}
	if m.task != nil {
		v := m.task
		line("Task", v.TaskID)
		line("Title", v.Title)
		line("Status", v.Status)
		line("Instructions", v.Description)
		optional("Acceptance criteria", v.AcceptanceCriteria)
		optional("Rejection criteria", v.RejectionCriteria)
		line("Skills", strings.Join(v.SkillTags, ", "))
		line("Contribution policy version", v.Compensation.ContributionPolicyVersionID)
		for _, terms := range []struct {
			label string
			raw   []byte
		}{{"Accepted submission terms", v.Compensation.AcceptedSubmission}, {"Completed review terms", v.Compensation.CompletedReview}} {
			awards, ok := api.CompensationAwards(terms.raw)
			if !ok {
				line(terms.label, "unavailable")
				continue
			}
			if len(awards) == 0 {
				line(terms.label, "unpaid")
			}
			for _, a := range awards {
				line(terms.label, a.Instrument+" / "+a.Unit+" / "+a.Quantity)
			}
		}
		out.WriteString("Terms are potential earned terms, not acceptance or fulfillment.\nNo action can be sent from this workbench.")
	}
	return out.String()
}

func (m *Model) guideText() string {
	var out strings.Builder
	v := m.context
	line := func(label, value string) { out.WriteString(label + ": " + m.clean(value) + "\n") }
	line("Task", v.Task.TaskID)
	line("Guide", v.Guide.ID)
	line("Locked guide version", v.Guide.Version)
	if len(v.GuideDocuments) == 0 {
		out.WriteString("No assigned guide documents.\n")
	}
	for index, d := range v.GuideDocuments {
		mark := "  "
		if index == m.guideSelected {
			mark = "> "
		}
		out.WriteString(mark + "Document " + fmt.Sprint(index+1) + "\n")
		line("Label", d.Label)
		line("Document ID", d.DocumentID)
		line("Order", fmt.Sprint(d.Order))
		line("Media type", d.MediaType)
		line("Bytes (server metadata; bytes not downloaded)", fmt.Sprint(d.ByteCount))
		line("SHA-256 (server metadata; bytes not downloaded)", d.SHA256)
	}
	if m.guideMode == guideDestination {
		line("Download directory", m.guideDirectory)
		out.WriteString("Enter confirms this existing directory; no directory is created.\n")
	} else if m.guideMode == guideConfirm && len(v.GuideDocuments) > 0 {
		d := v.GuideDocuments[m.guideSelected]
		out.WriteString("Confirm download\n")
		line("Task", v.Task.TaskID)
		line("Document", d.DocumentID)
		line("Download directory", m.guideDirectory)
		line("Filename", d.Filename())
		out.WriteString("y downloads verified bytes | esc cancels\n")
	} else if m.guideNotice != "" {
		out.WriteString(m.guideNotice + "\n")
	}
	out.WriteString("Guide metadata is not verified downloaded bytes.")
	return out.String()
}

func (m *Model) findingsText() string {
	var out strings.Builder
	line := func(label, value string) { out.WriteString(label + ": " + m.clean(value) + "\n") }
	optional := func(label string, value *string) {
		if value == nil {
			line(label, "not supplied")
		} else {
			line(label, *value)
		}
	}
	if len(m.findings.Items) == 0 {
		out.WriteString("No checker runs on this fetched page.\n")
	}
	for _, run := range m.findings.Items {
		line("Run", run.ID)
		line("Submission", run.Submission)
		line("Task", run.Task)
		line("Submission version", number(run.Version))
		line("Run status", run.Status)
		line("Attempt", number(run.Attempt))
		line("Current", fmt.Sprint(run.Current))
		optional("Predecessor run", run.Predecessor)
		line("Created", run.CreatedAt)
		optional("Completed", run.CompletedAt)
		for _, finding := range run.Results {
			line("Finding", finding.ID)
			line("Checker", finding.Checker)
			optional("Check ID", finding.CheckID)
			line("Finding status", finding.Status)
			line("Severity", finding.Severity)
			optional("Path", finding.Path)
			if finding.Line == nil {
				line("Line", "not supplied")
			} else {
				line("Line", fmt.Sprint(*finding.Line))
			}
			optional("Message", finding.Message)
			optional("Suggested fix", finding.Fix)
		}
		out.WriteString("\n")
	}
	out.WriteString("Checker findings are evidence, not acceptance.")
	return out.String()
}
