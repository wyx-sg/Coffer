//! Reading `~/.coffer/daemon.json` and probing whatever it names.
//!
//! This is step 1 of the daemon-resolution chain (`resolve.rs`) and the
//! liveness/shutdown plumbing `daemon.rs` restarts with. Raw HTTP/1.1 over
//! `TcpStream` throughout — not worth an HTTP-client dependency for two
//! loopback requests.
//!
//! Split out of `daemon.rs` to keep every file under the project's 400-line
//! cap (see `.agents/stack.md`).

use std::env;
use std::fs;
use std::path::PathBuf;

/// Extract the `"port"` value from the daemon discovery JSON. Returns `None`
/// for malformed JSON, a missing key, a non-numeric value, or a port outside
/// the u16 range. (serde_json is already in the Tauri dependency graph; a
/// hand-rolled string scan would silently couple to the daemon's serializer.)
fn parse_daemon_port(raw: &str) -> Option<u16> {
    let v: serde_json::Value = serde_json::from_str(raw).ok()?;
    u16::try_from(v.get("port")?.as_u64()?).ok()
}

/// Extract the `"token"` string value from the daemon discovery JSON.
fn parse_daemon_token(raw: &str) -> Option<String> {
    let v: serde_json::Value = serde_json::from_str(raw).ok()?;
    Some(v.get("token")?.as_str()?.to_string())
}

/// `~/.coffer/daemon.json` — the file every Coffer client reads.
fn discovery_file() -> Option<PathBuf> {
    let home = env::var("HOME")
        .ok()
        .or_else(|| env::var("USERPROFILE").ok())?;
    Some(PathBuf::from(home).join(".coffer").join("daemon.json"))
}

/// Read both the port and token from `~/.coffer/daemon.json`. Returns `None`
/// if the file is absent/unreadable or either field is missing — callers
/// treat that as "no daemon running".
pub fn read_daemon_info() -> Option<(u16, String)> {
    let raw = fs::read_to_string(discovery_file()?).ok()?;
    Some((parse_daemon_port(&raw)?, parse_daemon_token(&raw)?))
}

/// Best-effort check: is *anything* listening on `127.0.0.1:<port>`?
///
/// This is a bare TCP connect, so it cannot tell a Coffer daemon apart from a
/// port-squatter. Use it ONLY where "the socket is gone" is the question —
/// e.g. [`wait_for_port_free`] after a shutdown. For "is a live Coffer daemon
/// here?" use [`daemon_responds_ok`], which does an HTTP status probe.
fn daemon_is_listening(port: u16) -> bool {
    use std::net::{Ipv4Addr, SocketAddrV4, TcpStream};
    use std::time::Duration;
    let addr = SocketAddrV4::new(Ipv4Addr::LOCALHOST, port);
    TcpStream::connect_timeout(&addr.into(), Duration::from_millis(250)).is_ok()
}

/// Pure check: does an HTTP response head start with a `200` status line?
/// Split out so the liveness probe's accept/reject decision is unit-testable
/// without a socket. Accepts HTTP/1.0 and HTTP/1.1.
fn http_status_is_ok(response_head: &str) -> bool {
    let first = response_head.lines().next().unwrap_or("");
    first.starts_with("HTTP/1.1 200") || first.starts_with("HTTP/1.0 200")
}

/// Liveness probe: does a *Coffer daemon* answer `GET /api/v1/daemon/status`
/// with a 200 on `127.0.0.1:<port>`?
///
/// A bare TCP connect false-positives on any process squatting the recorded
/// port (after a daemon crash, an unrelated listener can land there), which
/// would wrongly report "daemon already running" and skip the respawn. The
/// status endpoint is auth-exempt, so no token is needed.
pub fn daemon_responds_ok(port: u16) -> bool {
    use std::io::{Read, Write};
    use std::net::{Ipv4Addr, SocketAddrV4, TcpStream};
    use std::time::Duration;

    let addr = SocketAddrV4::new(Ipv4Addr::LOCALHOST, port);
    let Ok(mut stream) = TcpStream::connect_timeout(&addr.into(), Duration::from_millis(250))
    else {
        return false;
    };
    if stream
        .set_write_timeout(Some(Duration::from_millis(500)))
        .and_then(|_| stream.set_read_timeout(Some(Duration::from_millis(500))))
        .is_err()
    {
        return false;
    }
    let req = format!(
        "GET /api/v1/daemon/status HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n\
         Connection: close\r\n\r\n"
    );
    if stream.write_all(req.as_bytes()).is_err() {
        return false;
    }
    let mut buf = [0u8; 64];
    let Ok(n) = stream.read(&mut buf) else {
        return false;
    };
    http_status_is_ok(&String::from_utf8_lossy(&buf[..n]))
}

/// Ask the running daemon to shut itself down via its token-gated
/// `POST /api/v1/daemon/shutdown` route. The daemon replies 204 and SIGTERMs
/// itself.
pub fn request_daemon_shutdown(port: u16, token: &str) -> Result<(), String> {
    use std::io::{Read, Write};
    use std::net::{Ipv4Addr, SocketAddrV4, TcpStream};
    use std::time::Duration;

    let addr = SocketAddrV4::new(Ipv4Addr::LOCALHOST, port);
    let mut stream = TcpStream::connect_timeout(&addr.into(), Duration::from_millis(500))
        .map_err(|e| format!("shutdown connect: {e}"))?;
    stream
        .set_write_timeout(Some(Duration::from_secs(2)))
        .and_then(|_| stream.set_read_timeout(Some(Duration::from_secs(2))))
        .map_err(|e| format!("shutdown socket timeout: {e}"))?;
    let req = format!(
        "POST /api/v1/daemon/shutdown HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n\
         X-Coffer-Token: {token}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
    );
    stream
        .write_all(req.as_bytes())
        .map_err(|e| format!("shutdown write: {e}"))?;
    let mut buf = [0u8; 32];
    let n = stream
        .read(&mut buf)
        .map_err(|e| format!("shutdown read: {e}"))?;
    let head = String::from_utf8_lossy(&buf[..n]);
    if head.starts_with("HTTP/1.1 204") || head.starts_with("HTTP/1.0 204") {
        Ok(())
    } else {
        Err(format!(
            "shutdown rejected: {}",
            head.lines().next().unwrap_or("")
        ))
    }
}

/// Poll until nothing is listening on `port` (the old daemon has exited),
/// up to `timeout`. Returns `true` when the port is free.
pub fn wait_for_port_free(port: u16, timeout: std::time::Duration) -> bool {
    use std::time::Instant;
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if !daemon_is_listening(port) {
            return true;
        }
        std::thread::sleep(std::time::Duration::from_millis(200));
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;

    #[test]
    fn parse_daemon_port_reads_well_formed_value() {
        assert_eq!(parse_daemon_port(r#"{"port": 8000, "pid": 1}"#), Some(8000));
    }

    #[test]
    fn parse_daemon_port_tolerates_spacing() {
        assert_eq!(parse_daemon_port(r#"{"port":8042}"#), Some(8042));
        assert_eq!(parse_daemon_port("{ \"port\" :   65535 }"), Some(65535));
    }

    #[test]
    fn parse_daemon_port_missing_key_is_none() {
        assert_eq!(parse_daemon_port(r#"{"pid": 1}"#), None);
    }

    #[test]
    fn parse_daemon_port_out_of_range_is_none() {
        // 70000 > u16::MAX — the conversion fails, so we report "no port".
        assert_eq!(parse_daemon_port(r#"{"port": 70000}"#), None);
    }

    #[test]
    fn parse_daemon_port_non_numeric_value_is_none() {
        assert_eq!(parse_daemon_port(r#"{"port": "abc"}"#), None);
    }

    #[test]
    fn parse_daemon_token_reads_urlsafe_value() {
        // Obviously-fake fixture (URL-safe `-`/`_` chars, low entropy) so the
        // secrets scanner doesn't flag it as a real token.
        let raw = r#"{"port": 8000, "token": "EXAMPLE-url_safe-token_value", "pid": 1}"#;
        assert_eq!(
            parse_daemon_token(raw).as_deref(),
            Some("EXAMPLE-url_safe-token_value")
        );
    }

    #[test]
    fn parse_daemon_token_missing_key_is_none() {
        assert_eq!(parse_daemon_token(r#"{"port": 8000}"#), None);
    }

    #[test]
    fn parse_daemon_token_tolerates_spacing() {
        assert_eq!(
            parse_daemon_token(r#"{ "token" :   "abc123" }"#).as_deref(),
            Some("abc123")
        );
    }

    #[test]
    fn http_status_is_ok_accepts_200_lines() {
        assert!(http_status_is_ok("HTTP/1.1 200 OK\r\n\r\n"));
        assert!(http_status_is_ok("HTTP/1.0 200 OK\r\n"));
    }

    #[test]
    fn http_status_is_ok_rejects_non_200_and_garbage() {
        assert!(!http_status_is_ok("HTTP/1.1 404 Not Found\r\n\r\n"));
        assert!(!http_status_is_ok("HTTP/1.1 503 Service Unavailable\r\n"));
        // A port-squatter that isn't speaking HTTP at all.
        assert!(!http_status_is_ok("garbage bytes from a non-http listener"));
        assert!(!http_status_is_ok(""));
    }

    /// daemon_responds_ok issues GET /api/v1/daemon/status and treats a 200 as
    /// "a live Coffer daemon is here". Driven against an in-test TCP listener.
    #[test]
    fn daemon_responds_ok_true_on_200_status() {
        use std::io::{Read, Write};
        use std::net::TcpListener;

        let listener = TcpListener::bind("127.0.0.1:0").expect("bind");
        let port = listener.local_addr().unwrap().port();
        let handle = std::thread::spawn(move || {
            let (mut sock, _) = listener.accept().expect("accept");
            let mut buf = [0u8; 1024];
            let n = sock.read(&mut buf).expect("read");
            let req = String::from_utf8_lossy(&buf[..n]).into_owned();
            sock.write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                .expect("write");
            req
        });

        assert!(daemon_responds_ok(port));
        let req = handle.join().expect("server thread");
        assert!(
            req.starts_with("GET /api/v1/daemon/status HTTP/1.1\r\n"),
            "{req}"
        );
    }

    /// A port-squatter that answers non-200 (or non-HTTP) is NOT a live daemon
    /// — the bare-TCP probe would false-positive here, the HTTP probe rejects.
    #[test]
    fn daemon_responds_ok_false_on_non_200_squatter() {
        use std::io::{Read, Write};
        use std::net::TcpListener;

        let listener = TcpListener::bind("127.0.0.1:0").expect("bind");
        let port = listener.local_addr().unwrap().port();
        std::thread::spawn(move || {
            let (mut sock, _) = listener.accept().expect("accept");
            let mut buf = [0u8; 1024];
            let _ = sock.read(&mut buf);
            let _ = sock.write_all(b"HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n");
        });

        assert!(!daemon_responds_ok(port));
    }

    #[test]
    fn daemon_responds_ok_false_when_nothing_listens() {
        use std::net::TcpListener;
        // Grab then release a port so nothing is listening on it.
        let port = {
            let l = TcpListener::bind("127.0.0.1:0").unwrap();
            l.local_addr().unwrap().port()
        };
        assert!(!daemon_responds_ok(port));
    }

    /// request_daemon_shutdown sends a token-carrying POST to the shutdown
    /// route and treats a 204 as success.
    #[test]
    fn request_daemon_shutdown_posts_token_and_accepts_204() {
        use std::io::{Read, Write};
        use std::net::TcpListener;

        let listener = TcpListener::bind("127.0.0.1:0").expect("bind");
        let port = listener.local_addr().unwrap().port();
        let handle = std::thread::spawn(move || {
            let (mut sock, _) = listener.accept().expect("accept");
            let mut buf = [0u8; 1024];
            let n = sock.read(&mut buf).expect("read");
            let req = String::from_utf8_lossy(&buf[..n]).into_owned();
            sock.write_all(b"HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n")
                .expect("write");
            req
        });

        request_daemon_shutdown(port, "tok-123").expect("shutdown ok");
        let req = handle.join().expect("server thread");
        assert!(
            req.starts_with("POST /api/v1/daemon/shutdown HTTP/1.1\r\n"),
            "{req}"
        );
        assert!(req.contains("X-Coffer-Token: tok-123\r\n"), "{req}");
    }

    #[test]
    fn request_daemon_shutdown_rejects_non_204() {
        use std::io::{Read, Write};
        use std::net::TcpListener;

        let listener = TcpListener::bind("127.0.0.1:0").expect("bind");
        let port = listener.local_addr().unwrap().port();
        std::thread::spawn(move || {
            let (mut sock, _) = listener.accept().expect("accept");
            let mut buf = [0u8; 1024];
            let _ = sock.read(&mut buf);
            let _ = sock.write_all(b"HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n\r\n");
        });

        let err = request_daemon_shutdown(port, "bad-token").unwrap_err();
        assert!(err.contains("401"), "{err}");
    }

    #[test]
    fn wait_for_port_free_returns_true_when_nothing_listens() {
        use std::net::TcpListener;
        // Grab a free port, then release it so nothing is listening.
        let port = {
            let l = TcpListener::bind("127.0.0.1:0").unwrap();
            l.local_addr().unwrap().port()
        };
        assert!(wait_for_port_free(port, Duration::from_millis(300)));
    }
}
