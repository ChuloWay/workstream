//! Closed host side of the private Smol guest capability stream.

use super::*;
use crate::proxy_transport::{
    connect_private, read_frame as read_proxy_frame, validate_private_socket,
    write_frame as write_proxy_frame,
};
use std::process::{ChildStderr, ChildStdin, ChildStdout};
use workstream_checker_guest::{
    GuestIoChannel, GuestIoHeader, GuestJob, MaterialRoot, CAPACITY_EXIT_CODE,
    EXECUTION_FRAME_MAXIMUM, GUEST_IO_PROTOCOL, MAX_JOB_BYTES, MODEL_FRAME_MAXIMUM,
};

const HEADER_MAXIMUM: usize = 4096;
const PROCESS_ERROR_MAXIMUM: usize = 64 * 1024;

pub(super) struct MaterialSource {
    pub(super) manifest: MaterialRoot,
    pub(super) root: PathBuf,
}

pub(crate) struct ProjectMaterials<'a> {
    pub(crate) current: (&'a Path, &'a WorkspaceInventory),
    pub(crate) predecessor: Option<(&'a Path, &'a WorkspaceInventory)>,
}

#[derive(Clone, Default)]
pub(crate) struct ProjectCallbacks {
    pub(crate) model: Option<PathBuf>,
    pub(crate) execution: Option<PathBuf>,
}

pub(super) fn material_source(
    name: &str,
    root: &Path,
    expected: &WorkspaceInventory,
    config: &ServiceConfig,
) -> Result<MaterialSource, String> {
    let observed = inspect_workspace(root, config.sandbox_uid, config.sandbox_gid)?;
    if &observed != expected {
        return Err("material changed before Smol transfer".into());
    }
    Ok(MaterialSource {
        manifest: MaterialRoot {
            name: name.into(),
            directories: observed.directories,
            files: observed
                .files
                .into_iter()
                .map(|file| workstream_checker_guest::MaterialFile {
                    normalized_path: file.normalized_path,
                    byte_count: file.byte_count,
                    sha256: file.sha256,
                    executable: file.executable,
                })
                .collect(),
        },
        root: root.to_owned(),
    })
}

pub(super) fn validate_endpoints(endpoints: &ProjectCallbacks) -> Result<(), String> {
    for path in [endpoints.model.as_deref(), endpoints.execution.as_deref()]
        .into_iter()
        .flatten()
    {
        validate_private_socket(path)?;
    }
    Ok(())
}

pub(super) struct IoGuard<'a> {
    pub(super) deadline: Instant,
    pub(super) client: Option<&'a UnixStream>,
    pub(super) cancelled: &'a [&'a AtomicBool],
}

impl IoGuard<'_> {
    fn cancel(&self) {
        for cancelled in self.cancelled {
            cancelled.store(true, Ordering::Release);
        }
    }

    pub(super) fn check(&self) -> Result<(), String> {
        if self
            .cancelled
            .iter()
            .any(|cancelled| cancelled.load(Ordering::Acquire))
        {
            return Err("guest session cancelled".into());
        }
        if Instant::now() >= self.deadline {
            self.cancel();
            return Err("deadline_exceeded".into());
        }
        if self
            .client
            .is_some_and(|client| !client_is_connected(client))
        {
            self.cancel();
            return Err("guest client disconnected".into());
        }
        Ok(())
    }
}

pub(super) fn write_all(
    stream: &mut ChildStdin,
    bytes: &[u8],
    guard: &IoGuard<'_>,
) -> Result<(), String> {
    let mut offset = 0;
    while offset < bytes.len() {
        guard.check()?;
        match stream.write(&bytes[offset..]) {
            Ok(0) => return Err("guest input closed".into()),
            Ok(count) => offset += count,
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                thread::sleep(Duration::from_millis(2));
            }
            Err(_) => return Err("guest input failed".into()),
        }
    }
    Ok(())
}

pub(super) fn read_exact(
    stream: &mut ChildStdout,
    bytes: &mut [u8],
    guard: &IoGuard<'_>,
) -> Result<(), String> {
    let mut offset = 0;
    while offset < bytes.len() {
        guard.check()?;
        match stream.read(&mut bytes[offset..]) {
            Ok(0) => return Err("guest output closed".into()),
            Ok(count) => offset += count,
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                thread::sleep(Duration::from_millis(2));
            }
            Err(_) => return Err("guest output failed".into()),
        }
    }
    Ok(())
}

fn encode_header(header: &GuestIoHeader) -> Result<Vec<u8>, String> {
    let bytes = serde_json::to_vec(header).map_err(|_| "guest header encoding failed")?;
    if bytes.is_empty() || bytes.len() > HEADER_MAXIMUM {
        return Err("guest header unbounded".into());
    }
    Ok(bytes)
}

fn write_header(
    input: &mut ChildStdin,
    header: &GuestIoHeader,
    guard: &IoGuard<'_>,
) -> Result<(), String> {
    let bytes = encode_header(header)?;
    write_all(input, &(bytes.len() as u32).to_be_bytes(), guard)?;
    write_all(input, &bytes, guard)
}

fn read_header(output: &mut ChildStdout, guard: &IoGuard<'_>) -> Result<GuestIoHeader, String> {
    let mut length = [0_u8; 4];
    read_exact(output, &mut length, guard)?;
    let length = u32::from_be_bytes(length) as usize;
    if length == 0 || length > HEADER_MAXIMUM {
        return Err("guest header unbounded".into());
    }
    let mut bytes = vec![0_u8; length];
    read_exact(output, &mut bytes, guard)?;
    serde_json::from_slice(&bytes).map_err(|_| "guest header invalid".into())
}

pub(super) fn write_job(
    input: &mut ChildStdin,
    job: &GuestJob,
    materials: &[MaterialSource],
    guard: &IoGuard<'_>,
) -> Result<(), String> {
    let bytes = serde_json::to_vec(job).map_err(|_| "guest job invalid")?;
    if bytes.is_empty() || bytes.len() > MAX_JOB_BYTES {
        return Err("guest job too large".into());
    }
    write_all(input, &(bytes.len() as u32).to_be_bytes(), guard)?;
    write_all(input, &bytes, guard)?;
    for material in materials {
        for file in &material.manifest.files {
            let path = material.root.join(&file.normalized_path);
            let mut source = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(path)
                .map_err(|_| "material unavailable")?;
            let mut remaining = file.byte_count;
            let mut buffer = [0_u8; 65536];
            while remaining > 0 {
                let count = remaining.min(buffer.len() as u64) as usize;
                source
                    .read_exact(&mut buffer[..count])
                    .map_err(|_| "material transfer truncated")?;
                write_all(input, &buffer[..count], guard)?;
                remaining -= count as u64;
            }
        }
    }
    Ok(())
}

fn endpoint(endpoints: &ProjectCallbacks, channel: GuestIoChannel) -> Option<&Path> {
    match channel {
        GuestIoChannel::Model => endpoints.model.as_deref(),
        GuestIoChannel::Execution => endpoints.execution.as_deref(),
    }
}

fn channel_maximum(channel: GuestIoChannel) -> usize {
    match channel {
        GuestIoChannel::Model => MODEL_FRAME_MAXIMUM,
        GuestIoChannel::Execution => EXECUTION_FRAME_MAXIMUM,
    }
}

#[derive(Default)]
struct RelayConnections {
    model: Option<UnixStream>,
    execution: Option<UnixStream>,
}

impl RelayConnections {
    fn channel(&mut self, channel: GuestIoChannel) -> &mut Option<UnixStream> {
        match channel {
            GuestIoChannel::Model => &mut self.model,
            GuestIoChannel::Execution => &mut self.execution,
        }
    }
}

fn bridge(
    endpoints: &ProjectCallbacks,
    connections: &mut RelayConnections,
    channel: GuestIoChannel,
    request: &[u8],
    deadline: Instant,
    cancelled: &AtomicBool,
) -> Result<Vec<u8>, String> {
    let path = endpoint(endpoints, channel).ok_or("guest capability not entitled")?;
    validate_private_socket(path)?;
    let maximum = channel_maximum(channel);
    let relay = connections.channel(channel);
    if relay.is_none() {
        *relay = Some(connect_private(path, deadline, cancelled)?);
    }
    let relay = relay.as_mut().ok_or("guest capability unavailable")?;
    write_proxy_frame(relay, request, maximum, deadline, cancelled)?;
    read_proxy_frame(relay, maximum, deadline, cancelled)
}

fn read_process_errors(mut errors: ChildStderr) -> (Vec<u8>, bool) {
    let mut bytes = Vec::new();
    let mut exceeded = false;
    let mut buffer = [0_u8; 8192];
    loop {
        match errors.read(&mut buffer) {
            Ok(0) => break,
            Ok(count) if bytes.len().saturating_add(count) <= PROCESS_ERROR_MAXIMUM => {
                bytes.extend_from_slice(&buffer[..count]);
            }
            Ok(_) => exceeded = true,
            Err(error) if error.kind() == std::io::ErrorKind::Interrupted => continue,
            Err(_) => {
                exceeded = true;
                break;
            }
        }
    }
    (bytes, exceeded)
}

fn expected_guest_status(oom_kills: u64, output_exceeded: bool, exit_code: Option<i32>) -> i32 {
    if oom_kills > 0 {
        CAPACITY_EXIT_CODE
    } else if output_exceeded {
        125
    } else if exit_code == Some(0) {
        0
    } else {
        125
    }
}

#[allow(clippy::too_many_arguments)]
pub(super) fn run_project(
    mut child: Child,
    job: &GuestJob,
    materials: &[MaterialSource],
    endpoints: &ProjectCallbacks,
    deadline: Instant,
    maximum_output: usize,
    client: &UnixStream,
    cancelled: &AtomicBool,
) -> Result<BoundedCommandOutput, String> {
    let mut input = child.stdin.take().ok_or("guest input unavailable")?;
    let mut output = child.stdout.take().ok_or("guest output unavailable")?;
    let errors = child.stderr.take().ok_or("guest errors unavailable")?;
    set_nonblocking(&input)?;
    set_nonblocking(&output)?;
    let mut error_reader = Some(thread::spawn(move || read_process_errors(errors)));
    let cancellation = [cancelled];
    let guard = IoGuard {
        deadline,
        client: Some(client),
        cancelled: &cancellation,
    };
    let mut child_reaped = false;
    let result = (|| {
        write_job(&mut input, job, materials, &guard)?;
        let mut next_sequence = 1_u32;
        let mut relay_connections = RelayConnections::default();
        loop {
            match read_header(&mut output, &guard)? {
                GuestIoHeader::Request {
                    protocol_version,
                    sequence,
                    channel,
                    byte_count,
                } => {
                    let maximum = channel_maximum(channel);
                    let byte_count = byte_count as usize;
                    if protocol_version != GUEST_IO_PROTOCOL
                        || sequence != next_sequence
                        || byte_count == 0
                        || byte_count > maximum
                    {
                        return Err("guest capability request invalid".into());
                    }
                    next_sequence = next_sequence
                        .checked_add(1)
                        .ok_or("guest I/O sequence exhausted")?;
                    let mut request = vec![0_u8; byte_count];
                    read_exact(&mut output, &mut request, &guard)?;
                    let response = bridge(
                        endpoints,
                        &mut relay_connections,
                        channel,
                        &request,
                        deadline,
                        cancelled,
                    )?;
                    write_header(
                        &mut input,
                        &GuestIoHeader::Response {
                            protocol_version: GUEST_IO_PROTOCOL.into(),
                            sequence,
                            channel,
                            byte_count: response.len() as u32,
                        },
                        &guard,
                    )?;
                    write_all(&mut input, &response, &guard)?;
                }
                GuestIoHeader::Completed {
                    protocol_version,
                    exit_code,
                    signal,
                    oom_kills,
                    output_exceeded,
                    stdout_bytes,
                    stderr_bytes,
                } => {
                    let stdout_bytes = stdout_bytes as usize;
                    let stderr_bytes = stderr_bytes as usize;
                    if protocol_version != GUEST_IO_PROTOCOL
                        || stdout_bytes > maximum_output
                        || stderr_bytes > PROCESS_ERROR_MAXIMUM
                        || (output_exceeded && (stdout_bytes != 0 || stderr_bytes != 0))
                        || (exit_code.is_some() == signal.is_some())
                    {
                        return Err("guest completion invalid".into());
                    }
                    let mut stdout = vec![0_u8; stdout_bytes];
                    let mut stderr = vec![0_u8; stderr_bytes];
                    read_exact(&mut output, &mut stdout, &guard)?;
                    read_exact(&mut output, &mut stderr, &guard)?;
                    let status = reap_child(&mut child, deadline)?;
                    child_reaped = true;
                    if status.code()
                        != Some(expected_guest_status(oom_kills, output_exceeded, exit_code))
                    {
                        return Err("guest completion status differs".into());
                    }
                    let (process_errors, errors_exceeded) = error_reader
                        .take()
                        .ok_or("guest error reader unavailable")?
                        .join()
                        .map_err(|_| "guest error reader failed")?;
                    if errors_exceeded
                        || stderr.len().saturating_add(process_errors.len()) > PROCESS_ERROR_MAXIMUM
                    {
                        return Err("guest process errors unbounded".into());
                    }
                    stderr.extend_from_slice(&process_errors);
                    if output_exceeded && oom_kills == 0 {
                        return Err("invalid_output".into());
                    }
                    return Ok(BoundedCommandOutput {
                        status,
                        stdout,
                        _stderr: stderr,
                    });
                }
                GuestIoHeader::Response { .. } => {
                    return Err("unsolicited guest capability response".into())
                }
            }
        }
    })();
    if result.is_err() {
        cancelled.store(true, Ordering::Release);
    }
    if result.is_err() && !child_reaped {
        let _ = stop_command_group(&mut child, Instant::now() + SOCKET_IO_TIMEOUT);
    }
    // On failures the reader may still be draining process stderr; joining
    // after process-group stop proves no descriptor remains live.
    if result.is_err() {
        let (_, exceeded) = error_reader
            .take()
            .ok_or("guest error reader unavailable")?
            .join()
            .map_err(|_| "guest error reader failed")?;
        if exceeded {
            return Err("guest process errors unbounded".into());
        }
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::{DirBuilderExt, PermissionsExt};

    #[test]
    fn channel_limits_are_closed_and_distinct() {
        assert_eq!(channel_maximum(GuestIoChannel::Model), 1024 * 1024);
        assert_eq!(channel_maximum(GuestIoChannel::Execution), 4 * 1024 * 1024);
        assert!(endpoint(&ProjectCallbacks::default(), GuestIoChannel::Model).is_none());
        assert!(endpoint(&ProjectCallbacks::default(), GuestIoChannel::Execution).is_none());
    }

    #[test]
    fn headers_are_bounded_closed_protocol_values() {
        let bytes = encode_header(&GuestIoHeader::Request {
            protocol_version: GUEST_IO_PROTOCOL.into(),
            sequence: 1,
            channel: GuestIoChannel::Model,
            byte_count: 7,
        })
        .unwrap();
        assert!(bytes.len() < HEADER_MAXIMUM);
        let decoded: GuestIoHeader = serde_json::from_slice(&bytes).unwrap();
        assert!(matches!(
            decoded,
            GuestIoHeader::Request {
                sequence: 1,
                channel: GuestIoChannel::Model,
                byte_count: 7,
                ..
            }
        ));
    }

    #[test]
    fn trusted_completion_codes_distinguish_capacity_and_output_bounds() {
        assert_eq!(expected_guest_status(0, false, Some(0)), 0);
        assert_eq!(expected_guest_status(0, true, Some(0)), 125);
        assert_eq!(expected_guest_status(1, true, None), CAPACITY_EXIT_CODE);
    }

    #[test]
    fn guard_cancels_every_owner_on_terminal_deadline() {
        let first = AtomicBool::new(false);
        let second = AtomicBool::new(false);
        let cancellation = [&first, &second];
        let guard = IoGuard {
            deadline: Instant::now(),
            client: None,
            cancelled: &cancellation,
        };
        assert!(guard.check().is_err());
        assert!(first.load(Ordering::Acquire));
        assert!(second.load(Ordering::Acquire));
    }

    #[test]
    fn model_frames_reuse_the_single_entitled_relay_session() {
        let root = std::env::temp_dir().join(format!(
            "ws-smol-io-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::DirBuilder::new().mode(0o700).create(&root).unwrap();
        let socket = root.join("model.sock");
        let listener = UnixListener::bind(&socket).unwrap();
        fs::set_permissions(&socket, fs::Permissions::from_mode(0o600)).unwrap();
        let deadline = Instant::now() + Duration::from_secs(2);
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let cancelled = AtomicBool::new(false);
            assert_eq!(
                read_proxy_frame(&mut stream, 32, deadline, &cancelled).unwrap(),
                b"first"
            );
            write_proxy_frame(&mut stream, b"one", 32, deadline, &cancelled).unwrap();
            assert_eq!(
                read_proxy_frame(&mut stream, 32, deadline, &cancelled).unwrap(),
                b"second"
            );
            write_proxy_frame(&mut stream, b"two", 32, deadline, &cancelled).unwrap();
        });
        let endpoints = ProjectCallbacks {
            model: Some(socket.clone()),
            execution: None,
        };
        let cancelled = AtomicBool::new(false);
        let mut connections = RelayConnections::default();
        assert_eq!(
            bridge(
                &endpoints,
                &mut connections,
                GuestIoChannel::Model,
                b"first",
                deadline,
                &cancelled,
            )
            .unwrap(),
            b"one"
        );
        assert_eq!(
            bridge(
                &endpoints,
                &mut connections,
                GuestIoChannel::Model,
                b"second",
                deadline,
                &cancelled,
            )
            .unwrap(),
            b"two"
        );
        drop(connections);
        server.join().unwrap();
        fs::remove_file(socket).unwrap();
        fs::remove_dir(root).unwrap();
    }
}
