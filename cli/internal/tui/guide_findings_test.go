package tui

import (
	"context"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"

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
	if strings.Index(text, "First") > strings.Index(text, "Second") || !strings.Contains(text, "bytes not downloaded") {
		t.Fatal(text)
	}
	directory := filepath.Join(t.TempDir(), "q?gr")
	if err := os.Mkdir(directory, 0700); err != nil {
		t.Fatal(err)
	}
	press(t, m, "down")
	press(t, m, "d")
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
	if !strings.Contains(m.detailText(), "Confirm download") || len(f.calls) != before || m.loading {
		t.Fatal(m.detailText())
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
		page := api.SubmissionCheckerPage{Items: []api.SubmissionCheckerRun{{
			ID: runID, Task: task, Submission: submissionID, Version: nil, Status: "completed", Attempt: nil,
			Current: requests != 2, Results: []api.ContributorFinding{{ID: findingID, Checker: "lint", CheckID: &check, Path: &path, Line: &line, Status: "coverage_incomplete", Severity: "medium", Message: &message, Fix: &fix}},
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
	for _, want := range []string{"Run: " + runID, "Current: true", "Checker: lint", "Check ID: lint.safe", "Finding status: coverage_incomplete", "Severity: medium", "Path: answer.md", "Line: 8", "Suggested fix: repair", "not acceptance"} {
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
