"""SSRF guard: refuse outbound requests to loopback, private, or link-local hosts.

Used by `source_fetcher` to validate user-supplied Git URLs before any
network round-trip. Resolves the host to one or more IPs; if any of them
fall into the blocked ranges, the URL is rejected.

This is intentionally strict: we accept only public IPv4/IPv6 destinations.

Residual gap (accepted): the guard resolves DNS at validation time, but
`git` resolves the host again independently when it connects, so a
DNS-rebinding host could still pass the check and then be re-pointed at an
internal address. Pinning the resolved IP through to `git` is not feasible
without breaking TLS SNI/cert verification. As defence-in-depth the Git
fetch sets `http.followRedirects=false` (so a validated URL cannot be
redirected to an internal host) and refuses interactive auth. For Coffer's
threat model — a localhost-only, single-user desktop daemon where the URL
is supplied by the user themselves — this residual rebinding risk is
accepted rather than mitigated.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


def is_blocked_host(host: str) -> bool:
    """True if the host (literal IP or DNS name) resolves to a blocked address.

    Blocked: loopback (127/8, ::1), link-local (169.254/16, fe80::/10),
    private (RFC1918: 10/8, 172.16/12, 192.168/16, fc00::/7), and reserved
    (multicast, unspecified). DNS resolution failures count as blocked,
    because we don't know what they map to.

    Pure host string in — does not parse URLs.
    """
    host = host.strip()
    if not host:
        return True

    # Strip brackets around IPv6 literals
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]

    try:
        ip = ipaddress.ip_address(host)
        return _ip_is_blocked(ip)
    except ValueError:
        # Host is a DNS name; resolve and check every result.
        try:
            results = socket.getaddrinfo(host, None)
        except OSError:
            return True
        ips: set[str] = set()
        for res in results:
            raw = res[4][0]
            if isinstance(raw, str):
                ips.add(raw)
        if not ips:
            return True
        for raw_ip in ips:
            # IPv6 addresses from getaddrinfo can include scope suffixes.
            ip_str = raw_ip.split("%", 1)[0]
            try:
                if _ip_is_blocked(ipaddress.ip_address(ip_str)):
                    return True
            except ValueError:
                return True
    return False


def _ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_private
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
    )


def check_url(url: str) -> str:
    """Parse and validate a public URL; return the netloc host.

    Raises ValueError if the scheme is not http(s) or the host is blocked.
    """
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"unsupported scheme: {parsed.scheme!r}")
    if not parsed.hostname:
        raise ValueError("URL has no host")
    if is_blocked_host(parsed.hostname):
        raise ValueError(f"SSRF: refusing host {parsed.hostname}")
    return parsed.hostname
