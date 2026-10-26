//go:build !windows

package download

import (
	"os"
	"testing"
)

func assertPrivateStage(t *testing.T, file *os.File) {
	t.Helper()
	info, err := file.Stat()
	if err != nil || info.Mode().Perm() != 0600 {
		t.Fatal("stage is not owner-only", info, err)
	}
}
