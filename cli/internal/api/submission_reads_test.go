package api

import (
	"encoding/json"
	"testing"
)

const (
	testSubmission = "019b9ba2-4100-7000-8000-000000000001"
	testTask       = "019b9ba2-4100-7000-8000-000000000002"
	testRun        = "019b9ba2-4100-7000-8000-000000000003"
	testFinding    = "019b9ba2-4100-7000-8000-000000000004"
)

func checkerRunJSON() map[string]any {
	return map[string]any{
		"id": testRun, "task_id": testTask, "submission_id": testSubmission,
		"submission_version": 2, "status": "completed", "attempt_number": 1,
		"supersedes_checker_run_id": nil, "is_current_for_submission": true,
		"created_at": "2026-10-26T10:00:00Z", "completed_at": "2026-10-26T10:01:00Z",
		"results": []any{map[string]any{
			"id": testFinding, "checker_name": "lint", "check_id": "lint.safe",
			"path": "answer.md", "line": 4, "status": "warning", "severity": "medium",
			"worker_message": "explain this", "worker_suggested_fix": "add detail",
		}},
	}
}

func TestDecodeSubmissionFindingsTypedPageAndRun(t *testing.T) {
	runRaw, err := json.Marshal(checkerRunJSON())
	if err != nil {
		t.Fatal(err)
	}
	exactBytes := string(runRaw)
	exact, err := decodeSubmissionFindings(runRaw, testSubmission, testRun, 50)
	if err != nil || exact.Run == nil || exact.Page != nil || exact.Run.ID != testRun || len(exact.Run.Results) != 1 {
		t.Fatal("exact run was not typed", exact, err)
	}
	if string(runRaw) != exactBytes {
		t.Fatal("exact raw response changed")
	}
	pageRaw, err := json.Marshal(map[string]any{"items": []any{checkerRunJSON()}, "next_cursor": "opaque-next"})
	if err != nil {
		t.Fatal(err)
	}
	pageBytes := string(pageRaw)
	page, err := decodeSubmissionFindings(pageRaw, testSubmission, "", 50)
	if err != nil || page.Page == nil || page.Run != nil || len(page.Page.Items) != 1 || page.Page.Cursor == nil || *page.Page.Cursor != "opaque-next" {
		t.Fatal("page was not typed", page, err)
	}
	if got := page.Page.Items[0]; got.Task != testTask || got.Results[0].Fix == nil || *got.Results[0].Fix != "add detail" {
		t.Fatal("typed fields were not preserved", got)
	}
	if string(pageRaw) != pageBytes {
		t.Fatal("page raw response changed")
	}
}

func TestDecodeSubmissionFindingsRejectsMisbinding(t *testing.T) {
	run := checkerRunJSON()
	run["submission_id"] = testTask
	raw, _ := json.Marshal(map[string]any{"items": []any{run}, "next_cursor": nil})
	if _, err := decodeSubmissionFindings(raw, testSubmission, "", 50); err == nil {
		t.Fatal("foreign Submission accepted")
	}
}
