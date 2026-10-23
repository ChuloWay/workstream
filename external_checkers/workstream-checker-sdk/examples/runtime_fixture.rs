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
    let result = completed_result(&request, Vec::new())?;
    std::io::stdout().write_all(&serde_json::to_vec(&result)?)?;
    Ok(())
}
