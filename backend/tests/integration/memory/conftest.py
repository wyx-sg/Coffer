"""Fixtures the memory integration tier shares: real git trees, real readers.

Integration rather than unit for one reason: these tests run ``git`` itself.
A worktree's ``.git`` file, its private directory's ``commondir``, and the
exact spelling ``git remote add`` writes into a config are all things this
layer parses by hand, and a fixture that wrote them by hand would be testing
the test's idea of git rather than git's.

``ResourceService``/``AuditService`` stay fake — nothing here needs a real
database, and the agent config directories all live under ``tmp_path``.
``COFFER_MEMORY_ROOT`` is pinned to ``tmp_path`` by the suite-wide
``_isolated_memory_root`` fixture in ``backend/tests/conftest.py``.
"""

from __future__ import annotations

import json
import pathlib
import subprocess

from tests.unit.memory.conftest import (  # re-exported for the integration tests
    FakeAudit,
    FakeResources,
    agent_source_resolver,
)

__all__ = [
    "FakeAudit",
    "FakeResources",
    "agent_source_resolver",
    "claude_code_config",
    "codex_config",
    "git",
    "init_repository",
    "second_clone",
    "worktree_of",
]


def git(*args: str, cwd: pathlib.Path) -> str:
    """Run one git command with an environment that cannot read the
    developer's own config — no global ``user.name``, no ``init.defaultBranch``
    surprise, no commit signing hook."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
            "HOME": str(cwd),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )
    return result.stdout.strip()


def init_repository(root: pathlib.Path, *, remote: str = "") -> pathlib.Path:
    """A real checkout with one commit, and optionally an ``origin``."""
    root.mkdir(parents=True, exist_ok=True)
    git("init", "-q", "-b", "main", ".", cwd=root)
    (root / "README.md").write_text("# fixture\n", encoding="utf-8")
    git("add", "README.md", cwd=root)
    git("commit", "-q", "-m", "first", cwd=root)
    if remote:
        git("remote", "add", "origin", remote, cwd=root)
    return root


def worktree_of(root: pathlib.Path, path: pathlib.Path, *, branch: str = "side") -> pathlib.Path:
    """A real ``git worktree add`` — the ``.git`` **file** case."""
    git("worktree", "add", "-q", "-b", branch, str(path), cwd=root)
    assert (path / ".git").is_file(), "a worktree's .git is a file, not a directory"
    return path


def second_clone(root: pathlib.Path, path: pathlib.Path, *, remote: str) -> pathlib.Path:
    """Another checkout of the same upstream, configured with a differently
    spelled but equivalent remote URL."""
    git("clone", "-q", str(root), str(path), cwd=root.parent)
    git("remote", "set-url", "origin", remote, cwd=path)
    return path


def claude_code_config(
    config_dir: pathlib.Path, project_root: pathlib.Path, files: dict[str, str]
) -> pathlib.Path:
    """A Claude Code config directory whose project slug decodes to
    ``project_root``.

    A sibling session transcript records the literal ``cwd``, which is how the
    reader recovers the project root authoritatively rather than by decoding
    the slug — the same path production takes.
    """
    slug = "-" + "-".join(
        "".join(ch if ch.isalnum() and ch.isascii() else "-" for ch in part)
        for part in project_root.parts
        if part != "/"
    )
    project_dir = config_dir / "projects" / slug
    memory_dir = project_dir / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "session.jsonl").write_text(
        json.dumps({"type": "user", "cwd": str(project_root)}) + "\n", encoding="utf-8"
    )
    for name, text in files.items():
        (memory_dir / name).write_text(text, encoding="utf-8")
    return config_dir


def codex_config(config_dir: pathlib.Path, memory_md: str, summary_md: str = "") -> pathlib.Path:
    memories = config_dir / "memories"
    memories.mkdir(parents=True, exist_ok=True)
    (memories / "MEMORY.md").write_text(memory_md, encoding="utf-8")
    if summary_md:
        (memories / "memory_summary.md").write_text(summary_md, encoding="utf-8")
    return config_dir
