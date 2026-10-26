use super::*;

#[test]
fn missing_lease_directory_does_not_poison_node_admission() {
    let (root, mut config) = super::super::tests::test_config();
    config.smol = Some(SmolConfig {
        binary: root.join("unused-runtime"),
        binary_sha256: format!("sha256:{}", "a".repeat(64)),
        home: root.join("home"),
        guest_binary: root.join("guest"),
        guest_sha256: format!("sha256:{}", "b".repeat(64)),
        cgroup_root: root.join("groups"),
        maximum_parallel: 2,
        maximum_storage_bytes: 4 * 1024 * 1024 * 1024,
    });
    config.smol_admission = Some(Arc::new(
        Admission::new(
            Capacity {
                slots: 2,
                memory_bytes: 1024 * 1024 * 1024,
                storage_bytes: 4 * 1024 * 1024 * 1024,
            },
            "e".repeat(64),
        )
        .unwrap(),
    ));
    let request = parse_request(include_bytes!("../../../fixtures/request.json")).unwrap();
    let (client, _peer) = UnixStream::pair().unwrap();
    let mut budget = RequestExecutionBudget::new(Instant::now() + Duration::from_secs(1), 32768);
    let inventory = WorkspaceInventory {
        directories: Vec::new(),
        files: Vec::new(),
    };
    let cancelled = AtomicBool::new(false);
    let result = execute(
        &config,
        &config.cache[0],
        &request,
        ProjectMaterials {
            current: (&root, &inventory),
            predecessor: None,
        },
        &ProjectCallbacks::default(),
        &client,
        &mut budget,
        &cancelled,
    );
    assert_eq!(
        result.unwrap_err(),
        ExecutionFailure::ordinary("implementation_unavailable", false)
    );
    assert!(!config
        .socket_path
        .parent()
        .unwrap()
        .join("smol-leases")
        .exists());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn concurrent_capacity_is_reserved_until_its_owner_releases_it() {
    let (root, mut config) = super::super::tests::test_config();
    let request = parse_request(include_bytes!("../../../fixtures/request.json")).unwrap();
    let capacity = request.memory_bytes + HOST_OVERHEAD;
    config.smol = Some(SmolConfig {
        binary: root.join("unused-runtime"),
        binary_sha256: format!("sha256:{}", "a".repeat(64)),
        home: root.clone(),
        guest_binary: root.join("guest"),
        guest_sha256: format!("sha256:{}", "b".repeat(64)),
        cgroup_root: root.join("groups"),
        maximum_parallel: 1,
        maximum_storage_bytes: 4 * 1024 * 1024 * 1024,
    });
    config.smol_admission = Some(Arc::new(
        Admission::new(
            Capacity {
                slots: 1,
                memory_bytes: capacity,
                storage_bytes: 4 * 1024 * 1024 * 1024,
            },
            "e".repeat(64),
        )
        .unwrap(),
    ));
    let held = reserve(&config, &request).unwrap();
    let concurrent = config.clone();
    let next = request.clone();
    assert!(thread::spawn(move || reserve(&concurrent, &next).is_err())
        .join()
        .unwrap());
    drop(held);
    assert!(reserve(&config, &request).is_ok());
    fs::remove_dir_all(config.socket_path.parent().unwrap().parent().unwrap()).unwrap();
}

#[test]
fn cached_image_config_must_match_its_pinned_digest_and_platform() {
    let (root, mut config) = super::super::tests::test_config();
    let path = root.join("image.json");
    let raw=br#"{"os":"linux","architecture":"amd64","config":{"Entrypoint":["/checker"],"Cmd":["--json"]}}"#;
    fs::write(&path, raw).unwrap();
    fs::set_permissions(&path, fs::Permissions::from_mode(0o400)).unwrap();
    let cache = &mut config.cache[0];
    cache.config_image_id = format!("sha256:{:x}", Sha256::digest(raw));
    cache.smol = Some(SmolImage {
        archive: root.join("unused.tar"),
        archive_sha256: format!("sha256:{}", "a".repeat(64)),
        image_config: path.clone(),
    });
    inspect_image(cache).unwrap();
    fs::hard_link(&path, root.join("runtime-cache-alias")).unwrap();
    inspect_image(cache).unwrap();
    cache.architecture = "arm64".into();
    assert!(inspect_image(cache).is_err());
    cache.architecture = "amd64".into();
    fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
    fs::write(&path, b"{}").unwrap();
    assert!(inspect_image(cache).is_err());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn private_child_home_is_derived_from_the_exact_lease() {
    let (root, _config) = super::super::tests::test_config();
    let lease_root = root.join("smol-leases");
    let child_home_root = root.join("trial-child-homes");
    let name = format!("ws-{}", "a".repeat(32));
    let runtime = SmolConfig {
        binary: root.join("runtime"),
        binary_sha256: format!("sha256:{}", "a".repeat(64)),
        home: child_home_root.join(format!("{name}.home")),
        guest_binary: root.join("guest"),
        guest_sha256: format!("sha256:{}", "b".repeat(64)),
        cgroup_root: root.join("groups"),
        maximum_parallel: 2,
        maximum_storage_bytes: 4 * 1024 * 1024 * 1024,
    };
    let mut lease = Lease {
        name,
        owner: "b".repeat(64),
        epoch: "c".repeat(64),
        expires_ms: 1,
        lifetime_ms: 1,
        root: lease_root,
        runtime,
        private_home_root: Some(child_home_root),
    };
    assert!(lease.valid());
    lease.runtime.home = root.join("shared-or-foreign-home");
    assert!(!lease.valid());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn quarantined_admission_makes_runtime_health_unavailable() {
    let (root, mut config) = super::super::tests::test_config();
    let admission = Arc::new(
        Admission::new(
            Capacity {
                slots: 2,
                memory_bytes: 20,
                storage_bytes: 20,
            },
            "e".repeat(64),
        )
        .unwrap(),
    );
    let held = admission
        .reserve(
            Capacity {
                slots: 1,
                memory_bytes: 10,
                storage_bytes: 10,
            },
            Some(Capacity {
                slots: 1,
                memory_bytes: 10,
                storage_bytes: 10,
            }),
        )
        .unwrap();
    held.child(Capacity {
        slots: 1,
        memory_bytes: 10,
        storage_bytes: 10,
    })
    .unwrap()
    .quarantine();
    config.smol_admission = Some(admission);
    assert_eq!(ready(&config).unwrap_err(), "node admission quarantined");
    fs::remove_dir_all(root).unwrap();
}
