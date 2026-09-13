// Tauri build script. Just delegates to `tauri-build`.
//
// CSP notes (see tauri.conf.json -> app.security.csp):
//
//   - `connect-src ... http://127.0.0.1:*` allows any loopback port. The
//     daemon now binds a fixed port by default (8000, see the desktop-shell
//     ADR), but that default is user-configurable via `coffer daemon port
//     set`, so the exact port is still not known at build time. Pinning a
//     single port here would break every user who moved it. The threat
//     surface stays local-only — no remote origin is permitted.
//
//   - `style-src 'self' 'unsafe-inline'` is required by Tailwind / Vite,
//     which emit small inline <style> tags for runtime-computed atomic
//     classes. Removing 'unsafe-inline' breaks the frontend build's
//     style hydration.
//
// If the configured port ever becomes build-time knowable, this script is the
// right place to inject the value into the CSP before tauri-build picks up
// tauri.conf.json.
fn main() {
    tauri_build::build()
}
