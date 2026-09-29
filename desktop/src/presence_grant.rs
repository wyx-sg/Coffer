//! The presence grant: the HMAC that tells the daemon a person approved one
//! exact operation (design D1 of `add-secret-boundary`; spec desktop-app
//! "Release plaintext and approvals only after a presence check in the
//! shell").
//!
//! The daemon holds the master key and issues a single-use nonce; the shell,
//! after the operating system has confirmed a person is present, signs
//! `op`, `target` and that nonce with a key derived from the same master key.
//! Both halves must agree byte-for-byte, which is why the derivation and the
//! message layout live here as constants and the test carries the vectors the
//! Python tests carry.

use hmac::{Hmac, Mac};
use sha2::Sha256;

type HmacSha256 = Hmac<Sha256>;

/// The label the grant key is derived under. Versioned so a later layout can
/// never verify against an old key by accident.
const GRANT_KEY_LABEL: &[u8] = b"coffer-presence-grant-key/v1";
/// The first line of every signed message.
const GRANT_PREFIX: &str = "coffer-presence-grant/v1";

/// The operations a grant can approve. The strings are the daemon's `op`
/// values; nothing else is ever signed.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GrantOp {
    Reveal,
    Approve,
    ExportMasterKey,
}

impl GrantOp {
    pub fn as_str(self) -> &'static str {
        match self {
            GrantOp::Reveal => "reveal",
            GrantOp::Approve => "approve",
            GrantOp::ExportMasterKey => "export_master_key",
        }
    }
}

/// `HMAC-SHA256(key = master key text, msg = label)`. Derived on demand from a
/// key the caller has just read, and dropped with it — never stored, and never
/// the master key itself.
fn grant_key(master_key: &[u8]) -> [u8; 32] {
    let mut mac = HmacSha256::new_from_slice(trim(master_key)).expect("HMAC takes any key length");
    mac.update(GRANT_KEY_LABEL);
    mac.finalize().into_bytes().into()
}

/// The lower-case hex signature over exactly one operation on one target
/// under one nonce. A nonce is single-use on the daemon's side, so the
/// signature is worth nothing after the request it goes with.
pub fn sign(master_key: &[u8], op: GrantOp, target: &str, nonce: &str) -> String {
    let key = grant_key(master_key);
    let mut mac = HmacSha256::new_from_slice(&key).expect("HMAC takes any key length");
    mac.update(format!("{GRANT_PREFIX}\n{}\n{target}\n{nonce}", op.as_str()).as_bytes());
    hex::encode(mac.finalize().into_bytes())
}

/// The Fernet key's base64 text with surrounding whitespace stripped — the
/// daemon keys its HMAC on the same bytes, and a trailing newline in a key
/// file must not make the two disagree.
fn trim(bytes: &[u8]) -> &[u8] {
    let start = bytes
        .iter()
        .position(|b| !b.is_ascii_whitespace())
        .unwrap_or(bytes.len());
    let end = bytes
        .iter()
        .rposition(|b| !b.is_ascii_whitespace())
        .map_or(start, |i| i + 1);
    &bytes[start..end]
}

#[cfg(test)]
mod tests {
    use super::*;

    const MASTER: &[u8] = b"ZmFrZS1tYXN0ZXIta2V5LWZvci10ZXN0cy0wMDAwMDA=";

    /// The vectors in design D1, shared with the daemon's own tests: if either
    /// side changes its derivation or layout, one of the two suites fails.
    // acceptance(spec = "desktop-app", scenario = "a presence grant signs exactly the approved operation")
    #[test]
    fn a_grant_matches_the_daemons_vectors_and_nothing_else() {
        assert_eq!(
            hex::encode(grant_key(MASTER)),
            "84cccae592fbe9961c40a663f512eaa2045d99f3ccd974e92fddbf8ea4492347"
        );
        assert_eq!(
            sign(MASTER, GrantOp::Reveal, "gh/token", "nonce-123"),
            "8654e8c12fcba0b8617f06e3c84c9636ab6d5a0a3b5221d531d1dc08c7a6cd50"
        );
        assert_eq!(
            sign(MASTER, GrantOp::Approve, "0123456789abcdef", "nonce-456"),
            "13c3e5b98ae8c394f98b1f1631ac06e4d886b604876383fc29aee12b6118892c"
        );
        assert_eq!(
            sign(
                MASTER,
                GrantOp::ExportMasterKey,
                "/Users/me/Backups",
                "nonce-789"
            ),
            "2382008c76facbd67f01aacbf1da779c690ae654af87f9a8bf5ade889cfba3bd"
        );
        // The same nonce on another target or another op is another signature:
        // a grant approves exactly what the person was shown.
        let approved = sign(MASTER, GrantOp::Reveal, "gh/token", "nonce-123");
        assert_ne!(
            approved,
            sign(MASTER, GrantOp::Reveal, "gh/other", "nonce-123")
        );
        assert_ne!(
            approved,
            sign(MASTER, GrantOp::Approve, "gh/token", "nonce-123")
        );
    }

    #[test]
    fn surrounding_whitespace_in_the_key_does_not_change_the_grant() {
        let padded = b"  ZmFrZS1tYXN0ZXIta2V5LWZvci10ZXN0cy0wMDAwMDA=\n";
        assert_eq!(grant_key(padded), grant_key(MASTER));
        assert_eq!(trim(b" \n\t"), b"");
    }
}
