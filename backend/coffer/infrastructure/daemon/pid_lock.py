"""Daemon discovery file (~/.coffer/daemon.json) with restrictive permissions."""

from __future__ import annotations

import contextlib
import json
import os
import stat
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class DaemonInfo:
    version: int
    pid: int
    port: int
    token: str
    started_at: datetime
    binary_path: str


def write(path: Path, info: DaemonInfo) -> None:
    """Atomically write daemon.json with mode 0600. Caller owns directory creation policy.

    Uses O_CREAT|O_EXCL|0600 on the tmp file so it never exists with mode
    broader than 0600 (the previous write_text+chmod pair widened that
    window depending on the caller's umask — CODE-018).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {**asdict(info), "started_at": info.started_at.isoformat()}
    tmp = path.with_suffix(".json.tmp")
    # Clear stale tmp from a previous crashed run so O_EXCL succeeds.
    with contextlib.suppress(FileNotFoundError):
        tmp.unlink()
    fd = os.open(
        str(tmp),
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        stat.S_IRUSR | stat.S_IWUSR,
    )
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(payload, indent=2))
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
        raise
    os.replace(str(tmp), str(path))


def read(path: Path) -> DaemonInfo:
    raw = json.loads(path.read_text())
    return DaemonInfo(
        version=raw["version"],
        pid=raw["pid"],
        port=raw["port"],
        token=raw["token"],
        started_at=datetime.fromisoformat(raw["started_at"]),
        binary_path=raw["binary_path"],
    )
