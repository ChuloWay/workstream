package api

import (
	"encoding/json"
	jsonv2 "encoding/json/v2"
	"math/big"
)

// CheckerModelPaidSlot identifies a retained effect across checker retries.
type CheckerModelPaidSlot struct {
	ProjectID           string   `json:"project_id"`
	AssignmentID        string   `json:"assignment_id"`
	SubmissionID        string   `json:"submission_id"`
	SubmissionVersion   *big.Int `json:"submission_version"`
	RequirementID       string   `json:"requirement_id"`
	RegistryEntryDigest string   `json:"registry_entry_digest"`
	ConfigurationSHA256 string   `json:"configuration_sha256"`
	ProfileID           string   `json:"profile_id"`
	ProfileVersion      *big.Int `json:"profile_version"`
	ProfileDigest       string   `json:"profile_digest"`
	SlotIndex           *big.Int `json:"slot_index"`
}

// CheckerModelRecoveryCandidate is a repair candidate, never dispatch authority.
type CheckerModelRecoveryCandidate struct {
	ParentAttemptID string               `json:"parent_attempt_id"`
	Slot            CheckerModelPaidSlot `json:"slot"`
	RegistryEntryID string               `json:"registry_entry_id"`
	TerminalDigest  string               `json:"terminal_digest"`
	RequestSHA256   string               `json:"request_sha256"`
}

func validCheckerModelRecoveryCandidates(raw json.RawMessage, item *CheckerRetrySourceItem) bool {
	var candidates []json.RawMessage
	if jsonv2.Unmarshal(raw, &candidates) != nil || candidates == nil || len(candidates) != len(item.ModelRecoveryCandidates) {
		return false
	}
	seen := map[[16]byte]bool{}
	for i, value := range candidates {
		candidate := &item.ModelRecoveryCandidates[i]
		fields, err := contextObject(value, candidate, []string{"parent_attempt_id", "slot", "registry_entry_id", "terminal_digest", "request_sha256"}, nil)
		if err != nil || !validUUID(candidate.RegistryEntryID) || !contextPolicyDigest.MatchString(candidate.TerminalDigest) || !contextPolicyDigest.MatchString(candidate.RequestSHA256) {
			return false
		}
		id, valid := uuidIdentity(candidate.ParentAttemptID)
		if !valid || seen[id] {
			return false
		}
		seen[id] = true
		slot := &candidate.Slot
		_, err = contextObject(fields["slot"], slot, []string{"project_id", "assignment_id", "submission_id", "submission_version", "requirement_id", "registry_entry_digest", "configuration_sha256", "profile_id", "profile_version", "profile_digest", "slot_index"}, nil)
		if err != nil || !sameUUID(slot.ProjectID, item.Source.ProjectID) || !sameUUID(slot.SubmissionID, item.Source.SubmissionID) ||
			!validUUID(slot.AssignmentID) || !validUUID(slot.ProfileID) || !boundedInteger(slot.SubmissionVersion, 1, 2_147_483_647) ||
			slot.SubmissionVersion.Cmp(item.Source.SubmissionVersion) != 0 || !boundedInteger(slot.ProfileVersion, 1, 2_147_483_647) ||
			!boundedInteger(slot.SlotIndex, 0, 0) || !postPolicyIdentifier.MatchString(slot.RequirementID) {
			return false
		}
		for _, digest := range []string{slot.RegistryEntryDigest, slot.ConfigurationSHA256, slot.ProfileDigest} {
			if !contextPolicyDigest.MatchString(digest) {
				return false
			}
		}
	}
	return true
}
