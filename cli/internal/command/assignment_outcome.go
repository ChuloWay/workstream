package command

import (
	"fmt"
	"io"

	"github.com/Flow-Research/workstream/cli/internal/api"
)

func writeAssignmentOutcome(w io.Writer, outcome *api.AssignmentOutcome) error {
	if outcome == nil {
		return nil
	}
	reason := "revision deadline expired"
	if outcome.Status == "revision_exhausted" {
		reason = "attempts exhausted"
	}
	_, err := fmt.Fprintf(w, "Closed assignment %s: %s; no further submissions on this assignment.\n",
		safeText(outcome.AssignmentID), reason)
	return err
}
