#!/usr/bin/env python3
"""Freshness stamp for the verify-before-commit guard (ADR-017 control layer).

``make verify`` records a content fingerprint of the repo's source files here;
the ``verify_before_commit`` hook recomputes it at commit time and asks for
confirmation when they differ — i.e. when source changed since the last passing
``make verify``.

The fingerprint hashes file *content* (via ``git hash-object``), not the index,
so it is stable across ``git add`` (staging is not a content change) and only
moves when a tracked-or-untracked source file actually changes. Non-source files
(docs, data) are excluded so doc-only commits do not trip the guard.

    python scripts/verify_stamp.py write   # record the current fingerprint
    python scripts/verify_stamp.py check   # exit 0 if fresh, 1 if stale
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

STAMP_NAME = ".coffer-verify.stamp"

# Extensions whose change means "re-run make verify". Build/config that the
# verify pipeline gates are included; docs/data are deliberately excluded.
_SOURCE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".toml", ".cfg", ".ini")
_SOURCE_NAMES = {"Makefile"}


def _is_source(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return name in _SOURCE_NAMES or path.endswith(_SOURCE_SUFFIXES)


def _source_files(repo: Path) -> list[str]:
    """Tracked + untracked-non-ignored source files, repo-relative, sorted."""
    proc = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-co", "--exclude-standard", "-z"],
        capture_output=True,
        text=True,
        check=True,
    )
    files = (f for f in proc.stdout.split("\0") if f)
    return sorted(f for f in files if _is_source(f))


def compute_digest(repo: Path) -> str:
    """A sha256 over (path, content-hash) of every source file, or "" if none."""
    files = _source_files(repo)
    if not files:
        return ""
    # One git process hashes every file's working-tree content.
    proc = subprocess.run(
        ["git", "-C", str(repo), "hash-object", "--stdin-paths"],
        input="\n".join(files) + "\n",
        capture_output=True,
        text=True,
        check=True,
    )
    blobs = proc.stdout.split()
    digest = hashlib.sha256()
    for path, blob in zip(files, blobs, strict=True):
        digest.update(path.encode())
        digest.update(b"\0")
        digest.update(blob.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def write_stamp(repo: Path) -> None:
    (repo / STAMP_NAME).write_text(compute_digest(repo) + "\n", encoding="utf-8")


def is_fresh(repo: Path) -> bool:
    """True when a stamp exists and matches the current source fingerprint."""
    stamp = repo / STAMP_NAME
    if not stamp.exists():
        return False
    try:
        recorded = stamp.read_text(encoding="utf-8").strip()
        return bool(recorded) and recorded == compute_digest(repo)
    except (OSError, subprocess.CalledProcessError):
        return False


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    repo = Path.cwd()
    if cmd == "write":
        write_stamp(repo)
        return 0
    if cmd == "check":
        return 0 if is_fresh(repo) else 1
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
