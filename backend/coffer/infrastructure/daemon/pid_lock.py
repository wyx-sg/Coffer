"""Daemon discovery file (~/.coffer/daemon.json) with restrictive permissions."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
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

    Uses ``tempfile.mkstemp`` (O_CREAT|O_EXCL, mode 0600) for the staging
    file so it never exists with mode broader than 0600 (the previous
    write_text+chmod pair widened that window depending on the caller's umask
    — CODE-018).

    The staging file gets a UNIQUE per-call name in the target directory.
    Two daemons racing to publish daemon.json (the ADR-006 detect-or-spawn
    window) therefore never collide on a shared ``daemon.json.tmp`` — the old
    fixed-name + O_EXCL form crashed the loser with FileExistsError, or let
    one unlink the other's tmp. The final ``os.replace`` is atomic, so the
    last writer wins cleanly with no partial file ever visible at ``path``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {**asdict(info), "started_at": info.started_at.isoformat()}
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f"{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
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
