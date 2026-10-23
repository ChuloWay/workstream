package tui

import (
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/Flow-Research/workstream/cli/internal/api"
)

func TestResizePreservesSelectionAndBoundsCells(t *testing.T) {
	f := &fakeClient{}
	m := boot(t, f)
	press(t, m, "enter")
	press(t, m, "enter")
	m.task.Description = strings.Repeat("長い é words ", 1000)
	m.projectName = strings.Repeat("hostile project name ", 1000)
	for _, plain := range []bool{true, false} {
		m.plain, m.noColor = plain, true
		for _, size := range [][2]int{{120, 40}, {80, 24}, {60, 18}, {40, 10}, {30, 8}, {100000, 100000}} {
			m.Update(tea.WindowSizeMsg{Width: size[0], Height: size[1]})
			view := m.View()
			if m.task == nil || m.task.TaskID != taskID {
				t.Fatal("resize lost identity")
			}
			if size[0] >= 40 {
				for _, line := range strings.Split(view.Content, "\n") {
					if lipgloss.Width(line) > m.width {
						t.Fatalf("line exceeds %d: %q", m.width, line)
					}
				}
				if lipgloss.Height(view.Content) > m.height {
					t.Fatalf("view exceeds %d rows: %d", m.height, lipgloss.Height(view.Content))
				}
			}
			if view.AltScreen != !plain || strings.Contains(view.Content, "\x1b") {
				t.Fatal("plain/no-color view has incorrect screen mode or color")
			}
		}
	}
}

func TestPotentialTermsAndStoredOutcomeAreDistinct(t *testing.T) {
	f := &fakeClient{}
	m := boot(t, f)
	press(t, m, "enter")
	press(t, m, "enter")
	m.task.Compensation = api.CompensationTerms{ContributionPolicyVersionID: policyID, AcceptedSubmission: []byte(`[{"instrument":"money","unit":"USD","quantity":"0.100000000000000001"}]`), CompletedReview: []byte(`"unpaid"`)}
	text := m.detailText()
	for _, want := range []string{"0.100000000000000001", "Completed review terms: unpaid", "not acceptance or fulfillment"} {
		if !strings.Contains(text, want) {
			t.Fatal(text)
		}
	}
	press(t, m, "esc")
	press(t, m, "tab")
	press(t, m, "tab")
	press(t, m, "enter")
	if !strings.Contains(m.detailText(), "Stored outcome: review_pending") {
		t.Fatal(m.detailText())
	}
}

func TestNoColorRetainsSelectionAndStatusLabels(t *testing.T) {
	m := boot(t, &fakeClient{})
	m.plain = false
	m.noColor = true
	press(t, m, "enter")
	v := m.View()
	if strings.Contains(v.Content, "\x1b") || !strings.Contains(v.Content, "> Task title [ready]") {
		t.Fatal(v.Content)
	}
}
