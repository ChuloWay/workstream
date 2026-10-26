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
	return escapeControls(value)
}

func escapeControls(value string) string {
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

// prose keeps author-supplied paragraph boundaries without treating any other
// external control character as terminal instructions. Redact before splitting
// so a bearer containing a line break cannot escape suppression.
func (m *Model) prose(value string) string {
	if m.token != "" {
		value = strings.ReplaceAll(value, m.token, "[redacted]")
	}
	value = strings.ReplaceAll(value, "\r\n", "\n")
	parts := strings.Split(value, "\n")
	for i := range parts {
		parts[i] = escapeControls(parts[i])
	}
	return strings.Join(parts, "\n")
}
