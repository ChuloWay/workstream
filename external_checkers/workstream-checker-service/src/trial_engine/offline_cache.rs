//! Exact custody verification for a sealed offline build cache.

use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs::{self, OpenOptions};
use std::io::Read;
use std::os::unix::fs::OpenOptionsExt;
use std::path::{Component, Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Instant;

const MAXIMUM_MANIFEST_BYTES: usize = 1024 * 1024;
const MAXIMUM_CACHE_ENTRIES: usize = 100_000;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum OfflineCacheFailure {
    Invalid,
    Capacity,
    Deadline,
    Cancelled,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct OfflineCacheUsage {
    pub(crate) bytes: u64,
    pub(crate) entries: u64,
}

/// Verify an exact regular-file inventory before any cache bytes enter a guest.
///
/// The manifest is the sibling `cache.sha256`, with canonical lowercase SHA-256
/// lines in the conventional `<digest>  ./<relative-path>` form. The cache root
/// itself must be canonical, so callers cannot authorize one path and stage a
/// symlink-selected tree.
pub(crate) fn verify_offline_cache(
    root: &Path,
    inventory_digest: &str,
    deadline: Instant,
    cancellations: &[&AtomicBool],
) -> Result<OfflineCacheUsage, OfflineCacheFailure> {
    require_available(deadline, cancellations)?;
    if !valid_sha256(inventory_digest) {
        return Err(OfflineCacheFailure::Invalid);
    }
    let canonical = fs::canonicalize(root).map_err(|_| OfflineCacheFailure::Invalid)?;
    let metadata = fs::symlink_metadata(&canonical).map_err(|_| OfflineCacheFailure::Invalid)?;
    if canonical != root || !metadata.file_type().is_dir() || metadata.file_type().is_symlink() {
        return Err(OfflineCacheFailure::Invalid);
    }
    let manifest_path = canonical
        .parent()
        .ok_or(OfflineCacheFailure::Invalid)?
        .join("cache.sha256");
    let manifest = read_bounded_regular(
        &manifest_path,
        MAXIMUM_MANIFEST_BYTES,
        deadline,
        cancellations,
    )?;
    if sha256_bytes(&manifest) != inventory_digest {
        return Err(OfflineCacheFailure::Invalid);
    }
    let mut usage = OfflineCacheUsage {
        bytes: manifest.len() as u64,
        entries: 2,
    };
    verify_manifest(&canonical, &manifest, deadline, cancellations, &mut usage)?;
    Ok(usage)
}

fn verify_manifest(
    root: &Path,
    manifest: &[u8],
    deadline: Instant,
    cancellations: &[&AtomicBool],
    usage: &mut OfflineCacheUsage,
) -> Result<(), OfflineCacheFailure> {
    require_available(deadline, cancellations)?;
    let text = std::str::from_utf8(manifest).map_err(|_| OfflineCacheFailure::Invalid)?;
    let mut expected = BTreeMap::new();
    for line in text.lines() {
        let (digest, relative) = line.split_once("  ").ok_or(OfflineCacheFailure::Invalid)?;
        if !valid_raw_sha256(digest) || !relative.starts_with("./") {
            return Err(OfflineCacheFailure::Invalid);
        }
        let relative = Path::new(&relative[2..]);
        if !valid_relative(relative)
            || expected
                .insert(relative.to_owned(), digest.to_owned())
                .is_some()
        {
            return Err(OfflineCacheFailure::Invalid);
        }
        if expected.len() > MAXIMUM_CACHE_ENTRIES {
            return Err(OfflineCacheFailure::Capacity);
        }
    }
    if expected.is_empty() {
        return Err(OfflineCacheFailure::Invalid);
    }

    let mut actual = Vec::new();
    collect_regular_files(root, root, &mut actual, deadline, cancellations, usage)?;
    if actual.len() != expected.len() {
        return Err(OfflineCacheFailure::Invalid);
    }
    for path in actual {
        let relative = path
            .strip_prefix(root)
            .map_err(|_| OfflineCacheFailure::Invalid)?;
        let digest = expected.get(relative).ok_or(OfflineCacheFailure::Invalid)?;
        if hash_regular_file(&path, deadline, cancellations)? != *digest {
            return Err(OfflineCacheFailure::Invalid);
        }
    }
    Ok(())
}

fn collect_regular_files(
    root: &Path,
    directory: &Path,
    files: &mut Vec<PathBuf>,
    deadline: Instant,
    cancellations: &[&AtomicBool],
    usage: &mut OfflineCacheUsage,
) -> Result<(), OfflineCacheFailure> {
    require_available(deadline, cancellations)?;
    let mut entries = fs::read_dir(directory)
        .map_err(|_| OfflineCacheFailure::Invalid)?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| OfflineCacheFailure::Invalid)?;
    entries.sort_by_key(fs::DirEntry::file_name);
    for entry in entries {
        require_available(deadline, cancellations)?;
        if files.len() >= MAXIMUM_CACHE_ENTRIES {
            return Err(OfflineCacheFailure::Capacity);
        }
        let path = entry.path();
        if !path.starts_with(root) {
            return Err(OfflineCacheFailure::Invalid);
        }
        let metadata = fs::symlink_metadata(&path).map_err(|_| OfflineCacheFailure::Invalid)?;
        usage.entries = usage
            .entries
            .checked_add(1)
            .ok_or(OfflineCacheFailure::Capacity)?;
        if metadata.file_type().is_dir() {
            collect_regular_files(root, &path, files, deadline, cancellations, usage)?;
        } else if metadata.file_type().is_file() && !metadata.file_type().is_symlink() {
            usage.bytes = usage
                .bytes
                .checked_add(metadata.len())
                .ok_or(OfflineCacheFailure::Capacity)?;
            files.push(path);
        } else {
            return Err(OfflineCacheFailure::Invalid);
        }
    }
    Ok(())
}

fn read_bounded_regular(
    path: &Path,
    maximum: usize,
    deadline: Instant,
    cancellations: &[&AtomicBool],
) -> Result<Vec<u8>, OfflineCacheFailure> {
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)
        .map_err(|_| OfflineCacheFailure::Invalid)?;
    let metadata = file.metadata().map_err(|_| OfflineCacheFailure::Invalid)?;
    if !metadata.file_type().is_file() {
        return Err(OfflineCacheFailure::Invalid);
    }
    let mut bytes = Vec::new();
    let mut source = file.by_ref().take(maximum.saturating_add(1) as u64);
    let mut buffer = [0; 32 * 1024];
    loop {
        require_available(deadline, cancellations)?;
        let count = source
            .read(&mut buffer)
            .map_err(|_| OfflineCacheFailure::Invalid)?;
        if count == 0 {
            break;
        }
        bytes.extend_from_slice(&buffer[..count]);
    }
    if bytes.len() > maximum {
        return Err(OfflineCacheFailure::Capacity);
    }
    Ok(bytes)
}

fn hash_regular_file(
    path: &Path,
    deadline: Instant,
    cancellations: &[&AtomicBool],
) -> Result<String, OfflineCacheFailure> {
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)
        .map_err(|_| OfflineCacheFailure::Invalid)?;
    if !file
        .metadata()
        .map_err(|_| OfflineCacheFailure::Invalid)?
        .file_type()
        .is_file()
    {
        return Err(OfflineCacheFailure::Invalid);
    }
    let mut hash = Sha256::new();
    let mut buffer = [0; 64 * 1024];
    loop {
        require_available(deadline, cancellations)?;
        let count = file
            .read(&mut buffer)
            .map_err(|_| OfflineCacheFailure::Invalid)?;
        if count == 0 {
            break;
        }
        hash.update(&buffer[..count]);
    }
    Ok(format!("{:x}", hash.finalize()))
}

fn require_available(
    deadline: Instant,
    cancellations: &[&AtomicBool],
) -> Result<(), OfflineCacheFailure> {
    if cancellations
        .iter()
        .any(|cancelled| cancelled.load(Ordering::SeqCst))
    {
        return Err(OfflineCacheFailure::Cancelled);
    }
    if Instant::now() >= deadline {
        return Err(OfflineCacheFailure::Deadline);
    }
    Ok(())
}

fn valid_relative(path: &Path) -> bool {
    !path.as_os_str().is_empty()
        && !path.is_absolute()
        && path
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
}

fn valid_raw_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f'))
}

fn valid_sha256(value: &str) -> bool {
    value.strip_prefix("sha256:").is_some_and(valid_raw_sha256)
}

fn sha256_bytes(bytes: &[u8]) -> String {
    format!("sha256:{:x}", Sha256::digest(bytes))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::symlink;
    use std::time::{Duration, SystemTime, UNIX_EPOCH};

    struct Scratch(PathBuf);

    impl Scratch {
        fn new() -> Self {
            let nonce = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos();
            let path = std::env::temp_dir().join(format!(
                "workstream-offline-cache-{}-{nonce}",
                std::process::id()
            ));
            fs::create_dir(&path).unwrap();
            Self(path)
        }
    }

    impl Drop for Scratch {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    fn sealed_cache() -> (Scratch, PathBuf, String) {
        let scratch = Scratch::new();
        let root = scratch.0.join("content");
        fs::create_dir(&root).unwrap();
        fs::write(root.join("base"), b"sealed").unwrap();
        let manifest = format!("{:x}  ./base\n", Sha256::digest(b"sealed"));
        fs::write(scratch.0.join("cache.sha256"), manifest.as_bytes()).unwrap();
        let digest = sha256_bytes(manifest.as_bytes());
        (scratch, root, digest)
    }

    #[test]
    fn exact_inventory_is_accepted_and_mutation_is_rejected() {
        let (_scratch, root, digest) = sealed_cache();
        let cancelled = AtomicBool::new(false);
        let usage = verify_offline_cache(
            &root,
            &digest,
            Instant::now() + Duration::from_secs(1),
            &[&cancelled],
        )
        .unwrap();
        assert_eq!(usage.entries, 3);
        fs::write(root.join("base"), b"mutated").unwrap();
        assert_eq!(
            verify_offline_cache(
                &root,
                &digest,
                Instant::now() + Duration::from_secs(1),
                &[&cancelled],
            ),
            Err(OfflineCacheFailure::Invalid)
        );
    }

    #[test]
    fn extra_missing_symlink_and_manifest_substitution_are_rejected() {
        let (_scratch, root, digest) = sealed_cache();
        let cancelled = AtomicBool::new(false);
        fs::write(root.join("extra"), b"extra").unwrap();
        assert_eq!(
            verify_offline_cache(
                &root,
                &digest,
                Instant::now() + Duration::from_secs(1),
                &[&cancelled],
            ),
            Err(OfflineCacheFailure::Invalid)
        );
        fs::remove_file(root.join("extra")).unwrap();
        fs::remove_file(root.join("base")).unwrap();
        symlink("/etc/passwd", root.join("base")).unwrap();
        assert_eq!(
            verify_offline_cache(
                &root,
                &digest,
                Instant::now() + Duration::from_secs(1),
                &[&cancelled],
            ),
            Err(OfflineCacheFailure::Invalid)
        );
        assert_eq!(
            verify_offline_cache(
                &root,
                &sha256_bytes(b"different"),
                Instant::now() + Duration::from_secs(1),
                &[&cancelled],
            ),
            Err(OfflineCacheFailure::Invalid)
        );
    }

    #[test]
    fn deadline_and_cancellation_stop_cache_verification() {
        let (_scratch, root, digest) = sealed_cache();
        assert_eq!(
            verify_offline_cache(&root, &digest, Instant::now(), &[&AtomicBool::new(false)],),
            Err(OfflineCacheFailure::Deadline)
        );
        assert_eq!(
            verify_offline_cache(
                &root,
                &digest,
                Instant::now() + Duration::from_secs(1),
                &[&AtomicBool::new(true)],
            ),
            Err(OfflineCacheFailure::Cancelled)
        );
    }
}
