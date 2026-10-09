"""Command-line arguments and the installed Coffer a run targets.

The target is whatever daemon a ``daemon.json`` names — by default the
installed app's ``~/.coffer/daemon.json``. Its token is read to talk to it and
never written anywhere: :meth:`Target.describe` is what a run records.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DAEMON_JSON = Path.home() / ".coffer" / "daemon.json"
APP_MACOS = Path("/Applications/Coffer.app/Contents/MacOS")
SHIM_NAME = "coffer-mcp-shim"


class RefusedError(Exception):
    """A safety guard refused the run before (or instead of) writing anything."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        #: What the guard read, written to the run's directory beside the refusal.
        self.details = details or {}


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--daemon-json",
        type=Path,
        default=DEFAULT_DAEMON_JSON,
        help="the target daemon's rendezvous file (default: ~/.coffer/daemon.json)",
    )
    parser.add_argument(
        "--shim",
        type=Path,
        default=None,
        help=f"the installed {SHIM_NAME} (default: next to the daemon binary, then {APP_MACOS})",
    )
    parser.add_argument(
        "--coffer",
        type=Path,
        default=Path("~/.coffer/bin/coffer"),
        help="the installed coffer CLI (used by the cli suite; never guessed from PATH)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="an empty or new directory outside the repository for the results",
    )
    parser.add_argument(
        "--allow-sync-remote",
        action="store_true",
        help="write even though the target syncs its vault to a remote",
    )


def checked_out_dir(path: Path) -> Path:
    """``path`` resolved and created, or :class:`RefusedError`.

    Results never land in the repository (they would be committed by accident)
    and never overwrite an earlier run's evidence.
    """
    out = path.expanduser().resolve()
    if out == REPO_ROOT or REPO_ROOT in out.parents:
        raise RefusedError(
            f"--out {out} is inside the repository {REPO_ROOT}; choose a path outside it"
        )
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise RefusedError(f"--out {out} exists and is not an empty directory")
    out.mkdir(parents=True, exist_ok=True)
    return out


def fingerprint(path: Path | None) -> dict[str, Any] | None:
    """Path, sha256, size and mtime of a binary, so a run names the exact build."""
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    stat = path.stat()
    return {
        "path": str(path),
        "sha256": digest.hexdigest(),
        "size": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
    }


@dataclass(frozen=True)
class Target:
    daemon_json: Path
    port: int
    pid: int
    binary_path: Path
    started_at: str
    token: str = field(repr=False)
    shim: Path | None = None
    coffer: Path | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def home(self) -> Path | None:
        """The HOME whose ``.coffer/daemon.json`` this is — what the shim reads."""
        parent = self.daemon_json.parent
        return parent.parent if parent.name == ".coffer" else None

    def describe(self, status: dict[str, Any] | None = None) -> dict[str, Any]:
        """Everything a run records about the target — never the token."""
        status = status or {}
        return {
            "daemon_json": str(self.daemon_json),
            "port": self.port,
            "pid": self.pid,
            "started_at": self.started_at,
            "version": status.get("version"),
            "commit": status.get("commit"),
            "executable": status.get("executable"),
            "features": status.get("features"),
            "daemon_binary": fingerprint(self.binary_path),
            "shim": fingerprint(self.shim) if self.shim else None,
            "coffer": str(self.coffer) if self.coffer else None,
        }


def resolve_shim(explicit: Path | None, binary_path: Path) -> Path | None:
    if explicit is not None:
        return explicit.expanduser().resolve()
    for candidate in (binary_path.parent / SHIM_NAME, APP_MACOS / SHIM_NAME):
        if candidate.is_file():
            return candidate
    return None


def read_target(args: argparse.Namespace) -> Target:
    path = Path(args.daemon_json).expanduser().resolve()
    if not path.is_file():
        raise RefusedError(f"no daemon rendezvous at {path}: is the target Coffer running?")
    raw = json.loads(path.read_text())
    binary = Path(raw["binary_path"])
    return Target(
        daemon_json=path,
        port=int(raw["port"]),
        pid=int(raw["pid"]),
        binary_path=binary,
        started_at=str(raw.get("started_at")),
        token=str(raw["token"]),
        shim=resolve_shim(args.shim, binary),
        coffer=Path(args.coffer).expanduser() if args.coffer else None,
    )
