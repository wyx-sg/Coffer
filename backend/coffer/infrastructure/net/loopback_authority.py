"""Whether a request's ``Host`` names this machine's loopback address and port.

Two listeners refuse a request addressed to anything else — the daemon
(:mod:`coffer.surfaces.http.host_guard`) and the local model proxy
(:mod:`coffer.infrastructure.model_proxy.app`) — for the same reason: both bind
``127.0.0.1`` only, which keeps remote hosts out but not a browser page whose
hostname an attacker re-resolves to ``127.0.0.1`` (DNS rebinding). Rebinding
does not change the ``Host`` header, so checking it closes that door.

The predicates live here, in kind-agnostic infrastructure, because the proxy is
infrastructure and must not import a surface; the daemon's guard imports them
back. They are pure string and IP-literal checks — no DNS, no I/O — so a
hostname that *resolves* to loopback but is not ``localhost`` or a loopback
literal is refused, which is the point.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable

#: Hostnames that are loopback but are not IP literals.
LOOPBACK_NAMES: frozenset[str] = frozenset({"localhost"})


def split_authority(authority: str) -> tuple[str, int | None] | None:
    """``(hostname, port)`` of a ``Host`` header; port None when absent.

    None when the value is not a well-formed authority. Handles
    ``127.0.0.1:8000``, ``[::1]:8000``, ``[::1]`` and ``localhost``.
    """
    value = authority.strip()
    if not value:
        return None
    if value.startswith("["):
        close = value.find("]")
        if close < 0:
            return None
        host, rest = value[1:close], value[close + 1 :]
        if not rest:
            return host, None
        if not rest.startswith(":") or not rest[1:].isdigit():
            return None
        return host, int(rest[1:])
    if value.count(":") > 1:
        # A bare IPv6 literal is not a valid Host header (RFC 3986 brackets it).
        return None
    head, sep, tail = value.rpartition(":")
    if not sep:
        return value, None
    if not head or not tail.isdigit():
        return None
    return head, int(tail)


def is_loopback_hostname(hostname: str) -> bool:
    """``localhost`` or a loopback IP literal (``127.0.0.0/8``, ``::1``)."""
    lowered = hostname.lower()
    if lowered in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(lowered).is_loopback
    except ValueError:
        return False


def is_allowed_host(authority: str | None, port: int, extra_hosts: Iterable[str] = ()) -> bool:
    """Whether ``authority`` names this machine's loopback address on ``port``.

    A ``Host`` without a port means the scheme's default (80), so it matches
    only a listener there. ``extra_hosts`` (lower-case) adds hostnames the
    caller accepts as well; ``*`` among them accepts anything. The caller
    decides where extras come from — the daemon reads ``COFFER_ALLOWED_HOSTS``
    for its in-process test transports; the proxy passes none.
    """
    extra = {h.lower() for h in extra_hosts}
    if "*" in extra:
        return True
    if authority is None:
        return False
    parts = split_authority(authority)
    if parts is None:
        return False
    hostname, given_port = parts
    if (given_port if given_port is not None else 80) != port:
        return False
    return is_loopback_hostname(hostname) or hostname.lower() in extra


__all__ = ["LOOPBACK_NAMES", "is_allowed_host", "is_loopback_hostname", "split_authority"]
