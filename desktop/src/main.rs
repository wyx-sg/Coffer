// Prevents an additional console window from appearing on Windows release
// builds. Required by Tauri 2 template — do not remove.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    coffer_desktop_lib::run()
}
