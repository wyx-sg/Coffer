#!/usr/bin/env python3
"""Fail when a `.gitignore` rule hides a real source file.

An unanchored ignore pattern matches a folder of that name at any depth. The
Python and Node templates `.gitignore` started from are full of them (`env/`,
`lib/`, `build/`, `secrets/`), and on case-insensitive macOS they also match
`Env/` or `ENV/`. That is how `frontend/src/components/mcp/env/` sat on disk,
imported and working, and was never committed: `git status` does not show an
ignored folder, so nothing looked wrong until a fresh clone failed to build.

Two checks:

  1. **Hidden paths.** Every path under the source trees below that git
     ignores — whether it exists only on disk or is already tracked, where the
     rule still hides every new file beside it — fails with the rule that
     matches it. Git is asked with ``core.ignorecase=true`` on every host, so a
     Linux run finds what a Mac would hide. Generated and cache outputs
     (``GENERATED_DIRS``, ``GENERATED_FILES``) are expected and skipped.
  2. **Risky patterns.** Every ``.gitignore`` line that is unanchored (no
     leading ``/`` and no ``/`` inside it) and names a common source-folder
     word (``SOURCE_WORDS``, compared case-insensitively) fails, because it
     would hide that folder anywhere in the tree. Anchor it (``/build/``) when
     it is meant for the repository root, or spell out its full path.

The first check only bites on a checkout that has the hidden files on disk;
the second bites everywhere, CI included. Exits non-zero with one line per
problem.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The trees that hold source. `e2e` and `docs-site` hold build and test output
#: too; the generated names below cover those.
SOURCE_ROOTS = (
    "backend/coffer",
    "backend/tests",
    "frontend/src",
    "desktop/src",
    "e2e",
    "docs-site",
    "openspec",
    "scripts",
    "evals",
)

#: Folder names that are build, test or cache output wherever they appear.
GENERATED_DIRS = frozenset(
    {
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".hypothesis",
        "node_modules",
        "dist",
        "coverage",
        "htmlcov",
        "test-results",
        "playwright-report",
        ".vite",
        ".cache",
    }
)
#: File names or suffixes that are generated wherever they appear.
GENERATED_FILES = (".pyc", ".pyo", ".ds_store", ".tsbuildinfo", ".log", ".coverage")
#: Output folders that are only generated under one parent.
GENERATED_NESTED = ((".vitepress", "cache"), (".vitepress", "dist"))

#: Folder names that are common in source trees, so an unanchored ignore
#: pattern naming one is almost certainly hiding more than it means to.
SOURCE_WORDS = frozenset(
    {
        "bin",
        "build",
        "config",
        "data",
        "develop-eggs",
        "downloads",
        "eggs",
        "env",
        "include",
        "lib",
        "lib64",
        "local",
        "logs",
        "out",
        "packages",
        "parts",
        "sdist",
        "secrets",
        "share",
        "src",
        "temp",
        "tmp",
        "var",
        "vendor",
        "venv",
        "wheels",
    }
)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "core.ignorecase=true", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    ).stdout


def is_generated(rel: str) -> bool:
    parts = [p.lower() for p in rel.rstrip("/").split("/")]
    if any(p in GENERATED_DIRS for p in parts):
        return True
    if not rel.endswith("/") and parts[-1].endswith(GENERATED_FILES):
        return True
    return any(
        (parent, child) == pair
        for parent, child in zip(parts, parts[1:])
        for pair in GENERATED_NESTED
    )


def _ignored_untracked(root: Path, paths: tuple[str, ...], *, collapse: bool) -> list[str]:
    args = ["ls-files", "-z", "--others", "--ignored", "--exclude-standard"]
    if collapse:
        args.append("--directory")
    return [p for p in _git(root, *args, "--", *paths).split("\0") if p]


#: Pathspecs that keep a folder listing out of the generated trees.
_PRUNE = tuple(f":(exclude,glob,icase)**/{name}/**" for name in sorted(GENERATED_DIRS))


def hidden_paths(root: Path, roots: tuple[str, ...] = SOURCE_ROOTS) -> list[str]:
    """Ignored paths under `roots` that are on disk or tracked, generated ones skipped."""
    found: set[str] = set()
    # Collapsed first, so a node_modules/ is one line rather than its every file.
    for rel in _ignored_untracked(root, roots, collapse=True):
        if is_generated(rel):
            continue
        if rel.endswith("/"):
            # Git reports a folder whole when everything in it is ignored or
            # untracked; it may hold generated output only, so look inside.
            inside = _ignored_untracked(root, (rel, *_PRUNE), collapse=False)
            found.update(f for f in inside if not is_generated(f))
        else:
            found.add(rel)
    tracked = _git(
        root, "ls-files", "-z", "--cached", "--ignored", "--exclude-standard", "--", *roots
    ).split("\0")
    found.update(p for p in tracked if p and not is_generated(p))
    return sorted(found)


def matching_rule(root: Path, rel: str) -> str:
    """`<source>:<line>: <pattern>` for the rule that ignores `rel`."""
    out = _git(root, "check-ignore", "-v", "--no-index", "--", rel).strip()
    rule, _, _ = out.partition("\t")
    source, _, rest = rule.partition(":")
    line, _, pattern = rest.partition(":")
    return f"{source}:{line}: {pattern}" if pattern else "an ignore rule"


def risky_patterns(gitignore: Path, rel: str) -> list[str]:
    """Unanchored lines in one `.gitignore` that name a source-folder word."""
    errors: list[str] = []
    for lineno, raw in enumerate(gitignore.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(("#", "!")):
            continue
        body = line.rstrip("/")
        if "/" in body:
            continue
        if body.lower() in SOURCE_WORDS:
            errors.append(
                f"{rel}:{lineno}: {line!r} is unanchored and hides every folder named "
                f"{body!r} — anchor it (/{line}) or spell out its full path"
            )
    return errors


def gitignore_files(root: Path) -> list[str]:
    listed = _git(root, "ls-files", "-z", "--", ".gitignore", "*/.gitignore").split("\0")
    return sorted(p for p in listed if p and "node_modules/" not in p)


def check(root: Path) -> list[str]:
    errors = [
        f"{rel}: ignored by git but part of a source tree ({matching_rule(root, rel)})"
        for rel in hidden_paths(root)
    ]
    for rel in gitignore_files(root):
        errors += risky_patterns(root / rel, rel)
    return errors


def main() -> int:
    errors = check(REPO_ROOT)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        print(f"\ncheck_ignored_sources: {len(errors)} problem(s)", file=sys.stderr)
        return 1
    print("check_ignored_sources: no source path is hidden by .gitignore")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
