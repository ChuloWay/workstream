//! Startup custody for exclusive ephemeral trial roots, under the service lock.

use super::*;

const MARKER: &str = ".workstream-trial-root.json";
const MAXIMUM_MARKER_BYTES: u64 = 4096;
const MAXIMUM_RECOVERY_ENTRIES: usize = 1_000_000;
const MAXIMUM_RECOVERY_DEPTH: usize = 256;

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Custody {
    schema: String,
    owner: String,
    deployment_owner: String,
    role: String,
    path: PathBuf,
    device: u64,
    inode: u64,
}

pub(crate) struct TrialRoots(Vec<Custody>);

fn root_identity(path: &Path) -> Result<fs::Metadata, String> {
    let metadata = fs::symlink_metadata(path).map_err(|_| "trial root unavailable")?;
    if fs::canonicalize(path).ok().as_deref() != Some(path)
        || !metadata.is_dir()
        || metadata.file_type().is_symlink()
        || metadata.uid() != unsafe { libc::geteuid() }
        || metadata.gid() != unsafe { libc::getegid() }
        || metadata.mode() & 0o7777 != 0o700
    {
        return Err("trial root custody differs".into());
    }
    Ok(metadata)
}

fn read_marker(expected: &Custody) -> Result<(), String> {
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK)
        .open(expected.path.join(MARKER))
        .map_err(|_| "trial root marker unavailable")?;
    let metadata = file
        .metadata()
        .map_err(|_| "trial root marker unavailable")?;
    if !metadata.is_file()
        || metadata.nlink() != 1
        || metadata.uid() != unsafe { libc::geteuid() }
        || metadata.gid() != unsafe { libc::getegid() }
        || metadata.mode() & 0o7777 != 0o600
        || metadata.len() > MAXIMUM_MARKER_BYTES
    {
        return Err("trial root marker custody differs".into());
    }
    let mut bytes = Vec::new();
    Read::by_ref(&mut file)
        .take(MAXIMUM_MARKER_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "trial root marker unavailable")?;
    let actual: Custody =
        serde_json::from_slice(&bytes).map_err(|_| "trial root marker invalid")?;
    if bytes.len() as u64 > MAXIMUM_MARKER_BYTES || &actual != expected {
        return Err("trial root ownership differs".into());
    }
    Ok(())
}

/// Called only while OwnedSocketListener holds the persistent service lock.
/// A root may first be claimed only while empty; a name prefix is never custody.
pub(crate) fn claim(config: &ServiceConfig) -> Result<Option<TrialRoots>, String> {
    let Some(runtime) = &config.trial_runtime else {
        return Ok(None);
    };
    let roots = [
        ("relay", &runtime.relay_root),
        ("scratch", &runtime.scratch_root),
        ("child_home", &runtime.child_home_root),
    ];
    let mut protected = vec![&config.material_root, &runtime.offline_cache_root];
    if let Some(path) = &config.model_relay_root {
        protected.push(path);
    }
    if let Some(smol) = &config.smol {
        protected.extend([&smol.home, &smol.cgroup_root]);
    }
    for (_, path) in roots {
        if roots
            .iter()
            .any(|(_, other)| path != *other && overlaps(path, other))
            || roots.iter().filter(|(_, other)| path == *other).count() != 1
            || protected.iter().any(|other| overlaps(path, other))
            || config.socket_path.starts_with(path)
            || [
                &runtime.trusted_launcher_path,
                &runtime.filesystem_tool_path,
            ]
            .into_iter()
            .any(|asset| asset.starts_with(path))
            || config.smol.as_ref().is_some_and(|smol| {
                smol.binary.starts_with(path) || smol.guest_binary.starts_with(path)
            })
            || config.cache.iter().any(|cache| {
                cache.smol.as_ref().is_some_and(|image| {
                    image.archive.starts_with(path) || image.image_config.starts_with(path)
                })
            })
        {
            return Err("trial roots overlap protected storage".into());
        }
    }
    let mut claims = Vec::new();
    let mut missing = Vec::new();
    for (role, path) in roots {
        let metadata = root_identity(path)?;
        let expected = Custody {
            schema: "workstream.trial_root.v1".into(),
            owner: container_owner(config)?.to_owned(),
            deployment_owner: runtime.deployment_owner.clone(),
            role: role.into(),
            path: path.clone(),
            device: metadata.dev(),
            inode: metadata.ino(),
        };
        match fs::symlink_metadata(path.join(MARKER)) {
            Ok(_) => read_marker(&expected)?,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                if fs::read_dir(path)
                    .map_err(|_| "trial root unavailable")?
                    .next()
                    .is_some()
                {
                    return Err("unclaimed trial root is not empty".into());
                }
                missing.push(expected.clone());
            }
            Err(_) => return Err("trial root marker unavailable".into()),
        }
        claims.push(expected);
    }
    // Validate every root before recording a first claim or deleting anything.
    for expected in missing {
        let bytes = serde_json::to_vec(&expected).map_err(|_| "trial root marker invalid")?;
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(expected.path.join(MARKER))
            .map_err(|_| "trial root claim failed")?;
        file.write_all(&bytes)
            .and_then(|_| file.sync_all())
            .map_err(|_| "trial root claim persistence failed")?;
        File::open(&expected.path)
            .and_then(|root| root.sync_all())
            .map_err(|_| "trial root claim persistence failed")?;
    }
    Ok(Some(TrialRoots(claims)))
}

fn overlaps(left: &Path, right: &Path) -> bool {
    left.starts_with(right) || right.starts_with(left)
}

fn owned_name(role: &str, name: &str) -> bool {
    let hex = |text: &str, length| {
        text.len() == length
            && text
                .bytes()
                .all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f'))
    };
    match role {
        "scratch" => name
            .strip_prefix("trial_")
            .is_some_and(|value| hex(value, 32)),
        "relay" => name
            .strip_prefix(".trial-")
            .is_some_and(|value| hex(value, 16)),
        "child_home" => name
            .strip_prefix("ws-")
            .and_then(|value| value.strip_suffix(".home"))
            .is_some_and(|value| hex(value, 32)),
        _ => false,
    }
}

struct RecoveryBudget {
    remaining: usize,
    deadline: Instant,
}

impl RecoveryBudget {
    fn check(&mut self, depth: usize) -> Result<(), String> {
        if depth > MAXIMUM_RECOVERY_DEPTH || Instant::now() >= self.deadline {
            return Err("trial recovery bound exceeded".into());
        }
        self.remaining = self
            .remaining
            .checked_sub(1)
            .ok_or("trial recovery bound exceeded")?;
        Ok(())
    }
}

fn inspect_entry(
    path: &Path,
    custody: &Custody,
    depth: usize,
    budget: &mut RecoveryBudget,
    remove: bool,
) -> Result<(), String> {
    budget.check(depth)?;
    let metadata = fs::symlink_metadata(path).map_err(|_| "trial recovery identity unavailable")?;
    let socket = metadata.file_type().is_socket();
    if metadata.dev() != custody.device
        || metadata.uid() != unsafe { libc::geteuid() }
        || metadata.gid() != unsafe { libc::getegid() }
        || metadata.file_type().is_symlink()
        || (!metadata.is_dir() && !metadata.is_file() && !(socket && custody.role == "relay"))
        || (metadata.is_file() && metadata.nlink() != 1)
        || (depth == 1 && !metadata.is_dir())
    {
        return Err("trial recovery entry custody differs".into());
    }
    if metadata.is_dir() {
        for entry in fs::read_dir(path).map_err(|_| "trial recovery inventory unavailable")? {
            let entry = entry.map_err(|_| "trial recovery inventory unavailable")?;
            inspect_entry(&entry.path(), custody, depth + 1, budget, remove)?;
        }
    }
    if remove {
        let current = fs::symlink_metadata(path).map_err(|_| "trial recovery identity changed")?;
        if (current.dev(), current.ino(), current.mode())
            != (metadata.dev(), metadata.ino(), metadata.mode())
        {
            return Err("trial recovery identity changed".into());
        }
        if metadata.is_dir() {
            fs::remove_dir(path)
        } else {
            fs::remove_file(path)
        }
        .map_err(|_| "trial recovery cleanup unsettled")?;
    }
    Ok(())
}

impl TrialRoots {
    pub(crate) fn preflight(&self) -> Result<(), String> {
        self.scan(false, Instant::now() + CLEANUP_TIMEOUT)
    }

    /// VM guardians/leases must settle before removing their private homes.
    pub(crate) fn recover(self) -> Result<(), String> {
        self.recover_until(Instant::now() + CLEANUP_TIMEOUT)
    }

    fn recover_until(self, deadline: Instant) -> Result<(), String> {
        // Preflight all residue before removing any entry. Unknown or replaced
        // custody fails closed and preserves foreign material for inspection.
        for remove in [false, true] {
            self.scan(remove, deadline)?;
        }
        Ok(())
    }

    fn scan(&self, remove: bool, deadline: Instant) -> Result<(), String> {
        let mut budget = RecoveryBudget {
            remaining: MAXIMUM_RECOVERY_ENTRIES,
            deadline,
        };
        for custody in &self.0 {
            budget.check(0)?;
            let metadata = root_identity(&custody.path)?;
            if (metadata.dev(), metadata.ino()) != (custody.device, custody.inode) {
                return Err("trial recovery root identity changed".into());
            }
            read_marker(custody)?;
            for entry in fs::read_dir(&custody.path).map_err(|_| "trial root unavailable")? {
                let entry = entry.map_err(|_| "trial root unavailable")?;
                let name = entry.file_name();
                if name == MARKER {
                    continue;
                }
                if !name
                    .to_str()
                    .is_some_and(|name| owned_name(&custody.role, name))
                {
                    return Err("unknown trial root residue".into());
                }
                inspect_entry(&entry.path(), custody, 1, &mut budget, remove)?;
            }
            if remove {
                File::open(&custody.path)
                    .and_then(|root| root.sync_all())
                    .map_err(|_| "trial recovery persistence failed")?;
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::symlink;

    fn configure(config: &mut ServiceConfig, root: &Path) {
        let runtime = TrialRuntimeConfiguration {
            relay_root: root.join("relay"),
            scratch_root: root.join("scratch"),
            child_home_root: root.join("children"),
            outer_runtime_config_digest: String::new(),
            offline_cache_root: root.join("cache"),
            deployment_owner: "test".into(),
            builder_image_id: String::new(),
            trusted_launcher_path: root.join("launcher"),
            trusted_launcher_digest: String::new(),
            filesystem_tool_path: root.join("mkfs"),
            filesystem_tool_digest: String::new(),
            maximum_candidate_archive_bytes: 1024,
        };
        for path in [
            &runtime.relay_root,
            &runtime.scratch_root,
            &runtime.child_home_root,
        ] {
            fs::create_dir_all(path).unwrap();
            fs::set_permissions(path, fs::Permissions::from_mode(0o700)).unwrap();
        }
        config.trial_runtime = Some(runtime);
    }

    fn private_directory(path: &Path) {
        fs::create_dir(path).unwrap();
        fs::set_permissions(path, fs::Permissions::from_mode(0o700)).unwrap();
    }

    #[test]
    fn restart_recovers_abandoned_owned_state() {
        const ROOT: &str = "WORKSTREAM_TRIAL_ROOT_CRASH_PATH";
        const OWNER: &str = "WORKSTREAM_TRIAL_ROOT_CRASH_OWNER";
        if let Some(path) = std::env::var_os(ROOT) {
            let (temporary, mut config) = super::super::tests::test_config();
            config.container_owner = Some(std::env::var(OWNER).unwrap());
            configure(&mut config, Path::new(&path));
            let _custody = claim(&config).unwrap().unwrap();
            let runtime = config.trial_runtime.as_ref().unwrap();
            let scratch = runtime
                .scratch_root
                .join(format!("trial_{}", "a".repeat(32)));
            private_directory(&scratch);
            fs::write(scratch.join("candidate.tar"), b"retained candidate").unwrap();
            let relay = runtime
                .relay_root
                .join(format!(".trial-{}", "b".repeat(16)));
            private_directory(&relay);
            let socket = UnixListener::bind(relay.join("execution.sock")).unwrap();
            fs::set_permissions(
                relay.join("execution.sock"),
                fs::Permissions::from_mode(0o600),
            )
            .unwrap();
            // This directory deliberately has no Smol lease: model the crash
            // between private-home mkdir and per-child lease persistence.
            let home = runtime
                .child_home_root
                .join(format!("ws-{}.home", "c".repeat(32)));
            private_directory(&home);
            fs::write(home.join("partial-image"), b"partially prepared").unwrap();
            fs::remove_dir_all(temporary).unwrap();
            std::mem::forget(socket);
            // Bypass all ordinary Drop/epilogue cleanup in this distinct process.
            std::process::exit(0);
        }
        let (root, mut config) = super::super::tests::test_config();
        configure(&mut config, &root);
        let status = Command::new(std::env::current_exe().unwrap())
            .args([
                "--exact",
                "trial_roots::tests::restart_recovers_abandoned_owned_state",
                "--nocapture",
            ])
            .env(ROOT, &root)
            .env(OWNER, container_owner(&config).unwrap())
            .status()
            .unwrap();
        assert!(status.success());
        let runtime = config.trial_runtime.as_ref().unwrap();
        assert!(fs::read_dir(&runtime.scratch_root).unwrap().count() > 1);
        let custody = claim(&config).unwrap().unwrap();
        custody.preflight().unwrap();
        custody.recover().unwrap();
        for path in [
            &runtime.relay_root,
            &runtime.scratch_root,
            &runtime.child_home_root,
        ] {
            assert_eq!(fs::read_dir(path).unwrap().count(), 1);
            assert!(path.join(MARKER).is_file());
        }
        claim(&config).unwrap().unwrap().recover().unwrap();
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn unclaimed_or_foreign_roots_preserve_even_owned_looking_residue() {
        let (root, mut config) = super::super::tests::test_config();
        configure(&mut config, &root);
        let scratch = &config.trial_runtime.as_ref().unwrap().scratch_root;
        let foreign = scratch.join(format!("trial_{}", "a".repeat(32)));
        private_directory(&foreign);
        fs::write(foreign.join("keep"), b"foreign material").unwrap();
        assert!(claim(&config).is_err());
        assert_eq!(fs::read(foreign.join("keep")).unwrap(), b"foreign material");
        fs::remove_dir_all(&foreign).unwrap();
        claim(&config).unwrap();
        private_directory(&foreign);
        fs::write(foreign.join("keep"), b"previous owner").unwrap();
        config.container_owner = Some("d".repeat(64));
        assert!(claim(&config).is_err());
        assert_eq!(fs::read(foreign.join("keep")).unwrap(), b"previous owner");
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn foreign_symlink_and_expired_cleanup_preserve_all_residue() {
        let (root, mut config) = super::super::tests::test_config();
        configure(&mut config, &root);
        claim(&config).unwrap();
        let runtime = config.trial_runtime.as_ref().unwrap();
        let scratch = runtime
            .scratch_root
            .join(format!("trial_{}", "a".repeat(32)));
        private_directory(&scratch);
        fs::write(scratch.join("keep"), b"owned input").unwrap();
        let home = runtime
            .child_home_root
            .join(format!("ws-{}.home", "b".repeat(32)));
        private_directory(&home);
        let evidence = config.material_root.join("retained-evidence");
        fs::write(&evidence, b"durable evidence").unwrap();
        symlink(&evidence, home.join("foreign-link")).unwrap();
        assert!(claim(&config).unwrap().unwrap().recover().is_err());
        assert_eq!(fs::read(scratch.join("keep")).unwrap(), b"owned input");
        assert_eq!(fs::read(&evidence).unwrap(), b"durable evidence");
        fs::remove_file(home.join("foreign-link")).unwrap();
        assert!(claim(&config)
            .unwrap()
            .unwrap()
            .recover_until(Instant::now())
            .is_err());
        assert!(scratch.join("keep").exists());
        fs::write(runtime.relay_root.join("foreign-resource"), b"keep foreign").unwrap();
        assert!(claim(&config).unwrap().unwrap().preflight().is_err());
        assert!(scratch.join("keep").exists());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn replaced_root_marker_links_and_protected_storage_are_refused() {
        let (root, mut config) = super::super::tests::test_config();
        configure(&mut config, &root);
        claim(&config).unwrap();
        let scratch = config.trial_runtime.as_ref().unwrap().scratch_root.clone();
        let saved = root.join("saved-scratch");
        fs::rename(&scratch, &saved).unwrap();
        private_directory(&scratch);
        fs::copy(saved.join(MARKER), scratch.join(MARKER)).unwrap();
        assert!(claim(&config).is_err());
        fs::remove_dir_all(&scratch).unwrap();
        symlink(&saved, &scratch).unwrap();
        assert!(claim(&config).is_err());
        fs::remove_file(&scratch).unwrap();
        fs::rename(&saved, &scratch).unwrap();
        let marker = scratch.join(MARKER);
        let outside = root.join("marker-link");
        fs::hard_link(&marker, &outside).unwrap();
        assert!(claim(&config).is_err());
        fs::remove_file(outside).unwrap();
        config.trial_runtime.as_mut().unwrap().scratch_root = config.material_root.clone();
        assert!(claim(&config).is_err());
        fs::remove_dir_all(root).unwrap();
    }
}
