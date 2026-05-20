use once_cell::sync::OnceCell;
use rand::RngCore;
use serde::Serialize;
use std::fs::{File, OpenOptions};
use std::io::Write;
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::Duration;
use tauri::{Listener, Manager};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_opener::OpenerExt;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

static SIDECAR_PROCESS: OnceCell<Mutex<Option<SidecarProcess>>> = OnceCell::new();
static SIDECAR_TOKEN: OnceCell<String> = OnceCell::new();
const SIDECAR_PORT_START: u16 = 8000;
const SIDECAR_PORT_END: u16 = 8020;
const SIDECAR_NAME: &str = "minos-desktop-api";

struct SidecarProcess {
    child: CommandChild,
    port: u16,
}

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
    let external_api_base_url = std::env::var("MINOS_DESKTOP_API_BASE_URL").ok();
    let managed_port = if external_api_base_url.is_some() {
        None
    } else {
        ensure_sidecar_running(&app)
    };
    let api_base_url = external_api_base_url.unwrap_or_else(|| {
        let port = managed_port.unwrap_or(SIDECAR_PORT_START);
        format!("http://127.0.0.1:{}", port)
    });
    BootstrapPayload {
        app_name: "MINOS-CORE".to_string(),
        version: "1.14.0".to_string(),
        api_base_url,
        api_token: SIDECAR_TOKEN
            .get()
            .cloned()
            .or_else(|| std::env::var("MINOS_DESKTOP_API_TOKEN").ok()),
        sidecar_managed: managed_port.is_some(),
        workspace_root: None,
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
    if let Some(slot) = SIDECAR_PROCESS.get() {
        if let Some(process) = slot.lock().map_err(|error| error.to_string())?.take() {
            let _ = process.child.kill();
        }
    }
    Ok(())
}

fn ensure_sidecar_running(app: &tauri::AppHandle) -> Option<u16> {
    if let Some(slot) = SIDECAR_PROCESS.get() {
        if let Ok(guard) = slot.lock() {
            if let Some(process) = guard.as_ref() {
                return Some(process.port);
            }
        }
    }
    let Some(port) = find_available_sidecar_port() else {
        return None;
    };
    let data_dir = app
        .path()
        .app_local_data_dir()
        .unwrap_or_else(|_| fallback_app_local_data_dir());
    let output_dir = data_dir.join("out");
    let db_path = data_dir.join("minos_desktop.sqlite3");
    let log_dir = data_dir.join("logs");
    let _ = std::fs::create_dir_all(&log_dir);
    let log_path = log_dir.join("api.log");
    let token = SIDECAR_TOKEN.get_or_init(generate_api_token).clone();

    let Ok(command) = app.shell().sidecar(SIDECAR_NAME) else {
        return None;
    };
    let port_arg = port.to_string();
    let db_path_arg = db_path.to_string_lossy().to_string();
    let output_dir_arg = output_dir.to_string_lossy().to_string();
    let command = command.args([
        "--host",
        "127.0.0.1",
        "--port",
        &port_arg,
        "--token",
        &token,
        "--db-path",
        &db_path_arg,
        "--output-dir",
        &output_dir_arg,
    ]);

    let Ok((mut rx, child)) = command.spawn() else {
        return None;
    };
    tauri::async_runtime::spawn(async move {
        let mut log_file = open_log_file(log_path);
        while let Some(event) = rx.recv().await {
            write_command_event(&mut log_file, event);
        }
    });

    let process = SidecarProcess { child, port };
    let process_slot = SIDECAR_PROCESS.get_or_init(|| Mutex::new(None));
    if let Ok(mut guard) = process_slot.lock() {
        *guard = Some(process);
    }
    let app_handle = app.clone();
    app.listen("tauri://close-requested", move |_| {
        let _ = shutdown_sidecar();
        let _ = app_handle.exit(0);
    });
    for _ in 0..30 {
        if is_api_port_open(port) {
            return Some(port);
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    Some(port)
}

fn generate_api_token() -> String {
    let mut bytes = [0u8; 24];
    rand::thread_rng().fill_bytes(&mut bytes);
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn fallback_app_local_data_dir() -> PathBuf {
    if cfg!(windows) {
        let base = std::env::var_os("LOCALAPPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|| {
                std::env::var_os("USERPROFILE")
                    .map(PathBuf::from)
                    .unwrap_or_else(std::env::temp_dir)
                    .join("AppData")
                    .join("Local")
            });
        base.join("MINOS-CORE")
    } else {
        std::env::var_os("HOME")
            .map(PathBuf::from)
            .unwrap_or_else(std::env::temp_dir)
            .join(".local")
            .join("share")
            .join("MINOS-CORE")
    }
}

fn open_log_file(path: PathBuf) -> Option<File> {
    OpenOptions::new().create(true).append(true).open(path).ok()
}

fn write_command_event(log_file: &mut Option<File>, event: CommandEvent) {
    let Some(file) = log_file.as_mut() else {
        return;
    };
    match event {
        CommandEvent::Stdout(line) => write_log_line(file, "stdout", &line),
        CommandEvent::Stderr(line) => write_log_line(file, "stderr", &line),
        CommandEvent::Error(error) => {
            let _ = writeln!(file, "[sidecar:error] {error}");
        }
        CommandEvent::Terminated(payload) => {
            let _ = writeln!(file, "[sidecar:terminated] code={:?}", payload.code);
        }
        _ => {}
    }
}

fn write_log_line(file: &mut File, stream: &str, line: &[u8]) {
    let text = String::from_utf8_lossy(line);
    let _ = writeln!(file, "[{stream}] {text}");
}

fn is_api_port_open(port: u16) -> bool {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    TcpStream::connect_timeout(&address, Duration::from_millis(200)).is_ok()
}

fn find_available_sidecar_port() -> Option<u16> {
    (SIDECAR_PORT_START..=SIDECAR_PORT_END).find(|port| {
        let address = SocketAddr::from(([127, 0, 0, 1], *port));
        TcpListener::bind(address).is_ok()
    })
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
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
