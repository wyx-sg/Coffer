//! Is this really Coffer's daemon? (spec desktop-app "Release plaintext and
//! approvals only after a presence check in the shell".)
//!
//! The shell finds a daemon through `~/.coffer/daemon.json`, a file any process
//! of the same user can write. A fake daemon there could relay to the real one,
//! capture a revealed value, or describe an approval harmlessly while the shell
//! signs the real id. So before the shell trusts a daemon with anything that
//! matters, it sends a random nonce and checks the answer against its own
//! derivation: `HMAC-SHA256(attest key, "coffer-attest/v1\n" + nonce + "\n" +
//! port)`, the attest key being derived from the master key. Only a process that
//! can read the master key can answer, and the port is in the signed text, so an
//! answer relayed from the real daemon on another port verifies for nothing.

use hmac::{Hmac, Mac};
use serde_json::{json, Value};
use sha2::Sha256;

use crate::daemon_http::{self, DEFAULT_READ_TIMEOUT};
use crate::master_key;

type HmacSha256 = Hmac<Sha256>;

/// The label the daemon attest key is derived under; the daemon's
/// `DAEMON_ATTEST_KEY_CONTEXT`.
const ATTEST_KEY_LABEL: &[u8] = b"coffer-daemon-attest-key/v1";
/// The first line of every attested message.
const ATTEST_PREFIX: &str = "coffer-attest/v1";

/// What every refused daemon is called, so the page and the log say one thing.
pub const NOT_COFFERS_DAEMON: &str = "This is not Coffer's daemon — nothing was sent";

/// `HMAC-SHA256(key = master key text, msg = label)`, whitespace-trimmed like
/// the grant key.
fn attest_key(master_key: &[u8]) -> [u8; 32] {
    let mut mac = HmacSha256::new_from_slice(trim(master_key)).expect("HMAC takes any key length");
    mac.update(ATTEST_KEY_LABEL);
    mac.finalize().into_bytes().into()
}

fn mac_for(key: &[u8; 32], nonce: &str, port: u16) -> HmacSha256 {
    let mut mac = HmacSha256::new_from_slice(key).expect("HMAC takes any key length");
    mac.update(format!("{ATTEST_PREFIX}\n{nonce}\n{port}").as_bytes());
    mac
}

/// The lower-case hex answer a genuine daemon on `port` gives to `nonce`.
#[cfg(test)]
fn expected_signature(master_key: &[u8], nonce: &str, port: u16) -> String {
    hex::encode(
        mac_for(&attest_key(master_key), nonce, port)
            .finalize()
            .into_bytes(),
    )
}

/// Whether `signature` (hex) is the genuine answer for `nonce` on `port`.
/// The comparison is constant-time (`Mac::verify_slice`).
fn verifies(master_key: &[u8], nonce: &str, port: u16, signature: &str) -> bool {
    let Ok(given) = hex::decode(signature.trim()) else {
        return false;
    };
    mac_for(&attest_key(master_key), nonce, port)
        .verify_slice(&given)
        .is_ok()
}

/// A fresh nonce: 32 url-safe characters from the operating system's RNG.
fn new_nonce() -> Result<String, String> {
    use std::io::Read;
    let mut bytes = [0u8; 16];
    std::fs::File::open("/dev/urandom")
        .and_then(|mut f| f.read_exact(&mut bytes))
        .map_err(|e| format!("could not get random bytes for a daemon check: {e}"))?;
    Ok(hex::encode(bytes))
}

/// Challenge the daemon on `port` and verify its answer, or refuse it. The
/// master key is read here and dropped before this returns.
pub fn verify_daemon(port: u16, token: &str) -> Result<(), String> {
    let nonce = new_nonce()?;
    let answer = daemon_http::post_json(
        port,
        token,
        "/api/v1/secrets/presence/attest",
        &json!({ "nonce": nonce }),
        DEFAULT_READ_TIMEOUT,
    )
    .ok()
    .and_then(|r| daemon_http::json_or_error(r).ok());
    let signature = answer
        .as_ref()
        .and_then(|v: &Value| v.get("signature"))
        .and_then(Value::as_str);
    let key = master_key::read()?;
    let genuine = signature.is_some_and(|s| verifies(&key, &nonce, port, s));
    drop(key);
    if genuine {
        Ok(())
    } else {
        log::warn!("daemon on port {port} failed the attestation check");
        Err(NOT_COFFERS_DAEMON.to_owned())
    }
}

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

    /// The vectors the daemon's own tests carry
    /// (`backend/tests/integration/security/test_daemon_attestation.py`).
    #[test]
    fn the_attest_key_matches_the_daemons_vector() {
        assert_eq!(
            hex::encode(attest_key(MASTER)),
            "1037a277fa914a1ae40b22967caeb076bba99cc8f5ada5ce47fce7f1a04f4e63"
        );
        // Whitespace around the key text does not change it.
        assert_eq!(
            attest_key(b" \n  ZmFrZS1tYXN0ZXIta2V5LWZvci10ZXN0cy0wMDAwMDA=\n"),
            attest_key(MASTER)
        );
    }

    /// With no port in the message the signature is the daemon's vector, which
    /// pins the prefix and the layout; the port is then appended.
    #[test]
    fn the_signature_matches_the_daemons_vector_and_is_bound_to_the_port() {
        let key = attest_key(MASTER);
        let mut mac = HmacSha256::new_from_slice(&key).unwrap();
        mac.update(format!("{ATTEST_PREFIX}\nnonce-123").as_bytes());
        assert_eq!(
            hex::encode(mac.finalize().into_bytes()),
            "9ea1bd3ea31d3819392c1a1ab7d367b01d1595860e08189d9dce98c9216fe23b"
        );
        let good = expected_signature(MASTER, "nonce-123", 38470);
        assert!(verifies(MASTER, "nonce-123", 38470, &good));
    }

    #[test]
    fn an_answer_for_another_port_nonce_or_key_does_not_verify() {
        let good = expected_signature(MASTER, "nonce-123", 38470);
        assert!(!verifies(MASTER, "nonce-123", 38471, &good));
        assert!(!verifies(MASTER, "nonce-124", 38470, &good));
        assert!(!verifies(b"another-key", "nonce-123", 38470, &good));
        assert!(!verifies(MASTER, "nonce-123", 38470, "not hex"));
        assert!(!verifies(MASTER, "nonce-123", 38470, ""));
        assert!(!verifies(
            MASTER,
            "nonce-123",
            38470,
            &good[..good.len() - 2]
        ));
    }

    #[test]
    fn nonces_are_url_safe_and_fresh() {
        let (a, b) = (new_nonce().unwrap(), new_nonce().unwrap());
        assert_eq!(a.len(), 32);
        assert!(a.chars().all(|c| c.is_ascii_hexdigit()));
        assert_ne!(a, b);
    }
}
