package tui

import "strings"

func (m *Model) handoffText() string {
	args := []string{"workstream"}
	if m.picker {
		args = append(args, "me", "projects")
	} else if m.detail {
		if selected, ok := m.selectedRow(); ok {
			if m.tab == submissions {
				args = append(args, "submission", "show", selected.id)
			} else {
				verb := "show"
				if m.section == 1 {
					verb = "context"
				}
				if m.section == 2 {
					verb = "requirements"
				}
				if m.section == 3 {
					verb = "guide"
				}
				args = append(args, "task", verb, selected.task)
			}
		}
	} else {
		switch m.tab {
		case ready:
			args = append(args, "task", "ready", m.project)
		case mine:
			args = append(args, "me", "assignments", "--project", m.project, "--state", "active")
		case submissions:
			args = append(args, "me", "submissions", "--project", m.project)
		}
	}
	if !m.detail {
		args = append(args, "--limit", "50")
		if m.pageCursor != "" {
			args = append(args, "--cursor", m.pageCursor)
		}
	}
	var out strings.Builder
	out.WriteString("MANUAL CLI HANDOFF\nArguments shown separately; not executed or copied.\n")
	if m.projectName != "" {
		out.WriteString("Observed project name: " + m.clean(m.projectName) + "\n")
	}
	if m.filter != "" {
		out.WriteString("Local filter (fetched page only): " + m.clean(m.filter) + "\n")
	}
	for _, arg := range args {
		out.WriteString("  argument: " + m.clean(arg) + "\n")
	}
	if m.project != "" {
		out.WriteString("\nEvidence: CLI handoff only - not available in this workbench.\n")
		for _, arg := range []string{"workstream", "contributions", "--project", m.project} {
			out.WriteString("  argument: " + m.clean(arg) + "\n")
		}
	}
	if m.detail && m.tab == submissions && m.section == 0 {
		if selected, ok := m.selectedRow(); ok {
			out.WriteString("\nDetailed findings: external manual read only.\n")
			for _, arg := range []string{"workstream", "submission", "findings", selected.id} {
				out.WriteString("  argument: " + m.clean(arg) + "\n")
			}
		}
	}
	return out.String()
}
