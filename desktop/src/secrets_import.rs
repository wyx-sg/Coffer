//! The IPC command that installs a master key (spec secret "Release plaintext
//! only to a present human in the desktop app"). Split from `secrets.rs` to keep
//! each file under the size cap.

use serde_json::{json, Value};
use tauri::AppHandle;

use crate::daemon_http::DEFAULT_READ_TIMEOUT;
use crate::presence::{self, Subject};
use crate::presence_grant::GrantOp;
use crate::secrets::{blocking, Daemon};

/// Writing the key is quick, but it is a disk write behind a request.
const IMPORT_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(30);

/// Install a master key from a file's text, after a presence check that names
/// the key's fingerprint. The shell asks the daemon whose key the file holds
/// (a read-only preview), shows that fingerprint in the operating system's
/// prompt, and signs a grant over it; the daemon installs the key only for a
/// grant over the fingerprint of the key it is sent. The passphrase of a
/// protected backup goes to the daemon in the import request and nowhere else.
#[tauri::command]
pub async fn import_master_key(
    app: AppHandle,
    material: String,
    passphrase: Option<String>,
) -> Result<Value, String> {
    blocking(move || {
        let daemon = Daemon::find()?;
        let development = daemon.development()?;
        let preview = daemon.post(
            "/api/v1/sync/key/import/preview",
            &json!({"material": material}),
            DEFAULT_READ_TIMEOUT,
        )?;
        let fingerprint = preview
            .get("fingerprint")
            .and_then(Value::as_str)
            .filter(|f| !f.is_empty())
            .ok_or("the daemon's preview carried no fingerprint")?
            .to_owned();
        presence::confirm(
            &app,
            &Subject::ImportMasterKey {
                fingerprint: &fingerprint,
            },
            development,
        )?;
        let (nonce, signature) = daemon.grant(GrantOp::ImportMasterKey, &fingerprint)?;
        daemon.post(
            "/api/v1/sync/key/import",
            &import_body(&material, passphrase.as_deref(), &nonce, &signature),
            IMPORT_TIMEOUT,
        )
    })
    .await
}

/// The import request: the material and passphrase, with the grant over the
/// fingerprint of that material.
fn import_body(material: &str, passphrase: Option<&str>, nonce: &str, signature: &str) -> Value {
    json!({
        "material": material,
        "passphrase": passphrase,
        "nonce": nonce,
        "signature": signature,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn an_import_request_carries_the_grant_beside_the_key() {
        let body = import_body("key-text", None, "n1", "sig");
        assert_eq!(
            body,
            json!({"material": "key-text", "passphrase": null, "nonce": "n1", "signature": "sig"})
        );
        assert_eq!(import_body("k", Some("pw"), "n", "s")["passphrase"], "pw");
    }
}
