# Sidecar Process Cleanup on Startup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kill stale sidecar processes from previous launches before spawning a new one, preventing port conflicts (8000 → 8001 drift) and frontend state confusion.

**Architecture:** Add a `kill_stale_sidecars()` function in `lib.rs` that runs platform-specific commands (`taskkill` on Windows, `pkill` on Unix) before `ensure_sidecar_running` spawns a new process. This is a 5-line insertion with no new dependencies.

**Tech Stack:** Rust / Tauri v2

---

## Problem

When the Tauri app restarts (user closes → reopens, or crash), the previous sidecar process (`minos-desktop-api.exe`) survives because:

1. `SIDECAR_PROCESS` is a `OnceCell` — reset on each Tauri launch, so the new process has no handle to the old one
2. `shutdown_sidecar()` only kills the process referenced in the current `OnceCell`
3. `ensure_sidecar_running()` checks port availability via `TcpListener::bind` — it finds 8000 busy and silently moves to 8001

**Symptoms:**
- Two sidecar processes accumulate (ports 8000 + 8001)
- Frontend may connect to wrong port or cache stale run IDs
- User operations (data clear) on one port don't sync to the other

---

### Task 1: Add `kill_stale_sidecars()` and call it before port scan

**Files:**
- Modify: `apps/desktop-tauri/src-tauri/src/lib.rs:111-121`

- [ ] **Step 1: Add `kill_stale_sidecars` function and call it**

Insert the function before `ensure_sidecar_running`, and add the call at its start.

In `apps/desktop-tauri/src-tauri/src/lib.rs`, after the `shutdown_sidecar` function (line 109) and before `ensure_sidecar_running` (line 111), add:

```rust
/// Kill any sidecar processes left over from a previous launch.
/// Without this, a restart leaves the old sidecar alive on port 8000,
/// forcing the new launch onto port 8001 and causing frontend confusion.
fn kill_stale_sidecars() {
    #[cfg(target_os = "windows")]
    {
        let _ = std::process::Command::new("taskkill")
            .args(["/F", "/IM", "minos-desktop-api.exe"])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status();
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = std::process::Command::new("pkill")
            .args(["-f", "minos-desktop-api"])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status();
    }
}
```

Then at the start of `ensure_sidecar_running` (line 111), add the call:

```rust
fn ensure_sidecar_running(app: &tauri::AppHandle) -> Option<u16> {
    kill_stale_sidecars();  // <-- NEW: clean up before port scan
    if let Some(slot) = SIDECAR_PROCESS.get() {
```

- [ ] **Step 2: Verify Rust compiles**

Run: `cargo -C "D:/MINOS-CORE/apps/desktop-tauri/src-tauri" check 2>&1`
Expected: exit 0, no errors.

But wait — `cargo` doesn't have `-C`. Use:

Run: `cd "D:/MINOS-CORE/apps/desktop-tauri/src-tauri" && cargo check 2>&1`
Expected: exit 0, no errors.

- [ ] **Step 3: Commit**

```bash
git -C "D:/MINOS-CORE" add apps/desktop-tauri/src-tauri/src/lib.rs
git -C "D:/MINOS-CORE" commit -m "fix(desktop): kill stale sidecar processes on startup to prevent port drift"
```

---

### Task 2: Rebuild the installer and verify

- [ ] **Step 1: Rebuild sidecar + Tauri + NSIS**

```bash
powershell -ExecutionPolicy Bypass -File "D:/MINOS-CORE/scripts/build_release.ps1"
```

Expected: installer at `release/MINOS-CORE_3.2.1_x64-setup.exe`

- [ ] **Step 2: Kill current stale processes (immediate fix for user)**

```bash
taskkill /F /IM minos-desktop-api.exe 2>$null
taskkill /F /IM minos-core-desktop.exe 2>$null
```

Then have user re-launch from the new installer.

---

## Summary

| File | Change | Risk |
|---|---|---|
| `lib.rs` | +14 lines: `kill_stale_sidecars()` + one call | Low — only adds cleanup, no behavior change for first launch |

**Total: 1 file, ~15 lines, 1 commit.**
