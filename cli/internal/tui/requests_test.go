package tui

import (
	"context"
	"strings"
	"testing"

	"github.com/Flow-Research/workstream/cli/internal/api"
)

func TestNonCooperativeLateSuccessCannotReplaceNewScope(t *testing.T) {
	f := &fakeClient{}
	m := boot(t, f)
	press(t, m, "enter")
	_, cmd := m.Update(keyMessage("enter"))
	late := cmd() // deliberately succeeds even after later cancellation
	press(t, m, "esc")
	press(t, m, "tab")
	m.Update(late)
	if m.tab != mine || m.detail || m.task != nil || len(m.rows) != 1 || m.rows[0].title != "Assigned task" {
		t.Fatal("late task replaced Mine")
	}
}

func TestLateSuccessAfterDenialCannotResurrectData(t *testing.T) {
	f := &fakeClient{}
	m := boot(t, f)
	press(t, m, "enter")
	_, cmd := m.Update(keyMessage("enter"))
	late := cmd().(response)
	m.Update(response{request: late.request, err: &api.Failure{Code: "revoked", Status: 403}})
	m.Update(late)
	if m.task != nil || len(m.rows) > 0 || !strings.Contains(m.failure, "Denied") {
		t.Fatal("late response resurrected data")
	}
}

func TestFresh401BlocksCachedNavigation(t *testing.T) {
	f := &fakeClient{}
	m := boot(t, f)
	press(t, m, "enter")
	_, cmd := m.Update(keyMessage("enter"))
	r := cmd().(response)
	m.Update(response{request: r.request, err: &api.Failure{Code: "expired", Status: 401}})
	if m.project != "" || m.request != (request{}) || strings.Contains(m.View().Content, projectID) {
		t.Fatal("authentication failure retained project or request selectors")
	}
	before := len(f.calls)
	for _, k := range []string{"g", "r", "tab", "enter"} {
		press(t, m, k)
	}
	if len(f.calls) != before || !m.blocked || m.actor != "" || len(m.rows) > 0 {
		t.Fatal("authentication failure retried")
	}
}

func TestDetailIdentityAndLockedContextMismatchRefused(t *testing.T) {
	for _, scenario := range []string{"task", "project", "policy", "guide"} {
		t.Run(scenario, func(t *testing.T) {
			f := &fakeClient{}
			m := boot(t, f)
			press(t, m, "enter")
			if scenario == "task" || scenario == "project" {
				f.task = func(context.Context, string) (api.Result[api.ContributorTaskDetail], error) {
					v := taskDetail()
					if scenario == "task" {
						v.TaskID = actorID
					} else {
						v.ProjectID = actorID
					}
					return api.Result[api.ContributorTaskDetail]{Value: v}, nil
				}
				press(t, m, "enter")
			} else {
				press(t, m, "tab")
				press(t, m, "enter")
				if scenario == "policy" {
					f.context = func(context.Context, string) (api.Result[api.WorkContext], error) {
						return api.Result[api.WorkContext]{Value: api.WorkContext{Task: taskDetail(), Project: api.ContextProject{ID: projectID}, Guide: api.ContextGuide{ProjectID: projectID}, ContributionPolicyVersionID: actorID}}, nil
					}
				}
				press(t, m, "tab")
				if scenario == "guide" {
					f.intake = func(context.Context, string) (api.Result[api.SubmissionRequirements], error) {
						return api.Result[api.SubmissionRequirements]{Value: api.SubmissionRequirements{TaskID: taskID, ProjectID: projectID, GuideVersion: "different"}}, nil
					}
					press(t, m, "tab")
				}
			}
			if m.failure == "" || m.task != nil || m.context != nil || m.intake != nil || len(m.rows) != 0 {
				t.Fatal("mismatched identity/lineage accepted")
			}
		})
	}
}

func TestRequestPanicIsBoundedWithoutBearerOrStack(t *testing.T) {
	f := &fakeClient{}
	m := boot(t, f)
	press(t, m, "enter")
	f.task = func(context.Context, string) (api.Result[api.ContributorTaskDetail], error) {
		panic("secret-token panic and stack")
	}
	press(t, m, "enter")
	if !strings.Contains(m.failure, "request_failed") || strings.Contains(m.View().Content, "secret-token") || strings.Contains(m.View().Content, "panic and stack") {
		t.Fatal(m.View().Content)
	}
}

func TestResourceTaskSubstitutionInOwnedAttempt(t *testing.T) {
	f := &fakeClient{}
	m := boot(t, f)
	press(t, m, "enter")
	press(t, m, "tab")
	press(t, m, "tab")
	_, cmd := m.Update(keyMessage("enter"))
	msg := cmd().(response)
	value := msg.value.(api.SubmissionHistory)
	value.Task = actorID
	msg.value = value
	m.Update(msg)
	if m.submission != nil || m.failure == "" {
		t.Fatal("foreign task accepted")
	}
}

func TestTransientProfileFailureRetriesBindingBeforeProjects(t *testing.T) {
	for _, scenario := range []string{"503", "panic"} {
		t.Run(scenario, func(t *testing.T) {
			f := &fakeClient{}
			attempts := 0
			f.profile = func(context.Context) (api.Result[api.Profile], error) {
				attempts++
				if attempts == 1 {
					if scenario == "panic" {
						panic("private profile error")
					}
					return api.Result[api.Profile]{}, &api.Failure{Code: "temporarily_unavailable", Status: 503}
				}
				return api.Result[api.Profile]{Value: api.Profile{ActorProfileID: actorID}}, nil
			}
			m := boot(t, f)
			if m.actor != "" || strings.Join(f.calls, ",") != "profile" {
				t.Fatal("projects read before binding", f.calls)
			}
			press(t, m, "r")
			if m.actor != actorID || strings.Join(f.calls, ",") != "profile,profile,projects" || len(m.rows) != 1 {
				t.Fatal("refresh skipped profile retry", f.calls)
			}
		})
	}
}

func TestRefreshReplacesDelayedFirstFindingsRead(t *testing.T) {
	calls := 0
	f := &fakeClient{findings: func(context.Context, string, string, int, *string) (api.Result[api.SubmissionFindingsResult], error) {
		calls++
		page := api.SubmissionCheckerPage{Items: []api.SubmissionCheckerRun{{ID: runID, Task: taskID, Submission: submissionID, Current: calls == 1}}}
		return api.Result[api.SubmissionFindingsResult]{Value: api.SubmissionFindingsResult{Page: &page}}, nil
	}}
	m := boot(t, f)
	press(t, m, "enter")
	press(t, m, "tab")
	press(t, m, "tab")
	press(t, m, "enter")
	_, delayed := m.Update(keyMessage("tab"))
	_, refreshed := m.Update(keyMessage("r"))
	if delayed == nil || refreshed == nil {
		t.Fatal("pending first findings read was not replaceable")
	}
	apply(t, m, refreshed)
	m.Update(delayed())
	if calls != 2 || m.findings == nil || !m.findings.Items[0].Current || m.loading || m.findingsPage != 1 {
		t.Fatal("late first findings response replaced refresh", calls, m.findings, m.findingsPage)
	}
}

func TestRefreshReplacesDelayedNextFindingsPageWithFirstPage(t *testing.T) {
	cursor := "next-page"
	calls := 0
	f := &fakeClient{findings: func(_ context.Context, _ string, _ string, _ int, next *string) (api.Result[api.SubmissionFindingsResult], error) {
		calls++
		page := api.SubmissionCheckerPage{Items: []api.SubmissionCheckerRun{{ID: runID, Task: taskID, Submission: submissionID, Current: next == nil}}}
		if next == nil {
			page.Cursor = &cursor
		}
		return api.Result[api.SubmissionFindingsResult]{Value: api.SubmissionFindingsResult{Page: &page}}, nil
	}}
	m := boot(t, f)
	press(t, m, "enter")
	press(t, m, "tab")
	press(t, m, "tab")
	press(t, m, "enter")
	press(t, m, "tab")
	_, delayedNext := m.Update(keyMessage("n"))
	_, refreshed := m.Update(keyMessage("r"))
	if delayedNext == nil || refreshed == nil {
		t.Fatal("pending continuation was not replaceable")
	}
	apply(t, m, refreshed)
	m.Update(delayedNext())
	if calls != 3 || m.findings == nil || !m.findings.Items[0].Current || m.findingsPage != 1 || m.findingsPageCursor != "" {
		t.Fatal("late continuation replaced refreshed first page", calls, m.findings, m.findingsPage, m.findingsPageCursor)
	}
}
