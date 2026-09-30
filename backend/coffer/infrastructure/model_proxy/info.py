"""``~/.coffer/proxy.json`` — how a daemon finds the proxy that is already running.

The proxy outlives daemon restarts (ADR api-key-providers-are-reached-through-
a-separate-local-model-proxy, Option C), so a freshly started daemon needs to
learn where the running one is and how to talk to it. The proxy publishes
``{port, pid, started_at, version, control_token}`` here once it has bound its
socket, mode ``0600`` because the control token is what lets a caller push
provider keys into it and tell it to drain.

It is runtime state in the same sense as ``daemon.json``: written by the
process it describes, and removed on exit only by that same process — a proxy
never deletes a file that already names its successor.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from coffer.infrastructure.daemon.atomic_write import write_json_0600
from coffer.infrastructure.vault.home import PROXY_INFO_FILENAME, proxy_info_path


def info_path(coffer_dir: Path | None = None) -> Path:
    """``proxy.json`` under ``coffer_dir`` (default: ``HOME``'s, read at call time)."""
    return coffer_dir / PROXY_INFO_FILENAME if coffer_dir else proxy_info_path()


@dataclass(frozen=True)
class ProxyInfo:
    """What a running proxy says about itself."""

    port: int
    pid: int
    started_at: str
    version: str
    control_token: str = field(repr=False)


def write_info(info: ProxyInfo, coffer_dir: Path | None = None) -> None:
    write_json_0600(info_path(coffer_dir), asdict(info))


def read_info(coffer_dir: Path | None = None) -> ProxyInfo | None:
    """The published info, or ``None`` when absent or not a well-formed record."""
    try:
        payload = json.loads(info_path(coffer_dir).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        port, pid = payload["port"], payload["pid"]
        started_at, version = payload["started_at"], payload["version"]
        token = payload["control_token"]
    except KeyError:
        return None
    if not (isinstance(port, int) and isinstance(pid, int)):
        return None
    if not all(isinstance(v, str) for v in (started_at, version, token)):
        return None
    return ProxyInfo(
        port=port, pid=pid, started_at=started_at, version=version, control_token=token
    )


def remove_info_if_owned(pid: int, coffer_dir: Path | None = None) -> bool:
    """Unlink ``proxy.json`` only if it still names ``pid``; True when removed."""
    current = read_info(coffer_dir)
    if current is None or current.pid != pid:
        return False
    with contextlib.suppress(FileNotFoundError):
        info_path(coffer_dir).unlink()
    return True


__all__ = [
    "ProxyInfo",
    "info_path",
    "read_info",
    "remove_info_if_owned",
    "write_info",
]
