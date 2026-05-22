fn main() {
    if std::env::var("PROFILE").as_deref() != Ok("release") {
        ensure_debug_sidecar_placeholders();
    }
    tauri_build::build();
}

fn ensure_debug_sidecar_placeholders() {
    let sidecar = std::path::Path::new("binaries")
        .join("minos-desktop-api-x86_64-pc-windows-msvc.exe");
    if !sidecar.exists() {
        if let Some(parent) = sidecar.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        let _ = std::fs::write(&sidecar, b"debug placeholder; run scripts/build_sidecar.ps1");
    }

    let internal = std::path::Path::new("binaries")
        .join("minos-desktop-api-x86_64-pc-windows-msvc")
        .join("_internal");
    if !internal.exists() {
        let _ = std::fs::create_dir_all(&internal);
        let _ = std::fs::write(internal.join(".placeholder"), b"debug placeholder");
        return;
    }
    if is_empty_dir(&internal) {
        let _ = std::fs::write(internal.join(".placeholder"), b"debug placeholder");
    }
}

fn is_empty_dir(path: &std::path::Path) -> bool {
    match std::fs::read_dir(path) {
        Ok(mut entries) => entries.next().is_none(),
        Err(_) => false,
    }
}
