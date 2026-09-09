use once_cell::sync::OnceCell;
use rand::RngCore;
use serde::Serialize;
use std::fs::{File, OpenOptions};
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::Duration;
use tauri::{Listener, Manager};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_dialog::FilePath;
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
    pid: u32,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct SidecarIdentity {
    pid: u32,
    port: u16,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
enum SidecarPhase {
    #[default]
    Stopped,
    Starting(SidecarIdentity),
    Running(SidecarIdentity),
}

#[derive(Debug, Default)]
struct SidecarLifecycle {
    phase: SidecarPhase,
}

impl SidecarLifecycle {
    fn with_running(identity: SidecarIdentity) -> Self {
        Self {
            phase: SidecarPhase::Running(identity),
        }
    }

    fn phase(&self) -> SidecarPhase {
        self.phase
    }

    fn current(&self) -> Option<SidecarIdentity> {
        match self.phase {
            SidecarPhase::Stopped => None,
            SidecarPhase::Starting(identity) | SidecarPhase::Running(identity) => Some(identity),
        }
    }

    fn register(&mut self, identity: SidecarIdentity) {
        self.phase = SidecarPhase::Starting(identity);
    }

    fn mark_running(&mut self, identity: SidecarIdentity) {
        if self.current() == Some(identity) {
            self.phase = SidecarPhase::Running(identity);
        }
    }

    fn mark_stopped(&mut self) {
        self.phase = SidecarPhase::Stopped;
    }

    fn terminated(&mut self, pid: u32) {
        if self.current().is_some_and(|current| current.pid == pid) {
            self.mark_stopped();
        }
    }

    fn ensure<FReady, FSpawn, FRegister, FStop>(
        &mut self,
        mut ready: FReady,
        spawn: FSpawn,
        mut register: FRegister,
        mut stop: FStop,
    ) -> Result<u16, String>
    where
        FReady: FnMut(u16) -> bool,
        FSpawn: FnOnce() -> Result<SidecarIdentity, String>,
        FRegister: FnMut(SidecarIdentity),
        FStop: FnMut(SidecarIdentity),
    {
        if let Some(current) = self.current() {
            if ready(current.port) {
                self.mark_running(current);
                return Ok(current.port);
            }
            self.mark_stopped();
            stop(current);
        }

        let spawned = spawn()?;
        self.register(spawned);
        register(spawned);
        if ready(spawned.port) {
            self.mark_running(spawned);
            return Ok(spawned.port);
        }

        self.mark_stopped();
        stop(spawned);
        Err("Sidecar readiness timed out".to_string())
    }
}

#[derive(Default)]
struct OpenPathAllowlist {
    selected_paths: Mutex<Vec<PathBuf>>,
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
fn get_bootstrap(app: tauri::AppHandle) -> Result<BootstrapPayload, String> {
    let external_api_base_url = std::env::var("MINOS_DESKTOP_API_BASE_URL").ok();
    let (api_base_url, sidecar_managed) = if let Some(api_base_url) = external_api_base_url {
        (api_base_url, false)
    } else {
        let port = ensure_sidecar_running(&app)?;
        (format!("http://127.0.0.1:{}", port), true)
    };
    Ok(BootstrapPayload {
        app_name: "MINOS-CORE".to_string(),
        version: "3.8.6".to_string(),
        api_base_url,
        api_token: SIDECAR_TOKEN
            .get()
            .cloned()
            .or_else(|| std::env::var("MINOS_DESKTOP_API_TOKEN").ok()),
        sidecar_managed,
        workspace_root: None,
    })
}

#[tauri::command]
fn select_drawing_file(app: tauri::AppHandle, open_paths: tauri::State<OpenPathAllowlist>) -> Option<String> {
    let selected = app.dialog()
        .file()
        .add_filter("图纸文件", &["pdf", "png", "jpg", "jpeg"])
        .blocking_pick_file();
    if let Some(path) = selected.as_ref() {
        remember_allowed_path(&open_paths, path);
    }
    selected.map(|path| path.to_string())
}

#[tauri::command]
fn select_output_dir(app: tauri::AppHandle, open_paths: tauri::State<OpenPathAllowlist>) -> Option<String> {
    let selected = app.dialog()
        .file()
        .blocking_pick_folder()
        .map(|path| {
            remember_allowed_path(&open_paths, &path);
            path
        });
    selected.map(|path| path.to_string())
}

#[tauri::command]
fn select_component_drawings(app: tauri::AppHandle, open_paths: tauri::State<OpenPathAllowlist>) -> Vec<String> {
    app.dialog()
        .file()
        .add_filter("图纸文件", &["pdf", "png", "jpg", "jpeg"])
        .blocking_pick_files()
        .map(|paths| {
            paths
                .iter()
                .map(|path| {
                    remember_allowed_path(&open_paths, path);
                    path.to_string()
                })
                .collect()
        })
        .unwrap_or_default()
}

#[tauri::command]
fn open_output_dir(app: tauri::AppHandle, open_paths: tauri::State<OpenPathAllowlist>, path: String) -> Result<(), String> {
    let checked_path = ensure_open_path_allowed(&app, &open_paths, path)?;
    app.opener()
        .open_path(checked_path.to_string_lossy().to_string(), None::<&str>)
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn open_path(app: tauri::AppHandle, open_paths: tauri::State<OpenPathAllowlist>, path: String) -> Result<(), String> {
    let checked_path = ensure_open_path_allowed(&app, &open_paths, path)?;
    app.opener()
        .open_path(checked_path.to_string_lossy().to_string(), None::<&str>)
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn reveal_file(app: tauri::AppHandle, open_paths: tauri::State<OpenPathAllowlist>, path: String) -> Result<(), String> {
    let checked_path = ensure_open_path_allowed(&app, &open_paths, path)?;
    app.opener()
        .reveal_item_in_dir(checked_path)
        .map_err(|error| error.to_string())
}

fn remember_allowed_path(state: &tauri::State<OpenPathAllowlist>, path: &FilePath) {
    let Ok(path) = path.clone().into_path() else {
        return;
    };
    let allowed = path.canonicalize().unwrap_or(path);
    if let Ok(mut paths) = state.selected_paths.lock() {
        if !paths.iter().any(|existing| existing == &allowed) {
            paths.push(allowed);
        }
    }
}

fn canonicalize_open_path(path: &str) -> Result<PathBuf, String> {
    if path.trim().is_empty() || path.contains('\0') {
        return Err("Invalid path".to_string());
    }
    PathBuf::from(path)
        .canonicalize()
        .map_err(|error| error.to_string())
}

fn is_path_allowed(app: &tauri::AppHandle, state: &tauri::State<OpenPathAllowlist>, path: &Path) -> bool {
    let app_data_dir = app
        .path()
        .app_local_data_dir()
        .unwrap_or_else(|_| fallback_app_local_data_dir())
        .canonicalize()
        .unwrap_or_else(|_| fallback_app_local_data_dir());
    if path.starts_with(app_data_dir) {
        return true;
    }
    let Ok(paths) = state.selected_paths.lock() else {
        return false;
    };
    paths.iter().any(|allowed| path == allowed || path.starts_with(allowed))
}

fn ensure_open_path_allowed(
    app: &tauri::AppHandle,
    state: &tauri::State<OpenPathAllowlist>,
    path: String,
) -> Result<PathBuf, String> {
    let canonical = canonicalize_open_path(&path)?;
    if is_path_allowed(app, state, &canonical) {
        return Ok(canonical);
    }
    Err("Path is not allowed to be opened by MINOS-CORE".to_string())
}

#[tauri::command]
fn shutdown_sidecar() -> Result<(), String> {
    let slot = SIDECAR_PROCESS.get_or_init(|| Mutex::new(None));
    if let Some(process) = slot.lock().map_err(|error| error.to_string())?.take() {
        let _ = process.child.kill();
    }
    Ok(())
}

fn sidecar_process_slot() -> &'static Mutex<Option<SidecarProcess>> {
    SIDECAR_PROCESS.get_or_init(|| Mutex::new(None))
}

fn ensure_sidecar_running(app: &tauri::AppHandle) -> Result<u16, String> {
    // Keep the check, spawn, registration, and readiness wait under one lock so
    // concurrent bootstrap calls cannot create duplicate sidecars.
    let process_slot = sidecar_process_slot();
    let mut guard = process_slot.lock().map_err(|error| error.to_string())?;
    let token = SIDECAR_TOKEN
        .get_or_init(|| {
            std::env::var("MINOS_DESKTOP_API_TOKEN").unwrap_or_else(|_| generate_api_token())
        })
        .clone();
    let data_dir = app
        .path()
        .app_local_data_dir()
        .unwrap_or_else(|_| fallback_app_local_data_dir());
    let output_dir = data_dir.join("out");
    let db_path = data_dir.join("minos_desktop.sqlite3");
    let log_dir = data_dir.join("logs");
    let _ = std::fs::create_dir_all(&log_dir);
    let log_path = log_dir.join("api.log");
    let initial_identity = guard.as_ref().map(|process| SidecarIdentity {
        pid: process.pid,
        port: process.port,
    });
    let mut lifecycle = initial_identity
        .map(SidecarLifecycle::with_running)
        .unwrap_or_default();
    let process_state = std::cell::RefCell::new(guard.take());
    let spawned_child = std::cell::RefCell::new(None);

    let result = lifecycle.ensure(
        |port| wait_for_sidecar_ready(port, &token),
        || {
            let port = find_available_sidecar_port()
                .ok_or_else(|| "No available sidecar port".to_string())?;
            let command = app
                .shell()
                .sidecar(SIDECAR_NAME)
                .map_err(|_| "Unable to configure sidecar command".to_string())?;
            let port_arg = port.to_string();
            let db_path_arg = db_path.to_string_lossy().to_string();
            let output_dir_arg = output_dir.to_string_lossy().to_string();
            let command = command.env("MINOS_DESKTOP_API_TOKEN", &token).args([
                "--host",
                "127.0.0.1",
                "--port",
                &port_arg,
                "--db-path",
                &db_path_arg,
                "--output-dir",
                &output_dir_arg,
            ]);
            let (mut rx, child) = command
                .spawn()
                .map_err(|_| "Unable to spawn sidecar".to_string())?;
            let pid = child.pid();
            spawned_child.borrow_mut().replace(child);

            let process_pid = pid;
            tauri::async_runtime::spawn(async move {
                let mut log_file = open_log_file(log_path);
                while let Some(event) = rx.recv().await {
                    let terminated = matches!(&event, CommandEvent::Terminated(_));
                    write_command_event(&mut log_file, event);
                    if terminated {
                        clear_sidecar_if_pid(process_pid);
                    }
                }
            });

            Ok(SidecarIdentity { pid, port })
        },
        |identity| {
            let child = spawned_child
                .borrow_mut()
                .take()
                .expect("sidecar child must be registered after spawn");
            *process_state.borrow_mut() = Some(SidecarProcess {
                child,
                port: identity.port,
                pid: identity.pid,
            });
        },
        |identity| {
            let should_stop = process_state
                .borrow()
                .as_ref()
                .is_some_and(|process| process.pid == identity.pid);
            if should_stop {
                if let Some(process) = process_state.borrow_mut().take() {
                    let _ = process.child.kill();
                }
            }
        },
    );

    *guard = process_state.into_inner();
    result
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
    let redacted = match SIDECAR_TOKEN.get() {
        Some(token) => redact_sidecar_log(&text, token),
        None => text.to_string(),
    };
    let _ = writeln!(file, "[{stream}] {redacted}");
}

fn redact_sidecar_log(text: &str, token: &str) -> String {
    if token.is_empty() {
        return text.to_string();
    }
    text.replace(token, "***REDACTED***")
}

fn clear_sidecar_if_pid(pid: u32) {
    let Some(slot) = SIDECAR_PROCESS.get() else {
        return;
    };
    let Ok(mut guard) = slot.lock() else {
        return;
    };
    let Some(current) = guard.as_ref().map(|process| SidecarIdentity {
        pid: process.pid,
        port: process.port,
    }) else {
        return;
    };
    let mut lifecycle = SidecarLifecycle::with_running(current);
    lifecycle.terminated(pid);
    if lifecycle.phase() == SidecarPhase::Stopped {
        *guard = None;
    }
}

fn is_sidecar_ready(port: u16, token: &str) -> bool {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(200)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(200)));
    let request = format!(
        "GET /api/health HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nAuthorization: Bearer {token}\r\nConnection: close\r\n\r\n"
    );
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }
    let mut bytes = Vec::new();
    if stream.read_to_end(&mut bytes).is_err() {
        return false;
    }
    let response = String::from_utf8_lossy(&bytes);
    let Some((headers, body)) = response.split_once("\r\n\r\n") else {
        return false;
    };
    let status_ok = headers
        .lines()
        .next()
        .is_some_and(|line| line.starts_with("HTTP/1.1 200") || line.starts_with("HTTP/1.0 200"));
    if !status_ok {
        return false;
    }
    let body = body
        .chars()
        .filter(|character| !character.is_whitespace())
        .collect::<String>();
    body.contains("\"ok\":true") && body.contains("\"status\":\"ok\"")
}

fn wait_for_sidecar_ready(port: u16, token: &str) -> bool {
    for _ in 0..30 {
        if is_sidecar_ready(port, token) {
            return true;
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    false
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
        .manage(OpenPathAllowlist::default())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let app_handle = app.handle().clone();
            app.listen("tauri://close-requested", move |_| {
                let _ = shutdown_sidecar();
                let _ = app_handle.exit(0);
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_bootstrap,
            select_drawing_file,
            select_output_dir,
            select_component_drawings,
            open_output_dir,
            open_path,
            reveal_file,
            shutdown_sidecar
        ])
        .run(tauri::generate_context!())
        .expect("failed to run MINOS-CORE desktop app");
}

#[cfg(test)]
mod tests {
    use super::{redact_sidecar_log, SidecarIdentity, SidecarLifecycle, SidecarPhase};
    use std::sync::{
        atomic::{AtomicUsize, Ordering},
        Arc, Barrier, Mutex,
    };
    use std::thread;

    #[test]
    fn sidecar_log_redacts_injected_token() {
        assert_eq!(
            redact_sidecar_log("authorization=test-token", "test-token"),
            "authorization=***REDACTED***"
        );
        assert_eq!(redact_sidecar_log("plain log", ""), "plain log");
    }

    #[test]
    fn concurrent_ensure_spawns_only_once() {
        let lifecycle = Arc::new(Mutex::new(SidecarLifecycle::default()));
        let spawn_count = Arc::new(AtomicUsize::new(0));
        let barrier = Arc::new(Barrier::new(8));
        let handles = (0..8)
            .map(|_| {
                let lifecycle = Arc::clone(&lifecycle);
                let spawn_count = Arc::clone(&spawn_count);
                let barrier = Arc::clone(&barrier);
                thread::spawn(move || {
                    barrier.wait();
                    let mut lifecycle = lifecycle.lock().expect("lifecycle lock");
                    lifecycle.ensure(
                        |_| true,
                        || {
                            spawn_count.fetch_add(1, Ordering::SeqCst);
                            Ok(SidecarIdentity {
                                pid: 101,
                                port: 8000,
                            })
                        },
                        |_| {},
                        |_| {},
                    )
                })
            })
            .collect::<Vec<_>>();

        for handle in handles {
            assert_eq!(handle.join().expect("worker join").expect("ready"), 8000);
        }
        assert_eq!(spawn_count.load(Ordering::SeqCst), 1);
        assert_eq!(
            lifecycle.lock().expect("lifecycle lock").phase(),
            SidecarPhase::Running(SidecarIdentity {
                pid: 101,
                port: 8000,
            })
        );
    }

    #[test]
    fn terminated_old_pid_does_not_clear_new_pid() {
        let mut lifecycle = SidecarLifecycle::default();
        lifecycle.register(SidecarIdentity {
            pid: 101,
            port: 8000,
        });
        assert_eq!(
            lifecycle.phase(),
            SidecarPhase::Starting(SidecarIdentity {
                pid: 101,
                port: 8000,
            })
        );

        lifecycle.terminated(99);
        assert_eq!(
            lifecycle.current(),
            Some(SidecarIdentity {
                pid: 101,
                port: 8000,
            })
        );

        lifecycle.terminated(101);
        assert_eq!(lifecycle.current(), None);
        assert_eq!(lifecycle.phase(), SidecarPhase::Stopped);
    }

    #[test]
    fn readiness_timeout_returns_error_and_cleans_up_registered_pid() {
        let mut lifecycle = SidecarLifecycle::default();
        let mut registered = Vec::new();
        let mut stopped = Vec::new();

        let result = lifecycle.ensure(
            |_| false,
            || {
                Ok(SidecarIdentity {
                    pid: 202,
                    port: 8001,
                })
            },
            |identity| registered.push(identity),
            |identity| stopped.push(identity),
        );

        assert_eq!(result, Err("Sidecar readiness timed out".to_string()));
        assert_eq!(
            registered,
            vec![SidecarIdentity {
                pid: 202,
                port: 8001,
            }]
        );
        assert_eq!(
            stopped,
            vec![SidecarIdentity {
                pid: 202,
                port: 8001,
            }]
        );
        assert_eq!(lifecycle.current(), None);
        assert_eq!(lifecycle.phase(), SidecarPhase::Stopped);
    }
}
