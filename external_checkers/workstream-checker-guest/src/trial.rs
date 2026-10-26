//! Trusted Smol sibling-trial supervisor.

use super::{disable_swap, mount, StagedJob};
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::{FileTypeExt, MetadataExt, OpenOptionsExt, PermissionsExt};
use std::os::unix::process::CommandExt;
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};
use workstream_checker_guest::{
    GuestJob, GuestPurpose, MaterialFile, TrialChildLimits, TrialChildOutcome, TrialChildResult,
    TrialExport, TrialExportHeader, TrialExportOutcome, TrialFilesystemLimit, TrialRequest,
    TrialTermination, MINIMUM_TRIAL_FILESYSTEM_BYTES, MINIMUM_TRIAL_FILESYSTEM_ENTRIES,
    MINIMUM_TRIAL_PIDS, TRIAL_CHILD_PROTOCOL, TRIAL_EXPORT_PROTOCOL, TRIAL_LIMITS_ARGUMENT,
    TRIAL_LIMITS_MAXIMUM_BYTES, TRIAL_OUTPUT_MAXIMUM_BYTES, TRIAL_REQUEST_PROTOCOL,
};

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

const BOOTSTRAP: &str = "/workstream-bootstrap";
const ROOT: &str = "/workstream-bootstrap/root";
const EXPORT: &str = "/workstream-bootstrap/export";
const LAUNCHER: &str = "/.workstream-trial-launcher";
const MKFS: &str = "/.workstream-mkfs.ext4";
const FILESYSTEMS: &str = "/work/.trial-filesystems";
const CGROUP: &str = "/sys/fs/cgroup/workstream-trial";
const CONTROL_CGROUP: &str = "/sys/fs/cgroup/workstream-trial/control";
const WORKLOAD_CGROUP: &str = "/sys/fs/cgroup/workstream-trial/workload";
const LOOP_CTL_GET_FREE: libc::c_ulong = 0x4c82;
const LOOP_SET_FD: libc::c_ulong = 0x4c00;
const LOOP_CLR_FD: libc::c_ulong = 0x4c01;
const STATUS_MAXIMUM: u64 = 16 * 1024;
const REQUEST_SCHEMA: &str = TRIAL_REQUEST_PROTOCOL;

pub(crate) struct TrialEnvelope {
    limits: TrialChildLimits,
    started: Instant,
    deadline: Instant,
    finalization_deadline: Instant,
    original_cgroup: PathBuf,
    active: bool,
}

struct Measurements {
    elapsed_ms: u64,
    cpu_time_ms: u64,
    peak_memory_bytes: u64,
    peak_pids: u64,
}

fn require_publishable_measurements(
    limits: TrialChildLimits,
    forced: Option<TrialTermination>,
    measurements: &Measurements,
) -> Result<()> {
    // A resource stop already observed while the child ran keeps its original
    // cause and terminal facts. After a normally completed child, the current
    // protocol cannot express a cleanup-only resource cause alongside that real
    // exit/signal. Refuse publication rather than inventing either fact.
    if forced.is_none()
        && (measurements.elapsed_ms >= limits.timeout_ms
            || measurements.cpu_time_ms >= limits.cpu_time_ms)
    {
        return Err("trial finalization exceeded the publishable operation allowance".into());
    }
    Ok(())
}

// Only the trusted host supplies this small scalar envelope. It must precede
// all input-dependent job allocation: moving an existing process into a cgroup
// does not transfer the charge for already allocated pages.
pub(crate) fn parse_bootstrap_limits(
    mut arguments: impl Iterator<Item = std::ffi::OsString>,
) -> Result<Option<TrialChildLimits>> {
    let Some(option) = arguments.next() else {
        return Ok(None);
    };
    if option != TRIAL_LIMITS_ARGUMENT {
        return Err("guest bootstrap argument invalid".into());
    }
    let document = arguments.next().ok_or("trial bootstrap limits missing")?;
    if document.len() > TRIAL_LIMITS_MAXIMUM_BYTES || arguments.next().is_some() {
        return Err("trial bootstrap limits unbounded".into());
    }
    let document = document.to_str().ok_or("trial bootstrap limits invalid")?;
    let limits: TrialChildLimits = serde_json::from_str(document)?;
    if !valid_child_limits(limits) {
        return Err("trial bootstrap limits invalid".into());
    }
    Ok(Some(limits))
}

pub(crate) fn bind_bootstrap_job(
    job: &GuestJob,
    bootstrap: Option<TrialChildLimits>,
) -> Result<Option<TrialRequest>> {
    let trial_purpose = matches!(
        job.purpose,
        GuestPurpose::TrialBuild { .. } | GuestPurpose::TrialStep { .. }
    );
    let Some(limits) = bootstrap else {
        return if trial_purpose {
            Err("trial bootstrap envelope missing".into())
        } else {
            Ok(None)
        };
    };
    let request: TrialRequest = serde_json::from_value(job.request.clone())?;
    if !matches!(
        (&job.purpose, &request),
        (GuestPurpose::TrialBuild { .. }, TrialRequest::Build { .. })
            | (GuestPurpose::TrialStep { .. }, TrialRequest::Step { .. })
    ) || job.uid == 0
        || job.gid == 0
        || request_limits(&request) != limits
    {
        return Err("trial bootstrap job binding differs".into());
    }
    validate_material_contract(job, &request)?;
    validate_request(job, &request)?;
    Ok(Some(request))
}

impl TrialEnvelope {
    pub(crate) fn prepare(limits: TrialChildLimits) -> Result<Self> {
        if !valid_child_limits(limits) {
            return Err("trial bootstrap limits invalid".into());
        }
        let started = Instant::now();
        let memberships = fs::read_to_string("/proc/self/cgroup")?;
        let original = memberships
            .lines()
            .find_map(|line| line.strip_prefix("0::"))
            .ok_or("original cgroup missing")?;
        if !original.starts_with('/')
            || Path::new(original)
                .components()
                .any(|part| matches!(part, Component::ParentDir))
        {
            return Err("original cgroup invalid".into());
        }
        let original_cgroup = Path::new("/sys/fs/cgroup").join(original.trim_start_matches('/'));
        configure_cgroup(limits)?;
        let envelope = Self {
            limits,
            started,
            deadline: started + Duration::from_millis(limits.timeout_ms),
            finalization_deadline: started + Duration::from_millis(limits.finalization_timeout_ms),
            original_cgroup,
            active: true,
        };
        envelope.check()?;
        Ok(envelope)
    }

    fn cause(&self) -> Result<Option<TrialTermination>> {
        Ok(if Instant::now() >= self.deadline {
            Some(TrialTermination::DeadlineExceeded)
        } else if cgroup_cpu_ms()? >= self.limits.cpu_time_ms {
            Some(TrialTermination::CpuExceeded)
        } else if cgroup_oom_kills()? > 0 {
            Some(TrialTermination::MemoryExceeded)
        } else if cgroup_pid_limit_hits()? > 0 {
            Some(TrialTermination::PidExceeded)
        } else {
            None
        })
    }

    pub(crate) fn check(&self) -> Result<()> {
        self.check_finalization()?;
        if self.cause()?.is_some() {
            return Err("trial operation ceiling reached".into());
        }
        Ok(())
    }

    fn check_finalization(&self) -> Result<()> {
        if Instant::now() >= self.finalization_deadline
            || cgroup_cpu_ms()? >= self.limits.finalization_cpu_time_ms
        {
            return Err("trial finalization ceiling reached".into());
        }
        Ok(())
    }

    fn measurements(&self) -> Result<Measurements> {
        Ok(Measurements {
            elapsed_ms: self.started.elapsed().as_millis() as u64,
            cpu_time_ms: cgroup_cpu_ms()?,
            peak_memory_bytes: cgroup_value("memory.peak")?,
            peak_pids: cgroup_value("pids.peak")?,
        })
    }

    fn finish(&mut self) -> Result<Measurements> {
        self.check_finalization()?;
        fs::write(Path::new(WORKLOAD_CGROUP).join("cgroup.kill"), "1")?;
        for _ in 0..1000 {
            self.check_finalization()?;
            if fs::read_to_string(Path::new(WORKLOAD_CGROUP).join("cgroup.events"))?
                .lines()
                .any(|line| line == "populated 0")
            {
                let measurements = self.measurements()?;
                // The operation's final measurement ends after stream flush and
                // filesystem cleanup. Receipt emission and cgroup removal are
                // bounded trusted management, never another workload allowance.
                self.leave_and_remove()?;
                self.active = false;
                return Ok(measurements);
            }
            std::thread::sleep(Duration::from_millis(2));
        }
        Err("trial workload cleanup unsettled".into())
    }

    fn leave_and_remove(&self) -> Result<()> {
        fs::write(self.original_cgroup.join("cgroup.procs"), "0")?;
        fs::remove_dir(WORKLOAD_CGROUP)?;
        fs::remove_dir(CONTROL_CGROUP)?;
        fs::remove_dir(CGROUP)?;
        Ok(())
    }
}

impl Drop for TrialEnvelope {
    fn drop(&mut self) {
        if self.active {
            let _ = fs::write(Path::new(WORKLOAD_CGROUP).join("cgroup.kill"), "1");
            let _ = self.leave_and_remove();
        }
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct LauncherStatus {
    schema: String,
    child: TrialChildOutcome,
    candidate_exported: bool,
    workspace_exported: bool,
    export_failure: Option<String>,
}

struct BoundedFilesystem {
    exposed: PathBuf,
    private_mount: PathBuf,
    backing: PathBuf,
    loop_path: PathBuf,
    loop_file: Option<File>,
    loop_attached: bool,
    private_mounted: bool,
    exposed_mounted: bool,
    maximum_bytes: u64,
}

struct BackingGuard {
    base: PathBuf,
    backing: PathBuf,
    armed: bool,
}

struct OutputCapture {
    retained: Vec<u8>,
    bytes: u64,
    eof: bool,
    truncated: bool,
}

impl OutputCapture {
    fn new() -> Self {
        Self {
            retained: Vec::new(),
            bytes: 0,
            eof: false,
            truncated: false,
        }
    }

    fn drain<R: Read>(&mut self, reader: &mut R, remaining: u64) -> Result<bool> {
        let mut buffer = [0_u8; 8 * 1024];
        let mut allowance = remaining;
        let mut drained = 0_usize;
        loop {
            match reader.read(&mut buffer) {
                Ok(0) => {
                    self.eof = true;
                    return Ok(false);
                }
                Ok(count) => {
                    let retained = count.min(allowance as usize);
                    self.retained.extend_from_slice(&buffer[..retained]);
                    self.bytes = self
                        .bytes
                        .checked_add(retained as u64)
                        .ok_or("trial output byte count overflow")?;
                    allowance -= retained as u64;
                    drained += count;
                    if retained != count {
                        self.truncated = true;
                        return Ok(true);
                    }
                    if drained >= 65_536 {
                        return Ok(false);
                    }
                }
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    return Ok(false);
                }
                Err(error) if error.kind() == std::io::ErrorKind::Interrupted => continue,
                Err(error) => return Err(error.into()),
            }
        }
    }

    fn finish(mut self) -> Result<(u64, String, String)> {
        if let Err(error) = std::str::from_utf8(&self.retained) {
            // A resource cut may split the last UTF-8 scalar. Preserve the
            // enforced OutputExceeded cause and only trim that incomplete tail.
            if !self.truncated
                || error.error_len().is_some()
                || self.retained.len().saturating_sub(error.valid_up_to()) > 3
            {
                return Err("trial retained output is not UTF-8".into());
            }
            self.retained.truncate(error.valid_up_to());
        }
        let text =
            String::from_utf8(self.retained).map_err(|_| "trial retained output is not UTF-8")?;
        Ok((
            text.len() as u64,
            format!("sha256:{:x}", Sha256::digest(text.as_bytes())),
            text,
        ))
    }
}

impl Drop for BackingGuard {
    fn drop(&mut self) {
        if self.armed {
            let _ = fs::remove_file(&self.backing);
            let _ = fs::remove_dir_all(&self.base);
        }
    }
}

impl BoundedFilesystem {
    fn create(
        operation: &str,
        name: &str,
        limit: TrialFilesystemLimit,
        exposed: &Path,
        mode: u32,
        envelope: &TrialEnvelope,
    ) -> Result<Self> {
        if limit.bytes < MINIMUM_TRIAL_FILESYSTEM_BYTES
            || limit.entries < MINIMUM_TRIAL_FILESYSTEM_ENTRIES
        {
            return Err("trial filesystem limit cannot hold ext4 metadata".into());
        }
        let base = Path::new(FILESYSTEMS).join(format!("{operation}-{name}"));
        fs::create_dir(&base)?;
        let backing = base.join("filesystem.ext4");
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&backing)?;
        let mut backing_guard = BackingGuard {
            base: base.clone(),
            backing: backing.clone(),
            armed: true,
        };
        file.set_len(limit.bytes)?;
        let entries = limit.entries.to_string();
        envelope.check()?;
        let mut formatter = Command::new(MKFS);
        formatter
            .args([
                "-F",
                "-q",
                "-t",
                "ext4",
                "-b",
                "4096",
                "-I",
                "256",
                "-m",
                "0",
                "-N",
                &entries,
                "-O",
                "none,extent,flex_bg,metadata_csum,64bit,dir_nlink,extra_isize",
                "-E",
                "lazy_itable_init=0,lazy_journal_init=0",
            ])
            .arg(&backing)
            .env_clear()
            .env("MKE2FS_CONFIG", "/dev/null")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        run_formatter(&mut formatter, envelope)?;
        ensure_device_node(Path::new("/dev/loop-control"), libc::S_IFCHR, 10, 237)?;
        let control = OpenOptions::new()
            .read(true)
            .write(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open("/dev/loop-control")?;
        let index = unsafe { libc::ioctl(control.as_raw_fd(), LOOP_CTL_GET_FREE as _) };
        if index < 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        let loop_path = PathBuf::from(format!("/dev/loop{index}"));
        ensure_device_node(&loop_path, libc::S_IFBLK, 7, index as u32)?;
        let loop_file = OpenOptions::new()
            .read(true)
            .write(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&loop_path)?;
        if unsafe { libc::ioctl(loop_file.as_raw_fd(), LOOP_SET_FD as _, file.as_raw_fd()) } != 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        let private_mount = base.join("mounted");
        let mut filesystem = Self {
            exposed: exposed.to_owned(),
            private_mount,
            backing,
            loop_path,
            loop_file: Some(loop_file),
            loop_attached: true,
            private_mounted: false,
            exposed_mounted: false,
            maximum_bytes: limit.bytes,
        };
        backing_guard.armed = false;
        fs::create_dir(&filesystem.private_mount)?;
        mount(
            filesystem.loop_path.to_str().ok_or("loop path invalid")?,
            filesystem
                .private_mount
                .to_str()
                .ok_or("mount path invalid")?,
            "ext4",
            libc::MS_NOSUID | libc::MS_NODEV | libc::MS_NOATIME | libc::MS_NODIRATIME,
            "",
        )?;
        filesystem.private_mounted = true;
        let child = filesystem.private_mount.join("child");
        fs::create_dir(&child)?;
        fs::set_permissions(&child, fs::Permissions::from_mode(mode))?;
        reserve_surplus_inodes(&filesystem.private_mount, limit.entries, envelope)?;
        fs::create_dir(exposed)?;
        mount(
            child.to_str().ok_or("child path invalid")?,
            exposed.to_str().ok_or("exposed path invalid")?,
            "",
            libc::MS_BIND,
            "",
        )?;
        filesystem.exposed_mounted = true;
        Ok(filesystem)
    }

    fn usage(&self, include_logical: bool, envelope: &TrialEnvelope) -> Result<(u64, u64, bool)> {
        let statistics = statfs(&self.private_mount)?;
        let free_bytes = (statistics.f_bavail as u64)
            .checked_mul(statistics.f_bsize as u64)
            .ok_or("ext4 free space overflow")?;
        // The backing length also covers superblocks, bitmaps and inode tables
        // omitted by statfs.f_blocks. Never subtract the formatter's baseline:
        // its metadata and the private inode-reservation tree consume custody.
        let physical_bytes = self
            .maximum_bytes
            .checked_sub(free_bytes)
            .ok_or("ext4 free space exceeds backing")?;
        let physical_entries = (statistics.f_files as u64)
            .checked_sub(statistics.f_ffree as u64)
            .ok_or("ext4 free inode count invalid")?;
        let (logical_bytes, logical_entries) = if include_logical {
            logical_filesystem_usage(&self.exposed, &|| envelope.check_finalization())?
        } else {
            (0, 0)
        };
        Ok((
            physical_bytes.max(logical_bytes),
            physical_entries.max(logical_entries),
            statistics.f_bavail == 0 || statistics.f_ffree == 0,
        ))
    }

    fn cleanup(mut self) -> Result<()> {
        self.cleanup_inner()
    }

    fn cleanup_inner(&mut self) -> Result<()> {
        if self.exposed_mounted {
            unmount(&self.exposed)?;
            self.exposed_mounted = false;
        }
        if self.private_mounted {
            unmount(&self.private_mount)?;
            self.private_mounted = false;
        }
        if self.loop_attached {
            let loop_file = self.loop_file.as_ref().ok_or("loop device handle absent")?;
            if unsafe { libc::ioctl(loop_file.as_raw_fd(), LOOP_CLR_FD as _) } != 0 {
                return Err(std::io::Error::last_os_error().into());
            }
            self.loop_attached = false;
        }
        self.loop_file.take();
        fs::remove_file(&self.backing)?;
        if let Some(base) = self.private_mount.parent() {
            fs::remove_dir_all(base)?;
        }
        let _ = fs::remove_dir(&self.exposed);
        Ok(())
    }
}

impl Drop for BoundedFilesystem {
    fn drop(&mut self) {
        let _ = self.cleanup_inner();
    }
}

fn unmount(path: &Path) -> Result<()> {
    let path = std::ffi::CString::new(path.as_os_str().as_encoded_bytes())?;
    if unsafe { libc::umount2(path.as_ptr(), 0) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    Ok(())
}

// Smol's minimal /dev need not contain loop nodes. Only the trusted bootstrap
// creates them, before any workload runs; existing image-owned paths must match
// the exact kernel device rather than being followed or replaced.
fn ensure_device_node(path: &Path, kind: libc::mode_t, major: u32, minor: u32) -> Result<()> {
    let device = libc::makedev(major, minor);
    match fs::symlink_metadata(path) {
        Ok(_) => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            let name = std::ffi::CString::new(path.as_os_str().as_encoded_bytes())?;
            if unsafe { libc::mknod(name.as_ptr(), kind | 0o600, device) } != 0 {
                return Err(std::io::Error::last_os_error().into());
            }
        }
        Err(error) => return Err(error.into()),
    }
    let metadata = fs::symlink_metadata(path)?;
    let correct_kind = match kind {
        libc::S_IFCHR => metadata.file_type().is_char_device(),
        libc::S_IFBLK => metadata.file_type().is_block_device(),
        _ => false,
    };
    if !correct_kind || metadata.rdev() != device {
        return Err("trial loop device node differs".into());
    }
    Ok(())
}

fn statfs(path: &Path) -> Result<libc::statfs> {
    let path = std::ffi::CString::new(path.as_os_str().as_encoded_bytes())?;
    let mut value = std::mem::MaybeUninit::<libc::statfs>::uninit();
    if unsafe { libc::statfs(path.as_ptr(), value.as_mut_ptr()) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    Ok(unsafe { value.assume_init() })
}

fn reserve_surplus_inodes(root: &Path, maximum_free: u64, envelope: &TrialEnvelope) -> Result<()> {
    let reserve = root.join(".workstream-reserved-inodes");
    fs::create_dir(&reserve)?;
    fs::set_permissions(&reserve, fs::Permissions::from_mode(0o000))?;
    let initial = statfs(root)?.f_ffree as u64;
    let surplus = initial.saturating_sub(maximum_free);
    if surplus > 65_536 {
        return Err("ext4 inode rounding is unbounded".into());
    }
    for index in 0..surplus {
        envelope.check()?;
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o000)
            .open(reserve.join(index.to_string()))?;
    }
    if statfs(root)?.f_ffree as u64 > maximum_free {
        return Err("ext4 inode quota unavailable".into());
    }
    Ok(())
}

fn valid_component(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
}

fn valid_relative(value: &str) -> bool {
    value == "."
        || (!value.is_empty()
            && !value.contains('\\')
            && !value.contains('\0')
            && Path::new(value)
                .components()
                .all(|part| matches!(part, Component::Normal(_))))
}

fn valid_environment(values: &[String]) -> bool {
    let mut keys = HashSet::new();
    values.len() <= 1024
        && values.iter().all(|value| {
            let Some((key, content)) = value.split_once('=') else {
                return false;
            };
            !key.is_empty()
                && key.len() <= 128
                && content.len() <= 64 * 1024
                && !content.contains('\0')
                && key.bytes().enumerate().all(|(index, byte)| {
                    byte == b'_'
                        || byte.is_ascii_alphabetic()
                        || (index > 0 && byte.is_ascii_digit())
                })
                && keys.insert(key)
        })
}

fn valid_limit(limit: TrialFilesystemLimit) -> bool {
    limit.bytes >= MINIMUM_TRIAL_FILESYSTEM_BYTES
        && limit.entries >= MINIMUM_TRIAL_FILESYSTEM_ENTRIES
}

fn valid_child_limits(limits: TrialChildLimits) -> bool {
    limits.cpu_quota_millis > 0
        && limits.cpu_time_ms > 0
        && limits.finalization_cpu_time_ms >= limits.cpu_time_ms
        && limits.memory_bytes > 0
        && limits.pids >= MINIMUM_TRIAL_PIDS
        && limits.timeout_ms > 0
        && limits.finalization_timeout_ms >= limits.timeout_ms
        && limits.output_bytes > 0
        && limits.output_bytes <= TRIAL_OUTPUT_MAXIMUM_BYTES
}

fn validate_request(job: &GuestJob, request: &TrialRequest) -> Result<()> {
    if job.command.is_empty()
        || job.command.len() > 256
        || job
            .command
            .iter()
            .any(|value| value.is_empty() || value.len() > 4096 || value.contains('\0'))
        || !valid_environment(&job.environment)
    {
        return Err("trial command configuration invalid".into());
    }
    match request {
        TrialRequest::Build {
            schema_version,
            operation_id,
            context_relative,
            dockerfile_relative,
            platform,
            destination,
            limits,
            root,
            tmp,
            shm,
            candidate_archive_max_bytes,
            output_max_bytes,
        } => {
            if schema_version != REQUEST_SCHEMA
                || !valid_component(operation_id)
                || !valid_relative(context_relative)
                || !valid_relative(dockerfile_relative)
                || platform != "linux/amd64"
                || !destination.starts_with("workstream-trial:")
                || !valid_child_limits(*limits)
                || !valid_limit(*root)
                || !valid_limit(*tmp)
                || !valid_limit(*shm)
                || *candidate_archive_max_bytes == 0
                || *candidate_archive_max_bytes > root.bytes
                || *output_max_bytes != limits.output_bytes
            {
                return Err("trial build request invalid".into());
            }
        }
        TrialRequest::Step {
            schema_version,
            operation_id,
            visible_roles,
            limits,
            root,
            workspace,
            tmp,
            shm,
            output_max_bytes,
        } => {
            if schema_version != REQUEST_SCHEMA
                || !valid_component(operation_id)
                || visible_roles.len() > 64
                || !valid_child_limits(*limits)
                || !valid_limit(*root)
                || !valid_limit(*workspace)
                || !valid_limit(*tmp)
                || !valid_limit(*shm)
                || *output_max_bytes != limits.output_bytes
                || (job.working_directory != "." && !valid_relative(&job.working_directory))
            {
                return Err("trial step request invalid".into());
            }
        }
    }
    Ok(())
}

fn require_static_tool(path: &str) -> Result<()> {
    let metadata = fs::symlink_metadata(path)?;
    if !metadata.file_type().is_file()
        || metadata.file_type().is_symlink()
        || metadata.uid() != 0
        || metadata.permissions().mode() & 0o022 != 0
    {
        return Err("trusted trial tool custody invalid".into());
    }
    Ok(())
}

fn bind_readonly(source: &Path, destination: &Path) -> Result<()> {
    fs::create_dir(destination)?;
    mount(
        source.to_str().ok_or("source path invalid")?,
        destination.to_str().ok_or("destination path invalid")?,
        "",
        libc::MS_BIND | libc::MS_REC,
        "",
    )?;
    mount(
        "",
        destination.to_str().ok_or("destination path invalid")?,
        "",
        libc::MS_BIND | libc::MS_REMOUNT | libc::MS_RDONLY | libc::MS_NOSUID | libc::MS_NODEV,
        "",
    )
}

fn prepare_bootstrap(
    staged: &StagedJob,
    request: &TrialRequest,
    export_uid: u32,
    export_gid: u32,
) -> Result<()> {
    fs::create_dir(BOOTSTRAP)?;
    fs::create_dir(EXPORT)?;
    fs::set_permissions(EXPORT, fs::Permissions::from_mode(0o700))?;
    let export = std::ffi::CString::new(EXPORT)?;
    if unsafe { libc::chown(export.as_ptr(), export_uid, export_gid) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    fs::create_dir(format!("{BOOTSTRAP}/input"))?;
    match request {
        TrialRequest::Build { .. } => {
            if staged.root("context").is_none() || staged.root("cache").is_none() {
                return Err("trial build materials invalid".into());
            }
            bind_readonly(
                staged.root("context").unwrap(),
                Path::new(BOOTSTRAP).join("input/context").as_path(),
            )?;
            bind_readonly(
                staged.root("cache").unwrap(),
                Path::new(BOOTSTRAP).join("input/cache").as_path(),
            )?;
        }
        TrialRequest::Step { visible_roles, .. } => {
            let workspace = staged
                .root("workspace")
                .ok_or("workspace material missing")?;
            bind_readonly(
                workspace,
                Path::new(BOOTSTRAP).join("input/workspace").as_path(),
            )?;
            fs::create_dir(format!("{BOOTSTRAP}/input/roles"))?;
            let mut names = HashSet::new();
            for role in visible_roles {
                if !valid_component(&role.role)
                    || !valid_component(&role.destination)
                    || !names.insert(role.role.as_str())
                {
                    return Err("visible role invalid".into());
                }
                let source = staged
                    .root(&role.role)
                    .ok_or("visible role material missing")?;
                bind_readonly(
                    source,
                    &Path::new(BOOTSTRAP).join("input/roles").join(&role.role),
                )?;
            }
        }
    }
    Ok(())
}

fn configure_cgroup(limits: TrialChildLimits) -> Result<()> {
    let root = Path::new("/sys/fs/cgroup");
    fs::write(root.join("cgroup.subtree_control"), "+cpu +memory +pids")?;
    fs::create_dir(CGROUP)?;
    fs::write(
        Path::new(CGROUP).join("cpu.max"),
        format!("{} 100000", limits.cpu_quota_millis.saturating_mul(100)),
    )?;
    fs::write(
        Path::new(CGROUP).join("memory.max"),
        limits.memory_bytes.to_string(),
    )?;
    disable_swap(Path::new(CGROUP), Path::new("/proc/meminfo"))?;
    // A whole-parent OOM may lose the trusted supervisor; the host then rejects
    // the incomplete exchange. Never grant an unaccounted control reservation.
    fs::write(Path::new(CGROUP).join("memory.oom.group"), "0")?;
    fs::write(Path::new(CGROUP).join("pids.max"), limits.pids.to_string())?;
    fs::write(
        Path::new(CGROUP).join("cgroup.subtree_control"),
        "+cpu +memory +pids",
    )?;
    fs::create_dir(CONTROL_CGROUP)?;
    fs::create_dir(WORKLOAD_CGROUP)?;
    fs::write(Path::new(WORKLOAD_CGROUP).join("memory.oom.group"), "1")?;
    // Exact peaks are a required kernel capability, not a sampled substitute.
    cgroup_value("pids.peak")?;
    cgroup_value("memory.peak")?;
    fs::write(Path::new(CONTROL_CGROUP).join("cgroup.procs"), "0")?;
    Ok(())
}

fn cgroup_value(path: &str) -> Result<u64> {
    Ok(fs::read_to_string(Path::new(CGROUP).join(path))?
        .trim()
        .parse()?)
}

fn cgroup_cpu_ms() -> Result<u64> {
    let value = fs::read_to_string(Path::new(CGROUP).join("cpu.stat"))?;
    let usage = value
        .lines()
        .find_map(|line| line.strip_prefix("usage_usec "))
        .ok_or("cgroup CPU fact missing")?;
    Ok(usage.parse::<u64>()? / 1000)
}

fn cgroup_oom_kills() -> Result<u64> {
    let value = fs::read_to_string(Path::new(CGROUP).join("memory.events"))?;
    Ok(value
        .lines()
        .find_map(|line| line.strip_prefix("oom_kill "))
        .ok_or("cgroup OOM fact missing")?
        .parse()?)
}

fn cgroup_pid_limit_hits() -> Result<u64> {
    let value = fs::read_to_string(Path::new(CGROUP).join("pids.events"))?;
    Ok(value
        .lines()
        .find_map(|line| line.strip_prefix("max "))
        .ok_or("cgroup PID fact missing")?
        .parse()?)
}

fn filesystem_usage(
    filesystems: &[BoundedFilesystem],
    include_logical: bool,
    envelope: &TrialEnvelope,
) -> Result<(u64, u64, bool)> {
    filesystems
        .iter()
        .try_fold((0_u64, 0_u64, false), |total, filesystem| {
            envelope.check_finalization()?;
            let usage = filesystem.usage(include_logical, envelope)?;
            Ok((
                total.0.checked_add(usage.0).ok_or("disk usage overflow")?,
                total.1.checked_add(usage.1).ok_or("entry usage overflow")?,
                total.2 || usage.2,
            ))
        })
}

fn launcher_arguments(job: &GuestJob, request: &TrialRequest) -> Result<Vec<String>> {
    let mut result = Vec::new();
    match request {
        TrialRequest::Build {
            root,
            tmp,
            shm,
            candidate_archive_max_bytes,
            ..
        } => {
            result.extend([
                "builder".into(),
                "--root-bytes".into(),
                root.bytes.to_string(),
            ]);
            result.extend(["--root-inodes".into(), root.entries.to_string()]);
            result.extend(["--tmp-bytes".into(), tmp.bytes.to_string()]);
            result.extend(["--tmp-inodes".into(), tmp.entries.to_string()]);
            result.extend(["--shm-bytes".into(), shm.bytes.to_string()]);
            result.extend(["--shm-inodes".into(), shm.entries.to_string()]);
            result.extend([
                "--candidate-bytes".into(),
                candidate_archive_max_bytes.to_string(),
            ]);
        }
        TrialRequest::Step {
            root,
            workspace,
            tmp,
            shm,
            visible_roles,
            ..
        } => {
            result.extend(["step".into(), "--root-bytes".into(), root.bytes.to_string()]);
            result.extend(["--root-inodes".into(), root.entries.to_string()]);
            result.extend(["--workspace-bytes".into(), workspace.bytes.to_string()]);
            result.extend(["--workspace-inodes".into(), workspace.entries.to_string()]);
            result.extend(["--tmp-bytes".into(), tmp.bytes.to_string()]);
            result.extend(["--tmp-inodes".into(), tmp.entries.to_string()]);
            result.extend(["--shm-bytes".into(), shm.bytes.to_string()]);
            result.extend(["--shm-inodes".into(), shm.entries.to_string()]);
            result.extend(["--working-directory".into(), job.working_directory.clone()]);
            result.extend([
                "--uid".into(),
                job.uid.to_string(),
                "--gid".into(),
                job.gid.to_string(),
            ]);
            for role in visible_roles {
                result.extend([
                    "--visible".into(),
                    format!("{}={}", role.role, role.destination),
                ]);
            }
        }
    }
    result.extend(["--export-uid".into(), job.uid.to_string()]);
    result.extend(["--export-gid".into(), job.gid.to_string(), "--".into()]);
    result.extend(job.command.iter().cloned());
    Ok(result)
}

fn request_limits(request: &TrialRequest) -> TrialChildLimits {
    match request {
        TrialRequest::Build { limits, .. } | TrialRequest::Step { limits, .. } => *limits,
    }
}

fn request_operation(request: &TrialRequest) -> &str {
    match request {
        TrialRequest::Build { operation_id, .. } | TrialRequest::Step { operation_id, .. } => {
            operation_id
        }
    }
}

fn validate_material_contract(job: &GuestJob, request: &TrialRequest) -> Result<()> {
    let materials = match &job.purpose {
        GuestPurpose::TrialBuild { materials } | GuestPurpose::TrialStep { materials } => materials,
        _ => return Err("trial purpose invalid".into()),
    };
    let actual = materials
        .iter()
        .map(|material| material.name.as_str())
        .collect::<HashSet<_>>();
    if actual.len() != materials.len() {
        return Err("duplicate trial material root".into());
    }
    let expected = match request {
        TrialRequest::Build { .. } => HashSet::from(["context", "cache"]),
        TrialRequest::Step { visible_roles, .. } => {
            let mut expected = HashSet::from(["workspace"]);
            expected.extend(visible_roles.iter().map(|role| role.role.as_str()));
            expected
        }
    };
    if actual != expected {
        return Err("trial material roots differ".into());
    }
    Ok(())
}

fn filesystem_specs(
    request: &TrialRequest,
) -> Vec<(&'static str, TrialFilesystemLimit, PathBuf, u32)> {
    match request {
        TrialRequest::Build { root, tmp, shm, .. } => vec![
            ("root", *root, PathBuf::from(ROOT), 0o755),
            ("tmp", *tmp, Path::new(ROOT).join("tmp"), 0o1777),
            ("shm", *shm, Path::new(ROOT).join("dev/shm"), 0o1777),
        ],
        TrialRequest::Step {
            root,
            workspace,
            tmp,
            shm,
            ..
        } => vec![
            ("root", *root, PathBuf::from(ROOT), 0o755),
            (
                "workspace",
                *workspace,
                Path::new(ROOT).join("workspace"),
                0o700,
            ),
            ("tmp", *tmp, Path::new(ROOT).join("tmp"), 0o1777),
            ("shm", *shm, Path::new(ROOT).join("dev/shm"), 0o1777),
        ],
    }
}

fn create_filesystems(
    request: &TrialRequest,
    envelope: &TrialEnvelope,
) -> Result<Vec<BoundedFilesystem>> {
    let operation = request_operation(request);
    if !valid_component(operation) {
        return Err("trial operation id invalid".into());
    }
    fs::create_dir(FILESYSTEMS)?;
    let specs = filesystem_specs(request);
    let mut result = Vec::new();
    for (index, (name, limit, exposed, mode)) in specs.into_iter().enumerate() {
        if index > 0 {
            if let Some(parent) = exposed.parent() {
                fs::create_dir_all(parent)?;
            }
        }
        envelope.check()?;
        result.push(BoundedFilesystem::create(
            operation, name, limit, &exposed, mode, envelope,
        )?);
    }
    Ok(result)
}

fn parse_status() -> Result<LauncherStatus> {
    let path = Path::new(EXPORT).join("status.json");
    let metadata = fs::symlink_metadata(&path)?;
    if !metadata.file_type().is_file()
        || metadata.file_type().is_symlink()
        || metadata.len() > STATUS_MAXIMUM
    {
        return Err("launcher status invalid".into());
    }
    Ok(serde_json::from_slice(&fs::read(path)?)?)
}

fn classify_status(
    request: &TrialRequest,
    status: &LauncherStatus,
) -> Result<(TrialChildOutcome, TrialExportOutcome)> {
    if status.schema != "workstream.trial_launcher_status.v1"
        || status.candidate_exported && status.workspace_exported
        || matches!(request, TrialRequest::Build { .. }) && status.workspace_exported
        || matches!(request, TrialRequest::Step { .. }) && status.candidate_exported
        || status.export_failure.is_some()
            && (status.candidate_exported || status.workspace_exported)
    {
        return Err("launcher status invalid".into());
    }
    let child = status.child;
    if !child.is_executed() {
        return Err("launcher child outcome invalid".into());
    }
    let outcome = match status.export_failure.as_deref() {
        None if status.candidate_exported || status.workspace_exported => {
            TrialExportOutcome::Exported
        }
        None => TrialExportOutcome::NotStarted,
        Some("capacity_exceeded") => TrialExportOutcome::CapacityExceeded,
        Some("invalid") => TrialExportOutcome::Invalid,
        _ => return Err("launcher export status invalid".into()),
    };
    Ok((child, outcome))
}

fn digest_file(path: &Path, check: &impl Fn() -> Result<()>) -> Result<(u64, String)> {
    check()?;
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)?;
    let length = file.metadata()?.len();
    let mut remaining = length;
    let mut hash = Sha256::new();
    let mut buffer = [0_u8; 65_536];
    while remaining > 0 {
        check()?;
        let maximum = remaining.min(buffer.len() as u64) as usize;
        let count = file.read(&mut buffer[..maximum])?;
        if count == 0 {
            return Err("trial export changed while hashing".into());
        }
        hash.update(&buffer[..count]);
        remaining -= count as u64;
    }
    check()?;
    if file.read(&mut buffer[..1])? != 0 {
        return Err("trial export grew while hashing".into());
    }
    Ok((length, format!("sha256:{:x}", hash.finalize())))
}

fn run_formatter(command: &mut Command, envelope: &TrialEnvelope) -> Result<()> {
    envelope.check()?;
    let mut formatter = command.spawn()?;
    let result = (|| loop {
        envelope.check()?;
        if let Some(status) = formatter.try_wait()? {
            return if status.success() {
                Ok(())
            } else {
                Err("trusted ext4 formatter failed".into())
            };
        }
        std::thread::sleep(Duration::from_millis(2));
    })();
    if result.is_err() {
        let _ = formatter.kill();
        // Cleanup consumes only the existing hard finalization allowance.
        while formatter.try_wait()?.is_none() {
            envelope.check_finalization()?;
            std::thread::sleep(Duration::from_millis(2));
        }
    }
    result
}

pub(crate) fn set_nonblocking<T: AsRawFd>(value: &T) -> Result<()> {
    let descriptor = value.as_raw_fd();
    let flags = unsafe { libc::fcntl(descriptor, libc::F_GETFL) };
    if flags < 0 || unsafe { libc::fcntl(descriptor, libc::F_SETFL, flags | libc::O_NONBLOCK) } < 0
    {
        return Err(std::io::Error::last_os_error().into());
    }
    Ok(())
}

fn drain_outputs<O: Read, E: Read>(
    stdout: &mut O,
    stderr: &mut E,
    stdout_capture: &mut OutputCapture,
    stderr_capture: &mut OutputCapture,
    maximum: u64,
) -> Result<bool> {
    let used = stdout_capture
        .bytes
        .checked_add(stderr_capture.bytes)
        .ok_or("trial output byte count overflow")?;
    let mut exceeded = stdout_capture.drain(stdout, maximum.saturating_sub(used))?;
    let used = stdout_capture
        .bytes
        .checked_add(stderr_capture.bytes)
        .ok_or("trial output byte count overflow")?;
    exceeded |= stderr_capture.drain(stderr, maximum.saturating_sub(used))?;
    Ok(exceeded)
}

fn write_guarded(
    output: &mut impl Write,
    mut bytes: &[u8],
    check: &impl Fn() -> Result<()>,
) -> Result<()> {
    while !bytes.is_empty() {
        check()?;
        match output.write(bytes) {
            Ok(0) => return Err("trial export output closed".into()),
            Ok(count) => bytes = &bytes[count..],
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                std::thread::sleep(Duration::from_millis(2));
            }
            Err(error) if error.kind() == std::io::ErrorKind::Interrupted => {}
            Err(error) => return Err(error.into()),
        }
    }
    check()
}

fn write_json_frame(
    output: &mut impl Write,
    document: &impl serde::Serialize,
    check: &impl Fn() -> Result<()>,
) -> Result<()> {
    check()?;
    let bytes = serde_json::to_vec(document)?;
    if bytes.is_empty() || bytes.len() > 1024 * 1024 {
        return Err("trial frame unbounded".into());
    }
    write_guarded(output, &(bytes.len() as u32).to_be_bytes(), check)?;
    write_guarded(output, &bytes, check)
}

fn copy_export_file(
    output: &mut impl Write,
    path: &Path,
    byte_count: u64,
    check: &impl Fn() -> Result<()>,
) -> Result<()> {
    check()?;
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)?;
    if file.metadata()?.len() != byte_count {
        return Err("trial export length changed".into());
    }
    let mut remaining = byte_count;
    let mut buffer = [0_u8; 65_536];
    while remaining > 0 {
        check()?;
        let maximum = remaining.min(buffer.len() as u64) as usize;
        let count = file.read(&mut buffer[..maximum])?;
        if count == 0 {
            return Err("trial export truncated".into());
        }
        write_guarded(output, &buffer[..count], check)?;
        remaining -= count as u64;
    }
    check()?;
    if file.read(&mut buffer[..1])? != 0 {
        return Err("trial export grew while streaming".into());
    }
    Ok(())
}

fn write_export(
    output: &mut impl Write,
    export: Option<&TrialExport>,
    check: &impl Fn() -> Result<()>,
) -> Result<()> {
    match export {
        Some(TrialExport::CandidateArchive { byte_count, .. }) => {
            copy_export_file(
                output,
                &Path::new(EXPORT).join("candidate.tar"),
                *byte_count,
                check,
            )?;
        }
        Some(TrialExport::Workspace { files, .. }) => {
            for entry in files {
                copy_export_file(
                    output,
                    &Path::new(EXPORT)
                        .join("workspace.next")
                        .join(&entry.normalized_path),
                    entry.byte_count,
                    check,
                )?;
            }
        }
        None => {}
    }
    Ok(())
}

pub(crate) fn run(
    job: &GuestJob,
    staged: &StagedJob,
    request: TrialRequest,
    mut envelope: TrialEnvelope,
) -> Result<()> {
    envelope.check()?;
    require_static_tool(LAUNCHER)?;
    require_static_tool(MKFS)?;
    prepare_bootstrap(staged, &request, job.uid, job.gid)?;
    envelope.check()?;
    let filesystems = create_filesystems(&request, &envelope)?;
    if unsafe { libc::unshare(libc::CLONE_NEWPID) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    envelope.check()?;
    let limits = envelope.limits;
    let mut command = Command::new(LAUNCHER);
    command
        .args(launcher_arguments(job, &request)?)
        .env_clear()
        .envs(
            job.environment
                .iter()
                .map(|value| value.split_once('=').expect("validated environment")),
        )
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    // Keep launcher-created binds, proc and device mounts out of the supervisor's
    // namespace. Once descendants are drained, those mounts disappear and the
    // supervisor can normally unmount its exact owned filesystems.
    // Only async-signal-safe syscalls run between fork and exec.
    unsafe {
        command.pre_exec(|| {
            if libc::unshare(libc::CLONE_NEWNS) != 0 {
                return Err(std::io::Error::last_os_error());
            }
            if libc::mount(
                std::ptr::null(),
                c"/".as_ptr(),
                std::ptr::null(),
                libc::MS_REC | libc::MS_PRIVATE,
                std::ptr::null(),
            ) != 0
            {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }
    let mut child = command.spawn()?;
    let mut stdout = child.stdout.take().ok_or("trial stdout unavailable")?;
    let mut stderr = child.stderr.take().ok_or("trial stderr unavailable")?;
    set_nonblocking(&stdout)?;
    set_nonblocking(&stderr)?;
    let mut stdout_capture = OutputCapture::new();
    let mut stderr_capture = OutputCapture::new();
    let mut output_exceeded = false;
    let mut child_status = None;

    let mut forced = None;
    let mut cpu_time_ms = 0;
    let mut peak_memory_bytes = 0;
    let mut peak_pids = 0;
    let mut written_bytes = 0;
    let mut written_entries = 0;
    let status = loop {
        output_exceeded |= drain_outputs(
            &mut stdout,
            &mut stderr,
            &mut stdout_capture,
            &mut stderr_capture,
            limits.output_bytes,
        )?;
        if child_status.is_none() {
            child_status = child.try_wait()?;
        }
        if child_status.is_some() {
            output_exceeded |= drain_outputs(
                &mut stdout,
                &mut stderr,
                &mut stdout_capture,
                &mut stderr_capture,
                limits.output_bytes,
            )?;
            if stdout_capture.eof && stderr_capture.eof {
                break child_status.expect("checked child status");
            }
        }
        cpu_time_ms = cpu_time_ms.max(cgroup_cpu_ms()?);
        peak_memory_bytes = peak_memory_bytes.max(cgroup_value("memory.peak")?);
        peak_pids = peak_pids.max(cgroup_value("pids.peak")?);
        let usage = filesystem_usage(&filesystems, false, &envelope)?;
        written_bytes = written_bytes.max(usage.0);
        written_entries = written_entries.max(usage.1);
        envelope.check_finalization()?;
        let cause = if let Some(cause) = envelope.cause()? {
            Some(cause)
        } else if usage.2 {
            Some(TrialTermination::DiskExceeded)
        } else if output_exceeded {
            Some(TrialTermination::OutputExceeded)
        } else {
            None
        };
        if forced.is_none() && cause.is_some() {
            forced = cause;
            fs::write(Path::new(WORKLOAD_CGROUP).join("cgroup.kill"), "1")?;
        }
        std::thread::sleep(Duration::from_millis(5));
    };

    cpu_time_ms = cpu_time_ms.max(cgroup_cpu_ms()?);
    peak_memory_bytes = peak_memory_bytes.max(cgroup_value("memory.peak")?);
    peak_pids = peak_pids.max(cgroup_value("pids.peak")?);
    let usage = filesystem_usage(&filesystems, true, &envelope)?;
    written_bytes = written_bytes.max(usage.0);
    written_entries = written_entries.max(usage.1);
    output_exceeded |= drain_outputs(
        &mut stdout,
        &mut stderr,
        &mut stdout_capture,
        &mut stderr_capture,
        limits.output_bytes,
    )?;
    if forced.is_none() {
        forced = if let Some(cause) = envelope.cause()? {
            Some(cause)
        } else if usage.2 {
            Some(TrialTermination::DiskExceeded)
        } else if output_exceeded {
            Some(TrialTermination::OutputExceeded)
        } else {
            None
        };
    }
    let stdout = stdout_capture.finish()?;
    let stderr = stderr_capture.finish()?;
    if forced.is_none() && !status.success() {
        return Err("trusted trial launcher failed".into());
    }
    let launcher = if forced.is_none() {
        Some(parse_status()?)
    } else {
        None
    };
    let export_usage = tree_usage(Path::new(EXPORT), &|| envelope.check_finalization())?;
    let (child, export_outcome, export) = if let Some(status) = launcher {
        let (child, outcome) = classify_status(&request, &status)?;
        if status.candidate_exported {
            let path = Path::new(EXPORT).join("candidate.tar");
            let (byte_count, sha256) = digest_file(&path, &|| envelope.check())?;
            (
                child,
                outcome,
                Some(TrialExport::CandidateArchive { byte_count, sha256 }),
            )
        } else if status.workspace_exported {
            let root = Path::new(EXPORT).join("workspace.next");
            let (directories, files) = inventory(&root, &envelope)?;
            (
                child,
                outcome,
                Some(TrialExport::Workspace { directories, files }),
            )
        } else {
            (child, outcome, None)
        }
    } else {
        (
            TrialChildOutcome {
                exit_code: None,
                signal: None,
            },
            TrialExportOutcome::Unavailable,
            None,
        )
    };
    written_bytes = written_bytes
        .checked_add(export_usage.0)
        .ok_or("trial written byte count overflow")?;
    // Output is retained in bounded guest memory and is not charged as disk.
    // The export tree is a physical duplicate outside the bounded child filesystems.
    written_entries = written_entries
        .checked_add(export_usage.1)
        .ok_or("trial written entry count overflow")?;
    let output_descriptor = unsafe { libc::dup(libc::STDOUT_FILENO) };
    if output_descriptor < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    let mut output = unsafe { File::from_raw_fd(output_descriptor) };
    set_nonblocking(&output)?;
    let header = TrialExportHeader {
        schema_version: TRIAL_EXPORT_PROTOCOL.into(),
        operation_id: request_operation(&request).into(),
        export: export.clone(),
        stdout_bytes: stdout.0,
        stdout_sha256: stdout.1.clone(),
        stderr_bytes: stderr.0,
        stderr_sha256: stderr.1.clone(),
    };
    // An interrupted raw payload has no final receipt and cannot be admitted.
    let check_stream = || {
        if forced.is_some() {
            envelope.check_finalization()
        } else {
            envelope.check()
        }
    };
    write_json_frame(&mut output, &header, &check_stream)?;
    write_export(&mut output, export.as_ref(), &check_stream)?;
    write_guarded(&mut output, stdout.2.as_bytes(), &check_stream)?;
    write_guarded(&mut output, stderr.2.as_bytes(), &check_stream)?;
    output.flush()?;
    for filesystem in filesystems.into_iter().rev() {
        envelope.check_finalization()?;
        filesystem.cleanup()?;
    }
    let measurements = envelope.finish()?;
    require_publishable_measurements(limits, forced, &measurements)?;
    cpu_time_ms = cpu_time_ms.max(measurements.cpu_time_ms);
    peak_memory_bytes = peak_memory_bytes.max(measurements.peak_memory_bytes);
    peak_pids = peak_pids.max(measurements.peak_pids);
    let result = TrialChildResult {
        schema_version: TRIAL_CHILD_PROTOCOL.into(),
        operation_id: request_operation(&request).into(),
        termination: forced.unwrap_or(if child.signal.is_some() {
            TrialTermination::Signalled
        } else {
            TrialTermination::Exited
        }),
        child,
        elapsed_ms: measurements.elapsed_ms,
        cpu_time_ms,
        peak_memory_bytes,
        peak_pids,
        stdout: stdout.2,
        stdout_sha256: stdout.1,
        stdout_bytes: stdout.0,
        stderr: stderr.2,
        stderr_sha256: stderr.1,
        stderr_bytes: stderr.0,
        written_bytes,
        written_entries,
        measurement_method: "smol_guest_cgroup_v2_and_bounded_ext4".into(),
        export_outcome,
        export,
        guest_cleanup_confirmed: true,
    };
    if !result.terminal_facts_are_valid() {
        return Err("trial terminal facts invalid".into());
    }
    write_json_frame(&mut output, &result, &|| {
        if Instant::now() >= envelope.finalization_deadline {
            Err("trial final receipt deadline reached".into())
        } else {
            Ok(())
        }
    })?;
    output.flush()?;
    Ok(())
}

fn inventory(root: &Path, envelope: &TrialEnvelope) -> Result<(Vec<String>, Vec<MaterialFile>)> {
    let mut directories = Vec::new();
    let mut files = Vec::new();
    let mut pending = vec![PathBuf::new()];
    while let Some(relative) = pending.pop() {
        envelope.check()?;
        let mut entries =
            fs::read_dir(root.join(&relative))?.collect::<std::io::Result<Vec<_>>>()?;
        entries.sort_by_key(|entry| entry.file_name());
        for entry in entries {
            envelope.check()?;
            let path = entry.path();
            let child = relative.join(entry.file_name());
            let normalized = child.to_str().ok_or("workspace path invalid")?.to_owned();
            let metadata = fs::symlink_metadata(&path)?;
            if metadata.file_type().is_dir() {
                directories.push(normalized);
                pending.push(child);
            } else if metadata.file_type().is_file() {
                let (byte_count, sha256) = digest_file(&path, &|| envelope.check())?;
                files.push(MaterialFile {
                    normalized_path: normalized,
                    byte_count,
                    sha256,
                    executable: metadata.permissions().mode() & 0o111 != 0,
                });
            } else {
                return Err("workspace export contains unsupported entry".into());
            }
        }
    }
    directories.sort();
    files.sort_by(|left, right| left.normalized_path.cmp(&right.normalized_path));
    Ok((directories, files))
}

// Run after the child has stopped. Skip nested mounts: each bounded filesystem
// is measured independently, and image/input bind mounts retain their own
// existing custody charge. Sparse file lengths still consume logical allowance.
fn logical_filesystem_usage(root: &Path, check: &impl Fn() -> Result<()>) -> Result<(u64, u64)> {
    let root_metadata = fs::symlink_metadata(root)?;
    let device = root_metadata.dev();
    let mut bytes = 0_u64;
    let mut entries = 1_u64;
    let mut pending = vec![root.to_owned()];
    while let Some(directory) = pending.pop() {
        check()?;
        for entry in fs::read_dir(directory)? {
            check()?;
            let entry = entry?;
            let metadata = fs::symlink_metadata(entry.path())?;
            if metadata.dev() != device {
                continue;
            }
            entries = entries
                .checked_add(1)
                .ok_or("logical entry count overflow")?;
            if metadata.file_type().is_dir() {
                pending.push(entry.path());
            } else if metadata.file_type().is_file() || metadata.file_type().is_symlink() {
                bytes = bytes
                    .checked_add(metadata.len())
                    .ok_or("logical byte count overflow")?;
            }
        }
    }
    Ok((bytes, entries))
}

fn tree_usage(root: &Path, check: &impl Fn() -> Result<()>) -> Result<(u64, u64)> {
    let metadata = fs::symlink_metadata(root)?;
    if !metadata.file_type().is_dir() || metadata.file_type().is_symlink() {
        return Err("trial export root invalid".into());
    }
    let mut bytes = metadata
        .blocks()
        .checked_mul(512)
        .ok_or("export byte count overflow")?;
    let mut entries = 1_u64;
    let mut pending = vec![root.to_owned()];
    while let Some(directory) = pending.pop() {
        check()?;
        for entry in fs::read_dir(directory)? {
            check()?;
            let entry = entry?;
            let metadata = fs::symlink_metadata(entry.path())?;
            let allocated = metadata
                .blocks()
                .checked_mul(512)
                .ok_or("export byte count overflow")?;
            bytes = bytes
                .checked_add(allocated.max(metadata.len()))
                .ok_or("export byte count overflow")?;
            entries = entries
                .checked_add(1)
                .ok_or("export entry count overflow")?;
            if metadata.file_type().is_dir() {
                pending.push(entry.path());
            } else if metadata.file_type().is_file() && !metadata.file_type().is_symlink() {
                // Already charged the larger of logical and allocated bytes above.
            } else {
                return Err("trial export contains unsupported entry".into());
            }
        }
    }
    Ok((bytes, entries))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture(name: &str) -> PathBuf {
        let root =
            std::env::temp_dir().join(format!("workstream-guest-{name}-{}", std::process::id()));
        fs::create_dir(&root).unwrap();
        root
    }

    #[test]
    fn retained_output_shares_one_bound_and_binds_exact_text() {
        let mut stdout = OutputCapture::new();
        let mut stderr = OutputCapture::new();
        assert!(drain_outputs(
            &mut &b"out"[..],
            &mut &b"error"[..],
            &mut stdout,
            &mut stderr,
            6,
        )
        .unwrap());
        let (bytes, digest, text) = stdout.finish().unwrap();
        assert_eq!((bytes, text.as_str()), (3, "out"));
        assert_eq!(digest, format!("sha256:{:x}", Sha256::digest(b"out")));
        let (bytes, digest, text) = stderr.finish().unwrap();
        assert_eq!((bytes, text.as_str()), (3, "err"));
        assert_eq!(digest, format!("sha256:{:x}", Sha256::digest(b"err")));
    }

    #[test]
    fn output_cut_trims_only_an_incomplete_utf8_tail() {
        for prefix_bytes in 1..=3 {
            let mut capture = OutputCapture::new();
            assert!(capture
                .drain(&mut "a😀z".as_bytes(), 1 + prefix_bytes)
                .unwrap());
            let (count, digest, text) = capture.finish().unwrap();
            assert_eq!((count, text.as_str()), (1, "a"));
            assert_eq!(digest, format!("sha256:{:x}", Sha256::digest(b"a")));
        }
        let mut complete = OutputCapture::new();
        assert!(complete.drain(&mut "a😀z".as_bytes(), 5).unwrap());
        assert_eq!(complete.finish().unwrap().2, "a😀");
        for (bytes, cap) in [(&b"a\xffz"[..], 2), (&b"a\xf0"[..], 2)] {
            let mut invalid = OutputCapture::new();
            invalid.drain(&mut &bytes[..], cap).unwrap();
            assert!(invalid.finish().is_err());
        }
    }

    #[test]
    fn late_finalization_limit_cannot_publish_a_successful_terminal_result() {
        let limits = TrialChildLimits {
            cpu_quota_millis: 1000,
            cpu_time_ms: 100,
            finalization_cpu_time_ms: 120,
            memory_bytes: 1024 * 1024,
            pids: MINIMUM_TRIAL_PIDS,
            timeout_ms: 500,
            finalization_timeout_ms: 550,
            output_bytes: 4096,
        };
        let child = TrialChildOutcome {
            exit_code: Some(0),
            signal: None,
        };
        for (elapsed_ms, cpu_time_ms, publishable) in [
            (499, 99, true),
            (500, 99, false),
            (499, 100, false),
            (501, 101, false),
        ] {
            let measurements = Measurements {
                elapsed_ms,
                cpu_time_ms,
                peak_memory_bytes: 1024,
                peak_pids: 3,
            };
            let mut terminal_bytes = Vec::new();
            let publication = (|| {
                require_publishable_measurements(limits, None, &measurements)?;
                write_json_frame(&mut terminal_bytes, &child, &|| Ok(()))
            })();
            assert_eq!(publication.is_ok(), publishable);
            assert_eq!(!terminal_bytes.is_empty(), publishable);
            assert_eq!(child.exit_code, Some(0));
            assert_eq!(child.signal, None);
        }
        // An actual forced cause is not rewritten by the publication guard.
        for forced in [
            TrialTermination::CpuExceeded,
            TrialTermination::DeadlineExceeded,
        ] {
            let measurements = Measurements {
                elapsed_ms: 510,
                cpu_time_ms: 110,
                peak_memory_bytes: 1024,
                peak_pids: 3,
            };
            require_publishable_measurements(limits, Some(forced), &measurements).unwrap();
        }
    }

    #[test]
    fn swap_control_is_enforced_or_guest_wide_zero_swap_is_proved() {
        let root = fixture("swap");
        let meminfo = root.join("meminfo");
        let group = root.join("group");
        fs::create_dir(&group).unwrap();
        let knob = group.join("memory.swap.max");
        fs::write(&meminfo, "MemTotal: 1048576 kB\nSwapTotal: 0 kB\n").unwrap();
        disable_swap(&group, &meminfo).unwrap();
        assert!(
            !knob.exists(),
            "absent controller must never be synthesized"
        );
        for value in [
            "SwapTotal: 1 kB\n",
            "MemTotal: 1 kB\n",
            "SwapTotal: 0 MB\n",
            "SwapTotal: 0 kB\nSwapTotal: 1 kB\n",
        ] {
            fs::write(&meminfo, value).unwrap();
            assert!(disable_swap(&group, &meminfo).is_err());
        }
        fs::write(&knob, "max\n").unwrap();
        disable_swap(&group, &meminfo).unwrap();
        assert_eq!(fs::read_to_string(&knob).unwrap(), "0");
        fs::remove_file(&knob).unwrap();
        std::os::unix::fs::symlink(&meminfo, &knob).unwrap();
        assert!(disable_swap(&group, &meminfo).is_err());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn loop_nodes_reject_regular_files_symlinks_wrong_kind_and_device() {
        let root = fixture("loop-node");
        let path = root.join("node");
        fs::write(&path, "untrusted").unwrap();
        assert!(ensure_device_node(&path, libc::S_IFCHR, 10, 237).is_err());
        assert_eq!(fs::read_to_string(&path).unwrap(), "untrusted");
        fs::remove_file(&path).unwrap();
        std::os::unix::fs::symlink("/dev/null", &path).unwrap();
        assert!(ensure_device_node(&path, libc::S_IFCHR, 1, 3).is_err());
        ensure_device_node(Path::new("/dev/null"), libc::S_IFCHR, 1, 3).unwrap();
        assert!(ensure_device_node(Path::new("/dev/null"), libc::S_IFCHR, 10, 237).is_err());
        assert!(ensure_device_node(Path::new("/dev/null"), libc::S_IFBLK, 1, 3).is_err());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn export_usage_charges_directory_storage_and_sparse_logical_lengths() {
        let root = fixture("usage");
        let empty = tree_usage(&root, &|| Ok(())).unwrap();
        let file = File::create(root.join("sparse")).unwrap();
        file.set_len(1024 * 1024).unwrap();
        fs::create_dir(root.join("directory")).unwrap();
        fs::write(root.join("directory/status.json"), "{}").unwrap();
        let measured = tree_usage(&root, &|| Ok(())).unwrap();
        assert_eq!(empty.1, 1);
        assert!(empty.0 >= fs::metadata(&root).unwrap().blocks() * 512);
        assert_eq!(measured.1, 4);
        assert!(measured.0 >= 1024 * 1024 + empty.0 + 2);
        assert_eq!(
            logical_filesystem_usage(&root, &|| Ok(())).unwrap(),
            (1024 * 1024 + 2, 4)
        );
        fs::remove_dir_all(root).unwrap();
    }

    fn build_request() -> TrialRequest {
        serde_json::from_value(serde_json::json!({
            "kind": "build",
            "schema_version": REQUEST_SCHEMA,
            "operation_id": "build_a",
            "context_relative": ".",
            "dockerfile_relative": "source/Containerfile",
            "platform": "linux/amd64",
            "destination": "workstream-trial:abc",
            "limits": {"cpu_quota_millis":1000,"cpu_time_ms":1000,"finalization_cpu_time_ms":1100,"memory_bytes":1048576,
                       "pids":8,"timeout_ms":1000,"finalization_timeout_ms":1100,"output_bytes":4096},
            "root": {"bytes":4194304,"entries":32},
            "tmp": {"bytes":4194304,"entries":32},
            "shm": {"bytes":4194304,"entries":32},
            "candidate_archive_max_bytes":1048576,
            "output_max_bytes":4096
        }))
        .unwrap()
    }

    fn build_job() -> GuestJob {
        serde_json::from_value(serde_json::json!({
            "purpose": {"kind": "trial_build", "materials": [
                {"name": "context", "directories": [], "files": []},
                {"name": "cache", "directories": [], "files": []}
            ]},
            "request": build_request(), "command": ["/kaniko/executor"],
            "environment": [], "working_directory": "/", "uid": 1000, "gid": 1000,
            "directories": [], "files": []
        }))
        .unwrap()
    }

    #[test]
    fn bootstrap_arguments_are_closed_bounded_and_optional_only_for_other_purposes() {
        use std::ffi::OsString;
        use std::os::unix::ffi::OsStringExt;
        let limits = request_limits(&build_request());
        let document = serde_json::to_string(&limits).unwrap();
        assert!(parse_bootstrap_limits(std::iter::empty())
            .unwrap()
            .is_none());
        assert_eq!(
            parse_bootstrap_limits(
                [
                    OsString::from(TRIAL_LIMITS_ARGUMENT),
                    OsString::from(&document)
                ]
                .into_iter()
            )
            .unwrap(),
            Some(limits)
        );
        for arguments in [
            vec![OsString::from("--unknown"), OsString::from(&document)],
            vec![OsString::from(TRIAL_LIMITS_ARGUMENT)],
            vec![
                OsString::from(TRIAL_LIMITS_ARGUMENT),
                OsString::from(&document),
                OsString::from("extra"),
            ],
            vec![
                OsString::from(TRIAL_LIMITS_ARGUMENT),
                OsString::from(" ".repeat(TRIAL_LIMITS_MAXIMUM_BYTES + 1)),
            ],
            vec![
                OsString::from(TRIAL_LIMITS_ARGUMENT),
                OsString::from_vec(vec![0xff]),
            ],
        ] {
            assert!(parse_bootstrap_limits(arguments.into_iter()).is_err());
        }
        let mut unknown = serde_json::to_value(limits).unwrap();
        unknown["provider_key"] = true.into();
        assert!(parse_bootstrap_limits(
            [
                OsString::from(TRIAL_LIMITS_ARGUMENT),
                OsString::from(unknown.to_string())
            ]
            .into_iter()
        )
        .is_err());
        let invalid = TrialChildLimits { pids: 2, ..limits };
        assert!(parse_bootstrap_limits(
            [
                OsString::from(TRIAL_LIMITS_ARGUMENT),
                OsString::from(serde_json::to_string(&invalid).unwrap())
            ]
            .into_iter()
        )
        .is_err());
    }

    #[test]
    fn trial_job_requires_early_envelope_and_exact_purpose_and_limits_binding() {
        let mut job = build_job();
        let limits = request_limits(&build_request());
        assert!(bind_bootstrap_job(&job, None).is_err());
        assert!(matches!(
            bind_bootstrap_job(&job, Some(limits)).unwrap(),
            Some(TrialRequest::Build { .. })
        ));
        let mut differences = [limits; 8];
        differences[0].cpu_quota_millis += 1;
        differences[1].cpu_time_ms += 1;
        differences[2].finalization_cpu_time_ms += 1;
        differences[3].memory_bytes += 1;
        differences[4].pids += 1;
        differences[5].timeout_ms += 1;
        differences[6].finalization_timeout_ms += 1;
        differences[7].output_bytes += 1;
        for different in differences {
            assert!(bind_bootstrap_job(&job, Some(different)).is_err());
        }
        job.purpose = GuestPurpose::TrialStep {
            materials: Vec::new(),
        };
        assert!(bind_bootstrap_job(&job, Some(limits)).is_err());
        job.purpose = GuestPurpose::TrustedIntake {
            cpu_millis: 1000,
            memory_bytes: 2 * 1024 * 1024 * 1024,
        };
        assert!(bind_bootstrap_job(&job, Some(limits)).is_err());
        assert!(bind_bootstrap_job(&job, None).unwrap().is_none());
    }

    #[test]
    fn trial_limits_reserve_three_processes_and_bound_finalization() {
        let limits = request_limits(&build_request());
        assert!(valid_child_limits(limits));
        assert!(!valid_child_limits(TrialChildLimits { pids: 2, ..limits }));
        assert!(valid_child_limits(TrialChildLimits { pids: 3, ..limits }));
        assert!(!valid_child_limits(TrialChildLimits {
            finalization_cpu_time_ms: limits.cpu_time_ms - 1,
            ..limits
        }));
        assert!(!valid_child_limits(TrialChildLimits {
            finalization_timeout_ms: limits.timeout_ms - 1,
            ..limits
        }));
    }

    #[test]
    fn hashing_and_export_streaming_obey_the_same_cancellation_boundary() {
        let root = fixture("bounded-stream");
        let path = root.join("payload");
        fs::write(&path, vec![7_u8; 4 * 65_536]).unwrap();
        let checks = std::cell::Cell::new(0);
        let check = || -> Result<()> {
            checks.set(checks.get() + 1);
            if checks.get() >= 4 {
                Err("cancelled".into())
            } else {
                Ok(())
            }
        };
        assert!(digest_file(&path, &check).is_err());
        checks.set(0);
        let mut output = Vec::new();
        assert!(copy_export_file(&mut output, &path, 4 * 65_536, &check).is_err());
        assert!(output.len() <= 65_536);
        assert!(output.len() < 4 * 65_536);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn blocked_export_cannot_prevent_deadline_checks() {
        struct Blocked;
        impl Write for Blocked {
            fn write(&mut self, _: &[u8]) -> std::io::Result<usize> {
                Err(std::io::ErrorKind::WouldBlock.into())
            }
            fn flush(&mut self) -> std::io::Result<()> {
                Ok(())
            }
        }
        let checks = std::cell::Cell::new(0);
        let result = write_guarded(&mut Blocked, b"payload", &|| {
            checks.set(checks.get() + 1);
            if checks.get() >= 3 {
                Err("deadline".into())
            } else {
                Ok(())
            }
        });
        assert!(result.is_err());
        assert_eq!(checks.get(), 3);
    }

    #[test]
    fn continuous_output_yields_to_resource_checks_before_capture_is_full() {
        struct Producer;
        impl Read for Producer {
            fn read(&mut self, bytes: &mut [u8]) -> std::io::Result<usize> {
                bytes.fill(b'x');
                Ok(bytes.len())
            }
        }
        let mut capture = OutputCapture::new();
        assert!(!capture.drain(&mut Producer, 1024 * 1024).unwrap());
        assert!(!capture.eof);
        assert_eq!(capture.bytes, 65_536);
    }

    #[test]
    fn paths_and_environment_contracts_are_closed() {
        assert!(valid_relative("."));
        assert!(valid_relative("source/Containerfile"));
        for value in ["", "../escape", "/absolute", "a/../b", "a\\b"] {
            assert!(!valid_relative(value));
        }
        assert!(valid_environment(&["A=1".into(), "B_TWO=value".into()]));
        assert!(!valid_environment(&["missing_separator".into()]));
        assert!(!valid_environment(&["A=1".into(), "A=2".into()]));
        assert!(!valid_environment(&["1BAD=value".into()]));
        assert!(!valid_environment(&["BAD=value\0hidden".into()]));
    }

    #[test]
    fn launcher_wire_status_accepts_nested_child_and_rejects_substituted_shapes() {
        // The trusted launcher emits this nested status.json contract. A real
        // nonzero child exit is work evidence, not an infrastructure error.
        let document = serde_json::json!({
            "schema": "workstream.trial_launcher_status.v1",
            "child": { "exit_code": 2, "signal": null },
            "candidate_exported": false,
            "workspace_exported": false,
            "export_failure": null
        });
        let status: LauncherStatus = serde_json::from_value(document.clone()).unwrap();
        let (child, outcome) = classify_status(&build_request(), &status).unwrap();
        assert_eq!(child.exit_code, Some(2));
        assert_eq!(outcome, TrialExportOutcome::NotStarted);
        let mut flattened = document.clone();
        flattened.as_object_mut().unwrap().remove("child");
        flattened["child_exit_code"] = 2.into();
        flattened["child_signal"] = serde_json::Value::Null;
        assert!(serde_json::from_value::<LauncherStatus>(flattened).is_err());
        let mut unknown = document.clone();
        unknown["child"]["extra"] = true.into();
        assert!(serde_json::from_value::<LauncherStatus>(unknown).is_err());
        let mut contradictory = document;
        contradictory["child"]["signal"] = 9.into();
        let status = serde_json::from_value(contradictory).unwrap();
        assert!(classify_status(&build_request(), &status).is_err());
    }

    #[test]
    fn launcher_status_cannot_cross_phase_or_mix_export_failure_with_output() {
        let request = build_request();
        let valid_nonzero = LauncherStatus {
            schema: "workstream.trial_launcher_status.v1".into(),
            child: TrialChildOutcome {
                exit_code: Some(2),
                signal: None,
            },
            candidate_exported: false,
            workspace_exported: false,
            export_failure: None,
        };
        assert_eq!(
            classify_status(&request, &valid_nonzero).unwrap().1,
            TrialExportOutcome::NotStarted
        );
        let wrong_phase = LauncherStatus {
            workspace_exported: true,
            ..valid_nonzero
        };
        assert!(classify_status(&request, &wrong_phase).is_err());
        let contradictory = LauncherStatus {
            child: TrialChildOutcome {
                exit_code: Some(0),
                signal: None,
            },
            workspace_exported: false,
            candidate_exported: true,
            export_failure: Some("capacity_exceeded".into()),
            ..wrong_phase
        };
        assert!(classify_status(&request, &contradictory).is_err());
    }

    #[test]
    fn output_bursts_are_drained_without_exceeding_the_aggregate_capture() {
        let prefix = vec![b'a'; 2 * 1024];
        let mut stdout = std::io::Cursor::new(prefix.clone());
        let mut stderr = std::io::Cursor::new(vec![b'b'; 1024 * 1024]);
        let mut stdout_capture = OutputCapture::new();
        let mut stderr_capture = OutputCapture::new();
        let mut exceeded = false;
        while !stdout_capture.eof || !stderr_capture.eof {
            exceeded |= drain_outputs(
                &mut stdout,
                &mut stderr,
                &mut stdout_capture,
                &mut stderr_capture,
                4096,
            )
            .unwrap();
        }
        assert!(exceeded);
        let stdout = stdout_capture.finish().unwrap();
        let stderr = stderr_capture.finish().unwrap();
        assert_eq!(stdout.0, 2048);
        assert_eq!(stderr.0, 2048);
        assert_eq!(stdout.1, format!("sha256:{:x}", Sha256::digest(prefix)));
        assert_eq!(stdout.0 + stderr.0, 4096);
    }
}
