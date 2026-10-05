"""Proof that a model proxy is the one Coffer started.

``proxy.json`` and the loopback port are both writable by any process of the
same OS user, and the health check only compares a version string — so an agent
could kill the real proxy, bind the port itself, write its own ``proxy.json``
and be pushed every upstream provider key. The daemon therefore hands the proxy
a key derived from the master key (through the child's stdin, never argv or the
environment) and, before any push, challenges it: the signature covers the
daemon's fresh nonce and the proxy's own listening port, so neither a replay nor
a relay on another port passes. Only HMAC lives here; the key derivation is the
composition root's (``application.secret.presence.derive_purpose_key``).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sys

import httpx

from coffer.domain.model_proxy.state import CONTROL_TOKEN_HEADER

ATTEST_PATH = "/_coffer/attest"


def new_nonce() -> str:
    return secrets.token_hex(16)


def sign(key: bytes, nonce: str, port: int) -> str:
    """``hex(HMAC-SHA256(key, "coffer-attest/v1\\n" + nonce + "\\n" + port))`` —
    the same shape as ``application.secret.presence.attest``."""
    return hmac.new(key, f"coffer-attest/v1\n{nonce}\n{port}".encode(), hashlib.sha256).hexdigest()


def matches(key: bytes, nonce: str, port: int, signature: object) -> bool:
    return isinstance(signature, str) and hmac.compare_digest(
        signature.encode(), sign(key, nonce, port).encode()
    )


async def challenge(client: httpx.AsyncClient, key: bytes, port: int, token: str) -> bool:
    """Ask the process on ``port`` to attest; ``True`` only for a valid answer."""
    nonce = new_nonce()
    try:
        r = await client.post(
            f"http://127.0.0.1:{port}{ATTEST_PATH}",
            headers={CONTROL_TOKEN_HEADER: token},
            json={"nonce": nonce},
        )
        if r.status_code != 200:
            return False
        payload = r.json()
    except (httpx.HTTPError, ValueError):
        return False
    return isinstance(payload, dict) and matches(key, nonce, port, payload.get("signature"))


def key_to_line(key: bytes) -> bytes:
    return key.hex().encode() + b"\n"


def read_key_from_stdin() -> bytes | None:
    """The attest key the daemon wrote to this process's stdin, if any."""
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return None
        line = sys.stdin.readline().strip()
        return bytes.fromhex(line) if line else None
    except (OSError, ValueError):
        return None
