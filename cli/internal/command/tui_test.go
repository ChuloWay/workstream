package command

import (
	"bytes"
	"context"
	"errors"
	"io"
	"os"
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"github.com/Flow-Research/workstream/cli/internal/api"
	"github.com/charmbracelet/x/term"
)

func TestTUIGuardsBeforeClientAndNetwork(t *testing.T) {
	for _, args := range [][]string{{"tui"}, {"tui", "--output", "json"}, {"tui", "--output", "invalid"}} {
		t.Run(strings.Join(args, " "), func(t *testing.T) {
			var out, errOut bytes.Buffer
			reads := 0
			code := Run(args, &out, &errOut, func(string) string { reads++; return "secret-token" }, "test")
			if code != 2 || reads != 0 || out.Len() != 0 || strings.Contains(errOut.String(), "secret-token") || strings.Contains(errOut.String(), "\x1b") {
				t.Fatalf("code=%d env=%d out=%q err=%q", code, reads, out.String(), errOut.String())
			}
		})
	}
}

func TestTUIHelpDoesNotReadConfiguration(t *testing.T) {
	var out, errOut bytes.Buffer
	code := Run([]string{"tui", "--help"}, &out, &errOut, func(string) string { t.Fatal("help read credentials"); return "" }, "test")
	if code != 0 || !strings.Contains(out.String(), "--plain") || errOut.Len() != 0 {
		t.Fatal(code, out.String(), errOut.String())
	}
}

func TestProgramErrorIsBounded(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	var out bytes.Buffer
	err := runTUI(ctx, nil, nil, &out, func(string) string { return "secret-token" }, true)
	var failure *api.Failure
	if !errors.As(err, &failure) || failure.Code != "terminal_unavailable" || strings.Contains(out.String(), "secret-token") {
		t.Fatal("unbounded program error", err, out.String())
	}
}

type failedTerminalWrite struct {
	short bool
	calls int
}

func (w *failedTerminalWrite) Write(value []byte) (int, error) {
	w.calls++
	if w.short {
		return len(value) - 1, nil
	}
	return 0, errors.New("secret-token private output failure")
}

type injectedTerminalProgram struct {
	run     func() error
	cleanup func()
}

func (p injectedTerminalProgram) Run() (tea.Model, error) { return nil, p.run() }
func (p injectedTerminalProgram) Kill()                   { p.cleanup() }

func TestFailedOutputCancelsAndCleansBeforeBoundedFailure(t *testing.T) {
	for _, short := range []bool{false, true} {
		t.Run(map[bool]string{false: "write error", true: "short write"}[short], func(t *testing.T) {
			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()
			destination := &failedTerminalWrite{short: short}
			output := &terminalOutput{destination: destination, cancel: cancel}
			var events []string
			program := injectedTerminalProgram{run: func() error {
				_, err := output.Write([]byte("terminal frame"))
				if err == nil || ctx.Err() == nil {
					t.Fatal("injected output failure was not observable")
				}
				if short && !errors.Is(err, io.ErrShortWrite) {
					t.Fatal("short write accepted", err)
				}
				events = append(events, "write failed")
				return err
			}, cleanup: func() { events = append(events, "cleanup") }}
			err := runTerminalProgram(program)
			events = append(events, "handle bounded error")
			var failure *api.Failure
			if destination.calls != 1 || !output.failed() || !errors.As(err, &failure) || failure.Code != "terminal_unavailable" || strings.Contains(err.Error(), "secret-token") {
				t.Fatal("output failure escaped or was ignored", err)
			}
			if strings.Join(events, ",") != "write failed,cleanup,handle bounded error" {
				t.Fatal("error handling preceded cleanup", events)
			}
		})
	}
}

func TestTerminalOutputPreservesRealDescriptor(t *testing.T) {
	observed := &terminalOutput{destination: os.Stdout, cancel: func() {}}
	var output io.Writer = terminalFileOutput{terminalOutput: observed, File: os.Stdout}
	file, ok := output.(term.File)
	if !ok || file.Fd() != os.Stdout.Fd() {
		t.Fatal("output observation hid terminal descriptor")
	}
}

func TestProgramPanicCleansBeforeBoundedFailure(t *testing.T) {
	cleaned := false
	err := runTerminalProgram(injectedTerminalProgram{run: func() error { panic("secret-token panic") }, cleanup: func() { cleaned = true }})
	var failure *api.Failure
	if !cleaned || !errors.As(err, &failure) || failure.Code != "terminal_unavailable" || strings.Contains(err.Error(), "secret-token") {
		t.Fatal("panic escaped before cleanup", err)
	}
}
