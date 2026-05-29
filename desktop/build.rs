// Tauri build script. Just delegates to `tauri-build`.
//
// CSP notes (see tauri.conf.json -> app.security.csp):
//
//   - `connect-src ... http://127.0.0.1:*` allows any loopback port. This is
//     deliberate: the bundled coffer-daemon allocates a free port at startup
//     (see backend/coffer/infrastructure/daemon/bootstrap.py), so the exact
//     port number is not known at build time. Restricting to a single port
//     would break the daemon's auto-port-allocation feature. The threat
//     surface stays local-only — no remote origin is permitted.
//
//   - `style-src 'self' 'unsafe-inline'` is required by Tailwind / Vite,
//     which emit small inline <style> tags for runtime-computed atomic
//     classes. Removing 'unsafe-inline' breaks the frontend build's
//     style hydration.
//
// If we later move to a fixed daemon port (or add a build-time substitution
// step), this script is the right place to inject the value into the CSP
// before tauri-build picks up tauri.conf.json.
fn main() {
    tauri_build::build()
}
