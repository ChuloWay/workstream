package tui

import (
	"context"
	"fmt"
	"image/color"
	"reflect"
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/Flow-Research/workstream/cli/internal/api"
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
	for _, size := range [][2]int{{80, 24}, {40, 10}, {40, 24}, {59, 24}, {60, 24}, {99, 24}, {100, 24}, {109, 24}, {110, 24}, {120, 40}, {80, 24}} {
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
	press(t, m, "enter")
	m.plain, m.noColor = false, false
	m.Update(tea.BackgroundColorMsg{Color: color.RGBA{R: 8, G: 14, B: 20, A: 255}})
	dark := m.styles()
	darkView := m.View()
	if !strings.Contains(darkView.Content, "[Ready]") || !strings.Contains(darkView.Content, "38;2;105;215;227") || darkView.BackgroundColor != nil {
		t.Fatal("dark background did not render exact focus color without a canvas", darkView.Content)
	}
	m.Update(tea.BackgroundColorMsg{Color: color.RGBA{R: 250, G: 250, B: 246, A: 255}})
	light := m.styles()
	lightView := m.View()
	if !strings.Contains(lightView.Content, "[Ready]") || !strings.Contains(lightView.Content, "38;2;8;126;140") || lightView.BackgroundColor != nil {
		t.Fatal("light background did not render exact focus color without a canvas", lightView.Content)
	}
	if !m.backgroundKnown || m.darkBackground || reflect.DeepEqual(dark.heading.GetForeground(), light.heading.GetForeground()) || light.selected.GetBackground() == nil {
		t.Fatal("light terminal did not switch semantic colors and selection surface")
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

func TestBelowMinimumTextModesAdvertiseEffectiveQuit(t *testing.T) {
	m := boot(t, &fakeClient{})
	press(t, m, "enter")
	press(t, m, "/")
	m.Update(tea.WindowSizeMsg{Width: 30, Height: 8})
	if got := m.View().Content; !strings.Contains(got, "Ctrl+C quit") || strings.Contains(got, "q quit") {
		t.Fatal("filter below minimum advertised an ineffective quit key", got)
	}
	press(t, m, "q")
	if m.closed || m.filter != "q" {
		t.Fatal("q should remain local filter input")
	}
	press(t, m, "ctrl+c")
	if !m.closed {
		t.Fatal("Ctrl+C did not quit during below-minimum filter editing")
	}

	document := api.TaskGuideDocument{DocumentID: actorID, Label: "Original", MediaType: "text/plain"}
	f := &fakeClient{context: func(context.Context, string) (api.Result[api.WorkContext], error) {
		return api.Result[api.WorkContext]{Value: guideContext(document)}, nil
	}}
	guide := openMineGuide(t, f)
	press(t, guide, "d")
	guide.Update(tea.WindowSizeMsg{Width: 30, Height: 8})
	if got := guide.View().Content; !strings.Contains(got, "Ctrl+C quit") || strings.Contains(got, "q quit") {
		t.Fatal("destination below minimum advertised an ineffective quit key", got)
	}
	press(t, guide, "q")
	if guide.closed || guide.guideDirectory != "q" {
		t.Fatal("q should remain download-directory input")
	}
	press(t, guide, "ctrl+c")
	if !guide.closed {
		t.Fatal("Ctrl+C did not quit during below-minimum destination editing")
	}
}

func TestCompactGuideFooterExposesWorkingDocumentAndScrollKeys(t *testing.T) {
	documents := []api.TaskGuideDocument{
		{DocumentID: actorID, Label: "First original", MediaType: "text/plain"},
		{DocumentID: policyID, Label: "Second original", MediaType: "text/plain"},
	}
	f := &fakeClient{context: func(context.Context, string) (api.Result[api.WorkContext], error) {
		return api.Result[api.WorkContext]{Value: guideContext(documents...)}, nil
	}}
	m := openMineGuide(t, f)
	m.Update(tea.WindowSizeMsg{Width: 40, Height: 10})
	footer := m.footerText()
	for _, key := range []string{"Up/Down doc", "PgUp/PgDn scroll", "d download", "Tab"} {
		if !strings.Contains(footer, key) {
			t.Fatalf("compact Guide footer lacks %q: %q", key, footer)
		}
	}
	assertShellBounded(t, m, 40, 10)
	press(t, m, "down")
	if m.guideSelected != 1 {
		t.Fatal("Down did not select next guide original")
	}
	m.Update(tea.KeyPressMsg{Code: tea.KeyPgDown})
	if m.viewport.YOffset() == 0 {
		t.Fatal("PgDown did not scroll the Guide viewport")
	}
	press(t, m, "d")
	if m.guideMode != guideDestination {
		t.Fatal("d did not enter download destination")
	}
	press(t, m, "esc")
	press(t, m, "tab")
	if m.section != 0 {
		t.Fatal("Tab did not change Guide section")
	}
}

func TestCompactFindingsFooterExposesWorkingScrollAndConditionalNext(t *testing.T) {
	m := boot(t, &fakeClient{})
	press(t, m, "enter")
	press(t, m, "tab")
	press(t, m, "tab")
	press(t, m, "enter")
	press(t, m, "tab")
	m.Update(tea.WindowSizeMsg{Width: 40, Height: 10})
	footer := m.footerText()
	for _, key := range []string{"PgUp/PgDn scroll", "Tab"} {
		if !strings.Contains(footer, key) {
			t.Fatalf("compact Findings footer lacks %q: %q", key, footer)
		}
	}
	if strings.Contains(footer, "n next") {
		t.Fatal("Findings footer offered unavailable continuation")
	}
	assertShellBounded(t, m, 40, 10)
	m.Update(tea.KeyPressMsg{Code: tea.KeyPgDown})
	if m.viewport.YOffset() == 0 {
		t.Fatal("PgDown did not scroll Findings")
	}
	m.findingsCursor = "opaque-next"
	if !strings.Contains(m.footerText(), "n next") {
		t.Fatal("available Findings continuation is not advertised")
	}
	m.reflow()
	assertShellBounded(t, m, 40, 10)
	_, cmd := m.Update(keyMessage("n"))
	if cmd == nil || m.findingsPage != 2 {
		t.Fatal("n did not request exactly one next Findings page")
	}
	apply(t, m, cmd)
	press(t, m, "tab")
	if m.section != 0 {
		t.Fatal("Tab did not change Findings section")
	}
}

func assertShellBounded(t *testing.T, m *Model, width, height int) {
	t.Helper()
	content := m.View().Content
	if lipgloss.Height(content) > height {
		t.Fatalf("view exceeds %d rows: %q", height, content)
	}
	for _, line := range strings.Split(content, "\n") {
		if lipgloss.Width(line) > width {
			t.Fatalf("view exceeds %d columns: %q", width, line)
		}
	}
}

func TestEmptyAndFilteredListsKeepOnlyApplicableControls(t *testing.T) {
	for _, screen := range []string{"empty", "filter-miss"} {
		m, _ := renderFixture(t, screen)
		m.plain, m.noColor = false, true
		for _, size := range [][2]int{{40, 10}, {40, 24}, {80, 24}, {120, 40}} {
			for _, more := range []bool{false, true} {
				m.cursor = nil
				if more {
					cursor := "opaque-next"
					m.cursor = &cursor
				}
				m.Update(tea.WindowSizeMsg{Width: size[0], Height: size[1]})
				view := m.View().Content
				if strings.Contains(view, "Enter") || strings.Contains(m.footerText(), "n next") != more {
					t.Fatal("empty list advertises unavailable inspection or wrong continuation", view)
				}
				for _, key := range []string{"/ filter", "? help", "q quit"} {
					if !strings.Contains(view, key) {
						t.Fatal("empty list lost recovery key", key, view)
					}
				}
				assertShellBounded(t, m, size[0], size[1])
			}
		}
	}
}
