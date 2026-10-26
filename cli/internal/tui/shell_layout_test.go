package tui

import (
	"fmt"
	"image/color"
	"reflect"
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
)

func TestWideShellKeepsSelectionOutsideScrollingDetails(t *testing.T) {
	f := &fakeClient{}
	m := boot(t, f)
	m.plain = false
	m.Update(tea.WindowSizeMsg{Width: 120, Height: 40})
	if got := m.View().Content; !strings.Contains(got, "Your projects") || !strings.Contains(got, "Project ID: "+projectID) || strings.Contains(got, "Exact instructions") {
		t.Fatal("picker preview used more than loaded row facts", got)
	}
	press(t, m, "enter")
	if got := m.View().Content; !strings.Contains(got, "[Ready]  Mine  Submissions") || !strings.Contains(got, "Enter to inspect full details") || strings.Contains(got, "Exact instructions") {
		t.Fatal("ready preview hid navigation or leaked unloaded detail", got)
	}
	press(t, m, "tab")
	press(t, m, "enter")
	m.task.Description = strings.Repeat("Detailed instructions for the selected assignment. ", 150)
	m.reflow()
	before := len(f.calls)
	m.viewport.ScrollDown(30)
	content := m.View().Content
	if !strings.Contains(content, "[Mine]") || !strings.Contains(content, "[Overview]  Context  Intake  Guide") || !strings.Contains(content, "> Assigned task [active]") {
		t.Fatal("scroll detached selected work or visible navigation", content)
	}
	if m.viewport.YOffset() == 0 || len(f.calls) != before {
		t.Fatal("detail did not scroll independently of requests")
	}
	for _, line := range strings.Split(content, "\n") {
		if lipgloss.Width(line) > 120 {
			t.Fatalf("wide line exceeds 120 cells: %q", line)
		}
	}
}

func TestWideLongListKeepsSelectionVisibleAndReversible(t *testing.T) {
	f := &fakeClient{}
	m := boot(t, f)
	m.plain = false
	press(t, m, "enter")
	m.rows = make([]row, 75)
	for i := range m.rows {
		m.rows[i] = row{id: taskID, task: taskID, project: projectID, title: fmt.Sprintf("Entry %03d", i), status: "ready"}
	}
	m.Update(tea.WindowSizeMsg{Width: 120, Height: 40})
	before := len(f.calls)
	for range 70 {
		press(t, m, "down")
	}
	if m.selected != 70 || !strings.Contains(m.View().Content, "> Entry 070 [ready]") || len(f.calls) != before {
		t.Fatal("long list lost selection or dispatched a read")
	}
	press(t, m, "up")
	if m.selected != 69 || !strings.Contains(m.View().Content, "> Entry 069 [ready]") {
		t.Fatal("selection did not reverse immediately")
	}
	press(t, m, "enter")
	if len(f.calls) != before+1 || !strings.Contains(m.View().Content, "> Entry 069 [ready]") {
		t.Fatal("fresh detail read detached selected row")
	}
	m.task.Description = strings.Repeat("long detail paragraph ", 150)
	m.reflow()
	m.viewport.ScrollDown(20)
	if !strings.Contains(m.View().Content, "> Entry 069 [ready]") || m.viewport.YOffset() == 0 {
		t.Fatal("scrolling detail moved or hid the worklist selection")
	}
}

func TestCompactShellReflowPreservesStateAndUsesOneColumn(t *testing.T) {
	f := &fakeClient{}
	m := boot(t, f)
	m.plain = false
	press(t, m, "enter")
	press(t, m, "tab")
	press(t, m, "enter")
	selected, page, generation := m.selected, m.page, m.generation
	before := len(f.calls)
	for _, size := range [][2]int{{80, 24}, {40, 10}, {120, 40}, {80, 24}} {
		m.Update(tea.WindowSizeMsg{Width: size[0], Height: size[1]})
		content := m.View().Content
		if lipgloss.Height(content) > size[1] {
			t.Fatalf("%dx%d view exceeded rows: %s", size[0], size[1], content)
		}
		for _, line := range strings.Split(content, "\n") {
			if lipgloss.Width(line) > size[0] {
				t.Fatalf("%dx%d view exceeded columns: %q", size[0], size[1], line)
			}
		}
		if size[0] < 100 && strings.Contains(content, "> Assigned task [active]") {
			t.Fatal("compact detail unexpectedly retained side-by-side worklist", content)
		}
	}
	if m.selected != selected || m.page != page || m.generation != generation || len(f.calls) != before || m.task == nil {
		t.Fatal("resize changed selection, request generation, or detail")
	}
}

func TestNoColorAndUnknownBackgroundUsePlainDefaults(t *testing.T) {
	m := boot(t, &fakeClient{})
	m.plain = false
	m.noColor = true
	if strings.Contains(m.View().Content, "\x1b") {
		t.Fatal("no-color shell emitted ANSI")
	}
	m.noColor = false
	m.backgroundKnown = false
	if strings.Contains(m.View().Content, "\x1b") {
		t.Fatal("unknown terminal background emitted assumed dark colors")
	}
}

func TestDetectedLightBackgroundUsesReadablePaletteWithoutCanvas(t *testing.T) {
	m := boot(t, &fakeClient{})
	m.plain, m.noColor = false, false
	m.Update(tea.BackgroundColorMsg{Color: color.RGBA{R: 8, G: 14, B: 20, A: 255}})
	dark := m.styles()
	m.Update(tea.BackgroundColorMsg{Color: color.RGBA{R: 250, G: 250, B: 246, A: 255}})
	light := m.styles()
	if !m.backgroundKnown || m.darkBackground || reflect.DeepEqual(dark.heading.GetForeground(), light.heading.GetForeground()) || light.selected.GetBackground() == nil {
		t.Fatal("light terminal did not switch semantic colors and selection surface")
	}
	if m.View().BackgroundColor != nil {
		t.Fatal("presentation forced a canvas over the terminal's own background")
	}
}

func TestFilterEditingFooterMatchesEffectiveKeys(t *testing.T) {
	f := &fakeClient{}
	m := boot(t, f)
	press(t, m, "enter")
	m.Update(tea.WindowSizeMsg{Width: 40, Height: 10})
	before := len(f.calls)
	press(t, m, "/")
	press(t, m, "q")
	if m.closed || m.filter != "q" || !strings.Contains(m.View().Content, "Enter apply  Esc cancel  Ctrl+C quit") || strings.Contains(m.View().Content, "q quit") {
		t.Fatal("filter mode advertised or handled q as quit", m.View().Content)
	}
	press(t, m, "enter")
	if m.filtering || m.filter != "q" || len(f.calls) != before {
		t.Fatal("Enter did not apply locally without a request")
	}
	press(t, m, "/")
	press(t, m, "x")
	press(t, m, "esc")
	if m.filtering || m.filter != "q" || len(f.calls) != before {
		t.Fatal("Esc did not restore the previous local filter")
	}
}
