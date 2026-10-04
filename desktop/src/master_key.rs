//! Where the shell reads the master key from, at the moment it signs a
//! presence grant (design D1 and D6 of `add-secret-boundary`).
//!
//! The key is read per signature and dropped with it: nothing here caches the
//! key or the grant key between operations, so a shell that has been open all
//! day holds no more than one that just launched.
//!
//! Two arrangements, chosen at compile time by the access group the release
//! pipeline stamps into a signed build (`COFFER_KEYCHAIN_ACCESS_GROUP`):
//!
//! * **Production** — the data-protection Keychain item (service `coffer`,
//!   account `master-key`) in that access group. Only binaries signed with the
//!   same Team ID and carrying the `keychain-access-groups` entitlement can
//!   read it, which is what keeps a process an agent controls from signing a
//!   grant. The shell only ever READS this item; creating, relocating and
//!   deleting it is the daemon's job (`master_key_backends.py`).
//! * **Development** — `~/.coffer/master.key`. This is the clearly-marked dev
//!   fallback: ANY process running as the same user can read that file, so in a
//!   development build a grant can be forged and the boundary does not hold.
//!   Every presence prompt says "Development build" for that reason.

use std::path::PathBuf;

use crate::coffer_home;

/// The access group a signed release build was stamped with, or `None` for
/// every build from source.
const ACCESS_GROUP: Option<&str> = option_env!("COFFER_KEYCHAIN_ACCESS_GROUP");

/// The Keychain item the daemon keeps the key in.
#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
const KEYCHAIN_SERVICE: &str = "coffer";
#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
const KEYCHAIN_ACCOUNT: &str = "master-key";

/// Whether this shell was built without a stamped access group — i.e. whether
/// it reads the key from a file any same-user process can read. Decided by the
/// shell's own build, never by anything the daemon says.
pub fn is_development_build() -> bool {
    ACCESS_GROUP.is_none()
}

/// The master key's text, read just now. Callers sign with it and drop it.
pub fn read() -> Result<Vec<u8>, String> {
    match ACCESS_GROUP {
        Some(group) => read_keychain(group),
        None => read_dev_file(),
    }
}

/// `~/.coffer/master.key` — the development arrangement's key file.
fn dev_key_file() -> Option<PathBuf> {
    let home = std::env::var_os("HOME")?;
    Some(coffer_home::master_key(home))
}

/// DEVELOPMENT FALLBACK: any same-user process can read this file, so a grant
/// signed from it proves nothing about a person — see the module comment.
fn read_dev_file() -> Result<Vec<u8>, String> {
    let path = dev_key_file().ok_or("HOME is not set, so the master key cannot be found")?;
    let raw = std::fs::read(&path).map_err(|e| {
        format!(
            "cannot read the development master key at {}: {e}",
            path.display()
        )
    })?;
    non_empty(raw)
}

fn non_empty(raw: Vec<u8>) -> Result<Vec<u8>, String> {
    if raw.iter().all(u8::is_ascii_whitespace) {
        return Err("the master key is empty".to_owned());
    }
    Ok(raw)
}

#[cfg(target_os = "macos")]
fn read_keychain(group: &str) -> Result<Vec<u8>, String> {
    use security_framework::passwords::{generic_password, PasswordOptions};

    let mut options = PasswordOptions::new_generic_password(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT);
    // The data-protection keychain, not the login keychain: access groups are
    // only enforced there (`kSecUseDataProtectionKeychain`).
    options.use_protected_keychain();
    options.set_access_group(group);
    let raw = generic_password(options)
        .map_err(|e| format!("cannot read Coffer's master key from the Keychain: {e}"))?;
    non_empty(raw)
}

#[cfg(not(target_os = "macos"))]
fn read_keychain(_group: &str) -> Result<Vec<u8>, String> {
    Err("the Keychain is only available on macOS".to_owned())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_blank_key_is_refused_rather_than_signed_with() {
        assert!(non_empty(b"  \n".to_vec()).is_err());
        assert!(non_empty(Vec::new()).is_err());
        assert_eq!(non_empty(b"k\n".to_vec()).unwrap(), b"k\n");
    }

    #[test]
    fn a_build_from_source_is_a_development_build() {
        // Tests are never built by the release pipeline, so the access group
        // is unset and the shell must say it is a development build.
        if option_env!("COFFER_KEYCHAIN_ACCESS_GROUP").is_none() {
            assert!(is_development_build());
        }
    }
}
