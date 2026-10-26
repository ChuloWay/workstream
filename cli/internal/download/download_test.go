package download

import (
	"os"
	"path/filepath"
	"runtime"
	"sync"
	"testing"
)

func TestStagePublishesPrivateFileWithoutOverwrite(t *testing.T) {
	directory := t.TempDir()
	root, err := OpenRoot(directory)
	if err != nil {
		t.Fatal(err)
	}
	defer root.Close()
	stage, err := root.Stage("guide.pdf")
	if err != nil {
		t.Fatal(err)
	}
	defer stage.Abort()
	if _, err := stage.Write([]byte("verified bytes")); err != nil {
		t.Fatal(err)
	}
	entries, err := os.ReadDir(directory)
	if err != nil || len(entries) != 1 || entries[0].Name() == "guide.pdf" {
		t.Fatal("bytes were not privately staged", entries, err)
	}
	info, err := entries[0].Info()
	if err != nil || info.Mode().Perm() != 0600 {
		t.Fatal("stage is not private", info, err)
	}
	if err := stage.Seal(); err != nil {
		t.Fatal(err)
	}
	if err := stage.Publish(); err != nil {
		t.Fatal(err)
	}
	if err := stage.Publish(); err != nil {
		t.Fatal("successful publication is not idempotent", err)
	}
	body, err := os.ReadFile(filepath.Join(directory, "guide.pdf"))
	if err != nil || string(body) != "verified bytes" {
		t.Fatal(string(body), err)
	}
	entries, _ = os.ReadDir(directory)
	if len(entries) != 1 || entries[0].Name() != "guide.pdf" {
		t.Fatal("private stage retained", entries)
	}
	stage.Abort()
}

func TestStageRefusesExistingFileAndSymlink(t *testing.T) {
	directory := t.TempDir()
	root, err := OpenRoot(directory)
	if err != nil {
		t.Fatal(err)
	}
	defer root.Close()
	if err := os.WriteFile(filepath.Join(directory, "existing"), []byte("untouched"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := root.Stage("existing"); err == nil {
		t.Fatal("existing file accepted")
	}
	if runtime.GOOS != "windows" {
		if err := os.Symlink(filepath.Join(directory, "existing"), filepath.Join(directory, "link")); err != nil {
			t.Fatal(err)
		}
		if _, err := root.Stage("link"); err == nil {
			t.Fatal("existing symlink accepted")
		}
	}
	if body, _ := os.ReadFile(filepath.Join(directory, "existing")); string(body) != "untouched" {
		t.Fatal("existing target changed")
	}
}

func TestOpenRootRejectsDirectorySymlink(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("ordinary test user cannot reliably create a directory symlink")
	}
	directory := t.TempDir()
	link := filepath.Join(t.TempDir(), "destination")
	if err := os.Symlink(directory, link); err != nil {
		t.Fatal(err)
	}
	if _, err := OpenRoot(link); err == nil {
		t.Fatal("directory symlink accepted")
	}
}

func TestAbortRacesWriterAndCleansWithoutResponseDelivery(t *testing.T) {
	directory := t.TempDir()
	root, err := OpenRoot(directory)
	if err != nil {
		t.Fatal(err)
	}
	defer root.Close()
	stage, err := root.Stage("never-published")
	if err != nil {
		t.Fatal(err)
	}
	started := make(chan struct{})
	var once sync.Once
	done := make(chan error, 1)
	go func() {
		for {
			once.Do(func() { close(started) })
			if _, err := stage.Write(make([]byte, 32*1024)); err != nil {
				done <- err
				return
			}
		}
	}()
	<-started
	stage.Abort()
	if err := <-done; err == nil {
		t.Fatal("aborted writer did not stop")
	}
	stage.Abort()
	entries, err := os.ReadDir(directory)
	if err != nil || len(entries) != 0 {
		t.Fatal("aborted stage retained bytes", entries, err)
	}
	if err := stage.Seal(); err == nil {
		t.Fatal("aborted stage sealed", err)
	}
}
