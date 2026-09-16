#!/usr/bin/env python3
"""Set Coffer's version in every file that carries it, in one step.

    python scripts/bump_version.py 0.2.0

The version is held in six places — see TARGETS below — and they must agree
exactly: the desktop shell compares its Cargo crate version with the one
`/api/v1/daemon/status` reports (the Python package's) by string equality, and
`tauri.conf.json` names the `.dmg`. Bumping them by hand invites the permanent
"daemon out of date" banner a single missed file produces, so this script
rewrites all of them (and
`backend/tests/integration/distribution/test_packaging_specs.py` pins that they
agree). Stdlib only; edits are textual and anchored so formatting elsewhere in
each file is left alone.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

#: PEP 440 / semver-shaped: three numeric parts, optional pre-release suffix.
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-.]?(?:a|b|rc|alpha|beta|dev)\d*)?$")


def _sub_once(text: str, pattern: str, replacement: str, *, where: str) -> str:
    new, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise SystemExit(f"bump_version: no version anchor found in {where}")
    return new


def _bump_pyproject(text: str, version: str) -> str:
    # The first `version = "..."` after `[project]` — never a dependency pin.
    head, sep, tail = text.partition("[project]")
    if not sep:
        raise SystemExit("bump_version: backend/pyproject.toml has no [project] table")
    return (
        head
        + sep
        + _sub_once(
            tail,
            r'^version = "[^"]+"',
            f'version = "{version}"',
            where="backend/pyproject.toml",
        )
    )


def _bump_cargo_toml(text: str, version: str) -> str:
    head, sep, tail = text.partition("[package]")
    if not sep:
        raise SystemExit("bump_version: desktop/Cargo.toml has no [package] table")
    return (
        head
        + sep
        + _sub_once(
            tail,
            r'^version = "[^"]+"',
            f'version = "{version}"',
            where="desktop/Cargo.toml",
        )
    )


def _bump_cargo_lock(text: str, version: str) -> str:
    # Only the crate's own entry; every other `version` line is a dependency's.
    return _sub_once(
        text,
        r'(\[\[package\]\]\nname = "coffer-desktop"\nversion = )"[^"]+"',
        rf'\g<1>"{version}"',
        where="desktop/Cargo.lock",
    )


def _bump_json_top_level(text: str, version: str, *, where: str) -> str:
    # The first top-level `"version": "..."` (two-space indent), so a nested
    # dependency's version in package-lock.json is never touched.
    return _sub_once(
        text, r'^  "version": "[^"]+"', f'  "version": "{version}"', where=where
    )


def _bump_package_lock(text: str, version: str) -> str:
    # The lockfile repeats the root package's version under `packages[""]`.
    text = _bump_json_top_level(text, version, where="frontend/package-lock.json")
    return _sub_once(
        text,
        r'(    "": \{\n      "name": "coffer-frontend",\n      "version": )"[^"]+"',
        rf'\g<1>"{version}"',
        where='frontend/package-lock.json packages[""]',
    )


#: Relative path -> rewriter. Six entries; the docstring's count refers to
#: this table. `backend/tests/integration/distribution/test_packaging_specs.py`
#: reads the same files back, so adding a file here means adding it there.
TARGETS: dict[str, object] = {
    "backend/pyproject.toml": _bump_pyproject,
    "frontend/package.json": lambda t, v: _bump_json_top_level(
        t, v, where="frontend/package.json"
    ),
    "frontend/package-lock.json": _bump_package_lock,
    "desktop/Cargo.toml": _bump_cargo_toml,
    "desktop/Cargo.lock": _bump_cargo_lock,
    "desktop/tauri.conf.json": lambda t, v: _bump_json_top_level(
        t, v, where="desktop/tauri.conf.json"
    ),
}


def bump(version: str, root: Path = _REPO_ROOT) -> list[Path]:
    """Rewrite every version-bearing file under ``root``; return the paths written.

    All files are rewritten in memory first, so a missing anchor in any one of
    them leaves every file untouched rather than half the set bumped.
    """
    if not _VERSION_RE.match(version):
        raise SystemExit(
            f"bump_version: {version!r} is not a version like 1.2.3 or 1.2.3rc1"
        )
    pending: list[tuple[Path, str]] = []
    for rel, rewrite in TARGETS.items():
        path = root / rel
        if not path.exists():
            raise SystemExit(f"bump_version: {rel} is missing under {root}")
        pending.append((path, rewrite(path.read_text(encoding="utf-8"), version)))  # type: ignore[operator]
    for path, text in pending:
        path.write_text(text, encoding="utf-8")
    return [p for p, _ in pending]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("version", help="the new version, e.g. 0.2.0")
    parser.add_argument("--root", type=Path, default=_REPO_ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    for path in bump(args.version, args.root):
        print(f"bumped {path.relative_to(args.root)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
