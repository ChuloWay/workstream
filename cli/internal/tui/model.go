// Package tui presents contributor observations through the existing public client.
package tui

import (
	"context"
	"strings"
	"time"
	"unicode/utf8"

	"charm.land/bubbles/v2/viewport"
	tea "charm.land/bubbletea/v2"
	"github.com/Flow-Research/workstream/cli/internal/api"
)

type tab int

const (
	ready tab = iota
	mine
	submissions
)

func (t tab) String() string { return [...]string{"READY", "MINE", "SUBMISSIONS"}[t] }

type row struct {
	id, task, project, title, status string
}

// Model owns one fetched page and one exact detail, never an authority cache.
type Model struct {
	client                                            ReadClient
	ctx                                               context.Context
	stop                                              context.CancelFunc
	cancel                                            context.CancelFunc
	token                                             string
	plain, noColor                                    bool
	width, height                                     int
	started, closed, blocked, picker, detail, loading bool
	help, handoff, filtering                          bool
	filter, savedFilter                               string
	actor, project, projectName                       string
	tab                                               tab
	section                                           int
	rows                                              []row
	selected, page                                    int
	cursor                                            *string
	pageCursor                                        string
	request                                           request
	generation                                        uint64
	failure                                           string
	observed                                          time.Time
	task                                              *api.ContributorTaskDetail
	context                                           *api.WorkContext
	intake                                            *api.SubmissionRequirements
	submission                                        *api.SubmissionHistory
	viewport                                          viewport.Model
}

// New has no I/O; the first adequately sized terminal event starts actor binding.
func New(ctx context.Context, client ReadClient, token string, plain, noColor bool) *Model {
	ctx, stop := context.WithCancel(ctx)
	return &Model{ctx: ctx, stop: stop, client: client, token: token, plain: plain,
		noColor: noColor || plain, picker: true, page: 1, viewport: viewport.New()}
}

func (m *Model) Init() tea.Cmd { return nil }

// Close cancels outstanding reads after the program has stopped, including errors.
func (m *Model) Close() { m.closed = true; m.invalidate(); m.stop() }

func (m *Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	defer m.reflow()
	if m.closed {
		return m, nil
	}
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width, m.height = min(max(msg.Width, 1), 300), min(max(msg.Height, 1), 150)
		if !m.started && !m.tooSmall() {
			m.started = true
			return m, m.begin(profileRead)
		}
	case response:
		return m, m.receive(msg)
	case tea.KeyPressMsg:
		return m, m.key(msg)
	}
	return m, nil
}

func (m *Model) tooSmall() bool { return m.width < 40 || m.height < 10 }

func (m *Model) invalidate() {
	if m.cancel != nil {
		m.cancel()
		m.cancel = nil
	}
	m.generation++
	m.loading = false
}

func (m *Model) clearDetail() {
	m.detail, m.section = false, 0
	m.task, m.context, m.intake, m.submission = nil, nil, nil, nil
	m.handoff = false
	m.viewport.GotoTop()
}

func (m *Model) clearPage() {
	m.rows, m.cursor = nil, nil
	m.pageCursor = ""
	m.selected, m.page = 0, 1
	m.filter, m.savedFilter, m.failure = "", "", ""
	m.filtering = false
	m.observed = time.Time{}
	m.clearDetail()
}

func (m *Model) visible() []row {
	if m.filter == "" {
		return m.rows
	}
	rows := make([]row, 0, len(m.rows))
	for _, row := range m.rows {
		if strings.Contains(strings.ToLower(m.clean(row.title)), strings.ToLower(m.clean(m.filter))) {
			rows = append(rows, row)
		}
	}
	return rows
}

func (m *Model) selectedRow() (row, bool) {
	rows := m.visible()
	if m.selected < 0 || m.selected >= len(rows) {
		return row{}, false
	}
	return rows[m.selected], true
}

func (m *Model) key(key tea.KeyPressMsg) tea.Cmd {
	k := key.String()
	if k == "ctrl+c" || (!m.filtering && k == "q") {
		m.closed = true
		m.invalidate()
		m.stop()
		return tea.Quit
	}
	if m.filtering {
		switch k {
		case "enter":
			m.filtering = false
		case "esc":
			m.filter, m.filtering = m.savedFilter, false
		case "backspace":
			_, size := utf8.DecodeLastRuneInString(m.filter)
			if size > 0 {
				m.filter = m.filter[:len(m.filter)-size]
			}
		default:
			if key.Text != "" && len(m.filter)+len(key.Text) <= 256 {
				m.filter += key.Text
			}
		}
		m.selected = 0
		return nil
	}
	if k == "?" {
		m.help, m.handoff = !m.help, false
		m.viewport.GotoTop()
		return nil
	}
	if k == "esc" && (m.help || m.handoff) {
		m.help, m.handoff = false, false
		return nil
	}
	if m.help {
		return m.scroll(k)
	}
	if m.blocked || m.tooSmall() {
		return nil
	}
	if k == "g" && m.actor != "" {
		m.invalidate()
		m.clearPage()
		m.picker = true
		m.project, m.projectName = "", ""
		return m.begin(projectsRead)
	}
	if k == "c" {
		m.handoff = !m.handoff
		m.viewport.GotoTop()
		return nil
	}
	if m.handoff {
		return m.scroll(k)
	}
	if k == "esc" && m.detail {
		m.invalidate()
		m.clearDetail()
		m.failure = ""
		return nil
	}
	if k == "tab" && !m.picker && !m.detail {
		m.invalidate()
		m.clearPage()
		m.tab = (m.tab + 1) % 3
		return m.begin(pageRead)
	}
	if k == "r" {
		if m.loading {
			return nil
		}
		if m.detail {
			m.context, m.intake, m.task, m.submission = nil, nil, nil, nil
			m.section = 0
			return m.begin(m.detailKind())
		}
		m.clearPage()
		if m.actor == "" {
			return m.begin(profileRead)
		}
		if m.picker {
			return m.begin(projectsRead)
		}
		return m.begin(pageRead)
	}
	if m.loading || m.failure != "" {
		return nil
	}
	if m.detail {
		if k == "tab" && m.tab == mine {
			m.section = (m.section + 1) % 3
			m.viewport.GotoTop()
			switch m.section {
			case 1:
				return m.begin(contextRead)
			case 2:
				return m.begin(intakeRead)
			}
		}
		return m.scroll(k)
	}
	switch k {
	case "/":
		m.filtering, m.savedFilter = true, m.filter
	case "up":
		m.selected = max(0, m.selected-1)
	case "down":
		m.selected = min(max(0, len(m.visible())-1), m.selected+1)
	case "n":
		if m.cursor != nil {
			cursor := *m.cursor
			m.rows, m.cursor = nil, nil
			m.selected = 0
			m.page++
			m.filter = ""
			if m.picker {
				return m.beginCursor(projectsRead, cursor)
			}
			return m.beginCursor(pageRead, cursor)
		}
	case "enter":
		if selected, ok := m.selectedRow(); ok {
			if m.picker {
				m.project, m.projectName = selected.id, selected.title
				m.picker, m.tab = false, ready
				m.clearPage()
				return m.begin(pageRead)
			}
			m.clearDetail()
			m.detail = true
			return m.begin(m.detailKind())
		}
	}
	return nil
}

func (m *Model) detailKind() readKind {
	if m.tab == submissions {
		return submissionRead
	}
	return taskRead
}

func (m *Model) scroll(key string) tea.Cmd {
	switch key {
	case "down":
		m.viewport.ScrollDown(1)
	case "up":
		m.viewport.ScrollUp(1)
	case "pgdown":
		m.viewport.ScrollDown(max(1, m.viewport.Height()-1))
	case "pgup":
		m.viewport.ScrollUp(max(1, m.viewport.Height()-1))
	}
	return nil
}
