//! One syscall policy for untrusted Linux/x86_64 guest workloads.
//!
//! Call after trusted namespace setup and privilege dropping, with NoNewPrivs
//! already set. The trusted supervisor and launcher must remain unfiltered.

/// Install the existing closed guest policy on this thread and its descendants.
pub fn install_workload_filter() -> std::io::Result<()> {
    // x86_64 is the closed node platform. Deny namespace/capability escape
    // operations and guest management transports. clone3 returns ENOSYS so
    // libc can use the filtered clone path for ordinary language threads.
    const LOAD: u16 = 0x20;
    const EQUAL: u16 = 0x15;
    const RETURN: u16 = 0x06;
    const AND: u16 = 0x54;
    const ALLOW: u32 = 0x7fff0000;
    const ERROR: u32 = 0x00050000;
    fn op(code: u16, jt: u8, jf: u8, k: u32) -> libc::sock_filter {
        libc::sock_filter { code, jt, jf, k }
    }
    let mut filter = vec![
        op(LOAD, 0, 0, 4),
        op(EQUAL, 1, 0, 0xc000003e),
        op(RETURN, 0, 0, 0x80000000),
        op(LOAD, 0, 0, 0),
        op(0x35, 0, 1, 0x40000000),
        op(RETURN, 0, 0, ERROR | libc::ENOSYS as u32),
    ];
    for call in [
        libc::SYS_mount,
        libc::SYS_umount2,
        libc::SYS_pivot_root,
        libc::SYS_unshare,
        libc::SYS_setns,
        libc::SYS_bpf,
        libc::SYS_perf_event_open,
        libc::SYS_userfaultfd,
        libc::SYS_ptrace,
        libc::SYS_reboot,
        libc::SYS_kexec_load,
        libc::SYS_init_module,
        libc::SYS_finit_module,
        libc::SYS_delete_module,
        libc::SYS_open_by_handle_at,
        libc::SYS_keyctl,
        libc::SYS_add_key,
        libc::SYS_request_key,
        libc::SYS_mount_setattr,
        libc::SYS_fsopen,
        libc::SYS_fsmount,
        libc::SYS_move_mount,
        libc::SYS_open_tree,
        // io_uring can issue socket/connect operations without passing through
        // the socket syscall rule below. No management-transport bypass.
        libc::SYS_io_uring_setup,
        libc::SYS_io_uring_enter,
        libc::SYS_io_uring_register,
    ] {
        filter.extend([
            op(EQUAL, 0, 1, call as u32),
            op(RETURN, 0, 0, ERROR | libc::EPERM as u32),
        ]);
    }
    filter.extend([
        op(EQUAL, 0, 1, libc::SYS_clone3 as u32),
        op(RETURN, 0, 0, ERROR | libc::ENOSYS as u32),
        op(EQUAL, 0, 4, libc::SYS_clone as u32),
        op(LOAD, 0, 0, 16),
        op(
            AND,
            0,
            0,
            (libc::CLONE_NEWUSER
                | libc::CLONE_NEWNS
                | libc::CLONE_NEWCGROUP
                | libc::CLONE_NEWPID
                | libc::CLONE_NEWNET
                | libc::CLONE_NEWIPC
                | libc::CLONE_NEWUTS) as u32,
        ),
        op(EQUAL, 1, 0, 0),
        op(RETURN, 0, 0, ERROR | libc::EPERM as u32),
        op(LOAD, 0, 0, 0),
        op(EQUAL, 0, 5, libc::SYS_socket as u32),
        op(LOAD, 0, 0, 16),
        op(EQUAL, 3, 0, libc::AF_UNIX as u32),
        op(EQUAL, 2, 0, libc::AF_INET as u32),
        op(EQUAL, 1, 0, libc::AF_INET6 as u32),
        op(RETURN, 0, 0, ERROR | libc::EAFNOSUPPORT as u32),
        op(RETURN, 0, 0, ALLOW),
    ]);
    let program = libc::sock_fprog {
        len: filter.len() as u16,
        filter: filter.as_mut_ptr(),
    };
    if unsafe { libc::prctl(libc::PR_SET_SECCOMP, 2, &program) } == 0 {
        Ok(())
    } else {
        Err(std::io::Error::last_os_error())
    }
}

#[cfg(all(test, target_os = "linux", target_arch = "x86_64"))]
mod tests {
    use super::*;
    use std::os::unix::process::CommandExt;
    use std::process::{Command, Stdio};
    use std::time::{Duration, Instant};

    fn filter_count() -> usize {
        std::fs::read_to_string("/proc/thread-self/status")
            .unwrap()
            .lines()
            .find_map(|line| line.strip_prefix("Seccomp_filters:"))
            .unwrap()
            .trim()
            .parse()
            .unwrap()
    }

    #[test]
    fn workload_filter_blocks_management_and_preserves_threads_and_exec() {
        const CHILD: &str = "WORKSTREAM_TEST_WORKLOAD_FILTER";
        if std::env::var_os(CHILD).is_some() {
            assert_eq!(
                unsafe { libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) },
                0
            );
            let before = filter_count();
            install_workload_filter().unwrap();
            assert_eq!(
                filter_count(),
                before + 1,
                "workload filter was not installed"
            );
            assert_eq!(
                unsafe { libc::socket(libc::AF_VSOCK, libc::SOCK_STREAM, 0) },
                -1
            );
            assert_eq!(
                std::io::Error::last_os_error().raw_os_error(),
                Some(libc::EAFNOSUPPORT)
            );
            assert_eq!(
                unsafe { libc::syscall(libc::SYS_unshare, libc::CLONE_NEWUSER) },
                -1
            );
            assert_eq!(
                std::io::Error::last_os_error().raw_os_error(),
                Some(libc::EPERM)
            );
            assert_eq!(
                unsafe {
                    libc::syscall(
                        libc::SYS_io_uring_setup,
                        0,
                        std::ptr::null::<libc::c_void>(),
                    )
                },
                -1
            );
            assert_eq!(
                std::io::Error::last_os_error().raw_os_error(),
                Some(libc::EPERM)
            );
            assert_eq!(
                unsafe { libc::syscall(libc::SYS_clone3, std::ptr::null::<libc::c_void>(), 0) },
                -1
            );
            assert_eq!(
                std::io::Error::last_os_error().raw_os_error(),
                Some(libc::ENOSYS)
            );
            assert_eq!(std::thread::spawn(|| 42).join().unwrap(), 42);
            assert!(Command::new("/bin/sh")
                .args(["-c", "exit 0"])
                .status()
                .unwrap()
                .success());
            return;
        }
        let mut child = Command::new(std::env::current_exe().unwrap())
            .args(["--exact", "confinement::tests::workload_filter_blocks_management_and_preserves_threads_and_exec"])
            .env(CHILD, "1")
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .process_group(0)
            .spawn()
            .unwrap();
        let deadline = Instant::now() + Duration::from_secs(15);
        while child.try_wait().unwrap().is_none() {
            if Instant::now() >= deadline {
                unsafe { libc::kill(-(child.id() as i32), libc::SIGKILL) };
                child.wait().unwrap();
                panic!("isolated workload-filter regression exceeded deadline");
            }
            std::thread::sleep(Duration::from_millis(2));
        }
        let result = child.wait_with_output().unwrap();
        assert!(
            result.status.success(),
            "{}{}",
            String::from_utf8_lossy(&result.stdout),
            String::from_utf8_lossy(&result.stderr)
        );
    }
}
