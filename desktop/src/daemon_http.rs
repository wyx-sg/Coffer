//! JSON over loopback HTTP to the daemon, shared by the sync watcher, the
//! approval watcher and the secret commands.
//!
//! Raw HTTP/1.1 over `TcpStream`, for the reason `discovery.rs` gives: an
//! HTTP-client dependency is not worth requests that never leave 127.0.0.1.
//! Every request carries the daemon's token (required by every route but the
//! daemon's own status probe, and harmless there) and `Connection: close`, so
//! the whole response is whatever arrives before the daemon hangs up.
//!
//! Callers get the status AND the body, because the secret commands have to
//! show the person the daemon's own reason for a refusal — an expired nonce, a
//! ref that does not exist — rather than a bare "request failed".

use std::io::{Read, Write};
use std::net::{Ipv4Addr, SocketAddrV4, TcpStream};
use std::time::Duration;

/// How long a request may wait for its answer when the caller has no reason
/// to wait longer. A request that shows the person a native dialog (the
/// folder picker) passes its own, much longer, budget.
pub const DEFAULT_READ_TIMEOUT: Duration = Duration::from_secs(5);

/// One answered request.
#[derive(Debug, PartialEq, Eq)]
pub struct Response {
    pub status: u16,
    pub body: String,
}

/// `GET <path>`.
pub fn get(port: u16, token: &str, path: &str, read_timeout: Duration) -> Result<Response, String> {
    send(port, token, "GET", path, None, read_timeout)
}

/// `POST <path>` with a JSON body.
pub fn post_json(
    port: u16,
    token: &str,
    path: &str,
    body: &serde_json::Value,
    read_timeout: Duration,
) -> Result<Response, String> {
    send(
        port,
        token,
        "POST",
        path,
        Some(body.to_string()),
        read_timeout,
    )
}

/// `PUT <path>` with a JSON body.
pub fn put_json(
    port: u16,
    token: &str,
    path: &str,
    body: &serde_json::Value,
    read_timeout: Duration,
) -> Result<Response, String> {
    send(
        port,
        token,
        "PUT",
        path,
        Some(body.to_string()),
        read_timeout,
    )
}

fn send(
    port: u16,
    token: &str,
    method: &str,
    path: &str,
    body: Option<String>,
    read_timeout: Duration,
) -> Result<Response, String> {
    let addr = SocketAddrV4::new(Ipv4Addr::LOCALHOST, port);
    let mut stream = TcpStream::connect_timeout(&addr.into(), Duration::from_millis(500))
        .map_err(|e| format!("cannot reach Coffer's daemon: {e}"))?;
    stream
        .set_write_timeout(Some(Duration::from_secs(2)))
        .and_then(|_| stream.set_read_timeout(Some(read_timeout)))
        .map_err(|e| format!("daemon socket: {e}"))?;
    stream
        .write_all(request_text(port, token, method, path, body.as_deref()).as_bytes())
        .map_err(|e| format!("daemon write: {e}"))?;
    let mut raw = Vec::new();
    stream
        .read_to_end(&mut raw)
        .map_err(|e| format!("daemon read: {e}"))?;
    parse_response(&String::from_utf8_lossy(&raw))
        .ok_or_else(|| "the daemon's answer was not a readable HTTP response".to_owned())
}

/// The request's bytes. Pure, so the header set is asserted rather than
/// assumed: `Content-Length` counts bytes, not characters.
fn request_text(port: u16, token: &str, method: &str, path: &str, body: Option<&str>) -> String {
    let mut req = format!(
        "{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n\
         X-Coffer-Token: {token}\r\nAccept: application/json\r\nConnection: close\r\n"
    );
    match body {
        Some(body) => {
            req.push_str("Content-Type: application/json\r\n");
            req.push_str(&format!("Content-Length: {}\r\n\r\n", body.len()));
            req.push_str(body);
        }
        None => req.push_str("\r\n"),
    }
    req
}

/// Split a raw response into its status and (de-chunked) body.
pub fn parse_response(response: &str) -> Option<Response> {
    let (head, body) = response.split_once("\r\n\r\n")?;
    let mut lines = head.lines();
    let status_line = lines.next()?;
    if !status_line.starts_with("HTTP/1.") {
        return None;
    }
    let status = status_line.split_whitespace().nth(1)?.parse::<u16>().ok()?;
    let chunked = lines.any(|line| {
        let line = line.to_ascii_lowercase();
        line.starts_with("transfer-encoding:") && line.contains("chunked")
    });
    let body = if chunked {
        dechunk(body)?
    } else {
        body.to_owned()
    };
    Some(Response { status, body })
}

/// The body of a `200` response, or `None` for anything else — a `401` from a
/// rotated token and a `404` from an older daemon both mean "no answer", never
/// "the vault is fine" or "nothing is pending". The watchers want exactly this.
pub fn ok_body(response: Response) -> Option<String> {
    (response.status == 200).then_some(response.body)
}

/// `GET <path>` for a watcher: the body of a `200`, or `None` for anything
/// that is not an answer — unreachable, refused, unreadable.
pub fn fetch_ok(port: u16, token: &str, path: &str) -> Option<String> {
    get(port, token, path, DEFAULT_READ_TIMEOUT)
        .ok()
        .and_then(ok_body)
}

/// A 2xx body parsed as JSON, or the daemon's own `error.message` for anything
/// else — that message is what the page shows the person.
pub fn json_or_error(response: Response) -> Result<serde_json::Value, String> {
    let parsed: Option<serde_json::Value> = serde_json::from_str(&response.body).ok();
    if (200..300).contains(&response.status) {
        return parsed.ok_or_else(|| "the daemon's answer was not JSON".to_owned());
    }
    let message = parsed
        .as_ref()
        .and_then(|v| v.pointer("/error/message"))
        .and_then(|m| m.as_str())
        .map(str::to_owned);
    Err(message.unwrap_or_else(|| format!("the daemon refused (HTTP {})", response.status)))
}

/// Reassemble a `Transfer-Encoding: chunked` body. The daemon sends a
/// `Content-Length` today; this is here so a server change that switches to
/// chunking degrades to a parse failure rather than to a feature that silently
/// stopped reporting anything.
fn dechunk(body: &str) -> Option<String> {
    let mut out = String::new();
    let mut rest = body;
    loop {
        let (size_line, tail) = rest.split_once("\r\n")?;
        let size = usize::from_str_radix(size_line.split(';').next()?.trim(), 16).ok()?;
        if size == 0 {
            return Some(out);
        }
        // `get` rather than an index: a chunk boundary that falls inside a
        // multi-byte character would panic on a slice.
        out.push_str(tail.get(..size)?);
        rest = tail.get(size + 2..)?;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn http_json_body(raw: &str) -> Option<String> {
        parse_response(raw).and_then(ok_body)
    }

    #[test]
    fn http_json_body_reads_a_content_length_response() {
        let raw = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\
                   Content-Length: 21\r\n\r\n{\"configured\": false}";
        assert_eq!(
            http_json_body(raw).as_deref(),
            Some("{\"configured\": false}")
        );
    }

    #[test]
    fn http_json_body_rejects_a_non_200() {
        // A rotated token gives 401, an older daemon 404. Neither is news
        // about the vault, and treating either as one would clear a real mark.
        for head in ["HTTP/1.1 401 Unauthorized", "HTTP/1.1 404 Not Found"] {
            let raw = format!("{head}\r\nContent-Length: 2\r\n\r\n{{}}");
            assert_eq!(http_json_body(&raw), None);
        }
    }

    #[test]
    fn http_json_body_rejects_a_response_with_no_header_terminator() {
        assert_eq!(http_json_body("HTTP/1.1 200 OK\r\n"), None);
        assert_eq!(http_json_body(""), None);
    }

    #[test]
    fn http_json_body_reassembles_a_chunked_response() {
        let raw = "HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n\
                   c\r\n{\"configured\r\n9\r\n\": false}\r\n0\r\n\r\n";
        assert_eq!(
            http_json_body(raw).as_deref(),
            Some("{\"configured\": false}")
        );
    }

    #[test]
    fn dechunk_gives_up_on_a_truncated_body_instead_of_panicking() {
        // Length says 20 bytes, four arrive.
        assert_eq!(dechunk("14\r\nshor"), None);
        assert_eq!(dechunk("not-hex\r\n"), None);
        // A chunk boundary inside a multi-byte character.
        assert_eq!(dechunk("1\r\né\r\n0\r\n\r\n"), None);
    }

    #[test]
    fn parse_response_keeps_the_status_of_a_refusal() {
        let raw = "HTTP/1.1 409 Conflict\r\nContent-Length: 2\r\n\r\n{}";
        assert_eq!(
            parse_response(raw),
            Some(Response {
                status: 409,
                body: "{}".into()
            })
        );
        assert_eq!(parse_response("SSH-2.0-OpenSSH\r\n\r\n"), None);
    }

    #[test]
    fn a_refusal_surfaces_the_daemons_own_message() {
        let body = r#"{"error":{"code":"presence_nonce_expired","message":"The approval expired.","details":{}}}"#;
        let err = json_or_error(Response {
            status: 403,
            body: body.into(),
        })
        .unwrap_err();
        assert_eq!(err, "The approval expired.");
        // No envelope: still an error, never a success.
        let err = json_or_error(Response {
            status: 500,
            body: "oops".into(),
        })
        .unwrap_err();
        assert!(err.contains("500"), "{err}");
        let ok = json_or_error(Response {
            status: 200,
            body: r#"{"value":"x"}"#.into(),
        })
        .unwrap();
        assert_eq!(ok["value"], "x");
    }

    #[test]
    fn a_post_counts_its_body_in_bytes() {
        let req = request_text(8000, "tok", "POST", "/p", Some(r#"{"a":"é"}"#));
        assert!(
            req.starts_with("POST /p HTTP/1.1\r\nHost: 127.0.0.1:8000\r\n"),
            "{req}"
        );
        assert!(req.contains("X-Coffer-Token: tok\r\n"), "{req}");
        assert!(req.contains("Content-Type: application/json\r\n"), "{req}");
        assert!(req.contains("Content-Length: 10\r\n\r\n"), "{req}");
        assert!(req.ends_with(r#"{"a":"é"}"#));
        let get = request_text(8000, "tok", "GET", "/g", None);
        assert!(get.ends_with("Connection: close\r\n\r\n"), "{get}");
        assert!(!get.contains("Content-Length"), "{get}");
    }
}
