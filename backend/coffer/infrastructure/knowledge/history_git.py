"""One ``git`` process over the knowledge root's history repository, and the
parsing of what ``git log`` answers.

The repository is ``<knowledge root>/.git`` (see ``history.py`` for why it is
the knowledge root's own until the vault is one repository). Every invocation
names both the git directory and the work tree explicitly, so a knowledge root
that has no repository yet can never be mistaken for a parent directory's —
without that, ``git -C root`` would climb to whatever repository the root
happens to sit inside.

Like the sync mirror's own invocations (``infrastructure/sync/git_invoke``),
each one runs with the user's global and system git config pinned to
``/dev/null`` and its identity given on the command line: a developer's own
git settings must not change what the daemon records, and Coffer must not write
an identity into any config. It is a separate module rather than an import of
that one because the two kinds may not import each other's infrastructure.

Synchronous on purpose — every call is a few milliseconds, and the callers run
it off the event loop (``asyncio.to_thread``) or inside a thread already.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
from datetime import UTC, datetime

from coffer.domain.knowledge.history import (
    ADDED,
    MODIFIED,
    REMOVED,
    Change,
    ChangeMeta,
    DocumentChange,
)

#: The trailer each ``ChangeMeta`` field is written as. The names follow ADR
#: every-vault-write-is-a-validated-commit-naming-its-writer, so the history
#: folds into the vault's repository without a translation.
TRAILERS = {
    "writer": "Coffer-Writer",
    "operation": "Coffer-Operation",
    "actor": "Coffer-Actor",
    "agent": "Coffer-Agent",
    "collection": "Coffer-Collection",
    "item": "Coffer-Item",
    "status": "Coffer-Status",
    "restored_from": "Coffer-Restored-From",
    "undoes": "Coffer-Undoes",
}
_FIELD_OF = {v.lower(): k for k, v in TRAILERS.items()}

#: ``git log`` record layout: a record separator, then the commit id, its
#: committer time and its raw message, then a group separator before the
#: ``--raw`` / ``--numstat`` lines.
LOG_FORMAT = "--format=%x1e%H%x1f%ct%x1f%B%x1d"

_EMAIL = "coffer@localhost"
TIMEOUT_S = 30.0


class GitCommandError(Exception):
    """A git invocation that exited non-zero where the caller needed success."""


def git_available() -> bool:
    return shutil.which("git") is not None


def _env(root: pathlib.Path, writer: str | None) -> dict[str, str]:
    env = dict(os.environ)
    env["GIT_DIR"] = str(root / ".git")
    env["GIT_WORK_TREE"] = str(root)
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    name = f"Coffer ({writer})" if writer else "Coffer"
    for role in ("AUTHOR", "COMMITTER"):
        env[f"GIT_{role}_NAME"] = name
        env[f"GIT_{role}_EMAIL"] = _EMAIL
    return env


def run(
    root: pathlib.Path,
    *args: str,
    check: bool = True,
    stdin: bytes | None = None,
    writer: str | None = None,
    literal: bool = False,
) -> subprocess.CompletedProcess[bytes]:
    """``git <args>`` over the knowledge root's repository, output captured.

    ``literal`` turns pathspec magic off, so a document path is always the
    path it names and never a pattern.
    """
    argv = [
        "git",
        "-c",
        "core.quotepath=false",
        "-c",
        "core.autocrlf=false",
        "-c",
        "commit.gpgsign=false",
        "-c",
        f"core.hooksPath={os.devnull}",
    ]
    if literal:
        argv.append("--literal-pathspecs")
    argv += list(args)
    # argv, never a shell: nothing in a path is re-parsed as a command.
    done = subprocess.run(
        argv,
        cwd=root,
        env=_env(root, writer),
        input=stdin,
        capture_output=True,
        timeout=TIMEOUT_S,
        check=False,
    )
    if check and done.returncode != 0:
        detail = done.stderr.decode("utf-8", "replace").strip() or f"exit {done.returncode}"
        raise GitCommandError(f"git {args[0] if args else ''} failed: {detail}")
    return done


def message(meta: ChangeMeta) -> bytes:
    """The commit message: the summary, a blank line, one trailer per field set."""
    lines = [meta.summary.strip() or meta.operation, ""]
    for field, trailer in TRAILERS.items():
        value = getattr(meta, field)
        if value:
            lines.append(f"{trailer}: {str(value).replace(chr(10), ' ')}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def parse_meta(body: str) -> ChangeMeta:
    """Read a commit message back into its ``ChangeMeta``.

    A commit Coffer did not write (a person's own ``git commit`` in the
    repository) has no trailers and reads as an edit on disk.
    """
    lines = body.strip("\n").split("\n")
    summary = lines[0] if lines else ""
    values: dict[str, str] = {}
    for line in lines[1:]:
        key, sep, value = line.partition(": ")
        field = _FIELD_OF.get(key.strip().lower())
        if sep and field:
            values[field] = value.strip()
    return ChangeMeta(
        writer=values.pop("writer", "disk"),
        operation=values.pop("operation", "edit"),
        summary=summary,
        **values,
    )


def _status(letter: str) -> str:
    return {"A": ADDED, "D": REMOVED}.get(letter[:1], MODIFIED)


def parse_log(raw: bytes) -> list[Change]:
    """Every record of a ``LOG_FORMAT`` log run with ``--raw --numstat``."""
    out: list[Change] = []
    for record in raw.decode("utf-8", "replace").split("\x1e"):
        if not record.strip():
            continue
        head, _, tail = record.partition("\x1d")
        version, _, rest = head.partition("\x1f")
        when, _, body = rest.partition("\x1f")
        statuses: dict[str, str] = {}
        counts: dict[str, tuple[int, int]] = {}
        for line in tail.split("\n"):
            if not line.strip():
                continue
            if line.startswith(":"):
                # ":100644 100644 abc def M\tpath"
                fields, _, path = line.partition("\t")
                statuses[path] = _status(fields.split()[-1])
                continue
            added, _, rest_line = line.partition("\t")
            removed, _, path = rest_line.partition("\t")
            if path:
                counts[path] = (
                    int(added) if added.isdigit() else 0,
                    int(removed) if removed.isdigit() else 0,
                )
        documents = tuple(
            DocumentChange(
                path=path,
                status=status,
                added=counts.get(path, (0, 0))[0],
                removed=counts.get(path, (0, 0))[1],
            )
            for path, status in statuses.items()
        )
        out.append(
            Change(
                version=version.strip(),
                time=datetime.fromtimestamp(int(when or 0), tz=UTC),
                meta=parse_meta(body),
                documents=documents,
            )
        )
    return out


__all__ = [
    "LOG_FORMAT",
    "TRAILERS",
    "GitCommandError",
    "git_available",
    "message",
    "parse_log",
    "parse_meta",
    "run",
]
