"""A home as the previous build left it: ``coffer.db`` at a pre-vault
revision with a row in every table the upgrade moves, and every tree at its
old place (the V4 gate's fixture; plan q9 §3).

Built from scratch in a test's own fake ``HOME``: Alembic brings a fresh
``coffer.db`` to the revision, rows are inserted by hand, and the trees are
written file by file — the knowledge root with a git history of its own and
curation stamps, as the previous build kept it.
"""

from __future__ import annotations

import contextlib
import importlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from alembic import command
from cryptography.fernet import Fernet

from coffer.surfaces.http.migrations_runner import _alembic_config

_0135 = importlib.import_module(
    "coffer.infrastructure.persistence.migrations.versions.20260930_0135_secrets"
)

AT = "2026-09-01 10:00:00.000000"
#: When the provider's key was last used on this machine (revision 0135).
LAST_USED = "2026-08-20T00:00:00+00:00"
UIDS = {
    "github": "a1" * 16,
    "linear": "a2" * 16,
    "files": "a3" * 16,
    "writing-tests": "b1" * 16,
    "deploy": "b2" * 16,
    "coffer-guide": "b3" * 16,
    "tg": "c1" * 16,
    "st": "c2" * 16,
    "anthropic": "d1" * 16,
    "ollama": "d2" * 16,
    "notes": "e1" * 16,
    "work": "e2" * 16,
    "claude_code": "f1" * 16,
    "codex": "f2" * 16,
    "global": "90" * 16,
    "coffer": "91" * 16,
}

#: ``(id, kind, name, config, enabled, scope agents | None, title)``.
Spec = tuple[int, str, str, dict[str, Any], bool, list[str] | None, str | None]


def resources(home: Path) -> list[Spec]:
    h = str(home)
    return [
        (
            1,
            "mcp_server",
            "github",
            {
                "transport": {
                    "type": "stdio",
                    "command": "/bin/echo",
                    "secret_refs": {"GITHUB_TOKEN": "mcp/github-token"},
                }
            },
            False,
            None,
            None,
        ),
        (
            2,
            "mcp_server",
            "linear",
            {"transport": {"type": "http", "url": "http://127.0.0.1:9/mcp"}},
            False,
            [UIDS["claude_code"]],
            None,
        ),
        (
            3,
            "mcp_server",
            "files",
            {"transport": {"type": "stdio", "command": "/bin/echo", "cwd": f"{h}/work"}},
            False,
            None,
            None,
        ),
        (
            4,
            "skill",
            "writing-tests",
            {
                "source": {"type": "local_import", "original_path": f"{h}/src/writing-tests"},
                "skill_md_description": "Write tests",
                "version_hash": "v1",
            },
            True,
            None,
            None,
        ),
        (
            5,
            "skill",
            "deploy",
            {
                "source": {
                    "type": "git_import",
                    "url": "https://x/y.git",
                    "commit": "0123456789abcdef",
                    "content_hash": "h1",
                },
                "skill_md_description": "Deploy",
                "version_hash": "v2",
            },
            False,
            [UIDS["codex"]],
            None,
        ),
        (
            6,
            "skill",
            "coffer-guide",
            {
                "source": {"type": "builtin"},
                "skill_md_description": "Coffer's guide",
                "version_hash": "v3",
            },
            True,
            None,
            None,
        ),
        (
            7,
            "channel",
            "tg",
            {
                "channel_type": "telegram",
                "bot_token_ref": "channel/tg/bot-token",
                "default_agent": UIDS["claude_code"],
            },
            False,
            None,
            "Telegram bot",
        ),
        (
            8,
            "channel",
            "st",
            {
                "channel_type": "seatalk",
                "app_id": "app-1",
                "app_secret_ref": "channel/st/app-secret",
                "runs_on": "elsewhere",
            },
            False,
            None,
            None,
        ),
        (
            9,
            "provider",
            "anthropic",
            {
                "protocol": "anthropic",
                "base_url": "https://api.anthropic.com",
                "secret_ref": "provider/anthropic",
            },
            True,
            None,
            "Work Anthropic",
        ),
        (
            10,
            "provider",
            "ollama",
            {"protocol": "ollama", "base_url": "http://127.0.0.1:11434"},
            False,
            [],
            None,
        ),
        (11, "knowledge", "notes", {}, True, None, None),
        (12, "knowledge", "work", {}, True, None, "Work notes"),
        (
            13,
            "agent",
            "claude_code",
            {"type": "claude_code", "config_dir": f"{h}/.claude"},
            True,
            None,
            None,
        ),
        (14, "agent", "codex", {"type": "codex"}, False, None, None),
        (15, "memory", "global", {"repository_key": "", "repository_path": ""}, True, None, None),
        (
            16,
            "memory",
            "coffer",
            {"repository_key": "remote:github.com/x/coffer", "repository_path": f"{h}/src/coffer"},
            True,
            None,
            None,
        ),
    ]


@dataclass
class LegacyHome:
    home: Path
    key: bytes
    secrets: dict[str, str] = field(default_factory=dict)
    #: Every tree file the fixture wrote, relative to ``~/.coffer``.
    files: dict[str, bytes] = field(default_factory=dict)

    @property
    def coffer(self) -> Path:
        return self.home / ".coffer"

    @property
    def db(self) -> Path:
        return self.coffer / "coffer.db"


def _insert(conn: sqlite3.Connection, table: str, row: dict[str, Any]) -> None:
    cols = ", ".join(f'"{c}"' for c in row)
    marks = ", ".join("?" for _ in row)
    conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(row.values()))


#: The revision that renamed the secret store's table, the sync remote's
#: columns and the two config keys that cite a secret; a home built below it
#: carries the old names, as that build wrote them.
SECRET_RENAME = "0135"


def _rows(conn: sqlite3.Connection, lh: LegacyHome, revision: str) -> None:
    fernet = Fernet(lh.key)
    renamed = revision >= SECRET_RENAME
    for rid, kind, name, config, enabled, agents, title in resources(lh.home):
        if not renamed:
            _0135.rewrite_config(kind, config, forward=False)
        _insert(
            conn,
            "resources",
            {
                "id": rid,
                "uid": UIDS[name],
                "kind": kind,
                "name": name,
                "description": f"the {name} {kind}",
                "config_json": json.dumps(config),
                "enabled": int(enabled),
                "created_at": AT,
                "updated_at": AT,
                "rev": 3,
                "scope_json": json.dumps({"agents": agents}) if agents is not None else None,
                "title": title,
            },
        )
    lh.secrets = {
        "mcp/github-token": "ghp-secret",
        "channel/tg/bot-token": "123:abc",
        "channel/st/app-secret": "st-secret",
        "provider/anthropic": "sk-ant",
        "secret/api key": "spaces and all",
        "proxy-token/claude_code": "local-proxy",
    }
    for ref, value in lh.secrets.items():
        row: dict[str, Any] = {
            "ref": ref,
            "ciphertext": fernet.encrypt(value.encode()),
            "created_at": "2026-08-01T00:00:00+00:00",
            "updated_at": "2026-08-02T00:00:00+00:00",
        }
        if renamed and ref == "provider/anthropic":
            row["last_used_at"] = LAST_USED
        _insert(conn, "secrets" if renamed else "credentials", row)
    _insert(
        conn,
        "secret_bindings",
        {
            "ref": "provider/anthropic",
            "destination_kind": "provider",
            "destination_uid": UIDS["anthropic"],
            "slot": "secret_ref",
            "target_fingerprint": "fp1",
            "approved_at": "2026-08-03T00:00:00+00:00",
            "approval_id": "ap-1",
        },
    )
    _insert(
        conn,
        "secret_approvals",
        {
            "id": "ap-1",
            "op": "bind",
            "status": "approved",
            "created_at": "2026-08-03T00:00:00+00:00",
            "requested_by": "user",
            "ref": "provider/anthropic",
            "destination_kind": "provider",
            "destination_uid": UIDS["anthropic"],
            "slot": "secret_ref",
            "target_fingerprint": "fp1",
            "decided_at": "2026-08-03T00:01:00+00:00",
            "decided_by": "user",
        },
    )
    _insert(
        conn,
        "secret_approvals",
        {
            "id": "ap-2",
            "op": "replace_value",
            "status": "pending",
            "created_at": "2026-08-04T00:00:00+00:00",
            "requested_by": "agent:claude_code",
            "ref": "mcp/github-token",
            "pending_ciphertext": fernet.encrypt(b"new"),
        },
    )
    _insert(conn, "secret_boundary_settings", {"key": "protection", "value": "on"})
    for i, (rid, ctype, key, on) in enumerate(
        [(1, "tool", "delete_repo", 0), (1, "tool", "list_repos", 1), (2, "prompt", "triage", 0)]
    ):
        _insert(
            conn,
            "mcp_capability_preferences",
            {
                "id": i + 1,
                "resource_id": rid,
                "capability_type": ctype,
                "capability_key": key,
                "enabled": on,
                "first_seen_at": AT,
                "last_seen_at": AT,
            },
        )
    _insert(
        conn,
        "channel_peers",
        {
            "id": 1,
            "resource_id": 7,
            "chat_id": "group-9",
            "display_name": "Team",
            "paired_at": "2026-09-02 10:00:00.000000",
            "sender_id": None,
        },
    )
    _insert(
        conn,
        "channel_peers",
        {
            "id": 2,
            "resource_id": 7,
            "chat_id": "dm-1",
            "display_name": "Me",
            "paired_at": "2026-09-01 09:00:00.000000",
            "sender_id": "42",
        },
    )
    conn.execute("DELETE FROM internal_engine_config")
    _insert(
        conn,
        "internal_engine_config",
        {
            "id": 1,
            "model": "anthropic/claude-sonnet",
            "updated_at": AT,
            "curate_owner_machine_id": "machine-a",
            "aggregate_interval_s": 600,
            "auto_distil_enabled": 0,
        },
    )
    conn.execute("DELETE FROM retention_policies")
    _insert(
        conn,
        "retention_policies",
        {
            "table_name": "audit_log",
            "retention_days": 90,
            "last_pruned_at": AT,
            "last_pruned_rows": 7,
            "updated_at": AT,
        },
    )
    _insert(
        conn,
        "skill_source_status",
        {
            "skill_resource_id": 5,
            "checked_at": AT,
            "last_success_at": AT,
            "latest_commit": "fedcba9876543210",
            "commits_ahead": 2,
            "files_changed": 1,
        },
    )
    _insert(
        conn,
        "skill_agent_bindings",
        {
            "skill_resource_id": 4,
            "agent_resource_id": 13,
            "enabled": 1,
            "last_linked_at": AT,
            "last_link_path": f"{lh.home}/.claude/skills/writing-tests",
            "link_mode": "copy_fallback",
        },
    )
    _insert(
        conn,
        "mcp_server_health",
        {"resource_uid": UIDS["github"], "status": "ok", "checked_at": AT},
    )
    if revision >= "0115":
        _insert(
            conn,
            "mcp_tool_reach",
            {
                "resource_uid": UIDS["github"],
                "tool": "search",
                "agents_json": json.dumps([UIDS["claude_code"]]),
                "updated_at": AT,
            },
        )
    _insert(
        conn,
        "sync_remotes",
        {
            "id": 1,
            "url": "/nowhere/remote.git",
            "branch": "main",
            "include_secrets" if renamed else "include_credentials": 0,
            "interval_seconds": 900,
            "enabled": 1,
            "worktree_path": "~/.coffer/sync",
            "updated_at": AT,
        },
    )
    for aid, rid in [(1, 1), (2, 7), (3, None), (4, 99)]:
        _insert(
            conn,
            "audit_log",
            {
                "id": aid,
                "timestamp": AT,
                "event_type": "resource_updated",
                "actor": "user",
                "resource_id": rid,
                "resource_kind": "k",
                "resource_name": "n",
            },
        )
    _insert(
        conn,
        "conversations",
        {
            "id": "conv-1",
            "agent_key": "claude_code",
            "title": "Hi",
            "created_at": AT,
            "updated_at": AT,
            "channel_uid": UIDS["tg"],
            "peer_chat_id": "dm-1",
        },
    )
    for seq, role in [(1, "user"), (2, "assistant")]:
        _insert(
            conn,
            "chat_messages",
            {
                "id": f"m{seq}",
                "conversation_id": "conv-1",
                "seq": seq,
                "role": role,
                "content": f"message {seq}",
                "created_at": AT,
            },
        )
    _insert(
        conn,
        "channel_thread_conversations",
        {
            "id": 1,
            "resource_id": 7,
            "chat_id": "dm-1",
            "thread_id": "",
            "active_conversation_id": "conv-1",
            "updated_at": AT,
        },
    )
    _insert(
        conn,
        "mcp_invocations",
        {
            "id": 1,
            "timestamp": AT,
            "resource_uid": UIDS["github"],
            "capability_type": "tool",
            "capability_key": "list_repos",
            "duration_ms": 5,
            "status": "ok",
        },
    )


def _git(cwd: Path, *args: str, when: str) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": when,
        "GIT_COMMITTER_DATE": when,
        "GIT_AUTHOR_NAME": "Coffer (disk)",
        "GIT_AUTHOR_EMAIL": "coffer@localhost",
        "GIT_COMMITTER_NAME": "Coffer (disk)",
        "GIT_COMMITTER_EMAIL": "coffer@localhost",
    }
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
    )


def _write(lh: LegacyHome, rel: str, data: bytes | str) -> Path:
    body = data.encode() if isinstance(data, str) else data
    path = lh.coffer / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    lh.files[rel] = body
    return path


SETTLED_DOC = """---
title: On call
description: Who is on call
actor: user
coffer_curated_at: '2030-01-01T00:00:00+00:00'
---

Primary on-call rotates every Monday.
"""
EDITED_DOC = """---
title: Runbook
coffer_curated_at: '2020-01-01T00:00:00+00:00'
---

Restart the gateway first.
"""


def _trees(lh: LegacyHome) -> None:
    k = lh.coffer / "knowledge"
    _write(lh, "knowledge/notes/README.md", "# Notes\n")
    _write(lh, "knowledge/notes/team/on-call.md", "---\ntitle: On call\n---\n\nFirst draft.\n")
    k.mkdir(parents=True, exist_ok=True)
    _git(k, "init", "-q", "-b", "main", when="2026-08-01T09:00:00+02:00")
    _git(k, "add", "-A", when="2026-08-01T09:00:00+02:00")
    _git(
        k,
        "commit",
        "-q",
        "-m",
        "Created notes\n\nCoffer-Writer: user\nCoffer-Operation: create",
        when="2026-08-01T09:00:00+02:00",
    )
    _write(lh, "knowledge/notes/team/on-call.md", SETTLED_DOC)
    _write(lh, "knowledge/work/runbook.md", EDITED_DOC)
    _git(k, "add", "-A", when="2026-08-02T10:30:00+02:00")
    _git(
        k,
        "commit",
        "-q",
        "-m",
        "Curated notes\n\nCoffer-Writer: curation\nCoffer-Operation: curate",
        when="2026-08-02T10:30:00+02:00",
    )
    _write(lh, "knowledge/work/.inbox/new.md", "---\ntitle: Queued\n---\n\nWaiting.\n")
    _write(lh, "knowledge/work/unsaved.md", "an edit never committed\n")
    # The settled document is not newer than its stamp; the runbook is.
    os.utime(k / "notes/team/on-call.md", (1_800_000_000, 1_800_000_000))
    _write(lh, "skills/writing-tests/SKILL.md", "---\nname: writing-tests\n---\nWrite tests.\n")
    run = _write(lh, "skills/writing-tests/scripts/run.sh", "#!/bin/sh\necho ok\n")
    run.chmod(0o755)
    _write(lh, "skills/deploy/SKILL.md", "---\nname: deploy\n---\nDeploy.\n")
    _write(lh, "skills/coffer-guide/SKILL.md", "---\nname: coffer-guide\n---\nGuide.\n")
    _write(lh, "memory/global/MEMORY.md", "# Memory\n")
    _write(lh, "memory/global/notes/a.md", "a lesson\n")
    _write(lh, "memory/coffer/.raw/entry.jsonl", '{"x": 1}\n')
    _write(lh, "vault/memory-triggers/rm-rf.md", "---\nid: rm-rf\n---\nNever rm -rf.\n")
    _write(lh, "chat-media/abc.bin", b"\x00\x01binary")
    _write(lh, "channel-media/photo.png", b"\x89PNG")
    _write(lh, "workspace/notes.txt", "scratch\n")
    _write(lh, "cache/agent/transcripts.json", "{}\n")
    _write(lh, "sync/resources/skill/x.yaml", "old: layout\n")
    _write(lh, "logs/daemon.log", "log line\n")
    link = lh.home / ".claude" / "projects" / "p" / "memory"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(lh.coffer / "memory" / "global")


_SCHEMAS: dict[str, Path] = {}


def _schema_at(revision: str) -> Path:
    """An empty ``coffer.db`` at ``revision``, built once per process (a full
    Alembic run takes seconds) and copied into each home. Built before any
    tree exists, so the data migrations on the way find nothing to rewrite."""
    if revision not in _SCHEMAS:
        path = Path(tempfile.mkdtemp(prefix="coffer-legacy-schema-")) / "coffer.db"
        command.upgrade(_alembic_config(f"sqlite+aiosqlite:///{path}"), revision)
        with contextlib.closing(sqlite3.connect(path)) as conn:
            conn.execute("PRAGMA journal_mode = DELETE")
        _SCHEMAS[revision] = path
    return _SCHEMAS[revision]


def build_legacy_home(home: Path, *, revision: str = SECRET_RENAME) -> LegacyHome:
    """A pre-vault home at ``home`` (the parent of ``.coffer``)."""
    lh = LegacyHome(home=home, key=Fernet.generate_key())
    lh.coffer.mkdir(parents=True, exist_ok=True)
    config = {"port": 8123, "features": {"vault_sync": True, "knowledge": False, "other": 1}}
    (lh.coffer / "daemon-config.json").write_text(json.dumps(config) + "\n", encoding="utf-8")
    key = lh.coffer / "master.key"
    key.write_bytes(lh.key)
    key.chmod(0o600)
    shutil.copy2(_schema_at(revision), lh.db)
    with sqlite3.connect(lh.db) as conn:
        _rows(conn, lh, revision)
        conn.commit()
    _trees(lh)
    return lh


__all__ = ["AT", "UIDS", "LegacyHome", "build_legacy_home", "resources"]
