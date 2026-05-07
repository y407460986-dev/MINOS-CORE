use once_cell::sync::OnceCell;
use serde::Serialize;
use std::net::{SocketAddr, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;
use tauri::Listener;
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_opener::OpenerExt;

static SIDECAR_CHILD: OnceCell<Mutex<Option<Child>>> = OnceCell::new();

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct BootstrapPayload {
    app_name: String,
    version: String,
    api_base_url: String,
    api_token: Option<String>,
    sidecar_managed: bool,
    workspace_root: Option<String>,
}

#[tauri::command]
fn get_bootstrap(app: tauri::AppHandle) -> BootstrapPayload {
    let api_base_url = std::env::var("MINOS_DESKTOP_API_BASE_URL")
        .unwrap_or_else(|_| "http://127.0.0.1:8000".to_string());
    let sidecar_managed = ensure_sidecar_running(&app);
    BootstrapPayload {
        app_name: "MINOS-CORE".to_string(),
        version: "1.14.0".to_string(),
        api_base_url,
        api_token: std::env::var("MINOS_DESKTOP_API_TOKEN").ok(),
        sidecar_managed,
        workspace_root: workspace_root().map(|path| path.to_string_lossy().to_string()),
    }
}

#[tauri::command]
fn select_drawing_file(app: tauri::AppHandle) -> Option<String> {
    app.dialog()
        .file()
        .add_filter("图纸文件", &["pdf", "png", "jpg", "jpeg"])
        .blocking_pick_file()
        .map(|path| path.to_string())
}

#[tauri::command]
fn select_output_dir(app: tauri::AppHandle) -> Option<String> {
    app.dialog()
        .file()
        .blocking_pick_folder()
        .map(|path| path.to_string())
}

#[tauri::command]
fn open_output_dir(app: tauri::AppHandle, path: String) -> Result<(), String> {
    app.opener()
        .open_path(path, None::<&str>)
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn reveal_file(app: tauri::AppHandle, path: String) -> Result<(), String> {
    app.opener()
        .reveal_item_in_dir(path)
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn shutdown_sidecar() -> Result<(), String> {
    if let Some(slot) = SIDECAR_CHILD.get() {
        if let Some(mut child) = slot.lock().map_err(|error| error.to_string())?.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
    Ok(())
}

fn ensure_sidecar_running(app: &tauri::AppHandle) -> bool {
    if is_api_port_open() {
        return false;
    }
    let Some(root) = workspace_root() else {
        return false;
    };
    let log_dir = root.join("out").join("desktop-api");
    let _ = std::fs::create_dir_all(&log_dir);
    let stdout = std::fs::File::create(log_dir.join("api.stdout.log"))
        .ok()
        .map(Stdio::from)
        .unwrap_or_else(Stdio::null);
    let stderr = std::fs::File::create(log_dir.join("api.stderr.log"))
        .ok()
        .map(Stdio::from)
        .unwrap_or_else(Stdio::null);

    let mut command = Command::new("python");
    command
        .args([
            "-m",
            "uvicorn",
            "minos_desktop.api.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ])
        .current_dir(&root)
        .env_remove("MINOS_DESKTOP_API_TOKEN")
        .stdin(Stdio::null())
        .stdout(stdout)
        .stderr(stderr);

    let Ok(child) = command.spawn() else {
        return false;
    };
    let slot = SIDECAR_CHILD.get_or_init(|| Mutex::new(None));
    if let Ok(mut guard) = slot.lock() {
        *guard = Some(child);
    }
    let app_handle = app.clone();
    app.listen("tauri://close-requested", move |_| {
        let _ = shutdown_sidecar();
        let _ = app_handle.exit(0);
    });
    for _ in 0..30 {
        if is_api_port_open() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    true
}

fn is_api_port_open() -> bool {
    let address = SocketAddr::from(([127, 0, 0, 1], 8000));
    TcpStream::connect_timeout(&address, Duration::from_millis(200)).is_ok()
}

fn workspace_root() -> Option<PathBuf> {
    let current = std::env::current_dir().ok()?;
    for ancestor in current.ancestors() {
        if ancestor.join("minos_core").is_dir() && ancestor.join("apps").join("desktop-tauri").is_dir() {
            return Some(ancestor.to_path_buf());
        }
    }
    None
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            get_bootstrap,
            select_drawing_file,
            select_output_dir,
            open_output_dir,
            reveal_file,
            shutdown_sidecar
        ])
        .run(tauri::generate_context!())
        .expect("failed to run MINOS-CORE desktop app");
}
