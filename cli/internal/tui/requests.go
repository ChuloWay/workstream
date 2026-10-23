package tui

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	tea "charm.land/bubbletea/v2"
	"github.com/Flow-Research/workstream/cli/internal/api"
)

// ReadClient is the bounded public read surface, satisfied directly by api.Client.
type ReadClient interface {
	Profile(context.Context) (api.Result[api.Profile], error)
	MyProjects(context.Context, api.PageQuery) (api.Result[api.ActorProjectPage], error)
	ReadyTasks(context.Context, string, int, *string) (api.Result[api.ReadyTaskPage], error)
	MyAssignments(context.Context, api.PageQuery) (api.Result[api.ContributorAssignmentPage], error)
	MySubmissions(context.Context, api.PageQuery) (api.Result[api.ContributorSubmissionPage], error)
	ContributorTask(context.Context, string) (api.Result[api.ContributorTaskDetail], error)
	WorkContext(context.Context, string) (api.Result[api.WorkContext], error)
	SubmissionRequirements(context.Context, string) (api.Result[api.SubmissionRequirements], error)
	Submission(context.Context, string) (api.Result[api.SubmissionHistory], error)
}

var _ ReadClient = (*api.Client)(nil)

type readKind int

const (
	profileRead readKind = iota
	projectsRead
	pageRead
	taskRead
	submissionRead
	contextRead
	intakeRead
)

// request is an immutable identity carried through a non-cooperative response.
type request struct {
	generation                             uint64
	actor, project, resource, task, cursor string
	tab                                    tab
	kind                                   readKind
	page, section                          int
}

type response struct {
	request request
	value   any
	err     error
}

func (m *Model) begin(kind readKind) tea.Cmd { return m.beginCursor(kind, "") }

func (m *Model) beginCursor(kind readKind, cursor string) tea.Cmd {
	m.invalidate()
	if kind == projectsRead || kind == pageRead {
		m.pageCursor = cursor
	}
	m.failure, m.loading = "", true
	m.observed = time.Time{}
	r := request{generation: m.generation, actor: m.actor, project: m.project, tab: m.tab,
		kind: kind, page: m.page, section: m.section, cursor: cursor}
	if selected, ok := m.selectedRow(); ok {
		r.resource, r.task = selected.id, selected.task
	}
	m.request = r
	ctx, cancel := context.WithCancel(m.ctx)
	m.cancel = cancel
	client := m.client
	return func() (message tea.Msg) {
		// Never hand an application panic (which may contain a bearer) to the
		// renderer's diagnostic logger or process-wide panic machinery.
		defer func() {
			if recover() != nil {
				message = response{r, nil, &api.Failure{Code: "request_failed"}}
			}
		}()
		var value any
		var err error
		var continuation *string
		if r.cursor != "" {
			continuation = &r.cursor
		}
		q := api.PageQuery{Limit: 50, Cursor: continuation}
		switch r.kind {
		case profileRead:
			var result api.Result[api.Profile]
			result, err = client.Profile(ctx)
			value = result.Value
		case projectsRead:
			var result api.Result[api.ActorProjectPage]
			result, err = client.MyProjects(ctx, q)
			value = result.Value
		case pageRead:
			q.ProjectID = &r.project
			switch r.tab {
			case ready:
				var result api.Result[api.ReadyTaskPage]
				result, err = client.ReadyTasks(ctx, r.project, 50, continuation)
				value = result.Value
			case mine:
				state := "active"
				q.State = &state
				var result api.Result[api.ContributorAssignmentPage]
				result, err = client.MyAssignments(ctx, q)
				value = result.Value
			case submissions:
				var result api.Result[api.ContributorSubmissionPage]
				result, err = client.MySubmissions(ctx, q)
				value = result.Value
			}
		case taskRead:
			var result api.Result[api.ContributorTaskDetail]
			result, err = client.ContributorTask(ctx, r.task)
			value = result.Value
		case submissionRead:
			var result api.Result[api.SubmissionHistory]
			result, err = client.Submission(ctx, r.resource)
			value = result.Value
		case contextRead:
			var result api.Result[api.WorkContext]
			result, err = client.WorkContext(ctx, r.task)
			value = result.Value
		case intakeRead:
			var result api.Result[api.SubmissionRequirements]
			result, err = client.SubmissionRequirements(ctx, r.task)
			value = result.Value
		}
		return response{r, value, err}
	}
}

func sameID(a, b string) bool {
	return strings.EqualFold(strings.ReplaceAll(a, "-", ""), strings.ReplaceAll(b, "-", ""))
}

func (m *Model) receive(msg response) tea.Cmd {
	if msg.request != m.request || msg.request.generation != m.generation || !m.loading {
		return nil
	}
	m.loading = false
	if m.cancel != nil {
		m.cancel()
		m.cancel = nil
	}
	if msg.err != nil {
		m.failed(msg.err, msg.request.kind == profileRead)
		return nil
	}
	bad := func() tea.Cmd { m.failed(&api.Failure{Code: "invalid_api_response"}, false); return nil }
	r := msg.request
	switch value := msg.value.(type) {
	case api.Profile:
		if r.kind != profileRead || value.ActorProfileID == "" {
			return bad()
		}
		m.actor = value.ActorProfileID
		return m.begin(projectsRead)
	case api.ActorProjectPage:
		if r.kind != projectsRead {
			return bad()
		}
		for _, item := range value.Items {
			m.rows = append(m.rows, row{id: item.ProjectID, project: item.ProjectID, title: item.Name, status: item.Status})
		}
		m.cursor = value.Cursor
	case api.ReadyTaskPage:
		if r.kind != pageRead || r.tab != ready || !sameID(value.ProjectID, r.project) {
			return bad()
		}
		for _, item := range value.Items {
			if !sameID(item.ProjectID, r.project) {
				return bad()
			}
			m.rows = append(m.rows, row{id: item.TaskID, task: item.TaskID, project: item.ProjectID, title: item.Title, status: "ready"})
		}
		m.cursor = value.NextCursor
	case api.ContributorAssignmentPage:
		if r.kind != pageRead || r.tab != mine {
			return bad()
		}
		for _, item := range value.Items {
			if !sameID(item.ProjectID, r.project) || item.State != "active" {
				return bad()
			}
			m.rows = append(m.rows, row{id: item.AssignmentID, task: item.TaskID, project: item.ProjectID, title: item.Title, status: item.AssignmentStatus})
		}
		m.cursor = value.Cursor
	case api.ContributorSubmissionPage:
		if r.kind != pageRead || r.tab != submissions {
			return bad()
		}
		for _, item := range value.Items {
			if !sameID(item.ProjectID, r.project) {
				return bad()
			}
			m.rows = append(m.rows, row{id: item.SubmissionID, task: item.TaskID, project: item.ProjectID, title: item.Title, status: item.Status})
		}
		m.cursor = value.Cursor
	case api.ContributorTaskDetail:
		if r.kind != taskRead || !sameID(value.TaskID, r.task) || !sameID(value.ProjectID, r.project) {
			return bad()
		}
		m.task = &value
	case api.SubmissionHistory:
		if r.kind != submissionRead || !sameID(value.ID, r.resource) || !sameID(value.Task, r.task) {
			return bad()
		}
		m.submission = &value
	case api.WorkContext:
		if r.kind != contextRead || !sameID(value.Task.TaskID, r.task) || !sameID(value.Project.ID, r.project) ||
			!sameID(value.Task.ProjectID, r.project) || !sameID(value.Guide.ProjectID, r.project) ||
			(m.task != nil && !sameID(value.ContributionPolicyVersionID, m.task.Compensation.ContributionPolicyVersionID)) ||
			(m.intake != nil && value.Guide.Version != m.intake.GuideVersion) {
			return bad()
		}
		m.context = &value
	case api.SubmissionRequirements:
		if r.kind != intakeRead || !sameID(value.TaskID, r.task) || !sameID(value.ProjectID, r.project) ||
			(m.context != nil && value.GuideVersion != m.context.Guide.Version) {
			return bad()
		}
		m.intake = &value
	default:
		return bad()
	}
	m.observed = time.Now()
	m.viewport.GotoTop()
	return nil
}

func (m *Model) failed(err error, actorRead bool) {
	m.invalidate()
	m.clearPage()
	m.projectName = ""
	var failure *api.Failure
	if errors.As(err, &failure) {
		if failure.Status == 401 || (actorRead && failure.Status == 403) {
			m.blocked = true
			m.actor = ""
		}
		label := "Unavailable"
		if failure.Status == 401 || failure.Status == 403 || failure.Status == 404 {
			label = "Denied"
		}
		m.failure = label + ": " + m.clean(failure.Code)
		if failure.Status != 0 {
			m.failure += fmt.Sprintf(" (HTTP %d)", failure.Status)
		}
		if failure.CorrelationID != "" {
			m.failure += " correlation " + m.clean(failure.CorrelationID)
		}
	} else {
		m.failure = "Unavailable: request_failed"
	}
	// No old observation survives a fresh refusal or transport failure.
	m.observed = time.Time{}
}
