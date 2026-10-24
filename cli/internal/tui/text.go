package tui

import (
	"fmt"
	"strings"
	"unicode"
)

// clean treats every external string as text, including reflected credentials.
// Application-owned labels/newlines are composed only after this boundary.
func (m *Model) clean(value string) string {
	if m.token != "" {
		value = strings.ReplaceAll(value, m.token, "[redacted]")
	}
	var out strings.Builder
	for _, r := range value {
		if !unicode.IsPrint(r) || unicode.Is(unicode.Cf, r) || r == '\u2028' || r == '\u2029' {
			fmt.Fprintf(&out, "\\u%04X", r)
		} else {
			out.WriteRune(r)
		}
	}
	return out.String()
}
