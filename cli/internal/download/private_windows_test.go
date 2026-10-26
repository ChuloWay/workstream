//go:build windows

package download

import (
	"os"
	"runtime"
	"testing"
	"unsafe"

	"golang.org/x/sys/windows"
)

func TestAtomicPrivateFileCreation(t *testing.T) {
	user, err := windows.GetCurrentProcessToken().GetTokenUser()
	if err != nil {
		t.Fatal(err)
	}
	descriptor, acl, err := currentUserDescriptor(user)
	if err != nil {
		t.Fatal(err)
	}
	if !descriptor.IsValid() {
		t.Fatal("creation descriptor is invalid")
	}
	control, _, err := descriptor.Control()
	if err != nil || control&windows.SE_SELF_RELATIVE != 0 || control&windows.SE_DACL_PRESENT == 0 ||
		control&windows.SE_DACL_PROTECTED == 0 || control&windows.SE_SACL_PRESENT != 0 {
		t.Fatal("creation descriptor has unexpected control flags", control, err)
	}
	assertCurrentUserDACL(t, descriptor, user)
	runtime.KeepAlive(acl)

	directory := t.TempDir()
	root, err := os.OpenRoot(directory)
	if err != nil {
		t.Fatal(err)
	}
	defer root.Close()
	const name = ".workstream-download-diagnostic"
	file, err := createPrivateFile(root, name)
	if err != nil {
		t.Fatalf("createPrivateFile raw Windows error: %T: %v", err, err)
	}
	defer root.Remove(name)
	defer file.Close()
	assertPrivateStage(t, file)
}

func assertPrivateStage(t *testing.T, file *os.File) {
	t.Helper()
	sd, err := windows.GetSecurityInfo(windows.Handle(file.Fd()), windows.SE_FILE_OBJECT, windows.DACL_SECURITY_INFORMATION)
	if err != nil {
		t.Fatal(err)
	}
	control, _, err := sd.Control()
	if err != nil || control&windows.SE_DACL_PRESENT == 0 || control&windows.SE_DACL_PROTECTED == 0 || control&windows.SE_SACL_PRESENT != 0 {
		t.Fatal("stage DACL inherits access", control, err)
	}
	user, err := windows.GetCurrentProcessToken().GetTokenUser()
	if err != nil {
		t.Fatal(err)
	}
	assertCurrentUserDACL(t, sd, user)
	runtime.KeepAlive(sd)
	runtime.KeepAlive(user)
}

func assertCurrentUserDACL(t *testing.T, descriptor *windows.SECURITY_DESCRIPTOR, user *windows.Tokenuser) {
	t.Helper()
	acl, _, err := descriptor.DACL()
	if err != nil || acl == nil || acl.AceCount != 1 {
		t.Fatal("descriptor does not have exactly one current-user ACE", acl, err)
	}
	var ace *windows.ACCESS_ALLOWED_ACE
	if err := windows.GetAce(acl, 0, &ace); err != nil {
		t.Fatal(err)
	}
	aceSID := (*windows.SID)(unsafe.Pointer(&ace.SidStart))
	if ace.Header.AceType != windows.ACCESS_ALLOWED_ACE_TYPE || ace.Header.AceFlags != 0 ||
		ace.Mask != fileAllAccess || !aceSID.Equals(user.User.Sid) {
		t.Fatal("DACL is not current-user full access", ace.Header, ace.Mask, aceSID)
	}
	runtime.KeepAlive(descriptor)
	runtime.KeepAlive(user)
}
