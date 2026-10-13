package taskimport

import (
	"crypto/sha256"
	"encoding/hex"
	"strings"
	"testing"
)

func TestJSONValidationPreservesInputCommitment(t *testing.T) {
	input := []byte(" {\n\"schema_version\":\"workstream.task_import.v1\",\"metadata\": {\"label\": null},\"tasks\":[{\"external_task_id\":\"É\",\"title\":\"Caption\",\"description\":\"日本語\",\"skill_tags\":[],\"difficulty\":null,\"estimated_time_minutes\": 30}]}\n")
	result, err := ValidateJSON(input)
	sum := sha256.Sum256(input)
	if err != nil || string(result.Bytes) != string(input) || result.ByteCount != len(input) || result.RowCount != 1 || result.SHA256 != "sha256:"+hex.EncodeToString(sum[:]) {
		t.Fatalf("valid original JSON bytes must remain unchanged: %#v, %v", result, err)
	}
	converted, err := ConvertCSV(strings.NewReader("external_task_id,title,description\na,T,D\n"), "")
	if err != nil {
		t.Fatal(err)
	}
	checked, err := ValidateJSON(converted.Bytes)
	if err != nil || checked.SHA256 != converted.SHA256 {
		t.Fatalf("converter output must pass canonical validation unchanged: %v", err)
	}
}

func TestAmbiguousAndNoncanonicalJSONRefused(t *testing.T) {
	base := `{"schema_version":"workstream.task_import.v1","tasks":[{"external_task_id":"a","title":"T","description":"D"}]}`
	for _, input := range []string{
		strings.Replace(base, `"title":"T"`, `"title":"T","title":"other"`, 1),
		strings.Replace(base, `"title":"T"`, `"title":null`, 1),
		strings.Replace(base, `"title":"T"`, `"title":"\ud800"`, 1),
		strings.Replace(base, `"title":"T"`, `"title":"\u0000"`, 1),
		strings.Replace(base, `"external_task_id":"a"`, `"external_task_id":" a"`, 1),
		strings.Replace(base, `"description":"D"`, `"description":"D","skill_tags":null`, 1),
		strings.Replace(base, `"description":"D"`, `"description":"D","skill_tags":[null]`, 1),
		strings.Replace(base, `"description":"D"`, `"description":"D","estimated_time_minutes":1.0`, 1),
		strings.Replace(base, `"description":"D"`, `"description":"D","estimated_time_minutes":true`, 1),
		strings.Replace(base, `"description":"D"`, `"description":"D","created_by":"actor"`, 1),
		strings.Replace(base, `"tasks":`, `"metadata":null,"tasks":`, 1),
		strings.Replace(base, `"tasks":`, `"metadata":{"label":""},"tasks":`, 1),
		base + `{}`,
	} {
		result, err := ValidateJSON([]byte(input))
		if err == nil || len(result.Bytes) != 0 {
			t.Fatalf("noncanonical JSON must produce no upload commitment: %s", input)
		}
	}
}
