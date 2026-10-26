// Package download owns private staging and atomic no-overwrite publication.
package download

import (
	"crypto/rand"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"sync"
)

// Root is an opened, inode-bound destination directory.
type Root struct {
	root *os.Root
}

// OpenRoot opens an existing real directory and refuses a path swapped while
// it is being opened.
func OpenRoot(directory string) (*Root, error) {
	if directory == "" {
		return nil, errors.New("download directory must be an existing real directory")
	}
	directory = filepath.Clean(directory)
	checked, err := os.Lstat(directory)
	if err != nil || !checked.IsDir() || checked.Mode()&os.ModeSymlink != 0 {
		return nil, errors.New("download directory must be an existing real directory")
	}
	root, err := os.OpenRoot(directory)
	if err != nil {
		return nil, errors.New("cannot open download directory")
	}
	opened, err := root.Stat(".")
	if err != nil || !os.SameFile(checked, opened) {
		_ = root.Close()
		return nil, errors.New("download directory changed during open")
	}
	return &Root{root: root}, nil
}

func (r *Root) Close() error { return r.root.Close() }

// Stage creates a private temporary file for one final leaf name. Abort,
// Seal, and Publish are serialized so cancellation can safely race a writer.
type Stage struct {
	mu        sync.Mutex
	root      *Root
	file      *os.File
	temporary string
	final     string
	sealed    bool
	finished  bool
	published bool
}

func (r *Root) Stage(name string) (*Stage, error) {
	if name == "" || name == "." || filepath.Base(name) != name || strings.ContainsAny(name, "/\\\x00") {
		return nil, errors.New("invalid download target name")
	}
	if _, err := r.root.Lstat(name); !os.IsNotExist(err) {
		return nil, errors.New("download target already exists or is inaccessible")
	}
	temporary := ".workstream-download-" + rand.Text()
	file, err := createPrivateFile(r.root, temporary)
	if err != nil {
		return nil, errors.New("cannot create private download")
	}
	return &Stage{root: r, file: file, temporary: temporary, final: name}, nil
}

func (s *Stage) Write(value []byte) (int, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.finished || s.sealed || s.file == nil {
		return 0, errors.New("download stage is closed")
	}
	return s.file.Write(value)
}

// Seal persists and closes verified staged bytes without publishing them.
func (s *Stage) Seal() error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.finished {
		return errors.New("download stage was aborted")
	}
	if s.sealed {
		return nil
	}
	if err := s.file.Sync(); err != nil {
		return errors.New("cannot persist download")
	}
	if err := s.file.Close(); err != nil {
		return errors.New("cannot close download")
	}
	s.file = nil
	s.sealed = true
	return nil
}

// Publish exposes sealed bytes with a hard link, never replacing an existing
// file or following a target symlink.
func (s *Stage) Publish() error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.published {
		return nil
	}
	if s.finished || !s.sealed {
		return errors.New("download stage is not publishable")
	}
	if err := s.root.root.Link(s.temporary, s.final); err != nil {
		_ = s.root.root.Remove(s.temporary)
		s.finished = true
		return errors.New("cannot publish download without overwrite")
	}
	s.finished = true
	s.published = true
	// Once linked, publication succeeded. A private sibling cleanup failure
	// cannot be reported as a failed download because the final file exists.
	_ = s.root.root.Remove(s.temporary)
	return nil
}

// Abort is idempotent and cleans an unpublished stage. Closing the handle
// first also permits removal on Windows while a cancelled writer unwinds.
func (s *Stage) Abort() {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.finished {
		return
	}
	s.finished = true
	if s.file != nil {
		_ = s.file.Close()
		s.file = nil
	}
	_ = s.root.root.Remove(s.temporary)
}

var _ io.Writer = (*Stage)(nil)
