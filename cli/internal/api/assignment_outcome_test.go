package api

import (
	"encoding/json"
	"testing"
)

func TestAssignmentOutcomeRejectsInconsistentClosure(t *testing.T) {
	valid := map[string]any{
		"assignment_id": "019b9ba2-4100-7000-8000-000000000001",
		"submission_id": "019b9ba2-4100-7000-8000-000000000002",
		"status":        "revision_exhausted", "status_reason": "revision_limit_reached",
		"closed_at": "2026-10-15T10:00:00Z", "next_action": "none",
	}
	raw, _ := json.Marshal(valid)
	if err := validateAssignmentOutcome(raw); err != nil {
		t.Fatal(err)
	}
	for _, changed := range []struct {
		key   string
		value any
	}{
		{"status_reason", "revision_deadline_expired"}, {"next_action", "submit"},
		{"assignment_id", "invalid"}, {"closed_at", nil}, {"status", "active"},
	} {
		altered := make(map[string]any)
		for k, v := range valid {
			altered[k] = v
		}
		altered[changed.key] = changed.value
		raw, _ := json.Marshal(altered)
		if validateAssignmentOutcome(raw) == nil {
			t.Errorf("accepted invalid %s", changed.key)
		}
	}
	valid["status"] = "revision_expired"
	valid["status_reason"] = "revision_deadline_expired"
	raw, _ = json.Marshal(valid)
	if err := validateAssignmentOutcome(raw); err != nil {
		t.Fatal(err)
	}
}
