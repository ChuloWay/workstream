package tui

import (
	"strings"
	"testing"
)

func TestHandoffUsesInertArgumentsAndNoExportReads(t *testing.T) {
	f := &fakeClient{}
	m := boot(t, f)
	press(t, m, "enter")
	before := len(f.calls)
	press(t, m, "c")
	text := m.handoffText()
	for _, want := range []string{"not executed or copied", "argument: task\n  argument: ready", "Evidence: CLI handoff only", "argument: contributions\n  argument: --project\n  argument: " + projectID} {
		if !strings.Contains(text, want) {
			t.Fatal(text)
		}
	}
	if len(f.calls) != before {
		t.Fatal("list handoff dispatched a read")
	}
	press(t, m, "esc")
	press(t, m, "tab")
	press(t, m, "tab")
	press(t, m, "enter")
	before = len(f.calls)
	press(t, m, "c")
	text = m.handoffText()
	if !strings.Contains(text, "argument: submission\n  argument: findings\n  argument: "+submissionID) || len(f.calls) != before {
		t.Fatal("handoff dispatched a read", text)
	}
}

func TestHandoffPreservesPageCursorAsSeparateArgument(t *testing.T) {
	m := boot(t, &fakeClient{})
	m.pageCursor = "opaque ' cursor; not shell"
	text := m.handoffText()
	if !strings.Contains(text, "argument: --limit\n  argument: 50") || !strings.Contains(text, "argument: --cursor\n  argument: opaque ' cursor; not shell") {
		t.Fatal(text)
	}
}
