//! Locate a binary Tauri staged inside the app bundle (`externalBin`).
//!
//! This module used to also COPY the bundled binaries into `~/.coffer/bin/`
//! on every launch. That job now belongs to the daemon's own frozen-start
//! path (spec daemon "Deploy frozen sibling binaries and back up the vault
//! before migrating",
//! `backend/coffer/application/binary_deploy.py`), which deploys `coffer`,
//! `coffer-daemon` and `coffer-mcp-shim` itself. Doing it
//! here as well would put two processes in a race to write the same
//! directory, so the shell only *reads* the bundle now — it never writes to
//! the user's bin dir.

use std::path::PathBuf;

use tauri::{AppHandle, Manager};

/// Locate a bundled sidecar binary alongside this application, probing each
/// of `exe_names` in every platform-specific candidate directory.
///
/// Tauri 2 stages `externalBin` differently per platform:
///   * macOS: `Foo.app/Contents/MacOS/<binary>` (next to the main exe).
///   * Linux/Windows AppImage/MSI: alongside the resource directory.
///
/// We probe `Contents/MacOS/` explicitly on macOS, plus the resource dir
/// itself and its parent to cover older layouts and Linux/Windows. On Windows
/// the caller's name(s) plus a `.exe` variant are both tried in each location.
///
/// This is step 2 of the daemon-resolution chain in
/// [`crate::resolve::resolve_daemon_source`].
pub fn resolve_sidecar(app: &AppHandle, exe_names: &[&str]) -> Result<PathBuf, String> {
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|e| format!("resource_dir: {e}"))?;

    let parent = resource_dir.parent().map(|p| p.to_owned());
    // macOS: Tauri places externalBin in Contents/MacOS/, sibling of
    // Contents/Resources/. resource_dir() returns Contents/Resources, so
    // its parent (Contents) joined with MacOS is where the sidecar lives.
    let macos_dir = parent.as_deref().map(|p| p.join("MacOS"));

    // Each probe directory, in priority order.
    let dirs: Vec<PathBuf> = [macos_dir, Some(resource_dir.clone()), parent]
        .into_iter()
        .flatten()
        .collect();

    let mut candidates: Vec<PathBuf> = Vec::new();
    for dir in &dirs {
        for name in exe_names {
            candidates.push(dir.join(name));
            // Always also try the Windows `.exe` variant so a probe configured
            // with a bare name still finds the `.exe` on Windows.
            if !name.ends_with(".exe") {
                candidates.push(dir.join(format!("{name}.exe")));
            }
        }
    }

    for c in &candidates {
        if c.is_file() {
            return Ok(c.clone());
        }
    }

    let wanted = exe_names.join(", ");
    Err(format!(
        "{wanted} not found near {} (searched {} candidates)",
        resource_dir.display(),
        candidates.len()
    ))
}
