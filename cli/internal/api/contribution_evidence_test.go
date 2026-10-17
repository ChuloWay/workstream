package api

import "testing"

func TestAdvanceContributionTraversalBounds(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name               string
		page, total, items int
		continues, valid   bool
		expectedTotal      int
	}{
		{name: "empty selection", page: 0, valid: true},
		{name: "first full page", page: 0, items: 1000, continues: true, valid: true, expectedTotal: 1000},
		{name: "partial final page", page: 1, total: 1000, items: 1, valid: true, expectedTotal: 1001},
		{name: "exact maximum", page: 99, total: 99_000, items: 1000, valid: true, expectedTotal: 100_000},
		{name: "continuation beyond maximum pages", page: 99, total: 99_000, items: 1000, continues: true, expectedTotal: 99_000},
		{name: "page beyond maximum", page: 100, total: 100_000, expectedTotal: 100_000},
		{name: "record beyond maximum", page: 99, total: 100_000, items: 1, expectedTotal: 100_000},
		{name: "empty continuation page", page: 1, total: 1000, expectedTotal: 1000},
		{name: "short nonterminal page", page: 1, total: 1000, items: 999, continues: true, expectedTotal: 1000},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			actual, valid := advanceContributionTraversal(
				test.page, test.total, test.items, test.continues,
			)
			if valid != test.valid || actual != test.expectedTotal {
				t.Fatalf("advance = (%d, %t), want (%d, %t)", actual, valid, test.expectedTotal, test.valid)
			}
		})
	}
}
