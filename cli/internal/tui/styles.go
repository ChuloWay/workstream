package tui

import "charm.land/lipgloss/v2"

// styleSet carries semantic emphasis without controlling the terminal canvas.
type styleSet struct {
	heading, secondary, focus, action, caution, error, selected, divider lipgloss.Style
}

func (m *Model) styles() styleSet {
	plain := lipgloss.NewStyle()
	if m.noColor || !m.backgroundKnown {
		return styleSet{plain, plain, plain, plain, plain, plain, plain, plain}
	}
	color := func(value string) lipgloss.Style { return lipgloss.NewStyle().Foreground(lipgloss.Color(value)) }
	if !m.darkBackground {
		return styleSet{
			heading: color("#087E8C").Bold(true), secondary: color("#465B62"),
			focus: color("#087E8C").Background(lipgloss.Color("#E7EFF0")).Bold(true), action: color("#95482E"),
			caution: color("#7D5A17"), error: color("#A63345"),
			selected: color("#244D58").Background(lipgloss.Color("#E7EFF0")), divider: color("#9AACB0"),
		}
	}
	return styleSet{
		heading: color("#69D7E3").Bold(true), secondary: color("#A9BAC3"),
		focus: color("#69D7E3").Background(lipgloss.Color("#192632")).Bold(true), action: color("#F2AE91"),
		caution: color("#E9C37B"), error: color("#ED8991"),
		selected: color("#EAF2F4").Background(lipgloss.Color("#192632")), divider: color("#354955"),
	}
}
