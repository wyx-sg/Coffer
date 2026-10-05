//! The daemon as the secret commands and the desktop-request watcher talk to
//! it: found through `daemon.json`, asked over loopback HTTP, and the one place
//! a presence grant is signed — the challenge must echo the operation and the
//! target the person approved, and the master key is read for the signature
//! and dropped with it.

use std::time::Duration;

use serde_json::{json, Value};

use crate::daemon_attest;
use crate::daemon_http::{self, DEFAULT_READ_TIMEOUT};
use crate::discovery::read_daemon_info;
use crate::master_key;
use crate::presence_grant::{self, GrantOp};

/// The running daemon, as `daemon.json` names it.
pub struct Daemon {
    port: u16,
    token: String,
}

impl Daemon {
    pub fn find() -> Result<Daemon, String> {
        let (port, token) = read_daemon_info().ok_or("Coffer's daemon is not running")?;
        // Before anything is sent: `daemon.json` can be written by any process
        // of this user, so the daemon it names must first prove it holds the key.
        daemon_attest::verify_daemon(port, &token)?;
        Ok(Daemon { port, token })
    }

    pub fn get(&self, path: &str) -> Result<Value, String> {
        daemon_http::json_or_error(daemon_http::get(
            self.port,
            &self.token,
            path,
            DEFAULT_READ_TIMEOUT,
        )?)
    }

    pub fn post(&self, path: &str, body: &Value, timeout: Duration) -> Result<Value, String> {
        daemon_http::json_or_error(daemon_http::post_json(
            self.port,
            &self.token,
            path,
            body,
            timeout,
        )?)
    }

    /// The daemon's own report of whether its key is in the development file.
    pub fn development(&self) -> Result<bool, String> {
        let status = self.get("/api/v1/secrets/presence/status")?;
        Ok(status
            .get("development")
            .and_then(Value::as_bool)
            .unwrap_or(true))
    }

    /// Ask for a nonce and sign `(op, target, nonce)`. The key is read here,
    /// after the presence check, and dropped before this returns.
    pub fn grant(&self, op: GrantOp, target: &str) -> Result<(String, String), String> {
        let challenge = self.post(
            "/api/v1/secrets/presence/challenge",
            &json!({"op": op.as_str(), "target": target}),
            DEFAULT_READ_TIMEOUT,
        )?;
        let nonce = challenge_nonce(&challenge, op, target)?;
        let key = master_key::read()?;
        let signature = presence_grant::sign(&key, op, target, &nonce);
        drop(key);
        Ok((nonce, signature))
    }
}

/// The nonce from a challenge — but only if the daemon echoed back the very
/// operation and target the person approved. A challenge for anything else is
/// refused rather than signed.
fn challenge_nonce(challenge: &Value, op: GrantOp, target: &str) -> Result<String, String> {
    let echoed_op = challenge.get("op").and_then(Value::as_str);
    let echoed_target = challenge.get("target").and_then(Value::as_str);
    if echoed_op != Some(op.as_str()) || echoed_target != Some(target) {
        return Err("the daemon issued a challenge for a different operation".to_owned());
    }
    challenge
        .get("nonce")
        .and_then(Value::as_str)
        .filter(|n| !n.is_empty())
        .map(str::to_owned)
        .ok_or_else(|| "the daemon's challenge carried no nonce".to_owned())
}

/// An approval id as one path segment. Ids are hex from the daemon; anything
/// that could step outside `/approvals/{id}` is refused rather than escaped.
pub fn path_segment(id: &str) -> Result<&str, String> {
    if !id.is_empty()
        && id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
    {
        Ok(id)
    } else {
        Err(format!("not an approval id: {id:?}"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_challenge_is_signed_only_for_the_operation_the_person_approved() {
        let good =
            json!({"nonce": "n1", "op": "reveal", "target": "gh/token", "expires_in_seconds": 120});
        assert_eq!(
            challenge_nonce(&good, GrantOp::Reveal, "gh/token").unwrap(),
            "n1"
        );
        assert!(challenge_nonce(&good, GrantOp::Reveal, "gh/other").is_err());
        assert!(challenge_nonce(&good, GrantOp::Approve, "gh/token").is_err());
        let no_nonce = json!({"op": "reveal", "target": "gh/token"});
        assert!(challenge_nonce(&no_nonce, GrantOp::Reveal, "gh/token").is_err());
    }

    #[test]
    fn an_approval_id_cannot_leave_its_path_segment() {
        assert_eq!(
            path_segment("0123456789abcdef").unwrap(),
            "0123456789abcdef"
        );
        for bad in ["", "../presence/reveal", "a/b", "a?b", "a b"] {
            assert!(path_segment(bad).is_err(), "{bad}");
        }
    }
}
