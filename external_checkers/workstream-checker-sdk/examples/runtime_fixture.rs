//! Native executable used by the opt-in Smol boundary proof, not a project rule.
use std::io::{Read, Write};
use workstream_checker_sdk::{completed_result, parse_request, MAX_REQUEST_BYTES};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut bytes = Vec::new();
    std::io::stdin()
        .take(MAX_REQUEST_BYTES as u64 + 1)
        .read_to_end(&mut bytes)?;
    let request = parse_request(&bytes)?;
    let status = std::fs::read_to_string("/proc/self/status")?;
    assert!(
        status
            .lines()
            .any(|line| line.starts_with("Uid:")
                && !line.split_whitespace().skip(1).any(|v| v == "0"))
    );
    assert!(std::fs::read_dir("/sys")?.next().is_none());
    if request.value["configuration"]["case"] == "io_uring" {
        // Denial must precede argument handling. If setup succeeds, a caller
        // can submit IORING_OP_SOCKET(AF_VSOCK) without socket(2) filtering.
        let mut parameters = [0u64; 15];
        fn denied(result: libc::c_long) {
            assert_eq!(result, -1);
            assert_eq!(
                std::io::Error::last_os_error().raw_os_error(),
                Some(libc::EPERM)
            );
        }
        unsafe {
            denied(libc::syscall(
                libc::SYS_io_uring_setup,
                2u32,
                parameters.as_mut_ptr(),
            ));
            denied(libc::syscall(
                libc::SYS_io_uring_enter,
                -1i32,
                0u32,
                0u32,
                0u32,
                0usize,
                0usize,
            ));
            denied(libc::syscall(
                libc::SYS_io_uring_register,
                -1i32,
                0u32,
                0usize,
                0u32,
            ));
        }
    }
    let result = completed_result(&request, Vec::new())?;
    std::io::stdout().write_all(&serde_json::to_vec(&result)?)?;
    Ok(())
}
