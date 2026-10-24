use std::collections::BTreeMap;
use std::env;
use std::ffi::{CString, OsStr, OsString};
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Write};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::{symlink, MetadataExt, OpenOptionsExt, PermissionsExt};
use std::path::{Component, Path, PathBuf};
use std::process;
use std::thread;
use std::time::Duration;

const BOOTSTRAP: &str = "/workstream-bootstrap";
const ROOT: &str = "/workstream-bootstrap/root";
const EXPORT: &str = "/workstream-bootstrap/export";
const INPUT_CONTEXT: &str = "/workstream-bootstrap/input/context";
const INPUT_CACHE: &str = "/workstream-bootstrap/input/cache";
const INPUT_WORKSPACE: &str = "/workstream-bootstrap/input/workspace";
const INPUT_ROLES: &str = "/workstream-bootstrap/input/roles";
const INFRASTRUCTURE_EXIT: i32 = 125;
const STATUS_SCHEMA: &str = "workstream.trial_launcher_status.v1";

const CAP_CHOWN: u32 = 0;
const CAP_DAC_OVERRIDE: u32 = 1;
const CAP_FOWNER: u32 = 3;

type Result<T> = std::result::Result<T, LauncherError>;

#[derive(Debug)]
struct LauncherError(String);

impl std::fmt::Display for LauncherError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.0)
    }
}

impl From<io::Error> for LauncherError {
    fn from(error: io::Error) -> Self {
        Self(error.to_string())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct FilesystemLimit {
    bytes: u64,
    inodes: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct BuilderArguments {
    root: FilesystemLimit,
    temporary: FilesystemLimit,
    shared_memory: FilesystemLimit,
    candidate_bytes: u64,
    command: Vec<OsString>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct VisibleRole {
    role: String,
    destination: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct StepArguments {
    root: FilesystemLimit,
    workspace: FilesystemLimit,
    temporary: FilesystemLimit,
    shared_memory: FilesystemLimit,
    working_directory: PathBuf,
    uid: u32,
    gid: u32,
    visible_roles: Vec<VisibleRole>,
    command: Vec<OsString>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct ChildOutcome {
    exit_code: Option<i32>,
    signal: Option<i32>,
}

struct SpawnedChild {
    pid: libc::pid_t,
    error: OwnedFd,
}

#[derive(Debug)]
enum Mode {
    Builder(BuilderArguments),
    Step(StepArguments),
}

fn main() {
    if let Err(error) = run() {
        eprintln!("trusted trial launcher infrastructure failure: {error}");
        process::exit(INFRASTRUCTURE_EXIT);
    }
}

fn run() -> Result<()> {
    require_static_pid_one()?;
    make_mounts_private()?;
    let mode = parse_arguments(env::args_os().skip(1).collect())?;
    match mode {
        Mode::Builder(arguments) => run_builder(arguments),
        Mode::Step(arguments) => run_step(arguments),
    }
}

fn require_static_pid_one() -> Result<()> {
    if unsafe { libc::getpid() } != 1 {
        return Err(failure("launcher must be container PID 1"));
    }
    if unsafe { libc::getauxval(libc::AT_BASE) } != 0 {
        return Err(failure("launcher must be statically linked"));
    }
    let bootstrap = fs::symlink_metadata(BOOTSTRAP)?;
    if !bootstrap.file_type().is_dir() || bootstrap.file_type().is_symlink() {
        return Err(failure("invalid trusted bootstrap root"));
    }
    Ok(())
}

fn parse_arguments(arguments: Vec<OsString>) -> Result<Mode> {
    let mut cursor = ArgumentCursor::new(arguments);
    match cursor.next_utf8("mode")?.as_str() {
        "builder" => parse_builder(&mut cursor).map(Mode::Builder),
        "step" => parse_step(&mut cursor).map(Mode::Step),
        _ => Err(failure("unsupported launcher mode")),
    }
}

fn parse_builder(cursor: &mut ArgumentCursor) -> Result<BuilderArguments> {
    let mut root = LimitBuilder::default();
    let mut temporary = LimitBuilder::default();
    let mut shared_memory = LimitBuilder::default();
    let mut candidate_bytes = None;
    while !cursor.at_separator() {
        let option = cursor.next_utf8("builder option")?;
        let value = cursor.next_u64(&option)?;
        match option.as_str() {
            "--root-bytes" => root.set_bytes(value)?,
            "--root-inodes" => root.set_inodes(value)?,
            "--tmp-bytes" => temporary.set_bytes(value)?,
            "--tmp-inodes" => temporary.set_inodes(value)?,
            "--shm-bytes" => shared_memory.set_bytes(value)?,
            "--shm-inodes" => shared_memory.set_inodes(value)?,
            "--candidate-bytes" => set_once(&mut candidate_bytes, value)?,
            _ => return Err(failure("unknown builder option")),
        }
    }
    let command = cursor.take_command()?;
    validate_builder_command(&command)?;
    let root = root.finish()?;
    let candidate_bytes = candidate_bytes.ok_or_else(|| failure("missing candidate byte limit"))?;
    if candidate_bytes > root.bytes {
        return Err(failure("candidate byte limit exceeds root byte limit"));
    }
    Ok(BuilderArguments {
        root,
        temporary: temporary.finish()?,
        shared_memory: shared_memory.finish()?,
        candidate_bytes,
        command,
    })
}

fn parse_step(cursor: &mut ArgumentCursor) -> Result<StepArguments> {
    let mut root = LimitBuilder::default();
    let mut workspace = LimitBuilder::default();
    let mut temporary = LimitBuilder::default();
    let mut shared_memory = LimitBuilder::default();
    let mut working_directory = None;
    let mut uid = None;
    let mut gid = None;
    let mut visible_roles = Vec::new();
    while !cursor.at_separator() {
        let option = cursor.next_utf8("step option")?;
        match option.as_str() {
            "--root-bytes" => root.set_bytes(cursor.next_u64(&option)?)?,
            "--root-inodes" => root.set_inodes(cursor.next_u64(&option)?)?,
            "--workspace-bytes" => workspace.set_bytes(cursor.next_u64(&option)?)?,
            "--workspace-inodes" => workspace.set_inodes(cursor.next_u64(&option)?)?,
            "--tmp-bytes" => temporary.set_bytes(cursor.next_u64(&option)?)?,
            "--tmp-inodes" => temporary.set_inodes(cursor.next_u64(&option)?)?,
            "--shm-bytes" => shared_memory.set_bytes(cursor.next_u64(&option)?)?,
            "--shm-inodes" => shared_memory.set_inodes(cursor.next_u64(&option)?)?,
            "--working-directory" => set_once(&mut working_directory, cursor.next_relative()?)?,
            "--uid" => set_once(&mut uid, cursor.next_u32(&option)?)?,
            "--gid" => set_once(&mut gid, cursor.next_u32(&option)?)?,
            "--visible" => visible_roles.push(cursor.next_visible_role()?),
            _ => return Err(failure("unknown step option")),
        }
    }
    let command = cursor.take_command()?;
    validate_visible_roles(&visible_roles)?;
    let uid = uid.ok_or_else(|| failure("missing step uid"))?;
    let gid = gid.ok_or_else(|| failure("missing step gid"))?;
    if uid == 0 || gid == 0 {
        return Err(failure("step uid and gid must be nonzero"));
    }
    Ok(StepArguments {
        root: root.finish()?,
        workspace: workspace.finish()?,
        temporary: temporary.finish()?,
        shared_memory: shared_memory.finish()?,
        working_directory: working_directory.ok_or_else(|| failure("missing working directory"))?,
        uid,
        gid,
        visible_roles,
        command,
    })
}

fn validate_builder_command(command: &[OsString]) -> Result<()> {
    let values = command
        .iter()
        .map(|value| {
            value
                .to_str()
                .ok_or_else(|| failure("non-UTF-8 builder argument"))
        })
        .collect::<Result<Vec<_>>>()?;
    if values.first().copied() != Some("/kaniko/executor")
        || !values.contains(&"--tar-path=/out/candidate.tar")
        || !values.contains(&"--ignore-path=/out")
        || !values
            .iter()
            .any(|value| value.starts_with("--context=dir:///workspace/"))
        || !values
            .iter()
            .any(|value| value.starts_with("--dockerfile=/workspace/"))
        || !values.contains(&"--cache-dir=/cache")
    {
        return Err(failure(
            "builder command violates the fixed sandbox contract",
        ));
    }
    Ok(())
}

fn validate_visible_roles(roles: &[VisibleRole]) -> Result<()> {
    let mut names = BTreeMap::new();
    let mut destinations = BTreeMap::new();
    for role in roles {
        if role.destination.as_os_str().is_empty() {
            return Err(failure(
                "visible role destination must not be workspace root",
            ));
        }
        if names.insert(&role.role, ()).is_some()
            || destinations.insert(&role.destination, ()).is_some()
        {
            return Err(failure("duplicate visible role or destination"));
        }
    }
    for (index, role) in roles.iter().enumerate() {
        if roles.iter().skip(index + 1).any(|other| {
            role.destination.starts_with(&other.destination)
                || other.destination.starts_with(&role.destination)
        }) {
            return Err(failure("visible role destinations overlap"));
        }
    }
    Ok(())
}

fn run_builder(arguments: BuilderArguments) -> Result<()> {
    require_empty_export()?;
    create_clean_directory(Path::new(ROOT), 0o700)?;
    mount_tmpfs(Path::new(ROOT), &arguments.root, 0o755, false)?;
    prepare_builder_root(&arguments)?;
    let export = open_export_directory()?;
    let output = open_directory(Path::new(ROOT).join("out"))?;
    enter_root(Path::new(ROOT))?;
    make_parent_process()?;
    let child = spawn_child(
        &arguments.command,
        ChildIdentity::Builder,
        export.as_raw_fd(),
    )?;
    let outcome = wait_for_child(child.pid)?;
    drain_descendants()?;
    require_no_child_setup_error(child.error)?;
    let candidate_exported = outcome.exit_code == Some(0);
    if candidate_exported {
        export_regular_file_at(
            output.as_raw_fd(),
            "candidate.tar",
            export.as_raw_fd(),
            "candidate.tar",
            arguments.candidate_bytes,
        )?;
    }
    write_status(export.as_raw_fd(), outcome, candidate_exported, false)
}

fn prepare_builder_root(arguments: &BuilderArguments) -> Result<()> {
    for path in [
        "workspace",
        "cache",
        "out",
        "kaniko",
        "kaniko/ssl",
        "kaniko/ssl/certs",
        "etc",
        "etc/ssl",
        "etc/ssl/certs",
        "proc",
        "dev",
        "dev/shm",
        "sys",
        "tmp",
    ] {
        create_directory(&Path::new(ROOT).join(path), 0o755)?;
    }
    create_file(&Path::new(ROOT).join("kaniko/executor"), 0o500)?;
    bind_readonly(
        Path::new("/kaniko/executor"),
        &Path::new(ROOT).join("kaniko/executor"),
        false,
    )?;
    bind_optional_certificate(&Path::new(ROOT).join("kaniko/ssl/certs/ca-certificates.crt"))?;
    bind_optional_certificate(&Path::new(ROOT).join("etc/ssl/certs/ca-certificates.crt"))?;
    bind_readonly(
        Path::new(INPUT_CONTEXT),
        &Path::new(ROOT).join("workspace"),
        true,
    )?;
    bind_readonly(Path::new(INPUT_CACHE), &Path::new(ROOT).join("cache"), true)?;
    mount_process_filesystems(Path::new(ROOT), &arguments.shared_memory)?;
    mount_tmpfs(
        &Path::new(ROOT).join("tmp"),
        &arguments.temporary,
        0o1777,
        true,
    )?;
    Ok(())
}

fn run_step(arguments: StepArguments) -> Result<()> {
    require_empty_export()?;
    create_clean_directory(Path::new(ROOT), 0o700)?;
    mount_tmpfs(Path::new(ROOT), &arguments.root, 0o755, false)?;
    prepare_candidate_skeleton(Path::new(ROOT))?;
    prepare_step_workspace(&arguments)?;
    let export = open_export_directory()?;
    enter_root(Path::new(ROOT))?;
    make_parent_process()?;
    let working_directory = Path::new("/workspace").join(&arguments.working_directory);
    require_safe_directory_beneath(Path::new("/workspace"), &arguments.working_directory)?;
    env::set_current_dir(&working_directory)?;
    let child = spawn_child(
        &arguments.command,
        ChildIdentity::Step {
            uid: arguments.uid,
            gid: arguments.gid,
        },
        export.as_raw_fd(),
    )?;
    let outcome = wait_for_child(child.pid)?;
    drain_descendants()?;
    require_no_child_setup_error(child.error)?;
    unmount_visible_roles(&arguments.visible_roles)?;
    export_workspace(
        export.as_raw_fd(),
        arguments.workspace.bytes,
        arguments.workspace.inodes,
    )?;
    write_status(export.as_raw_fd(), outcome, false, true)?;
    Ok(())
}

fn prepare_step_workspace(arguments: &StepArguments) -> Result<()> {
    let root = Path::new(ROOT);
    mount_tmpfs(&root.join("workspace"), &arguments.workspace, 0o700, false)?;
    change_owner(&root.join("workspace"), arguments.uid, arguments.gid)?;
    copy_tree_contents(
        Path::new(INPUT_WORKSPACE),
        &root.join("workspace"),
        Some((arguments.uid, arguments.gid)),
    )?;
    mount_tmpfs(&root.join("tmp"), &arguments.temporary, 0o1777, true)?;
    mount_process_filesystems(root, &arguments.shared_memory)?;
    for role in &arguments.visible_roles {
        let source = Path::new(INPUT_ROLES).join(&role.role);
        let destination = root.join("workspace").join(&role.destination);
        require_safe_directory_beneath(&root.join("workspace"), &role.destination)?;
        bind_readonly(&source, &destination, true)?;
    }
    Ok(())
}

fn prepare_candidate_skeleton(root: &Path) -> Result<()> {
    let protected = [
        "dev",
        "proc",
        "sys",
        "tmp",
        "workspace",
        "workstream-bootstrap",
    ];
    let mut entries = BTreeMap::new();
    for entry in fs::read_dir("/")? {
        let entry = entry?;
        entries.insert(entry.file_name(), entry.path());
    }
    for (name, source) in entries {
        let name_text = name
            .to_str()
            .ok_or_else(|| failure("candidate root contains non-UTF-8 entry"))?;
        if protected.contains(&name_text) {
            continue;
        }
        mirror_readonly_entry(&source, &root.join(&name))?;
    }
    for path in ["dev", "dev/shm", "proc", "sys", "tmp", "workspace"] {
        create_directory(&root.join(path), 0o755)?;
    }
    mount_empty_readonly(&root.join("workstream-bootstrap"))?;
    fs::set_permissions(root, fs::Permissions::from_mode(0o555))?;
    Ok(())
}

fn mirror_readonly_entry(source: &Path, destination: &Path) -> Result<()> {
    let metadata = fs::symlink_metadata(source)?;
    if metadata.file_type().is_symlink() {
        symlink(fs::read_link(source)?, destination)?;
    } else if metadata.file_type().is_dir() {
        create_directory(destination, 0o555)?;
        bind_readonly(source, destination, false)?;
    } else if metadata.file_type().is_file() {
        create_file(destination, 0o400)?;
        bind_readonly(source, destination, false)?;
    } else {
        return Err(failure(
            "candidate root contains unsupported top-level entry",
        ));
    }
    Ok(())
}

fn mount_process_filesystems(root: &Path, shared_memory: &FilesystemLimit) -> Result<()> {
    mount_fs(
        Some("proc"),
        &root.join("proc"),
        Some("proc"),
        libc::MS_NOSUID | libc::MS_NODEV | libc::MS_NOEXEC,
        None,
    )?;
    bind_readonly(Path::new("/sys"), &root.join("sys"), true)?;
    for device in ["null", "zero", "random", "urandom"] {
        let destination = root.join("dev").join(device);
        create_file(&destination, 0o600)?;
        bind_device(&Path::new("/dev").join(device), &destination)?;
    }
    for (name, target) in [
        ("fd", "/proc/self/fd"),
        ("stdin", "/proc/self/fd/0"),
        ("stdout", "/proc/self/fd/1"),
        ("stderr", "/proc/self/fd/2"),
    ] {
        symlink(target, root.join("dev").join(name))?;
    }
    mount_tmpfs(&root.join("dev/shm"), shared_memory, 0o1777, true)
}

fn mount_empty_readonly(destination: &Path) -> Result<()> {
    create_directory(destination, 0o555)?;
    let empty = Path::new(BOOTSTRAP).join("empty");
    create_clean_directory(&empty, 0o555)?;
    bind_readonly(&empty, destination, true)
}

fn unmount_visible_roles(roles: &[VisibleRole]) -> Result<()> {
    for role in roles.iter().rev() {
        let destination = Path::new("/workspace").join(&role.destination);
        let destination = path_cstring(&destination)?;
        if unsafe { libc::umount2(destination.as_ptr(), libc::MNT_DETACH) } != 0 {
            return Err(io::Error::last_os_error().into());
        }
    }
    Ok(())
}

fn make_mounts_private() -> Result<()> {
    mount_fs(
        None,
        Path::new("/"),
        None,
        libc::MS_REC | libc::MS_PRIVATE,
        None,
    )
}

fn mount_tmpfs(destination: &Path, limit: &FilesystemLimit, mode: u32, noexec: bool) -> Result<()> {
    let data = format!(
        "size={},nr_inodes={},mode={mode:o}",
        limit.bytes, limit.inodes
    );
    let mut flags = libc::MS_NOSUID | libc::MS_NODEV;
    if noexec {
        flags |= libc::MS_NOEXEC;
    }
    mount_fs(
        Some("tmpfs"),
        destination,
        Some("tmpfs"),
        flags,
        Some(&data),
    )
}

fn mount_fs(
    source: Option<&str>,
    destination: &Path,
    filesystem: Option<&str>,
    flags: libc::c_ulong,
    data: Option<&str>,
) -> Result<()> {
    let source = source
        .map(CString::new)
        .transpose()
        .map_err(|_| failure("invalid mount source"))?;
    let destination = path_cstring(destination)?;
    let filesystem = filesystem
        .map(CString::new)
        .transpose()
        .map_err(|_| failure("invalid filesystem name"))?;
    let data = data
        .map(CString::new)
        .transpose()
        .map_err(|_| failure("invalid mount data"))?;
    let result = unsafe {
        libc::mount(
            source
                .as_ref()
                .map_or(std::ptr::null(), |value| value.as_ptr()),
            destination.as_ptr(),
            filesystem
                .as_ref()
                .map_or(std::ptr::null(), |value| value.as_ptr()),
            flags,
            data.as_ref()
                .map_or(std::ptr::null(), |value| value.as_ptr().cast()),
        )
    };
    if result != 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(())
}

fn bind_readonly(source: &Path, destination: &Path, noexec: bool) -> Result<()> {
    bind_mount(source, destination)?;
    let mut flags =
        libc::MS_BIND | libc::MS_REMOUNT | libc::MS_RDONLY | libc::MS_NOSUID | libc::MS_NODEV;
    if noexec {
        flags |= libc::MS_NOEXEC;
    }
    remount_bind(destination, flags)
}

fn bind_device(source: &Path, destination: &Path) -> Result<()> {
    bind_mount(source, destination)?;
    remount_bind(
        destination,
        libc::MS_BIND | libc::MS_REMOUNT | libc::MS_RDONLY | libc::MS_NOSUID | libc::MS_NOEXEC,
    )
}

fn bind_mount(source: &Path, destination: &Path) -> Result<()> {
    let source = path_cstring(source)?;
    let destination = path_cstring(destination)?;
    if unsafe {
        libc::mount(
            source.as_ptr(),
            destination.as_ptr(),
            std::ptr::null(),
            libc::MS_BIND,
            std::ptr::null(),
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    Ok(())
}

fn remount_bind(destination: &Path, flags: libc::c_ulong) -> Result<()> {
    let destination = path_cstring(destination)?;
    if unsafe {
        libc::mount(
            std::ptr::null(),
            destination.as_ptr(),
            std::ptr::null(),
            flags,
            std::ptr::null(),
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    Ok(())
}

fn bind_optional_certificate(destination: &Path) -> Result<()> {
    let source = Path::new("/kaniko/ssl/certs/ca-certificates.crt");
    if !source.exists() {
        return Ok(());
    }
    create_file(destination, 0o400)?;
    bind_readonly(source, destination, true)
}

fn enter_root(root: &Path) -> Result<()> {
    let root = path_cstring(root)?;
    if unsafe { libc::chroot(root.as_ptr()) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    env::set_current_dir("/")?;
    Ok(())
}

fn make_parent_process() -> Result<()> {
    if unsafe { libc::prctl(libc::PR_SET_DUMPABLE, 0, 0, 0, 0) } != 0
        || unsafe { libc::prctl(libc::PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    Ok(())
}

enum ChildIdentity {
    Builder,
    Step { uid: u32, gid: u32 },
}

fn spawn_child(
    command: &[OsString],
    identity: ChildIdentity,
    export_fd: RawFd,
) -> Result<SpawnedChild> {
    let mut pipe = [-1; 2];
    if unsafe { libc::pipe2(pipe.as_mut_ptr(), libc::O_CLOEXEC) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    let pid = unsafe { libc::fork() };
    if pid < 0 {
        unsafe {
            libc::close(pipe[0]);
            libc::close(pipe[1]);
        }
        return Err(io::Error::last_os_error().into());
    }
    if pid == 0 {
        unsafe { libc::close(pipe[0]) };
        if unsafe { libc::close(export_fd) } != 0 {
            unsafe { libc::_exit(126) };
        }
        match prepare_child_error_fd(pipe[1]) {
            Ok(error_fd) => {
                if let Err(error) = child_exec(command, identity, error_fd) {
                    write_child_error(error_fd, &error);
                }
            }
            Err(error) => write_child_error(pipe[1], &error),
        }
        unsafe { libc::_exit(126) };
    }
    unsafe { libc::close(pipe[1]) };
    Ok(SpawnedChild {
        pid,
        error: unsafe { OwnedFd::from_raw_fd(pipe[0]) },
    })
}

fn prepare_child_error_fd(descriptor: RawFd) -> Result<RawFd> {
    if descriptor != 3 {
        if unsafe { libc::dup3(descriptor, 3, libc::O_CLOEXEC) } < 0 {
            return Err(io::Error::last_os_error().into());
        }
        unsafe { libc::close(descriptor) };
    } else if unsafe { libc::fcntl(3, libc::F_SETFD, libc::FD_CLOEXEC) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(3)
}

fn child_exec(command: &[OsString], identity: ChildIdentity, _error_fd: RawFd) -> Result<()> {
    close_other_file_descriptors()?;
    match identity {
        ChildIdentity::Builder => drop_builder_capabilities()?,
        ChildIdentity::Step { uid, gid } => drop_step_identity(uid, gid)?,
    }
    exec_command(command)
}

fn close_other_file_descriptors() -> Result<()> {
    #[cfg(target_os = "linux")]
    {
        let result = unsafe { libc::syscall(libc::SYS_close_range, 4_u32, u32::MAX, 0_u32) };
        if result == 0 {
            return Ok(());
        }
        let error = io::Error::last_os_error();
        if !matches!(error.raw_os_error(), Some(libc::ENOSYS | libc::EINVAL)) {
            return Err(error.into());
        }
    }
    let maximum = unsafe { libc::sysconf(libc::_SC_OPEN_MAX) }.clamp(3, 65_536);
    for descriptor in 4..maximum {
        unsafe { libc::close(descriptor as RawFd) };
    }
    Ok(())
}

fn write_child_error(descriptor: RawFd, error: &LauncherError) {
    let mut message = error.0.as_bytes();
    if message.len() > 4096 {
        message = &message[..4096];
    }
    while !message.is_empty() {
        let written = unsafe { libc::write(descriptor, message.as_ptr().cast(), message.len()) };
        if written <= 0 {
            break;
        }
        message = &message[written as usize..];
    }
}

fn require_no_child_setup_error(error: OwnedFd) -> Result<()> {
    let error = File::from(error);
    let mut message = String::new();
    error.take(4097).read_to_string(&mut message)?;
    if message.is_empty() {
        return Ok(());
    }
    if message.len() > 4096 {
        return Err(failure("child setup error exceeded its bound"));
    }
    Err(LauncherError(format!("child setup failed: {message}")))
}

fn exec_command(command: &[OsString]) -> Result<()> {
    let command = command
        .iter()
        .map(|value| CString::new(value.as_bytes()).map_err(|_| failure("command contains NUL")))
        .collect::<Result<Vec<_>>>()?;
    let mut pointers = command
        .iter()
        .map(|value| value.as_ptr())
        .collect::<Vec<_>>();
    pointers.push(std::ptr::null());
    unsafe { libc::execvp(command[0].as_ptr(), pointers.as_ptr()) };
    Err(io::Error::last_os_error().into())
}

fn drop_builder_capabilities() -> Result<()> {
    let retained = [CAP_CHOWN, CAP_DAC_OVERRIDE, CAP_FOWNER];
    drop_bounding_capabilities(&retained)?;
    set_capabilities(&retained, &retained)?;
    for capability in retained {
        if unsafe {
            libc::prctl(
                libc::PR_CAP_AMBIENT,
                libc::PR_CAP_AMBIENT_RAISE,
                capability,
                0,
                0,
            )
        } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
    }
    set_no_new_privileges()
}

fn drop_step_identity(uid: u32, gid: u32) -> Result<()> {
    drop_bounding_capabilities(&[])?;
    if unsafe { libc::setgroups(0, std::ptr::null()) } != 0 {
        return Err(os_failure("setgroups"));
    }
    if unsafe { libc::setresgid(gid, gid, gid) } != 0 {
        return Err(os_failure("setresgid"));
    }
    if unsafe { libc::setresuid(uid, uid, uid) } != 0 {
        return Err(os_failure("setresuid"));
    }
    set_capabilities(&[], &[])?;
    clear_ambient_capabilities()?;
    set_no_new_privileges()
}

#[repr(C)]
struct CapabilityHeader {
    version: u32,
    pid: i32,
}

#[repr(C)]
#[derive(Clone, Copy, Default)]
struct CapabilityData {
    effective: u32,
    permitted: u32,
    inheritable: u32,
}

fn set_capabilities(retained: &[u32], inheritable: &[u32]) -> Result<()> {
    let header = CapabilityHeader {
        version: 0x2008_0522,
        pid: 0,
    };
    let mut data = [CapabilityData::default(); 2];
    for capability in retained {
        let index = (*capability / 32) as usize;
        let mask = 1_u32 << (*capability % 32);
        data[index].effective |= mask;
        data[index].permitted |= mask;
        if inheritable.contains(capability) {
            data[index].inheritable |= mask;
        }
    }
    if unsafe { libc::syscall(libc::SYS_capset, &header, data.as_ptr()) } != 0 {
        return Err(os_failure("capset"));
    }
    Ok(())
}

fn drop_bounding_capabilities(retained: &[u32]) -> Result<()> {
    clear_ambient_capabilities()?;
    let maximum = fs::read_to_string("/proc/sys/kernel/cap_last_cap")
        .ok()
        .and_then(|value| value.trim().parse::<u32>().ok())
        .unwrap_or(63)
        .min(63);
    for capability in 0..=maximum {
        if retained.contains(&capability) {
            continue;
        }
        if unsafe { libc::prctl(libc::PR_CAPBSET_DROP, capability, 0, 0, 0) } != 0 {
            return Err(LauncherError(format!(
                "bounding capability drop {capability}: {}",
                io::Error::last_os_error()
            )));
        }
    }
    Ok(())
}

fn clear_ambient_capabilities() -> Result<()> {
    if unsafe {
        libc::prctl(
            libc::PR_CAP_AMBIENT,
            libc::PR_CAP_AMBIENT_CLEAR_ALL,
            0,
            0,
            0,
        )
    } != 0
    {
        return Err(os_failure("clear ambient capabilities"));
    }
    Ok(())
}

fn set_no_new_privileges() -> Result<()> {
    if unsafe { libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) } != 0 {
        return Err(os_failure("set no-new-privileges"));
    }
    Ok(())
}

fn wait_for_child(pid: libc::pid_t) -> Result<ChildOutcome> {
    loop {
        let mut status = 0;
        let result = unsafe { libc::waitpid(pid, &mut status, 0) };
        if result == pid {
            if libc::WIFEXITED(status) {
                return Ok(ChildOutcome {
                    exit_code: Some(libc::WEXITSTATUS(status)),
                    signal: None,
                });
            }
            if libc::WIFSIGNALED(status) {
                return Ok(ChildOutcome {
                    exit_code: None,
                    signal: Some(libc::WTERMSIG(status)),
                });
            }
            return Err(failure("child returned an unsupported wait status"));
        }
        let error = io::Error::last_os_error();
        if error.kind() != io::ErrorKind::Interrupted {
            return Err(error.into());
        }
    }
}

fn drain_descendants() -> Result<()> {
    for _ in 0..200 {
        let pids = descendant_pids()?;
        for pid in &pids {
            if unsafe { libc::kill(*pid, libc::SIGKILL) } != 0 {
                let error = io::Error::last_os_error();
                if error.raw_os_error() != Some(libc::ESRCH) {
                    return Err(error.into());
                }
            }
        }
        reap_available_children()?;
        if descendant_pids()?.is_empty() {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(5));
    }
    Err(failure("descendants did not terminate"))
}

fn descendant_pids() -> Result<Vec<libc::pid_t>> {
    let mut pids = Vec::new();
    for entry in fs::read_dir("/proc")? {
        let entry = entry?;
        let Some(value) = entry
            .file_name()
            .to_str()
            .and_then(|value| value.parse::<i32>().ok())
        else {
            continue;
        };
        if value > 1 {
            pids.push(value);
        }
    }
    Ok(pids)
}

fn reap_available_children() -> Result<()> {
    loop {
        let mut status = 0;
        let result = unsafe { libc::waitpid(-1, &mut status, libc::WNOHANG) };
        if result > 0 {
            continue;
        }
        if result == 0 {
            return Ok(());
        }
        let error = io::Error::last_os_error();
        if error.raw_os_error() == Some(libc::ECHILD) {
            return Ok(());
        }
        if error.kind() != io::ErrorKind::Interrupted {
            return Err(error.into());
        }
    }
}

fn require_empty_export() -> Result<()> {
    let metadata = fs::symlink_metadata(EXPORT)?;
    if !metadata.file_type().is_dir() || metadata.file_type().is_symlink() {
        return Err(failure("invalid export directory"));
    }
    if fs::read_dir(EXPORT)?.next().is_some() {
        return Err(failure("export directory must be empty"));
    }
    Ok(())
}

fn open_export_directory() -> Result<OwnedFd> {
    open_directory(Path::new(EXPORT))
}

fn open_directory(path: impl AsRef<Path>) -> Result<OwnedFd> {
    let path = path_cstring(path.as_ref())?;
    let descriptor = unsafe {
        libc::open(
            path.as_ptr(),
            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        )
    };
    if descriptor < 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(unsafe { OwnedFd::from_raw_fd(descriptor) })
}

fn export_regular_file_at(
    source_fd: RawFd,
    source_name: &str,
    export_fd: RawFd,
    export_name: &str,
    maximum_bytes: u64,
) -> Result<()> {
    let source_name = CString::new(source_name).map_err(|_| failure("invalid source name"))?;
    let descriptor = unsafe {
        libc::openat(
            source_fd,
            source_name.as_ptr(),
            libc::O_RDONLY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        )
    };
    if descriptor < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let mut input = unsafe { File::from_raw_fd(descriptor) };
    let metadata = input.metadata()?;
    if !metadata.file_type().is_file() || metadata.nlink() != 1 || metadata.len() > maximum_bytes {
        return Err(failure(
            "candidate export violates the bounded regular-file contract",
        ));
    }
    let mut output = create_export_file(export_fd, export_name, 0o600)?;
    let mut bounded = Read::take(&mut input, maximum_bytes.saturating_add(1));
    let copied = io::copy(&mut bounded, &mut output)?;
    if copied != metadata.len() {
        return Err(failure("candidate export changed while copying"));
    }
    output.sync_all()?;
    if unsafe { libc::unlinkat(source_fd, source_name.as_ptr(), 0) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    sync_directory(export_fd)
}

fn export_workspace(export_fd: RawFd, maximum_bytes: u64, maximum_entries: u64) -> Result<()> {
    let export_root = export_fd_path(export_fd).join("workspace.next");
    fs::create_dir(&export_root)?;
    fs::set_permissions(&export_root, fs::Permissions::from_mode(0o700))?;
    let mut budget = CopyBudget::new(maximum_bytes, maximum_entries);
    copy_export_tree(Path::new("/workspace"), &export_root, &mut budget)?;
    sync_tree(&export_root)?;
    sync_directory(export_fd)
}

fn write_status(
    export_fd: RawFd,
    outcome: ChildOutcome,
    candidate_exported: bool,
    workspace_exported: bool,
) -> Result<()> {
    let exit_code = outcome
        .exit_code
        .map_or_else(|| "null".to_owned(), |value| value.to_string());
    let signal = outcome
        .signal
        .map_or_else(|| "null".to_owned(), |value| value.to_string());
    let document = format!(
        "{{\"candidate_exported\":{candidate_exported},\"child\":{{\"exit_code\":{exit_code},\"signal\":{signal}}},\"schema\":\"{STATUS_SCHEMA}\",\"workspace_exported\":{workspace_exported}}}"
    );
    let mut temporary = create_export_file(export_fd, "status.json.tmp", 0o600)?;
    temporary.write_all(document.as_bytes())?;
    temporary.sync_all()?;
    drop(temporary);
    rename_export(export_fd, "status.json.tmp", "status.json")?;
    sync_directory(export_fd)
}

fn create_export_file(export_fd: RawFd, name: &str, mode: u32) -> Result<File> {
    let name = CString::new(name).map_err(|_| failure("invalid export name"))?;
    let descriptor = unsafe {
        libc::openat(
            export_fd,
            name.as_ptr(),
            libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL | libc::O_NOFOLLOW | libc::O_CLOEXEC,
            mode,
        )
    };
    if descriptor < 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(unsafe { File::from_raw_fd(descriptor) })
}

fn rename_export(export_fd: RawFd, source: &str, destination: &str) -> Result<()> {
    let source = CString::new(source).map_err(|_| failure("invalid export name"))?;
    let destination = CString::new(destination).map_err(|_| failure("invalid export name"))?;
    if unsafe { libc::renameat(export_fd, source.as_ptr(), export_fd, destination.as_ptr()) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(())
}

fn sync_directory(descriptor: RawFd) -> Result<()> {
    if unsafe { libc::fsync(descriptor) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(())
}

fn export_fd_path(descriptor: RawFd) -> PathBuf {
    PathBuf::from(format!("/proc/self/fd/{descriptor}"))
}

fn copy_tree_contents(source: &Path, destination: &Path, owner: Option<(u32, u32)>) -> Result<()> {
    require_directory_without_symlink(source)?;
    let mut children = BTreeMap::new();
    for entry in fs::read_dir(source)? {
        let entry = entry?;
        children.insert(entry.file_name(), entry.path());
    }
    for (name, path) in children {
        copy_input_entry(&path, &destination.join(name), owner)?;
    }
    Ok(())
}

fn copy_input_entry(source: &Path, destination: &Path, owner: Option<(u32, u32)>) -> Result<()> {
    let metadata = fs::symlink_metadata(source)?;
    if metadata.file_type().is_symlink() {
        return Err(failure("input tree contains a symlink"));
    }
    if metadata.file_type().is_dir() {
        create_directory(destination, 0o700)?;
        if let Some((uid, gid)) = owner {
            change_owner(destination, uid, gid)?;
        }
        copy_tree_contents(source, destination, owner)?;
        return Ok(());
    }
    if !metadata.file_type().is_file() {
        return Err(failure("input tree contains a special file"));
    }
    let mode = if metadata.permissions().mode() & 0o111 == 0 {
        0o600
    } else {
        0o700
    };
    copy_regular(source, destination, mode)?;
    if let Some((uid, gid)) = owner {
        change_owner(destination, uid, gid)?;
    }
    Ok(())
}

fn copy_export_tree(source: &Path, destination: &Path, budget: &mut CopyBudget) -> Result<()> {
    let mut children = BTreeMap::new();
    for entry in fs::read_dir(source)? {
        let entry = entry?;
        children.insert(entry.file_name(), entry.path());
    }
    for (name, path) in children {
        let target = destination.join(name);
        let metadata = fs::symlink_metadata(&path)?;
        if metadata.file_type().is_symlink() {
            return Err(failure("workspace export contains a symlink"));
        }
        budget.charge(if metadata.file_type().is_file() {
            metadata.len()
        } else {
            0
        })?;
        if metadata.file_type().is_dir() {
            fs::create_dir(&target)?;
            fs::set_permissions(&target, fs::Permissions::from_mode(0o700))?;
            copy_export_tree(&path, &target, budget)?;
            fs::remove_dir(&path)?;
        } else if metadata.file_type().is_file() {
            let mode = if metadata.permissions().mode() & 0o111 == 0 {
                0o600
            } else {
                0o700
            };
            copy_regular(&path, &target, mode)?;
            fs::remove_file(&path)?;
        } else {
            return Err(failure("workspace export contains a special file"));
        }
    }
    Ok(())
}

fn copy_regular(source: &Path, destination: &Path, mode: u32) -> Result<()> {
    let mut input = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(source)?;
    let opened = input.metadata()?;
    if !opened.file_type().is_file() {
        return Err(failure("copy source is not a regular file"));
    }
    let mut output = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(mode)
        .open(destination)?;
    let copied = io::copy(&mut input, &mut output)?;
    if copied != opened.len() {
        return Err(failure("copy source changed while copying"));
    }
    output.sync_all()?;
    Ok(())
}

fn sync_tree(root: &Path) -> Result<()> {
    for entry in fs::read_dir(root)? {
        let path = entry?.path();
        let metadata = fs::symlink_metadata(&path)?;
        if metadata.file_type().is_dir() {
            sync_tree(&path)?;
        } else if metadata.file_type().is_file() {
            File::open(&path)?.sync_all()?;
        }
    }
    File::open(root)?.sync_all()?;
    Ok(())
}

fn create_clean_directory(path: &Path, mode: u32) -> Result<()> {
    match fs::symlink_metadata(path) {
        Ok(_) => return Err(failure("trusted path already exists")),
        Err(error) if error.kind() == io::ErrorKind::NotFound => {}
        Err(error) => return Err(error.into()),
    }
    create_directory(path, mode)
}

fn create_directory(path: &Path, mode: u32) -> Result<()> {
    fs::create_dir(path)?;
    fs::set_permissions(path, fs::Permissions::from_mode(mode))?;
    Ok(())
}

fn create_file(path: &Path, mode: u32) -> Result<()> {
    OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(mode)
        .open(path)?;
    Ok(())
}

fn require_directory_without_symlink(path: &Path) -> Result<()> {
    let metadata = fs::symlink_metadata(path)?;
    if !metadata.file_type().is_dir() || metadata.file_type().is_symlink() {
        return Err(failure("expected an ordinary directory"));
    }
    Ok(())
}

fn require_safe_directory_beneath(root: &Path, relative: &Path) -> Result<()> {
    require_directory_without_symlink(root)?;
    let mut current = root.to_path_buf();
    for component in relative.components() {
        let Component::Normal(name) = component else {
            return Err(failure("unsafe relative directory"));
        };
        current.push(name);
        require_directory_without_symlink(&current)?;
    }
    Ok(())
}

fn change_owner(path: &Path, uid: u32, gid: u32) -> Result<()> {
    let path = path_cstring(path)?;
    if unsafe { libc::chown(path.as_ptr(), uid, gid) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(())
}

fn path_cstring(path: &Path) -> Result<CString> {
    CString::new(path.as_os_str().as_bytes()).map_err(|_| failure("path contains NUL"))
}

fn normalized_relative(value: &OsStr) -> Result<PathBuf> {
    if value == "." {
        return Ok(PathBuf::new());
    }
    let path = Path::new(value);
    if path.as_os_str().is_empty()
        || path.is_absolute()
        || path
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err(failure("path must be normalized and relative"));
    }
    if path.as_os_str().as_bytes().len() > 4096 {
        return Err(failure("relative path is too long"));
    }
    Ok(path.to_path_buf())
}

fn valid_role(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 100
        && value != "."
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-' | b'.'))
}

fn set_once<T>(slot: &mut Option<T>, value: T) -> Result<()> {
    if slot.replace(value).is_some() {
        return Err(failure("duplicate launcher option"));
    }
    Ok(())
}

fn failure(message: &str) -> LauncherError {
    LauncherError(message.to_owned())
}

fn os_failure(operation: &str) -> LauncherError {
    LauncherError(format!("{operation}: {}", io::Error::last_os_error()))
}

#[derive(Default)]
struct LimitBuilder {
    bytes: Option<u64>,
    inodes: Option<u64>,
}

impl LimitBuilder {
    fn set_bytes(&mut self, value: u64) -> Result<()> {
        set_once(&mut self.bytes, value)
    }

    fn set_inodes(&mut self, value: u64) -> Result<()> {
        set_once(&mut self.inodes, value)
    }

    fn finish(self) -> Result<FilesystemLimit> {
        let bytes = self.bytes.ok_or_else(|| failure("missing byte limit"))?;
        let inodes = self.inodes.ok_or_else(|| failure("missing inode limit"))?;
        if bytes == 0 || inodes == 0 {
            return Err(failure("filesystem limits must be positive"));
        }
        Ok(FilesystemLimit { bytes, inodes })
    }
}

struct ArgumentCursor {
    arguments: Vec<OsString>,
    index: usize,
}

impl ArgumentCursor {
    fn new(arguments: Vec<OsString>) -> Self {
        Self {
            arguments,
            index: 0,
        }
    }

    fn at_separator(&self) -> bool {
        self.arguments
            .get(self.index)
            .is_some_and(|value| value == "--")
    }

    fn next(&mut self, name: &str) -> Result<OsString> {
        let value = self
            .arguments
            .get(self.index)
            .cloned()
            .ok_or_else(|| failure(&format!("missing {name}")))?;
        self.index += 1;
        Ok(value)
    }

    fn next_utf8(&mut self, name: &str) -> Result<String> {
        self.next(name)?
            .into_string()
            .map_err(|_| failure(&format!("{name} must be UTF-8")))
    }

    fn next_u64(&mut self, name: &str) -> Result<u64> {
        self.next_utf8(name)?
            .parse::<u64>()
            .ok()
            .filter(|value| *value > 0)
            .ok_or_else(|| failure(&format!("{name} must be a positive integer")))
    }

    fn next_u32(&mut self, name: &str) -> Result<u32> {
        self.next_utf8(name)?
            .parse::<u32>()
            .map_err(|_| failure(&format!("{name} must be an integer")))
    }

    fn next_relative(&mut self) -> Result<PathBuf> {
        normalized_relative(&self.next("relative path")?)
    }

    fn next_visible_role(&mut self) -> Result<VisibleRole> {
        let value = self.next_utf8("visible role")?;
        let (role, destination) = value
            .split_once('=')
            .ok_or_else(|| failure("visible role must be ROLE=DESTINATION"))?;
        if !valid_role(role) {
            return Err(failure("invalid visible role"));
        }
        Ok(VisibleRole {
            role: role.to_owned(),
            destination: normalized_relative(OsStr::new(destination))?,
        })
    }

    fn take_command(&mut self) -> Result<Vec<OsString>> {
        if !self.at_separator() {
            return Err(failure("missing command separator"));
        }
        self.index += 1;
        let command = self.arguments[self.index..].to_vec();
        if command.is_empty() || command.len() > 256 {
            return Err(failure("invalid command length"));
        }
        if command
            .iter()
            .any(|value| value.as_bytes().len() > 4096 || value.as_bytes().contains(&0))
        {
            return Err(failure("invalid command argument"));
        }
        self.index = self.arguments.len();
        Ok(command)
    }
}

struct CopyBudget {
    bytes_left: u64,
    entries_left: u64,
}

impl CopyBudget {
    fn new(bytes: u64, entries: u64) -> Self {
        Self {
            bytes_left: bytes,
            entries_left: entries,
        }
    }

    fn charge(&mut self, bytes: u64) -> Result<()> {
        self.entries_left = self
            .entries_left
            .checked_sub(1)
            .ok_or_else(|| failure("workspace entry limit exceeded"))?;
        self.bytes_left = self
            .bytes_left
            .checked_sub(bytes)
            .ok_or_else(|| failure("workspace byte limit exceeded"))?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn strings(values: &[&str]) -> Vec<OsString> {
        values.iter().map(OsString::from).collect()
    }

    #[test]
    fn builder_requires_bounded_filesystems_and_fixed_output_contract() {
        let parsed = parse_arguments(strings(&[
            "builder",
            "--root-bytes",
            "1000",
            "--root-inodes",
            "20",
            "--tmp-bytes",
            "100",
            "--tmp-inodes",
            "4",
            "--shm-bytes",
            "100",
            "--shm-inodes",
            "4",
            "--candidate-bytes",
            "800",
            "--",
            "/kaniko/executor",
            "--dockerfile=/workspace/Dockerfile",
            "--context=dir:///workspace/source",
            "--cache-dir=/cache",
            "--tar-path=/out/candidate.tar",
            "--ignore-path=/out",
        ]))
        .unwrap();
        assert!(matches!(parsed, Mode::Builder(_)));
    }

    #[test]
    fn builder_rejects_unbounded_or_redirected_output() {
        let missing_limit = parse_arguments(strings(&[
            "builder",
            "--root-bytes",
            "1000",
            "--root-inodes",
            "20",
            "--tmp-bytes",
            "100",
            "--tmp-inodes",
            "4",
            "--shm-bytes",
            "100",
            "--",
            "/kaniko/executor",
        ]));
        assert!(missing_limit.is_err());

        let oversized_candidate = parse_arguments(strings(&[
            "builder",
            "--root-bytes",
            "1000",
            "--root-inodes",
            "20",
            "--tmp-bytes",
            "100",
            "--tmp-inodes",
            "4",
            "--shm-bytes",
            "100",
            "--shm-inodes",
            "4",
            "--candidate-bytes",
            "1001",
            "--",
            "/kaniko/executor",
            "--dockerfile=/workspace/Dockerfile",
            "--context=dir:///workspace/source",
            "--cache-dir=/cache",
            "--tar-path=/out/candidate.tar",
            "--ignore-path=/out",
        ]));
        assert!(oversized_candidate.is_err());
    }

    #[test]
    fn step_requires_nonroot_identity_and_normalized_destinations() {
        let parsed = parse_arguments(strings(&[
            "step",
            "--root-bytes",
            "1000",
            "--root-inodes",
            "20",
            "--workspace-bytes",
            "1000",
            "--workspace-inodes",
            "20",
            "--tmp-bytes",
            "100",
            "--tmp-inodes",
            "4",
            "--shm-bytes",
            "100",
            "--shm-inodes",
            "4",
            "--working-directory",
            "src",
            "--uid",
            "65532",
            "--gid",
            "65532",
            "--visible",
            "tests=tests",
            "--",
            "/bin/sh",
            "-c",
            "true",
        ]))
        .unwrap();
        assert!(matches!(parsed, Mode::Step(_)));

        let unsafe_destination = parse_arguments(strings(&[
            "step",
            "--root-bytes",
            "1000",
            "--root-inodes",
            "20",
            "--workspace-bytes",
            "1000",
            "--workspace-inodes",
            "20",
            "--tmp-bytes",
            "100",
            "--tmp-inodes",
            "4",
            "--shm-bytes",
            "100",
            "--shm-inodes",
            "4",
            "--working-directory",
            ".",
            "--uid",
            "65532",
            "--gid",
            "65532",
            "--visible",
            "tests=../tests",
            "--",
            "/bin/true",
        ]));
        assert!(unsafe_destination.is_err());
    }

    #[test]
    fn duplicate_role_and_destination_are_rejected() {
        let roles = vec![
            VisibleRole {
                role: "tests".into(),
                destination: "tests".into(),
            },
            VisibleRole {
                role: "solution".into(),
                destination: "tests".into(),
            },
        ];
        assert!(validate_visible_roles(&roles).is_err());
    }
}
