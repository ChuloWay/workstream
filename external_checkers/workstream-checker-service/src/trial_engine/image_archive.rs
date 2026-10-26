//! Inspect candidate image archives before granting a sandbox runtime decompression work.

use flate2::read::MultiGzDecoder;
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::Path;
use std::time::Instant;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum ImageArchiveFailure {
    Invalid,
    CapacityExceeded,
    DeadlineExceeded,
}

#[derive(Debug, PartialEq, Eq)]
pub(crate) struct ValidatedImageArchive {
    pub(crate) expanded_bytes: u64,
    pub(crate) expanded_entries: u64,
    pub(crate) config_image_id: String,
    pub(crate) platform: String,
    pub(crate) environment: Vec<String>,
}

#[derive(Debug, Default, PartialEq, Eq)]
pub(crate) struct ExpandedImage {
    pub(crate) bytes: u64,
    pub(crate) entries: u64,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ImageArchiveManifest {
    #[serde(rename = "Config")]
    config: String,
    #[serde(rename = "RepoTags")]
    repo_tags: Vec<String>,
    #[serde(rename = "Layers")]
    layers: Vec<String>,
}

pub(crate) fn validate_single_image_archive(
    archive: &Path,
    expected_tag: &str,
    expected_platform: &str,
    maximum_bytes: u64,
    maximum_expanded_bytes: u64,
    maximum_expanded_entries: u64,
    deadline: Instant,
) -> Result<ValidatedImageArchive, ImageArchiveFailure> {
    let mut file = File::open(archive).map_err(|_| invalid())?;
    let length = file.metadata().map_err(|_| invalid())?.len();
    if length == 0 || length > maximum_bytes || length % 512 != 0 {
        return Err(invalid());
    }
    let mut offset = 0_u64;
    let mut manifest = None;
    let mut entries = HashMap::new();
    while offset.saturating_add(512) <= length {
        file.seek(SeekFrom::Start(offset)).map_err(|_| invalid())?;
        let mut header = [0_u8; 512];
        file.read_exact(&mut header).map_err(|_| invalid())?;
        if header.iter().all(|byte| *byte == 0) {
            if length.saturating_sub(offset) < 1024 {
                return Err(invalid());
            }
            file.seek(SeekFrom::Start(offset)).map_err(|_| invalid())?;
            let mut trailing = vec![0_u8; (length - offset) as usize];
            file.read_exact(&mut trailing).map_err(|_| invalid())?;
            if trailing.iter().any(|byte| *byte != 0) {
                return Err(invalid());
            }
            offset = length;
            break;
        }
        validate_tar_checksum(&header)?;
        if !matches!(header[156], 0 | b'0') || header[157..257].iter().any(|byte| *byte != 0) {
            return Err(invalid());
        }
        let name = tar_text(&header[0..100])?;
        let prefix = tar_text(&header[345..500])?;
        let path = if prefix.is_empty() {
            name
        } else {
            format!("{prefix}/{name}")
        };
        if !valid_archive_path(&path)
            || entries.len() >= 4096
            || entries.contains_key(&path)
            || path == "repositories"
        {
            return Err(invalid());
        }
        let size = tar_octal(&header[124..136])?;
        let data = offset.checked_add(512).ok_or_else(invalid)?;
        let padded = size
            .checked_add(511)
            .map(|value| value / 512 * 512)
            .ok_or_else(invalid)?;
        offset = data
            .checked_add(padded)
            .filter(|value| *value <= length)
            .ok_or_else(invalid)?;
        entries.insert(path.clone(), (data, size));
        if path == "manifest.json" {
            if manifest.is_some() || size > 1024 * 1024 {
                return Err(invalid());
            }
            file.seek(SeekFrom::Start(data)).map_err(|_| invalid())?;
            let mut bytes = vec![0_u8; size as usize];
            file.read_exact(&mut bytes).map_err(|_| invalid())?;
            manifest = Some(bytes);
        }
    }
    if offset != length {
        return Err(invalid());
    }
    let manifest = manifest.ok_or_else(invalid)?;
    let manifests: Vec<ImageArchiveManifest> =
        serde_json::from_slice(&manifest).map_err(|_| invalid())?;
    if manifests.len() != 1 {
        return Err(invalid());
    }
    let manifest = manifests.first().expect("length checked");
    let config_digest = if valid_sha256(&manifest.config) {
        &manifest.config[7..]
    } else if manifest.config.len() == 69
        && manifest.config.ends_with(".json")
        && manifest.config[..64]
            .bytes()
            .all(|item| item.is_ascii_hexdigit() && !item.is_ascii_uppercase())
    {
        &manifest.config[..64]
    } else {
        return Err(invalid());
    };
    if manifest.repo_tags.as_slice() != [expected_tag] || manifest.layers.is_empty() {
        return Err(invalid());
    }
    let Some((config_offset, config_size)) = entries.get(&manifest.config).copied() else {
        return Err(invalid());
    };
    if config_size == 0 || config_size > 16 * 1024 * 1024 {
        return Err(invalid());
    }
    file.seek(SeekFrom::Start(config_offset))
        .map_err(|_| invalid())?;
    let mut config_bytes = vec![0_u8; config_size as usize];
    file.read_exact(&mut config_bytes).map_err(|_| invalid())?;
    if format!("{:x}", Sha256::digest(&config_bytes)) != config_digest {
        return Err(invalid());
    }
    let mut referenced = HashSet::from(["manifest.json".to_owned(), manifest.config.clone()]);
    for layer in &manifest.layers {
        if !valid_archive_path(layer)
            || layer == "manifest.json"
            || layer == &manifest.config
            || !entries.contains_key(layer)
        {
            return Err(invalid());
        }
        referenced.insert(layer.clone());
    }
    if referenced.len() != entries.len() {
        return Err(invalid());
    }
    let expanded = validate_layers(
        &mut file,
        &entries,
        &manifest.layers,
        &config_bytes,
        maximum_expanded_bytes,
        maximum_expanded_entries,
        deadline,
    )?;
    let config: serde_json::Value = serde_json::from_slice(&config_bytes).map_err(|_| invalid())?;
    let os = config
        .get("os")
        .and_then(|value| value.as_str())
        .ok_or_else(invalid)?;
    let architecture = config
        .get("architecture")
        .and_then(|value| value.as_str())
        .ok_or_else(invalid)?;
    let platform = format!("{os}/{architecture}");
    if platform != expected_platform {
        return Err(invalid());
    }
    let environment = validated_environment(&config)?;
    Ok(ValidatedImageArchive {
        expanded_bytes: expanded.bytes,
        expanded_entries: expanded.entries,
        config_image_id: format!("sha256:{config_digest}"),
        platform,
        environment,
    })
}

/// Charge every layer, including repeated content, without materializing it.
pub(crate) fn validate_layers(
    file: &mut File,
    entries: &HashMap<String, (u64, u64)>,
    layers: &[String],
    config: &[u8],
    maximum_bytes: u64,
    maximum_entries: u64,
    deadline: Instant,
) -> Result<ExpandedImage, ImageArchiveFailure> {
    let config: serde_json::Value = serde_json::from_slice(config).map_err(|_| invalid())?;
    validate_runtime_configuration(&config)?;
    let rootfs = config.get("rootfs").ok_or_else(invalid)?;
    if rootfs.get("type").and_then(|v| v.as_str()) != Some("layers") {
        return Err(invalid());
    }
    let diff_ids = rootfs
        .get("diff_ids")
        .and_then(|v| v.as_array())
        .ok_or_else(invalid)?;
    if diff_ids.len() != layers.len() {
        return Err(invalid());
    }
    let mut expanded = ExpandedImage::default();
    for (layer, expected_digest) in layers.iter().zip(diff_ids) {
        let (offset, size) = *entries.get(layer).ok_or_else(invalid)?;
        if Instant::now() >= deadline {
            return Err(ImageArchiveFailure::DeadlineExceeded);
        }
        if size < 2 {
            return Err(invalid());
        }
        file.seek(SeekFrom::Start(offset)).map_err(|_| invalid())?;
        let mut magic = [0; 2];
        file.read_exact(&mut magic).map_err(|_| invalid())?;
        file.seek(SeekFrom::Start(offset)).map_err(|_| invalid())?;
        let source = file.by_ref().take(size);
        let reader: Box<dyn Read + '_> = if magic == [0x1f, 0x8b] {
            Box::new(MultiGzDecoder::new(source))
        } else {
            Box::new(source)
        };
        let mut stream = LayerStream {
            reader,
            digest: Sha256::new(),
            expanded: &mut expanded,
            maximum_bytes,
            maximum_entries,
            deadline,
        };
        inspect_tar(&mut stream)?;
        if expected_digest.as_str()
            != Some(format!("sha256:{:x}", stream.digest.finalize()).as_str())
        {
            return Err(invalid());
        }
    }
    Ok(expanded)
}

fn validate_runtime_configuration(config: &serde_json::Value) -> Result<(), ImageArchiveFailure> {
    // Docker creates image-declared anonymous volumes before the trusted
    // launcher runs. They would sit outside its bounded filesystem and owner
    // ledger, so this runtime does not admit that image capability.
    if let Some(volumes) = config.get("config").and_then(|value| value.get("Volumes")) {
        if !volumes.is_null() && !volumes.as_object().is_some_and(|value| value.is_empty()) {
            return Err(invalid());
        }
    }
    Ok(())
}

fn validated_environment(config: &serde_json::Value) -> Result<Vec<String>, ImageArchiveFailure> {
    let Some(environment) = config.get("config").and_then(|value| value.get("Env")) else {
        return Ok(Vec::new());
    };
    if environment.is_null() {
        return Ok(Vec::new());
    }
    let environment = environment.as_array().ok_or_else(invalid)?;
    if environment.len() > 1024 {
        return Err(invalid());
    }
    let mut total = 0_usize;
    let mut names = HashSet::new();
    environment
        .iter()
        .map(|value| {
            let value = value.as_str().ok_or_else(invalid)?;
            let (name, _) = value.split_once('=').ok_or_else(invalid)?;
            let mut characters = name.bytes();
            if value.len() > 8192
                || !characters
                    .next()
                    .is_some_and(|byte| byte.is_ascii_alphabetic() || byte == b'_')
                || !characters.all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')
                || !names.insert(name.to_owned())
            {
                return Err(invalid());
            }
            total = total.checked_add(value.len()).ok_or_else(capacity)?;
            if total > 1024 * 1024 {
                return Err(capacity());
            }
            Ok(value.to_owned())
        })
        .collect()
}

struct LayerStream<'a> {
    reader: Box<dyn Read + 'a>,
    digest: Sha256,
    expanded: &'a mut ExpandedImage,
    maximum_bytes: u64,
    maximum_entries: u64,
    deadline: Instant,
}

impl LayerStream<'_> {
    fn read(&mut self, output: &mut [u8]) -> Result<usize, ImageArchiveFailure> {
        if Instant::now() >= self.deadline {
            return Err(ImageArchiveFailure::DeadlineExceeded);
        }
        let count = self.reader.read(output).map_err(|_| invalid())?;
        self.expanded.bytes = self
            .expanded
            .bytes
            .checked_add(count as u64)
            .ok_or_else(capacity)?;
        if self.expanded.bytes > self.maximum_bytes {
            return Err(capacity());
        }
        self.digest.update(&output[..count]);
        Ok(count)
    }

    fn exact(&mut self, mut output: &mut [u8]) -> Result<(), ImageArchiveFailure> {
        while !output.is_empty() {
            let count = self.read(output)?;
            if count == 0 {
                return Err(invalid());
            }
            output = &mut output[count..];
        }
        Ok(())
    }

    fn discard(&mut self, mut bytes: u64) -> Result<(), ImageArchiveFailure> {
        let mut buffer = [0; 32 * 1024];
        while bytes != 0 {
            let count = usize::try_from(bytes.min(buffer.len() as u64)).map_err(|_| invalid())?;
            self.exact(&mut buffer[..count])?;
            bytes -= count as u64;
        }
        Ok(())
    }

    fn charge_entries(&mut self, count: u64) -> Result<(), ImageArchiveFailure> {
        self.expanded.entries = self
            .expanded
            .entries
            .checked_add(count)
            .ok_or_else(capacity)?;
        // Reserve one allocation block per inode, including implicit directories.
        // Tar payload/padding is charged separately; never subtract whiteouts or
        // assume that repeated files/layers deduplicate on the target daemon.
        self.expanded.bytes = self
            .expanded
            .bytes
            .checked_add(count.checked_mul(4096).ok_or_else(capacity)?)
            .ok_or_else(capacity)?;
        if self.expanded.entries > self.maximum_entries || self.expanded.bytes > self.maximum_bytes
        {
            return Err(capacity());
        }
        Ok(())
    }
}

fn inspect_tar(stream: &mut LayerStream<'_>) -> Result<(), ImageArchiveFailure> {
    let mut next_path: Option<String> = None;
    let mut metadata_pending = false;
    loop {
        let mut header = [0; 512];
        stream.exact(&mut header)?;
        if header.iter().all(|b| *b == 0) {
            if metadata_pending {
                return Err(invalid());
            }
            stream.exact(&mut header)?;
            if header.iter().any(|b| *b != 0) {
                return Err(invalid());
            }
            loop {
                let count = stream.read(&mut header)?;
                if count == 0 {
                    return Ok(());
                }
                if header[..count].iter().any(|b| *b != 0) {
                    return Err(invalid());
                }
            }
        }
        validate_tar_checksum(&header)?;
        if &header[257..263] != b"ustar\0" && &header[257..263] != b"ustar " {
            return Err(invalid());
        }
        let size = tar_octal(&header[124..136])?;
        let padded = size
            .checked_add(511)
            .map(|v| v / 512 * 512)
            .ok_or_else(invalid)?;
        match header[156] {
            b'x' | b'L' | b'K' => {
                // Metadata is bounded independently of the decompression budget.
                if size == 0 || size > 64 * 1024 {
                    return Err(invalid());
                }
                stream.charge_entries(1)?;
                let mut metadata = vec![0; size as usize];
                stream.exact(&mut metadata)?;
                stream.discard(padded - size)?;
                metadata_pending = true;
                if header[156] == b'x' {
                    if let Some(path) = pax_path(&metadata)? {
                        next_path = Some(path);
                    }
                } else {
                    let text = tar_text(&metadata)?;
                    if text.is_empty() || text.len() > 4096 {
                        return Err(invalid());
                    }
                    if header[156] == b'L' {
                        next_path = Some(text);
                    }
                }
            }
            0 | b'0' | b'1' | b'2' | b'5' => {
                if !matches!(header[156], 0 | b'0') && size != 0 {
                    return Err(invalid());
                }
                let path = if let Some(path) = next_path.take() {
                    path
                } else {
                    let name = tar_text(&header[..100])?;
                    // GNU's old header uses this region for other metadata.
                    let prefix = if &header[257..263] == b"ustar\0" {
                        tar_text(&header[345..500])?
                    } else {
                        String::new()
                    };
                    if prefix.is_empty() {
                        name
                    } else {
                        format!("{prefix}/{name}")
                    }
                };
                stream.charge_entries(path_entries(&path)?)?;
                metadata_pending = false;
                stream.discard(padded)?;
            }
            // Sparse, device, FIFO, global PAX and unknown extensions have
            // allocation semantics not covered by this conservative scanner.
            _ => return Err(invalid()),
        }
    }
}

fn path_entries(path: &str) -> Result<u64, ImageArchiveFailure> {
    if path.is_empty() || path.len() > 4096 || path.starts_with('/') || path.contains('\0') {
        return Err(invalid());
    }
    let mut count = 0;
    for part in path.split('/') {
        match part {
            ".." => return Err(invalid()),
            "" | "." => {}
            _ => count += 1,
        }
    }
    Ok(count.max(1))
}

fn pax_path(bytes: &[u8]) -> Result<Option<String>, ImageArchiveFailure> {
    let mut remaining = bytes;
    let mut path = None;
    let mut keys = std::collections::HashSet::new();
    while !remaining.is_empty() {
        let space = remaining
            .iter()
            .position(|b| *b == b' ')
            .ok_or_else(invalid)?;
        let length: usize = std::str::from_utf8(&remaining[..space])
            .map_err(|_| invalid())?
            .parse()
            .map_err(|_| invalid())?;
        if length <= space + 2 || length > remaining.len() || remaining[length - 1] != b'\n' {
            return Err(invalid());
        }
        let record =
            std::str::from_utf8(&remaining[space + 1..length - 1]).map_err(|_| invalid())?;
        let (key, value) = record.split_once('=').ok_or_else(invalid)?;
        if !keys.insert(key) {
            return Err(invalid());
        }
        match key {
            "path" => {
                path_entries(value)?;
                path = Some(value.to_owned());
            }
            "linkpath" if value.len() <= 4096 && !value.contains('\0') => {}
            "mtime" | "atime" | "ctime" | "uid" | "gid" | "uname" | "gname" => {}
            _ if key.starts_with("SCHILY.xattr.") => {}
            // In particular, reject size overrides and every sparse extension.
            _ => return Err(invalid()),
        }
        remaining = &remaining[length..];
    }
    Ok(path)
}

fn valid_archive_path(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 4096
        && !value.starts_with('/')
        && !value.ends_with('/')
        && !value.contains('\\')
        && value.bytes().all(|byte| {
            byte.is_ascii_alphanumeric() || matches!(byte, b'/' | b'.' | b'_' | b'-' | b':')
        })
        && value
            .split('/')
            .all(|part| !part.is_empty() && part != "." && part != "..")
}

fn validate_tar_checksum(header: &[u8; 512]) -> Result<(), ImageArchiveFailure> {
    let expected = tar_octal(&header[148..156])?;
    let actual: u64 = header
        .iter()
        .enumerate()
        .map(|(index, byte)| {
            if (148..156).contains(&index) {
                u64::from(b' ')
            } else {
                u64::from(*byte)
            }
        })
        .sum();
    if actual != expected {
        return Err(invalid());
    }
    Ok(())
}

fn tar_text(bytes: &[u8]) -> Result<String, ImageArchiveFailure> {
    let end = bytes
        .iter()
        .position(|byte| *byte == 0)
        .unwrap_or(bytes.len());
    std::str::from_utf8(&bytes[..end])
        .map(str::to_owned)
        .map_err(|_| invalid())
}

fn tar_octal(bytes: &[u8]) -> Result<u64, ImageArchiveFailure> {
    let text = std::str::from_utf8(bytes)
        .map_err(|_| invalid())?
        .trim_matches(|character| character == '\0' || character == ' ');
    u64::from_str_radix(text, 8).map_err(|_| invalid())
}

fn valid_sha256(value: &str) -> bool {
    value.len() == 71
        && value.starts_with("sha256:")
        && value[7..]
            .bytes()
            .all(|item| item.is_ascii_hexdigit() && !item.is_ascii_uppercase())
}

fn invalid() -> ImageArchiveFailure {
    ImageArchiveFailure::Invalid
}
fn capacity() -> ImageArchiveFailure {
    ImageArchiveFailure::CapacityExceeded
}

#[cfg(test)]
mod tests {
    use super::*;
    use flate2::write::GzEncoder;
    use flate2::Compression;
    use std::io::Write;
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::time::Duration;

    static SEQUENCE: AtomicU64 = AtomicU64::new(0);

    fn entry(path: &str, kind: u8, body: &[u8]) -> Vec<u8> {
        let mut header = [0; 512];
        header[..path.len()].copy_from_slice(path.as_bytes());
        header[124..136].copy_from_slice(format!("{:011o}\0", body.len()).as_bytes());
        header[148..156].fill(b' ');
        header[156] = kind;
        header[257..263].copy_from_slice(b"ustar\0");
        header[263..265].copy_from_slice(b"00");
        let checksum: u64 = header.iter().map(|v| u64::from(*v)).sum();
        header[148..156].copy_from_slice(format!("{checksum:06o}\0 ").as_bytes());
        let mut result = header.to_vec();
        result.extend(body);
        result.resize(result.len().next_multiple_of(512), 0);
        result
    }

    fn layer(path: &str, body: &[u8]) -> Vec<u8> {
        let mut result = entry(path, b'0', body);
        result.extend([0; 1024]);
        result
    }

    fn gzip(bytes: &[u8]) -> Vec<u8> {
        let mut encoder = GzEncoder::new(Vec::new(), Compression::default());
        encoder.write_all(bytes).unwrap();
        encoder.finish().unwrap()
    }

    fn validate(
        wire: &[u8],
        plain: &[u8],
        copies: usize,
        bytes: u64,
        entries: u64,
    ) -> Result<ExpandedImage, ImageArchiveFailure> {
        let path = std::env::temp_dir().join(format!(
            "ws-image-layers-{}-{}",
            std::process::id(),
            SEQUENCE.fetch_add(1, Ordering::SeqCst)
        ));
        let mut file = std::fs::OpenOptions::new()
            .write(true)
            .read(true)
            .create_new(true)
            .open(&path)
            .unwrap();
        file.write_all(wire).unwrap();
        // Unix unlinks the private temporary immediately; its descriptor stays
        // valid for the bounded reader and no failed assertion leaves a file.
        std::fs::remove_file(path).unwrap();
        let index = HashMap::from([("layer".to_owned(), (0, wire.len() as u64))]);
        let config = serde_json::to_vec(&serde_json::json!({"rootfs": {
            "type": "layers", "diff_ids": vec![format!("sha256:{:x}", Sha256::digest(plain)); copies]
        }})).unwrap();
        validate_layers(
            &mut file,
            &index,
            &vec!["layer".to_owned(); copies],
            &config,
            bytes,
            entries,
            Instant::now() + Duration::from_secs(5),
        )
    }

    fn archive(config: serde_json::Value) -> Vec<u8> {
        let plain = layer("usr/bin/value", b"value");
        let mut config = config;
        config["rootfs"] = serde_json::json!({
            "type": "layers",
            "diff_ids": [format!("sha256:{:x}", Sha256::digest(&plain))],
        });
        let config = serde_json::to_vec(&config).unwrap();
        let config_name = format!("{:x}.json", Sha256::digest(&config));
        let manifest = serde_json::to_vec(&serde_json::json!([{
            "Config": config_name,
            "RepoTags": ["workstream-trial:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"],
            "Layers": ["layer.tar"],
        }]))
        .unwrap();
        let mut result = entry("manifest.json", b'0', &manifest);
        result.extend(entry(&config_name, b'0', &config));
        result.extend(entry("layer.tar", b'0', &plain));
        result.extend([0; 1024]);
        result
    }

    fn validate_archive(
        bytes: &[u8],
        platform: &str,
    ) -> Result<ValidatedImageArchive, ImageArchiveFailure> {
        let path = std::env::temp_dir().join(format!(
            "ws-image-archive-{}-{}",
            std::process::id(),
            SEQUENCE.fetch_add(1, Ordering::SeqCst)
        ));
        std::fs::write(&path, bytes).unwrap();
        let result = validate_single_image_archive(
            &path,
            "workstream-trial:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            platform,
            1024 * 1024,
            1024 * 1024,
            4096,
            Instant::now() + Duration::from_secs(5),
        );
        std::fs::remove_file(path).unwrap();
        result
    }

    #[test]
    fn archive_platform_and_environment_are_exact_pre_import_facts() {
        let bytes = archive(serde_json::json!({
            "os": "linux",
            "architecture": "amd64",
            "config": {"Env": ["PATH=/bin", "VALUE=one"]},
        }));
        let validated = validate_archive(&bytes, "linux/amd64").unwrap();
        assert_eq!(validated.platform, "linux/amd64");
        assert_eq!(validated.environment, ["PATH=/bin", "VALUE=one"]);
        assert!(validated.config_image_id.starts_with("sha256:"));
        assert_eq!(
            validate_archive(&bytes, "linux/arm64"),
            Err(ImageArchiveFailure::Invalid)
        );

        for environment in [
            serde_json::json!(["missing_separator"]),
            serde_json::json!(["DUP=one", "DUP=two"]),
            serde_json::json!(["1INVALID=value"]),
        ] {
            let malformed = archive(serde_json::json!({
                "os": "linux",
                "architecture": "amd64",
                "config": {"Env": environment},
            }));
            assert_eq!(
                validate_archive(&malformed, "linux/amd64"),
                Err(ImageArchiveFailure::Invalid)
            );
        }
    }

    #[test]
    fn compressed_and_raw_layers_have_the_same_bound_and_digest() {
        let plain = layer("usr/share/value", b"hello");
        let expected = ExpandedImage {
            bytes: plain.len() as u64 + 3 * 4096,
            entries: 3,
        };
        assert_eq!(validate(&plain, &plain, 1, 65536, 16).unwrap(), expected);
        assert_eq!(
            validate(&gzip(&plain), &plain, 1, 65536, 16).unwrap(),
            expected
        );
        let wrong = layer("usr/share/value", b"other");
        assert_eq!(
            validate(&gzip(&plain), &wrong, 1, 65536, 16),
            Err(invalid())
        );
    }

    #[test]
    fn image_declared_volumes_cannot_create_unaccounted_writable_storage() {
        for volumes in [
            serde_json::json!({"/data": {}}),
            serde_json::json!(["/data"]),
        ] {
            assert_eq!(
                validate_runtime_configuration(
                    &serde_json::json!({"config": {"Volumes": volumes}})
                ),
                Err(invalid())
            );
        }
        validate_runtime_configuration(&serde_json::json!({"config": {"Volumes": {}}})).unwrap();
        validate_runtime_configuration(&serde_json::json!({"config": {"Volumes": null}})).unwrap();
    }

    #[test]
    fn compressed_expansion_and_implicit_directory_limits_fail_before_loading() {
        let plain = layer("value", &vec![0; 1024 * 1024]);
        let compressed = gzip(&plain);
        assert!(compressed.len() < 4096);
        assert_eq!(validate(&compressed, &plain, 1, 65536, 16), Err(capacity()));
        let deep = layer("a/b/c/d/value", b"x");
        assert_eq!(validate(&gzip(&deep), &deep, 1, 65536, 4), Err(capacity()));
    }

    #[test]
    fn repeated_layers_consume_the_aggregate_allowance() {
        let plain = layer("value", b"x");
        let one = validate(&plain, &plain, 1, 65536, 16).unwrap();
        assert_eq!(validate(&plain, &plain, 2, one.bytes, 16), Err(capacity()));
        assert_eq!(validate(&plain, &plain, 2, 65536, 1), Err(capacity()));
        let both = validate(&plain, &plain, 2, 65536, 16).unwrap();
        assert_eq!(both.bytes, 2 * one.bytes);
        assert_eq!(both.entries, 2);
    }

    #[test]
    fn malformed_streams_and_unsupported_sparse_metadata_are_refused() {
        let plain = layer("value", b"x");
        let mut truncated = gzip(&plain);
        truncated.truncate(truncated.len() - 3);
        assert_eq!(validate(&truncated, &plain, 1, 65536, 16), Err(invalid()));
        let mut extra = gzip(&plain);
        extra.extend(b"not gzip");
        assert_eq!(validate(&extra, &plain, 1, 65536, 16), Err(invalid()));
        for kind in [b'S', b'3', b'4', b'6', b'g'] {
            let mut unsupported = entry("value", kind, b"");
            unsupported.extend([0; 1024]);
            assert_eq!(
                validate(&unsupported, &unsupported, 1, 65536, 16),
                Err(invalid())
            );
        }
        assert_eq!(pax_path(b"16 size=1048576\n"), Err(invalid()));
        assert_eq!(pax_path(b"23 GNU.sparse.size=999\n"), Err(invalid()));
    }

    #[test]
    fn bounded_pax_paths_cannot_hide_implicit_directories() {
        let path = "one/two/three/four";
        let record = format!("{} path={}\n", path.len() + 9, path);
        assert_eq!(record.len(), path.len() + 9);
        let mut plain = entry("PaxHeader/value", b'x', record.as_bytes());
        plain.extend(entry("value", b'0', b"x"));
        plain.extend([0; 1024]);
        assert_eq!(
            validate(&gzip(&plain), &plain, 1, 65536, 4),
            Err(capacity())
        );
        assert_eq!(
            validate(&gzip(&plain), &plain, 1, 65536, 5)
                .unwrap()
                .entries,
            5
        );
    }
}
