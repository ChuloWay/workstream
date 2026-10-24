package tui

import (
	"strings"
	"testing"
)

func TestExternalTextEscapesTerminalAndFormatControls(t *testing.T) {
	m := &Model{token: "private-bearer"}
	s := m.clean("private-bearer\x1b]52;c;YQ==\a\x1b]8;;https://evil\x1b\\\x1b[2J\u009b\u202e\u2028\u2029\n\t")
	for _, raw := range []string{"private-bearer", "\x1b", "\a", "\u009b", "\u202e", "\u2028", "\u2029", "\n", "\t"} {
		if strings.Contains(s, raw) {
			t.Fatalf("unescaped %q in %q", raw, s)
		}
	}
	if !strings.Contains(s, "[redacted]") || !strings.Contains(s, "\\u001B") {
		t.Fatal(s)
	}
}
