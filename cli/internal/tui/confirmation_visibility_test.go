package tui

import (
	"context"
	"os"
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"github.com/Flow-Research/workstream/cli/internal/api"
)

func TestHiddenConfirmationCannotStageOrDispatch(t *testing.T) {
	doc := api.TaskGuideDocument{DocumentID: actorID, Label: "Exact original", MediaType: "text/markdown", ByteCount: 5, SHA256: "sha256:" + strings.Repeat("a", 64)}
	f := &fakeClient{context: func(context.Context, string) (api.Result[api.WorkContext], error) {
		return api.Result[api.WorkContext]{Value: guideContext(doc)}, nil
	}}
	m := openMineGuide(t, f)
	t.Cleanup(m.Close)
	directory := t.TempDir()
	press(t, m, "d")
	press(t, m, directory)
	press(t, m, "enter")
	before := len(f.calls)
	m.Update(tea.WindowSizeMsg{Width: 30, Height: 8})
	_, cmd := m.Update(keyMessage("y"))
	if cmd != nil || m.download != nil || m.loading || len(f.calls) != before {
		t.Fatal("hidden confirmation staged or dispatched a download")
	}
	entries, err := os.ReadDir(directory)
	if err != nil || len(entries) != 0 {
		t.Fatal("hidden confirmation touched destination", entries, err)
	}
	m.Update(tea.WindowSizeMsg{Width: 80, Height: 24})
	if m.guideMode != guideConfirm || m.guideDirectory != directory || m.context.GuideDocuments[m.guideSelected].DocumentID != doc.DocumentID {
		t.Fatal("resize lost exact confirmation target")
	}
	if !strings.Contains(m.View().Content, "Confirm download") {
		t.Fatal("restored confirmation is not visible")
	}
	press(t, m, "y")
	entries, err = os.ReadDir(directory)
	if err != nil || len(entries) != 1 || entries[0].Name() != doc.Filename() {
		t.Fatal("visible deliberate confirmation did not publish exact original", entries, err)
	}
}
