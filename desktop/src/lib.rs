// Tauri 2 entry point. The `mobile_entry_point` macro lets the same crate
// be reused later for iOS/Android without restructuring.
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
