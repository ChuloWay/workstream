//! Static bootstrap for an untrusted image, invoked before its first instruction.
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, HashSet};
use std::ffi::CString;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::os::unix::net::{UnixListener, UnixStream};
use std::os::unix::process::CommandExt;
use std::path::{Component, Path, PathBuf};
use std::process::Command;
use std::sync::mpsc::{self, Sender, SyncSender};
use std::thread;
use std::time::Duration;
use workstream_checker_guest::{
    GuestCapabilities, GuestIoChannel, GuestIoHeader, GuestJob, GuestPurpose, MaterialRoot,
    CAPACITY_EXIT_CODE, EXECUTION_FRAME_MAXIMUM, EXECUTION_SOCKET, GUEST_IO_PROTOCOL, INPUT_ROOT,
    MAX_JOB_BYTES, MODEL_FRAME_MAXIMUM, MODEL_SOCKET, PREDECESSOR_ROOT,
};
use workstream_checker_sdk::parse_request;

mod trial;

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

fn c(value: &str) -> Result<CString> {
    Ok(CString::new(value)?)
}
fn syscall_ok(value: libc::c_int) -> Result<()> {
    if value == 0 {
        Ok(())
    } else {
        Err(std::io::Error::last_os_error().into())
    }
}
fn mount(source: &str, target: &str, kind: &str, flags: libc::c_ulong, data: &str) -> Result<()> {
    // All arguments are owned, terminated strings, valid for this syscall.
    syscall_ok(unsafe {
        libc::mount(
            c(source)?.as_ptr(),
            c(target)?.as_ptr(),
            c(kind)?.as_ptr(),
            flags,
            c(data)?.as_ptr().cast(),
        )
    })
}
fn private_mounts() -> Result<()> {
    syscall_ok(unsafe { libc::unshare(libc::CLONE_NEWNS) })?;
    mount("", "/", "", libc::MS_REC | libc::MS_PRIVATE, "")
}
fn cgroups(cpu: u64, memory: u64) -> Result<()> {
    let root = Path::new("/sys/fs/cgroup");
    fs::write(root.join("cgroup.subtree_control"), "+cpu +memory +pids")?;
    let group = root.join("workstream-checker");
    fs::create_dir(&group)?;
    fs::write(group.join("cpu.max"), format!("{} 100000", cpu * 100))?;
    fs::write(group.join("memory.max"), memory.to_string())?;
    disable_swap(&group, Path::new("/proc/meminfo"))?;
    fs::write(group.join("memory.oom.group"), "1")?;
    fs::write(
        group.join("pids.max"),
        (memory / (16 * 1024 * 1024)).clamp(16, 256).to_string(),
    )?;
    Ok(())
}
// Some fixed guest kernels omit the swap controller. In that case only a
// verified guest-wide absence of swap can replace the per-cgroup zero limit.
fn disable_swap(group: &Path, meminfo: &Path) -> Result<()> {
    let swap_limit = group.join("memory.swap.max");
    match fs::symlink_metadata(&swap_limit) {
        Ok(metadata) => {
            if !metadata.is_file() || metadata.file_type().is_symlink() {
                return Err("guest swap control invalid".into());
            }
            fs::write(&swap_limit, "0")?;
            if fs::read_to_string(&swap_limit)?.trim() != "0" {
                return Err("guest swap limit differs".into());
            }
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            let meminfo = fs::read_to_string(meminfo)?;
            let totals = meminfo
                .lines()
                .filter(|line| line.starts_with("SwapTotal:"))
                .collect::<Vec<_>>();
            if totals.len() != 1
                || totals[0].split_whitespace().collect::<Vec<_>>() != ["SwapTotal:", "0", "kB"]
            {
                return Err("unbounded guest swap".into());
            }
        }
        Err(error) => return Err(error.into()),
    }
    Ok(())
}

fn material_path_is_relative(value: &str) -> bool {
    // ART owns Unicode normalization and project archive limits. Bootstrap only
    // enforces filesystem containment; finding-path presentation rules differ.
    !value.is_empty()
        && !value.contains('\\')
        && !value.contains('\0')
        && value
            .split('/')
            .all(|part| !part.is_empty() && part != "." && part != "..")
        && Path::new(value)
            .components()
            .all(|part| matches!(part, Component::Normal(_)))
}

fn mount_directory(path: &Path) -> Result<()> {
    // No image code or other threads run before confinement. Refuse image-owned
    // symlinks (including dangling ones) instead of mounting through them.
    match fs::symlink_metadata(path) {
        Ok(metadata) if metadata.is_dir() => Ok(()),
        Ok(_) => Err("mount target is not a directory".into()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(fs::create_dir(path)?),
        Err(error) => Err(error.into()),
    }
}

pub(crate) struct StagedJob {
    request: File,
    roots: BTreeMap<String, PathBuf>,
}

impl StagedJob {
    #[allow(dead_code)] // Consumed by the separately owned trial guest module.
    pub(crate) fn root(&self, name: &str) -> Option<&Path> {
        self.roots.get(name).map(PathBuf::as_path)
    }
}

fn valid_root_name(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'_')
}

fn stage(job: &GuestJob, roots: &[MaterialRoot], input: &mut impl Read) -> Result<StagedJob> {
    // Mask any image-owned /work before handling untrusted paths. Only this
    // trusted process runs in the image until staging and confinement complete.
    mount_directory(Path::new("/work"))?;
    mount_directory(Path::new("/tmp"))?;
    // Stage on the VM's bounded ephemeral disk, so immutable input pages can
    // be reclaimed independently of the checker heap. Never put the submitted
    // tree in tmpfs or silently add its expanded size to the workload limit.
    let mut entropy = [0u8; 16];
    File::open("/dev/urandom")?.read_exact(&mut entropy)?;
    let suffix: String = entropy.iter().map(|byte| format!("{byte:02x}")).collect();
    let staging = format!("/.workstream-material-{suffix}");
    fs::create_dir(&staging)?;
    mount(&staging, "/work", "", libc::MS_BIND, "")?;
    fs::create_dir("/work/.materials")?;
    fs::set_permissions("/work/.materials", fs::Permissions::from_mode(0o700))?;
    let mut names = HashSet::new();
    let mut staged_roots = BTreeMap::new();
    for root in roots {
        if !valid_root_name(&root.name) || !names.insert(root.name.as_str()) {
            return Err("material root invalid".into());
        }
        let root_path = Path::new("/work/.materials").join(&root.name);
        fs::create_dir(&root_path)?;
        for directory in &root.directories {
            if !material_path_is_relative(directory) {
                return Err("unsafe directory".into());
            }
            fs::create_dir_all(root_path.join(directory))?;
        }
        for entry in &root.files {
            if !material_path_is_relative(&entry.normalized_path) {
                return Err("unsafe file".into());
            }
            let path = root_path.join(&entry.normalized_path);
            if let Some(parent) = path.parent() {
                fs::create_dir_all(parent)?;
            }
            let mut file = OpenOptions::new()
                .write(true)
                .create_new(true)
                .mode(if entry.executable { 0o555 } else { 0o444 })
                .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(&path)?;
            let mut remaining = entry.byte_count;
            let mut hash = Sha256::new();
            let mut bytes = [0u8; 65536];
            while remaining > 0 {
                let size = remaining.min(bytes.len() as u64) as usize;
                input.read_exact(&mut bytes[..size])?;
                hash.update(&bytes[..size]);
                file.write_all(&bytes[..size])?;
                remaining -= size as u64;
            }
            if format!("sha256:{:x}", hash.finalize()) != entry.sha256 {
                return Err("material hash differs".into());
            }
        }
        staged_roots.insert(root.name.clone(), root_path);
    }
    let request = "/work/request.json";
    fs::write(request, serde_json::to_vec(&job.request)?)?;
    fs::set_permissions(request, fs::Permissions::from_mode(0o444))?;
    Ok(StagedJob {
        request: File::open(request)?,
        roots: staged_roots,
    })
}

fn bind_material_root(staged: &StagedJob, name: &str, destination: &str) -> Result<()> {
    let source = staged.roots.get(name).ok_or("material root missing")?;
    let destination = Path::new(destination);
    if let Some(parent) = destination.parent() {
        fs::create_dir_all(parent)?;
    }
    mount_directory(destination)?;
    mount(
        source.to_str().ok_or("material path invalid")?,
        destination.to_str().ok_or("material path invalid")?,
        "",
        libc::MS_BIND,
        "",
    )
}

fn bind_project_materials(staged: &StagedJob) -> Result<()> {
    if !valid_project_material_roots(staged.roots.keys().map(String::as_str)) {
        return Err("project material roots invalid".into());
    }
    bind_material_root(staged, "current", INPUT_ROOT)?;
    if staged.roots.len() == 2 {
        bind_material_root(staged, "predecessor", PREDECESSOR_ROOT)?;
    }
    Ok(())
}

fn valid_project_material_roots<'a>(names: impl IntoIterator<Item = &'a str>) -> bool {
    let names: Vec<_> = names.into_iter().collect();
    names == ["current"] || names == ["current", "predecessor"]
}

fn create_capability_socket(path: &str, uid: u32, gid: u32) -> Result<UnixListener> {
    let listener = UnixListener::bind(path)?;
    fs::set_permissions(path, fs::Permissions::from_mode(0o600))?;
    syscall_ok(unsafe { libc::chown(c(path)?.as_ptr(), uid, gid) })?;
    listener.set_nonblocking(true)?;
    Ok(listener)
}

fn write_guest_header(header: &GuestIoHeader) -> Result<()> {
    let bytes = serde_json::to_vec(header)?;
    if bytes.is_empty() || bytes.len() > 4096 {
        return Err("guest I/O header invalid".into());
    }
    let mut output = std::io::stdout().lock();
    output.write_all(&(bytes.len() as u32).to_be_bytes())?;
    output.write_all(&bytes)?;
    output.flush()?;
    Ok(())
}

fn read_guest_header(input: &mut File) -> Result<GuestIoHeader> {
    let mut length = [0_u8; 4];
    input.read_exact(&mut length)?;
    let length = u32::from_be_bytes(length) as usize;
    if length == 0 || length > 4096 {
        return Err("guest I/O header invalid".into());
    }
    let mut bytes = vec![0_u8; length];
    input.read_exact(&mut bytes)?;
    Ok(serde_json::from_slice(&bytes)?)
}

fn read_local_frame(stream: &mut UnixStream, maximum: usize) -> Result<Option<Vec<u8>>> {
    let mut length = [0_u8; 4];
    let mut offset = 0;
    while offset < length.len() {
        match stream.read(&mut length[offset..]) {
            Ok(0) if offset == 0 => return Ok(None),
            Ok(0) => return Err("guest capability frame truncated".into()),
            Ok(count) => offset += count,
            Err(error) if error.kind() == std::io::ErrorKind::Interrupted => continue,
            Err(error) => return Err(error.into()),
        }
    }
    let length = u32::from_be_bytes(length) as usize;
    if length == 0 || length > maximum {
        return Err("guest capability frame unbounded".into());
    }
    let mut bytes = vec![0_u8; length];
    stream.read_exact(&mut bytes)?;
    Ok(Some(bytes))
}

fn write_local_frame(stream: &mut UnixStream, bytes: &[u8], maximum: usize) -> Result<()> {
    if bytes.is_empty() || bytes.len() > maximum {
        return Err("guest capability frame unbounded".into());
    }
    stream.write_all(&(bytes.len() as u32).to_be_bytes())?;
    stream.write_all(bytes)?;
    Ok(())
}

struct CapabilityExchange {
    channel: GuestIoChannel,
    request: Vec<u8>,
    response: SyncSender<std::result::Result<Vec<u8>, String>>,
}

fn serve_capability_session(
    mut stream: UnixStream,
    channel: GuestIoChannel,
    exchanges: Sender<CapabilityExchange>,
) -> Result<()> {
    let maximum = match channel {
        GuestIoChannel::Model => MODEL_FRAME_MAXIMUM,
        GuestIoChannel::Execution => EXECUTION_FRAME_MAXIMUM,
    };
    while let Some(request) = read_local_frame(&mut stream, maximum)? {
        let (response, receiver) = mpsc::sync_channel(0);
        exchanges.send(CapabilityExchange {
            channel,
            request,
            response,
        })?;
        let response = receiver
            .recv()?
            .map_err(|error| -> Box<dyn std::error::Error> { error.into() })?;
        write_local_frame(&mut stream, &response, maximum)?;
    }
    Ok(())
}

fn accept_capability_session(
    listener: Option<&UnixListener>,
    channel: GuestIoChannel,
    accepted: &mut bool,
    exchanges: &Sender<CapabilityExchange>,
    sessions: &mut Vec<thread::JoinHandle<bool>>,
) -> Result<bool> {
    let Some(listener) = listener else {
        return Ok(false);
    };
    match listener.accept() {
        Ok((stream, _)) => {
            if *accepted {
                return Err("guest capability opened more than one session".into());
            }
            *accepted = true;
            let exchanges = exchanges.clone();
            sessions.push(thread::spawn(move || {
                serve_capability_session(stream, channel, exchanges).is_ok()
            }));
            Ok(true)
        }
        Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => Ok(false),
        Err(error) => Err(error.into()),
    }
}

fn forward_capability(
    input: &mut File,
    channel: GuestIoChannel,
    sequence: &mut u32,
    request: &[u8],
) -> Result<Vec<u8>> {
    let maximum = match channel {
        GuestIoChannel::Model => MODEL_FRAME_MAXIMUM,
        GuestIoChannel::Execution => EXECUTION_FRAME_MAXIMUM,
    };
    *sequence = sequence
        .checked_add(1)
        .ok_or("guest I/O sequence exhausted")?;
    write_guest_header(&GuestIoHeader::Request {
        protocol_version: GUEST_IO_PROTOCOL.into(),
        sequence: *sequence,
        channel,
        byte_count: request.len() as u32,
    })?;
    std::io::stdout().write_all(request)?;
    std::io::stdout().flush()?;
    let response = read_guest_header(input)?;
    let byte_count = match response {
        GuestIoHeader::Response {
            protocol_version,
            sequence: observed_sequence,
            channel: observed_channel,
            byte_count,
        } if protocol_version == GUEST_IO_PROTOCOL
            && observed_sequence == *sequence
            && observed_channel == channel =>
        {
            byte_count as usize
        }
        _ => return Err("guest capability response invalid".into()),
    };
    if byte_count == 0 || byte_count > maximum {
        return Err("guest capability response unbounded".into());
    }
    let mut bytes = vec![0_u8; byte_count];
    input.read_exact(&mut bytes)?;
    Ok(bytes)
}

fn read_bounded(mut stream: UnixStream, maximum: usize) -> (Vec<u8>, bool) {
    let mut output = Vec::new();
    let mut exceeded = false;
    let mut buffer = [0_u8; 8192];
    loop {
        match stream.read(&mut buffer) {
            Ok(0) => break,
            Ok(count) => {
                if output.len().saturating_add(count) <= maximum {
                    output.extend_from_slice(&buffer[..count]);
                } else {
                    exceeded = true;
                }
            }
            Err(error) if error.kind() == std::io::ErrorKind::Interrupted => continue,
            Err(_) => {
                exceeded = true;
                break;
            }
        }
    }
    (output, exceeded)
}

fn socket_pair() -> Result<(UnixStream, UnixStream)> {
    Ok(UnixStream::pair()?)
}
fn confined_devices() -> Result<()> {
    mount(
        "tmpfs",
        "/dev",
        "tmpfs",
        libc::MS_NOSUID | libc::MS_NOEXEC,
        "size=65536,mode=0755",
    )?;
    for (name, minor) in [
        ("null", 3),
        ("zero", 5),
        ("full", 7),
        ("random", 8),
        ("urandom", 9),
    ] {
        syscall_ok(unsafe {
            libc::mknod(
                c(&format!("/dev/{name}"))?.as_ptr(),
                libc::S_IFCHR | 0o666,
                libc::makedev(1, minor),
            )
        })?;
    }
    for (name, target) in [
        ("fd", "/proc/self/fd"),
        ("stdin", "/proc/self/fd/0"),
        ("stdout", "/proc/self/fd/1"),
        ("stderr", "/proc/self/fd/2"),
    ] {
        std::os::unix::fs::symlink(target, format!("/dev/{name}"))?;
    }
    Ok(())
}

fn syscall_filter() -> Result<()> {
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
    syscall_ok(unsafe { libc::prctl(libc::PR_SET_SECCOMP, 2, &program) })
}

fn readonly_filesystem() -> Result<()> {
    // mount_setattr recursively freezes every existing mount, including image
    // overlays and material. Then install the sole writable, bounded scratch.
    #[repr(C)]
    struct Attr {
        set: u64,
        clear: u64,
        propagation: u64,
        userns: u64,
    }
    let attr = Attr {
        set: 1 | 2 | 4,
        clear: 0,
        propagation: 0,
        userns: 0,
    }; // RDONLY,NOSUID,NODEV: image-owned device nodes must never be usable.
    let result = unsafe {
        libc::syscall(
            libc::SYS_mount_setattr,
            libc::AT_FDCWD,
            c("/")?.as_ptr(),
            0x8000u32,
            &attr,
            std::mem::size_of::<Attr>(),
        )
    };
    if result != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    // Only the trusted, freshly constructed /dev whitelist may contain usable
    // device nodes. Keep its read-only and nosuid attributes in place.
    let devices = Attr {
        set: 0,
        clear: 4,
        propagation: 0,
        userns: 0,
    };
    let result = unsafe {
        libc::syscall(
            libc::SYS_mount_setattr,
            libc::AT_FDCWD,
            c("/dev")?.as_ptr(),
            0u32,
            &devices,
            std::mem::size_of::<Attr>(),
        )
    };
    if result != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    mount(
        "tmpfs",
        "/tmp",
        "tmpfs",
        libc::MS_NOSUID | libc::MS_NODEV | libc::MS_NOEXEC,
        "size=16777216,mode=1777",
    )?;
    // Hide the management filesystem, cgroup controls and agent storage. Mounts
    // are private, so the supervisor outside this namespace remains functional.
    for target in ["/sys", "/storage", "/workspace", "/run"] {
        if Path::new(target).is_dir() {
            mount(
                "tmpfs",
                target,
                "tmpfs",
                libc::MS_RDONLY | libc::MS_NOSUID | libc::MS_NODEV | libc::MS_NOEXEC,
                "size=4096,mode=0555",
            )?;
        }
    }
    Ok(())
}
fn drop_privileges(uid: u32, gid: u32) -> Result<()> {
    if uid == 0 || gid == 0 {
        return Err("root checker forbidden".into());
    }
    // Drop the bounding set while privileged, then supplementary groups and IDs.
    for capability in 0..=40 {
        syscall_ok(unsafe { libc::prctl(libc::PR_CAPBSET_DROP, capability, 0, 0, 0) })?;
    }
    syscall_ok(unsafe { libc::setgroups(0, std::ptr::null()) })?;
    syscall_ok(unsafe { libc::setresgid(gid, gid, gid) })?;
    syscall_ok(unsafe { libc::setresuid(uid, uid, uid) })?;
    syscall_ok(unsafe { libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) })?;
    Ok(())
}
fn supervised_exit(status: i32, oom_kills: u64) -> i32 {
    if oom_kills > 0 {
        CAPACITY_EXIT_CODE
    } else if libc::WIFEXITED(status) && libc::WEXITSTATUS(status) == 0 {
        0
    } else {
        125
    }
}

fn finish_workload_cgroup() -> Result<u64> {
    let group = Path::new("/sys/fs/cgroup/workstream-checker");
    if group.join("cgroup.kill").exists() {
        fs::write(group.join("cgroup.kill"), "1")?;
    }
    for _ in 0..5000 {
        let events = fs::read_to_string(group.join("cgroup.events"))?;
        if events.lines().any(|line| line == "populated 0") {
            let memory = fs::read_to_string(group.join("memory.events"))?;
            return Ok(memory
                .lines()
                .find_map(|line| line.strip_prefix("oom_kill "))
                .ok_or("memory OOM evidence missing")?
                .parse::<u64>()?);
        }
        thread::sleep(Duration::from_millis(2));
    }
    Err("workload descendants did not stop".into())
}

fn run_project(
    job: GuestJob,
    capabilities: GuestCapabilities,
    staged: StagedJob,
    mut input: File,
    cpu: u64,
    memory: u64,
    maximum_output_bytes: usize,
) -> Result<()> {
    bind_project_materials(&staged)?;
    let model = capabilities
        .model
        .then(|| create_capability_socket(MODEL_SOCKET, job.uid, job.gid))
        .transpose()?;
    let execution = capabilities
        .execution
        .then(|| create_capability_socket(EXECUTION_SOCKET, job.uid, job.gid))
        .transpose()?;
    let (stdout_parent, stdout_child) = socket_pair()?;
    let (stderr_parent, stderr_child) = socket_pair()?;
    cgroups(cpu, memory).map_err(|error| format!("cgroup: {error}"))?;
    // The supervisor retains the trusted stream and capability listeners. The
    // workload receives separate output pipes, so it cannot forge mux frames.
    let child = unsafe { libc::fork() };
    if child < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    if child == 0 {
        drop(stdout_parent);
        drop(stderr_parent);
        drop(model);
        drop(execution);
        drop(input);
        private_mounts().map_err(|error| format!("workload mount namespace: {error}"))?;
        fs::write(
            "/sys/fs/cgroup/workstream-checker/cgroup.procs",
            std::process::id().to_string(),
        )?;
        confined_devices().map_err(|error| format!("devices: {error}"))?;
        readonly_filesystem().map_err(|error| format!("filesystem: {error}"))?;
        drop_privileges(job.uid, job.gid).map_err(|error| format!("privileges: {error}"))?;
        // SAFETY: both streams are live child-owned descriptors and dup2
        // atomically replaces the conventional output descriptors.
        if unsafe { libc::dup2(stdout_child.as_raw_fd(), 1) } < 0
            || unsafe { libc::dup2(stderr_child.as_raw_fd(), 2) } < 0
        {
            return Err(std::io::Error::last_os_error().into());
        }
        drop(stdout_child);
        drop(stderr_child);
        syscall_filter().map_err(|error| format!("syscall policy: {error}"))?;
        let mut command = Command::new(&job.command[0]);
        command
            .args(&job.command[1..])
            .env_clear()
            .stdin(staged.request);
        for entry in &job.environment {
            let (key, value) = entry.split_once('=').ok_or("invalid image environment")?;
            command.env(key, value);
        }
        command.current_dir(if job.working_directory.is_empty() {
            "/"
        } else {
            &job.working_directory
        });
        return Err(command.exec().into());
    }
    drop(stdout_child);
    drop(stderr_child);
    let stdout_reader = thread::spawn(move || read_bounded(stdout_parent, maximum_output_bytes));
    let stderr_reader = thread::spawn(move || read_bounded(stderr_parent, 64 * 1024));
    let (exchange_sender, exchange_receiver) = mpsc::channel::<CapabilityExchange>();
    let mut sessions = Vec::new();
    let mut model_accepted = false;
    let mut execution_accepted = false;
    let mut sequence = 0_u32;
    let mut status = 0_i32;
    loop {
        let waited = unsafe { libc::waitpid(child, &mut status, libc::WNOHANG) };
        if waited == child {
            break;
        }
        if waited < 0 && std::io::Error::last_os_error().kind() != std::io::ErrorKind::Interrupted {
            return Err(std::io::Error::last_os_error().into());
        }
        let mut handled = false;
        handled |= accept_capability_session(
            model.as_ref(),
            GuestIoChannel::Model,
            &mut model_accepted,
            &exchange_sender,
            &mut sessions,
        )?;
        handled |= accept_capability_session(
            execution.as_ref(),
            GuestIoChannel::Execution,
            &mut execution_accepted,
            &exchange_sender,
            &mut sessions,
        )?;
        match exchange_receiver.try_recv() {
            Ok(exchange) => {
                handled = true;
                let response = match forward_capability(
                    &mut input,
                    exchange.channel,
                    &mut sequence,
                    &exchange.request,
                ) {
                    Ok(response) => response,
                    Err(error) => {
                        let message = error.to_string();
                        let _ = exchange.response.send(Err(message));
                        let _ = fs::write("/sys/fs/cgroup/workstream-checker/cgroup.kill", "1");
                        let _ = unsafe { libc::waitpid(child, &mut status, 0) };
                        return Err(error);
                    }
                };
                exchange
                    .response
                    .send(Ok(response))
                    .map_err(|_| "guest capability client disconnected")?;
            }
            Err(mpsc::TryRecvError::Empty) => {}
            Err(mpsc::TryRecvError::Disconnected) => {
                return Err("guest capability workers unavailable".into())
            }
        }
        let mut index = 0;
        while index < sessions.len() {
            if sessions[index].is_finished() {
                let session = sessions.swap_remove(index);
                if !matches!(session.join(), Ok(true)) {
                    let _ = fs::write("/sys/fs/cgroup/workstream-checker/cgroup.kill", "1");
                    let _ = unsafe { libc::waitpid(child, &mut status, 0) };
                    return Err("guest capability session failed".into());
                }
            } else {
                index += 1;
            }
        }
        if !handled {
            thread::sleep(Duration::from_millis(2));
        }
    }
    drop(model);
    drop(execution);
    let oom_kills = finish_workload_cgroup()?;
    drop(exchange_receiver);
    drop(exchange_sender);
    for session in sessions {
        if !matches!(session.join(), Ok(true)) {
            return Err("guest capability session failed".into());
        }
    }
    let (stdout, stdout_exceeded) = stdout_reader
        .join()
        .map_err(|_| "workload stdout reader failed")?;
    let (stderr, stderr_exceeded) = stderr_reader
        .join()
        .map_err(|_| "workload stderr reader failed")?;
    let output_exceeded = stdout_exceeded || stderr_exceeded;
    let (stdout, stderr) = if output_exceeded {
        (Vec::new(), Vec::new())
    } else {
        (stdout, stderr)
    };
    let exit_code = libc::WIFEXITED(status).then(|| libc::WEXITSTATUS(status));
    let signal = libc::WIFSIGNALED(status).then(|| libc::WTERMSIG(status));
    write_guest_header(&GuestIoHeader::Completed {
        protocol_version: GUEST_IO_PROTOCOL.into(),
        exit_code,
        signal,
        oom_kills,
        output_exceeded,
        stdout_bytes: stdout.len() as u32,
        stderr_bytes: stderr.len() as u32,
    })?;
    let mut output = std::io::stdout().lock();
    output.write_all(&stdout)?;
    output.write_all(&stderr)?;
    output.flush()?;
    std::process::exit(if output_exceeded && oom_kills == 0 {
        125
    } else {
        supervised_exit(status, oom_kills)
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn mount_targets_reject_image_symlinks_and_non_directories() {
        let root = std::env::temp_dir().join(format!("ws-guest-mounts-{}", std::process::id()));
        fs::create_dir(&root).unwrap();
        let target = root.join("directory");
        mount_directory(&target).unwrap();
        mount_directory(&target).unwrap();
        let link = root.join("link");
        std::os::unix::fs::symlink(&target, &link).unwrap();
        assert!(mount_directory(&link).is_err());
        fs::remove_dir(&target).unwrap();
        assert!(mount_directory(&link).is_err());
        fs::write(&target, b"image file").unwrap();
        assert!(mount_directory(&target).is_err());
        assert_eq!(fs::read(&target).unwrap(), b"image file");
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn material_containment_does_not_apply_finding_presentation_limits() {
        assert!(material_path_is_relative(&format!(
            "folder/{}",
            "x".repeat(1001)
        )));
        assert!(material_path_is_relative("folder/a\u{200b}b"));
        for path in [
            "/absolute",
            "../outside",
            "a/../outside",
            "a/./b",
            "a//b",
            "a\\b",
        ] {
            assert!(!material_path_is_relative(path));
        }
    }
    #[test]
    fn checker_exit_codes_cannot_forge_trusted_oom_classification() {
        assert_eq!(supervised_exit(CAPACITY_EXIT_CODE << 8, 0), 125);
        assert_eq!(supervised_exit(libc::SIGKILL, 0), 125);
        assert_eq!(supervised_exit(libc::SIGKILL, 1), CAPACITY_EXIT_CODE);
        assert_eq!(supervised_exit(0, 0), 0);
    }

    #[test]
    fn project_material_topology_is_closed() {
        assert!(valid_project_material_roots(["current"]));
        assert!(valid_project_material_roots(["current", "predecessor"]));
        assert!(!valid_project_material_roots([]));
        assert!(!valid_project_material_roots(["predecessor"]));
        assert!(!valid_project_material_roots(["current", "other"]));
        assert!(!valid_project_material_roots([
            "current",
            "predecessor",
            "other"
        ]));
    }

    #[test]
    fn capability_session_distinguishes_clean_eof_from_truncated_frame() {
        let (mut reader, writer) = UnixStream::pair().unwrap();
        drop(writer);
        assert!(read_local_frame(&mut reader, 16).unwrap().is_none());

        let (mut reader, mut writer) = UnixStream::pair().unwrap();
        writer.write_all(&[0, 0]).unwrap();
        writer.shutdown(std::net::Shutdown::Write).unwrap();
        assert!(read_local_frame(&mut reader, 16).is_err());
    }

    #[test]
    fn persistent_model_session_does_not_block_execution_or_second_model_call() {
        let unique = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "ws-guest-capabilities-{}-{unique}",
            std::process::id()
        ));
        fs::create_dir(&root).unwrap();
        let model_listener = UnixListener::bind(root.join("model.sock")).unwrap();
        let execution_listener = UnixListener::bind(root.join("execution.sock")).unwrap();
        model_listener.set_nonblocking(true).unwrap();
        execution_listener.set_nonblocking(true).unwrap();
        let mut model_client = UnixStream::connect(root.join("model.sock")).unwrap();
        let mut execution_client = UnixStream::connect(root.join("execution.sock")).unwrap();
        let (sender, receiver) = mpsc::channel();
        let mut sessions = Vec::new();
        let mut model_accepted = false;
        let mut execution_accepted = false;
        assert!(accept_capability_session(
            Some(&model_listener),
            GuestIoChannel::Model,
            &mut model_accepted,
            &sender,
            &mut sessions,
        )
        .unwrap());
        assert!(accept_capability_session(
            Some(&execution_listener),
            GuestIoChannel::Execution,
            &mut execution_accepted,
            &sender,
            &mut sessions,
        )
        .unwrap());

        let exchange = |client: &mut UnixStream,
                        expected_channel: GuestIoChannel,
                        request: &[u8],
                        response: &[u8]| {
            write_local_frame(client, request, 1024).unwrap();
            let exchange = receiver.recv_timeout(Duration::from_secs(1)).unwrap();
            assert_eq!(exchange.channel, expected_channel);
            assert_eq!(exchange.request, request);
            exchange.response.send(Ok(response.to_vec())).unwrap();
            assert_eq!(read_local_frame(client, 1024).unwrap().unwrap(), response);
        };
        exchange(
            &mut model_client,
            GuestIoChannel::Model,
            b"model-one",
            b"model-one-response",
        );
        exchange(
            &mut execution_client,
            GuestIoChannel::Execution,
            b"execute",
            b"execution-response",
        );
        exchange(
            &mut model_client,
            GuestIoChannel::Model,
            b"model-two",
            b"model-two-response",
        );

        drop(model_client);
        drop(execution_client);
        drop(sender);
        assert!(sessions.into_iter().all(|session| session.join().unwrap()));
        fs::remove_dir_all(root).unwrap();
    }
}

fn main() {
    if let Err(error) = run() {
        eprintln!("workstream guest bootstrap failed: {error}");
        std::process::exit(125);
    }
}
fn run() -> Result<()> {
    // Read exactly the bootstrap bytes without userspace read-ahead: trusted
    // intake keeps the remaining command stream as its stdin after exec.
    let descriptor = unsafe { libc::dup(0) };
    if descriptor < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    let mut input = unsafe { File::from_raw_fd(descriptor) };
    let mut length = [0u8; 4];
    input.read_exact(&mut length)?;
    let length = u32::from_be_bytes(length) as usize;
    if length == 0 || length > MAX_JOB_BYTES {
        return Err("job size invalid".into());
    }
    let mut bytes = vec![0; length];
    input.read_exact(&mut bytes)?;
    let job: GuestJob = serde_json::from_slice(&bytes)?;
    let purpose = job.purpose.clone();
    let (cpu, memory, roots) = match &purpose {
        GuestPurpose::Project { materials, .. } => {
            if !job.directories.is_empty() || !job.files.is_empty() {
                return Err("project material roots invalid".into());
            }
            let request = parse_request(&serde_json::to_vec(&job.request)?)?;
            (request.cpu_millis, request.memory_bytes, materials.clone())
        }
        GuestPurpose::TrustedIntake {
            cpu_millis,
            memory_bytes,
        } => {
            if *cpu_millis != 1000
                || *memory_bytes != 2 * 1024 * 1024 * 1024
                || job.files.len() != 1
                || job.files[0].normalized_path != "archive.zip"
                || job.files[0].byte_count > 512 * 1024 * 1024
                || !job.directories.is_empty()
            {
                return Err("trusted intake bootstrap invalid".into());
            }
            (
                *cpu_millis,
                *memory_bytes,
                vec![MaterialRoot {
                    name: "archive".into(),
                    directories: job.directories.clone(),
                    files: job.files.clone(),
                }],
            )
        }
        GuestPurpose::TrialBuild { materials } | GuestPurpose::TrialStep { materials } => {
            if !job.directories.is_empty() || !job.files.is_empty() {
                return Err("trial material roots invalid".into());
            }
            (0, 0, materials.clone())
        }
    };
    if job.command.is_empty() || job.command.len() > 256 || job.environment.len() > 1024 {
        return Err("image configuration invalid".into());
    }
    private_mounts().map_err(|e| format!("mount namespace: {e}"))?;
    // Stage before applying workload memory: submitted files are immutable input,
    // not checker heap. The enclosing VMM and disk bounds cover staging custody.
    let staged = stage(&job, &roots, &mut input).map_err(|e| format!("staging: {e}"))?;
    if matches!(
        purpose,
        GuestPurpose::TrialBuild { .. } | GuestPurpose::TrialStep { .. }
    ) {
        return trial::run(&job, &staged, &mut input);
    }
    if let GuestPurpose::Project { capabilities, .. } = &purpose {
        let request = parse_request(&serde_json::to_vec(&job.request)?)?;
        return run_project(
            job,
            *capabilities,
            staged,
            input,
            cpu,
            memory,
            request.maximum_output_bytes,
        );
    }
    drop(input);
    bind_material_root(&staged, "archive", INPUT_ROOT)?;
    if matches!(purpose, GuestPurpose::TrustedIntake { .. }) {
        fs::create_dir("/work/scratch")?;
        mount("/work/scratch", "/work/scratch", "", libc::MS_BIND, "")?;
        syscall_ok(unsafe { libc::chown(c("/work/scratch")?.as_ptr(), job.uid, job.gid) })?;
        fs::set_permissions("/work/scratch", fs::Permissions::from_mode(0o700))?;
    }
    cgroups(cpu, memory).map_err(|e| format!("cgroup: {e}"))?;
    // The trusted, single-threaded supervisor stays outside the workload cgroup
    // so an OOM cannot destroy the kernel evidence before it is classified.
    // stdin's lock has been dropped and no other threads exist at this fork.
    let child = unsafe { libc::fork() };
    if child < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    if child > 0 {
        let mut status = 0;
        loop {
            let waited = unsafe { libc::waitpid(child, &mut status, 0) };
            if waited == child {
                break;
            }
            if waited < 0
                && std::io::Error::last_os_error().kind() != std::io::ErrorKind::Interrupted
            {
                return Err(std::io::Error::last_os_error().into());
            }
        }
        let events = fs::read_to_string("/sys/fs/cgroup/workstream-checker/memory.events")?;
        let oom = events
            .lines()
            .find_map(|line| line.strip_prefix("oom_kill "))
            .ok_or("memory OOM evidence missing")?
            .parse::<u64>()?;
        std::process::exit(supervised_exit(status, oom));
    }
    private_mounts().map_err(|e| format!("workload mount namespace: {e}"))?;
    fs::write(
        "/sys/fs/cgroup/workstream-checker/cgroup.procs",
        std::process::id().to_string(),
    )?;
    confined_devices().map_err(|e| format!("devices: {e}"))?;
    readonly_filesystem().map_err(|e| format!("filesystem: {e}"))?;
    if matches!(purpose, GuestPurpose::TrustedIntake { .. }) {
        // Only the trusted worker receives private VM-disk scratch. Project
        // workloads retain their existing bounded tmpfs-only writable surface.
        mount(
            "",
            "/work/scratch",
            "",
            libc::MS_BIND | libc::MS_REMOUNT | libc::MS_NOSUID | libc::MS_NODEV | libc::MS_NOEXEC,
            "",
        )?;
    }
    drop_privileges(job.uid, job.gid).map_err(|e| format!("privileges: {e}"))?;
    syscall_filter().map_err(|e| format!("syscall policy: {e}"))?;
    let mut command = Command::new(&job.command[0]);
    command.args(&job.command[1..]).env_clear();
    // Trusted intake retains the remaining host command stream as stdin.
    for entry in &job.environment {
        let (key, value) = entry.split_once('=').ok_or("invalid image environment")?;
        command.env(key, value);
    }
    command.current_dir(if job.working_directory.is_empty() {
        "/"
    } else {
        &job.working_directory
    });
    let error = command.exec();
    Err(error.into())
}
