package tui

import (
	"context"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/Flow-Research/workstream/cli/internal/api"
)

func guideContext(documents ...api.TaskGuideDocument) api.WorkContext {
	return api.WorkContext{
		Task: taskDetail(), Project: api.ContextProject{ID: projectID},
		Guide:                       api.ContextGuide{ID: actorID, ProjectID: projectID, Version: "locked-v1"},
		ContributionPolicyVersionID: policyID,
		Lifecycle:                   api.ContextLifecycle{AssignedToCurrentActor: true},
		GuideDocuments:              documents,
	}
}

func openMineGuide(t *testing.T, f *fakeClient) *Model {
	t.Helper()
	m := boot(t, f)
	press(t, m, "enter")
	press(t, m, "tab")
	press(t, m, "enter")
	press(t, m, "tab")
	press(t, m, "tab")
	press(t, m, "tab")
	if m.section != 3 || m.context == nil {
		t.Fatal("Guide did not load", f.calls)
	}
	return m
}

func TestGuidePreservesOrderAndPublishesOnlyAfterConfirmation(t *testing.T) {
	doc1 := api.TaskGuideDocument{DocumentID: actorID, Order: 2, Label: "First", MediaType: "text/markdown", ByteCount: 5, SHA256: "sha256:" + strings.Repeat("a", 64)}
	doc2 := api.TaskGuideDocument{DocumentID: policyID, Order: 7, Label: "Second", MediaType: "application/pdf", ByteCount: 5, SHA256: "sha256:" + strings.Repeat("b", 64)}
	f := &fakeClient{context: func(context.Context, string) (api.Result[api.WorkContext], error) {
		return api.Result[api.WorkContext]{Value: guideContext(doc1, doc2)}, nil
	}}
	m := openMineGuide(t, f)
	text := m.detailText()
	for _, want := range []string{"1. First", "2. Second", "Label: First", "Order: 2", doc1.DocumentID, doc1.SHA256, "bytes not downloaded"} {
		if !strings.Contains(text, want) {
			t.Fatal(want, text)
		}
	}
	if strings.Index(text, "1. First") > strings.Index(text, "2. Second") || strings.Contains(text, doc2.SHA256) {
		t.Fatal(text)
	}
	directory := filepath.Join(t.TempDir(), "qgr")
	if err := os.Mkdir(directory, 0700); err != nil {
		t.Fatal(err)
	}
	press(t, m, "down")
	for _, want := range []string{"Label: Second", "Order: 7", doc2.DocumentID, doc2.SHA256, "Bytes (server metadata; bytes not downloaded): 5"} {
		if !strings.Contains(m.detailText(), want) {
			t.Fatal("selected original lost exact metadata", want, m.detailText())
		}
	}
	if strings.Contains(m.detailText(), doc1.SHA256) {
		t.Fatal("previous original metadata retained as selected")
	}
	press(t, m, "d")
	press(t, m, "?")
	if m.guideDirectory != "?" {
		t.Fatal("question mark triggered a global key", m.guideDirectory)
	}
	press(t, m, "backspace")
	for _, character := range directory {
		press(t, m, string(character))
	}
	if m.closed {
		t.Fatal("destination text triggered a global key")
	}
	if !strings.Contains(m.detailText(), "Download directory: "+directory) {
		t.Fatal(m.detailText())
	}
	before := len(f.calls)
	press(t, m, "enter")
	confirmation := m.detailText()
	for _, want := range []string{"Confirm download", "Task: " + taskID, "Document: " + doc2.DocumentID, "Filename: " + doc2.Filename()} {
		if !strings.Contains(confirmation, want) {
			t.Fatal(want, confirmation)
		}
	}
	if len(f.calls) != before || m.loading {
		t.Fatal(confirmation)
	}
	if entries, _ := os.ReadDir(directory); len(entries) != 0 {
		t.Fatal("confirmation performed I/O", entries)
	}
	press(t, m, "y")
	target := filepath.Join(directory, doc2.Filename())
	if body, err := os.ReadFile(target); err != nil || string(body) != "guide" || !strings.Contains(m.detailText(), "Downloaded: "+doc2.Filename()) {
		t.Fatal(string(body), err, m.detailText())
	}
}

func TestGuideNavigationAbortsStageAndLateResponseCannotPublish(t *testing.T) {
	document := api.TaskGuideDocument{DocumentID: actorID, Label: "Guide", MediaType: "text/markdown", ByteCount: 5, SHA256: "sha256:" + strings.Repeat("a", 64)}
	f := &fakeClient{context: func(context.Context, string) (api.Result[api.WorkContext], error) {
		return api.Result[api.WorkContext]{Value: guideContext(document)}, nil
	}}
	m := openMineGuide(t, f)
	directory := t.TempDir()
	press(t, m, "d")
	press(t, m, directory)
	press(t, m, "enter")
	_, cmd := m.Update(keyMessage("y"))
	if cmd == nil || m.download == nil {
		t.Fatal("download was not staged")
	}
	press(t, m, "esc")
	late := cmd()
	m.Update(late)
	if _, err := os.Stat(filepath.Join(directory, document.Filename())); !os.IsNotExist(err) {
		t.Fatal("cancelled response published", err)
	}
	if entries, _ := os.ReadDir(directory); len(entries) != 0 {
		t.Fatal("cancelled stage retained", entries)
	}
}

func TestGuideRefreshAbortsDownloadAndReloadsFreshContext(t *testing.T) {
	document := api.TaskGuideDocument{DocumentID: actorID, Label: "Guide", MediaType: "text/markdown", ByteCount: 5, SHA256: "sha256:" + strings.Repeat("a", 64)}
	contextReads := 0
	f := &fakeClient{context: func(context.Context, string) (api.Result[api.WorkContext], error) {
		contextReads++
		return api.Result[api.WorkContext]{Value: guideContext(document)}, nil
	}}
	m := openMineGuide(t, f)
	directory := t.TempDir()
	press(t, m, "d")
	press(t, m, directory)
	press(t, m, "enter")
	_, downloadCmd := m.Update(keyMessage("y"))
	if downloadCmd == nil {
		t.Fatal("download was not staged")
	}
	_, refreshCmd := m.Update(keyMessage("r"))
	if refreshCmd == nil || m.request.kind != contextRead {
		t.Fatal("refresh did not replace pending download with Guide context read")
	}
	apply(t, m, refreshCmd)
	late := downloadCmd()
	m.Update(late)
	if contextReads < 3 || m.context == nil || m.section != 3 {
		t.Fatal("Guide context was not freshly restored", contextReads, m.section)
	}
	if entries, _ := os.ReadDir(directory); len(entries) != 0 {
		t.Fatal("refreshed download published or retained bytes", entries)
	}
}

func TestGuideReloadClampsSelectionBeforeConfirmation(t *testing.T) {
	for _, reload := range []string{"refresh", "tab"} {
		for _, empty := range []bool{false, true} {
			name := reload + "/shorter"
			if empty {
				name = reload + "/empty"
			}
			t.Run(name, func(t *testing.T) {
				documents := []api.TaskGuideDocument{
					{DocumentID: actorID, Label: "Remaining", MediaType: "text/markdown"},
					{DocumentID: policyID, Label: "Removed", MediaType: "text/markdown"},
				}
				f := &fakeClient{context: func(context.Context, string) (api.Result[api.WorkContext], error) {
					return api.Result[api.WorkContext]{Value: guideContext(documents...)}, nil
				}}
				m := openMineGuide(t, f)
				press(t, m, "down")
				documents = documents[:1]
				if empty {
					documents = nil
				}
				if reload == "refresh" {
					press(t, m, "r")
				} else {
					for range 4 {
						press(t, m, "tab")
					}
				}
				before := len(f.calls)
				press(t, m, "d")
				if empty {
					if m.guideMode != guideBrowse || len(f.calls) != before {
						t.Fatal("empty guide opened a download", m.guideMode, f.calls)
					}
					return
				}
				press(t, m, t.TempDir())
				press(t, m, "enter")
				confirmation := m.detailText()
				if !strings.Contains(confirmation, "Document: "+actorID) || strings.Contains(confirmation, "Document: "+policyID) || len(f.calls) != before {
					t.Fatal("confirmation did not bind the refreshed document without I/O", confirmation, f.calls)
				}
			})
		}
	}
}

func TestFindingsNavigationPaginationAndMisbinding(t *testing.T) {
	cursor := "next-page"
	requests := 0
	f := &fakeClient{findings: func(_ context.Context, submission, run string, limit int, next *string) (api.Result[api.SubmissionFindingsResult], error) {
		requests++
		if submission != submissionID || run != "" || limit != 50 {
			t.Fatal(submission, run, limit)
		}
		path, line, check, message, fix := "answer.md", int64(8), "lint.safe", "hostile\x1b]52;c;token\a", "repair"
		task := taskID
		if requests == 3 {
			task = actorID
		}
		predecessor := actorID
		page := api.SubmissionCheckerPage{Items: []api.SubmissionCheckerRun{{
			ID: runID, Task: task, Submission: submissionID, Version: nil, Status: "completed", Attempt: nil,
			Current: requests != 2, Predecessor: &predecessor, Results: []api.ContributorFinding{
				{ID: findingID, Checker: "lint", CheckID: &check, Path: &path, Line: &line, Status: "coverage_incomplete", Severity: "medium", Message: &message, Fix: &fix},
				{ID: policyID, Checker: "format", Status: "passed", Severity: "info"},
			},
		}}}
		if next == nil {
			page.Cursor = &cursor
		} else if *next != cursor {
			t.Fatal(*next)
		}
		return api.Result[api.SubmissionFindingsResult]{Value: api.SubmissionFindingsResult{Page: &page}}, nil
	}}
	m := boot(t, f)
	press(t, m, "enter")
	press(t, m, "tab")
	press(t, m, "tab")
	press(t, m, "enter")
	press(t, m, "tab")
	text := m.detailText()
	for _, want := range []string{"Run: " + runID, "Current: true", "Predecessor run: " + actorID, "Checker: lint", "Check ID: lint.safe", "Finding status: coverage_incomplete", "Severity: medium", "Path: answer.md", "Line: 8", "Suggested fix\nrepair", "Severity: info\nFinding status: passed\nChecker: format\nCheck ID: not supplied\nMessage: not supplied\nPath: not supplied\nLine: not supplied\nSuggested fix: not supplied", "stored submission outcome determines disposition"} {
		if !strings.Contains(text, want) {
			t.Fatal(want, text)
		}
	}
	if strings.Contains(m.View().Content, "\x1b]52") {
		t.Fatal("terminal control reached view", m.View().Content)
	}
	press(t, m, "n")
	if requests != 2 || m.findingsPage != 2 || !strings.Contains(m.detailText(), "Current: false") {
		t.Fatal(requests, m.findingsPage, m.detailText())
	}
	press(t, m, "r")
	if requests != 3 || m.failure == "" || m.findings != nil || m.submission != nil {
		t.Fatal("foreign task finding retained", requests, m.failure)
	}
}

func TestGuideAndFindingsViewsFitMinimumTerminal(t *testing.T) {
	document := api.TaskGuideDocument{DocumentID: actorID, Order: 4, Label: strings.Repeat("wide guide label ", 20), MediaType: "text/markdown", ByteCount: 5, SHA256: "sha256:" + strings.Repeat("a", 64)}
	guideClient := &fakeClient{context: func(context.Context, string) (api.Result[api.WorkContext], error) {
		return api.Result[api.WorkContext]{Value: guideContext(document)}, nil
	}}
	guide := openMineGuide(t, guideClient)
	guide.Update(tea.WindowSizeMsg{Width: 40, Height: 10})
	assertBoundedView(t, guide.View().Content, 40, 10, "[Guide]")

	findings := boot(t, &fakeClient{})
	press(t, findings, "enter")
	press(t, findings, "tab")
	press(t, findings, "tab")
	press(t, findings, "enter")
	press(t, findings, "tab")
	findings.Update(tea.WindowSizeMsg{Width: 40, Height: 10})
	assertBoundedView(t, findings.View().Content, 40, 10, "[Findings]")
}

func assertBoundedView(t *testing.T, content string, width, height int, heading string) {
	t.Helper()
	if !strings.Contains(content, heading) || lipgloss.Height(content) > height {
		t.Fatal("view is not usable at minimum size", content)
	}
	for _, line := range strings.Split(content, "\n") {
		if lipgloss.Width(line) > width {
			t.Fatalf("line exceeds %d cells: %q", width, line)
		}
	}
}

func TestDownloadPanicAbortsPrivateStage(t *testing.T) {
	document := api.TaskGuideDocument{DocumentID: actorID, Label: "Guide", MediaType: "text/markdown", ByteCount: 5, SHA256: "sha256:" + strings.Repeat("a", 64)}
	f := &fakeClient{context: func(context.Context, string) (api.Result[api.WorkContext], error) {
		return api.Result[api.WorkContext]{Value: guideContext(document)}, nil
	}, download: func(context.Context, string, api.TaskGuideDocument, io.Writer) error {
		panic("secret-token download panic")
	}}
	m := openMineGuide(t, f)
	directory := t.TempDir()
	press(t, m, "d")
	press(t, m, directory)
	press(t, m, "enter")
	press(t, m, "y")
	if entries, _ := os.ReadDir(directory); len(entries) != 0 || strings.Contains(m.View().Content, "secret-token") {
		t.Fatal(entries, m.View().Content)
	}
}
