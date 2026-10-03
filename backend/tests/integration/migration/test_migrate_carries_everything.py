"""``coffer migrate`` on a pre-vault home: every resource, secret, document,
skill file, memory file and history row survives, in the class
directory it belongs to, in the bytes its store would write (plan q9 §3)."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from coffer.domain.vault.document import ResourceDocument, parse_resource
from coffer.domain.vault.writers import parse_meta
from coffer.infrastructure.secret.boundary_store import FileBoundaryStore
from coffer.infrastructure.secret.encrypted_store import EncryptedSecretStore
from coffer.infrastructure.vault.migration.run import migrate
from coffer.infrastructure.vault.migration.verify import check, take_inventory
from coffer.infrastructure.vault.reach_store import ReachStore, reach_path

from .conftest import UPGRADE
from .legacy_home import LAST_USED, UIDS, LegacyHome, resources

_CLASS = {"agent": "local", "memory": "derived"}


def _migrate(legacy: LegacyHome):  # type: ignore[no-untyped-def]
    return migrate(legacy.home, upgrade_db=UPGRADE, build="test")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    ).stdout


@pytest.mark.acceptance(spec="vault-storage", scenario="the upgrade carries every item")
def test_the_inventory_of_the_old_home_is_all_there(legacy: LegacyHome) -> None:
    inventory = take_inventory(legacy.home)
    assert len(inventory.resources) == 16 and len(inventory.secrets) == 6
    report = _migrate(legacy)
    assert report.outcome == "migrated", report.lines()
    assert check(legacy.home, inventory) == []
    assert report.skipped == []


def test_each_resource_is_its_stores_file_with_uid_and_no_created_at(legacy: LegacyHome) -> None:
    _migrate(legacy)
    for _id, kind, name, config, _on, _agents, title in resources(legacy.home):
        cls = "derived" if name == "coffer-guide" else _CLASS.get(kind, "vault")
        path = legacy.coffer / cls / "resources" / kind / f"{name}.json"
        data = path.read_bytes()
        doc = parse_resource(data)
        assert doc.uid == UIDS[name] and doc.title == title and doc.created_at is None
        assert "created_at" not in json.loads(data)
        text = json.dumps(config).replace(str(legacy.home), "${HOME}")
        expected = ResourceDocument(
            uid=UIDS[name],
            kind=kind,
            name=name,
            description=f"the {name} {kind}",
            title=title,
            config=json.loads(text),
        ).to_bytes()
        assert data == expected, f"{kind} {name} is not the store's own bytes"


def test_a_retired_mcp_server_key_is_dropped_on_the_way_into_the_file(
    legacy: LegacyHome,
) -> None:
    """``MCPServerConfig`` refuses keys it does not declare, so a row still
    carrying ``idle_timeout_seconds`` becomes a file without it — and the
    upgrade's own check counts that as carried, not as a difference."""
    with sqlite3.connect(legacy.db) as conn:
        (raw,) = conn.execute(
            "SELECT config_json FROM resources WHERE kind='mcp_server' AND name='github'"
        ).fetchone()
        config = json.loads(raw)
        conn.execute(
            "UPDATE resources SET config_json=? WHERE kind='mcp_server' AND name='github'",
            (json.dumps({**config, "idle_timeout_seconds": 600}),),
        )
    inventory = take_inventory(legacy.home)
    report = _migrate(legacy)
    assert report.outcome == "migrated", report.lines()
    assert check(legacy.home, inventory) == []
    written = parse_resource(
        (legacy.coffer / "vault" / "resources" / "mcp_server" / "github.json").read_bytes()
    )
    assert written.config == config


@pytest.mark.acceptance(spec="vault-sync", scenario="reach stays on the machine it was set on")
def test_reach_is_local_and_keeps_enabled_and_scope(legacy: LegacyHome) -> None:
    _migrate(legacy)
    reach = ReachStore(reach_path(legacy.home)).all()
    assert set(reach) == set(UIDS.values())
    assert reach[UIDS["github"]].enabled is False
    assert reach[UIDS["linear"]].scope is not None
    assert reach[UIDS["linear"]].scope.agents == [UIDS["claude_code"]]
    assert reach[UIDS["ollama"]].scope is not None and reach[UIDS["ollama"]].scope.agents == []
    assert reach[UIDS["writing-tests"]].enabled and reach[UIDS["writing-tests"]].scope is None
    assert not (legacy.coffer / "vault" / "reach.json").exists()


def test_every_secret_decrypts_from_its_file(legacy: LegacyHome) -> None:
    _migrate(legacy)
    store = EncryptedSecretStore(legacy.key, home=legacy.home)
    # When a value was last used here is machine-local, and carried as it was.
    assert store.last_used() == {"provider/anthropic": LAST_USED}
    for ref, value in legacy.secrets.items():
        assert store.get(ref) == value
    assert (legacy.coffer / "local/secret/proxy-token/claude_code.enc").is_file()
    assert (legacy.coffer / "vault/secret/secret/api%20key.enc").stat().st_mode & 0o777 == 0o600
    assert store.created_at("provider/anthropic") is not None
    head = _git(legacy.coffer / "vault", "ls-tree", "-r", "--name-only", "HEAD")
    assert "secret/" not in head, "ciphertext is committed only when the remote carries it"


def test_the_boundary_keeps_bindings_approvals_and_switches(legacy: LegacyHome) -> None:
    _migrate(legacy)
    boundary = FileBoundaryStore(legacy.home)
    assert [b.approval_id for b in boundary.bindings("provider/anthropic")] == ["ap-1"]
    assert boundary.get_approval("ap-1").status == "approved"  # type: ignore[union-attr]
    pending = boundary.pending_ciphertext("ap-2")
    assert pending is not None and Fernet(legacy.key).decrypt(pending) == b"new"
    assert boundary.get_setting("protection") == "on"


def test_state_documents_are_vault_files_keyed_by_the_owner_uid(legacy: LegacyHome) -> None:
    _migrate(legacy)
    state = legacy.coffer / "vault" / "state"
    prefs = json.loads((state / "mcp-preferences/github.json").read_text())
    assert prefs == {
        "server_uid": UIDS["github"],
        "format_version": 1,
        "disabled": {"tool": ["delete_repo"]},
    }
    peers = json.loads((state / "channel-peers/tg.json").read_text())
    assert peers["channel_uid"] == UIDS["tg"]
    assert [p["chat_id"] for p in peers["peers"]] == ["dm-1", "group-9"], "pairing order"
    engine = json.loads((state / "settings/internal-engine.json").read_text())
    assert engine["model"] == "anthropic/claude-sonnet"
    assert engine["curate_owner_machine_id"] == "machine-a"
    assert engine["upkeep"]["aggregate"] == {"enabled": True, "interval_s": 600}
    assert engine["upkeep"]["distil"]["enabled"] is False


@pytest.mark.acceptance(
    spec="vault-sync", scenario="machine-local files never reach the working tree"
)
def test_machine_local_settings_are_under_local(legacy: LegacyHome) -> None:
    _migrate(legacy)
    local = legacy.coffer / "local"
    retention = json.loads((local / "retention.json").read_text())
    assert retention["audit_log"]["retention_days"] == 90
    assert retention["audit_log"]["last_pruned_rows"] == 7
    status = json.loads((local / "skill-source-status.json").read_text())
    assert status[UIDS["deploy"]]["latest_commit"] == "fedcba9876543210"
    reach = json.loads((local / "tool-reach.json").read_text())
    assert reach == {UIDS["github"]: {"search": [UIDS["claude_code"]]}}
    remote = json.loads((local / "sync/remote.json").read_text())
    assert remote["url"] == "/nowhere/remote.git" and remote["interval_seconds"] == 900
    assert remote["include_secret"] is False


def test_derived_rows_are_copied_not_lost(legacy: LegacyHome) -> None:
    _migrate(legacy)
    with sqlite3.connect(legacy.coffer / "derived" / "derived.db") as conn:
        assert conn.execute("SELECT count(*) FROM mcp_capability_seen").fetchone() == (3,)
        assert conn.execute("SELECT status FROM mcp_server_health").fetchone() == ("ok",)
        assert conn.execute(
            "SELECT skill_uid, agent_uid, enabled FROM skill_agent_bindings"
        ).fetchall() == [(UIDS["writing-tests"], UIDS["claude_code"], 1)]


def test_every_tree_moved_to_its_class_with_its_bytes(legacy: LegacyHome) -> None:
    _migrate(legacy)
    moved = {
        "skills/coffer-guide/": "derived/skills/coffer-guide/",
        "knowledge/": "vault/knowledge/",
        "skills/": "vault/skills/",
        "memory/": "derived/memory/",
        "chat-media/": "content/chat-media/",
        "channel-media/": "content/channel-media/",
        "workspace/": "content/workspace/",
        "cache/agent/": "derived/cache/agent/",
    }
    for rel, data in legacy.files.items():
        prefix = next((p for p in moved if rel.startswith(p)), None)
        target = moved[prefix] + rel[len(prefix) :] if prefix else rel
        path = legacy.coffer / target
        assert path.is_file(), target
        if b"coffer_curated_at" not in data:
            assert path.read_bytes() == data, target
        if prefix:
            assert not (legacy.coffer / rel).exists()
    assert (legacy.coffer / "vault/skills/writing-tests/scripts/run.sh").stat().st_mode & 0o111


def test_history_rows_are_in_runs_db_keyed_to_uids(legacy: LegacyHome) -> None:
    _migrate(legacy)
    assert not legacy.db.exists()
    with sqlite3.connect(legacy.coffer / "runs.db") as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone() == ("0142",)
        assert conn.execute("SELECT id, resource_uid FROM audit_log ORDER BY id").fetchall() == [
            (1, UIDS["github"]),
            (2, UIDS["tg"]),
            (3, None),
            (4, None),
        ]
        assert conn.execute("SELECT count(*) FROM chat_messages").fetchone() == (2,)
        assert conn.execute(
            "SELECT resource_uid, active_conversation_id FROM channel_thread_conversations"
        ).fetchall() == [(UIDS["tg"], "conv-1")]
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "resources" not in tables and "secrets" not in tables


def test_the_knowledge_history_is_the_vaults_under_knowledge(legacy: LegacyHome) -> None:
    _migrate(legacy)
    vault = legacy.coffer / "vault"
    log = _git(
        vault, "log", "--format=%H%x00%an%x00%aI%x00%B%x01", "--", "knowledge/notes/team/on-call.md"
    ).split("\x01")
    commits = [c.strip("\n").split("\x00") for c in log if c.strip()]
    assert [parse_meta(c[3]).writer for c in commits] == ["daemon", "curation", "user"]
    assert commits[1][2] == "2026-08-02T10:30:00+02:00" and commits[1][1] == "Coffer (disk)"
    assert parse_meta(commits[0][3]).layout == "db -> 3"
    first = _git(vault, "show", f"{commits[2][0]}:knowledge/notes/team/on-call.md")
    assert "First draft." in first
    assert not (vault / "knowledge" / ".git").exists()
    assert (legacy.coffer / "pre-vault" / "knowledge.git" / "HEAD").is_file()


def test_one_daemon_commit_holds_the_whole_layout(legacy: LegacyHome) -> None:
    _migrate(legacy)
    vault = legacy.coffer / "vault"
    assert _git(vault, "status", "--porcelain") == ""
    meta = parse_meta(_git(vault, "log", "-1", "--format=%B"))
    assert (meta.writer, meta.operation, meta.layout) == ("daemon", "layout", "db -> 3")
    files = set(_git(vault, "show", "--name-only", "--format=", "HEAD").split())
    assert {
        "resources/mcp_server/github.json",
        "state/channel-peers/tg.json",
        "skills/writing-tests/SKILL.md",
        "knowledge/work/unsaved.md",
        "knowledge/work/.inbox/new.md",
    } <= files
    assert json.loads((vault / "manifest.json").read_text()) == {"schema_version": 3}


def test_stamps_are_stripped_and_settled_documents_recorded(legacy: LegacyHome) -> None:
    _migrate(legacy)
    knowledge = legacy.coffer / "vault" / "knowledge"
    settled = (knowledge / "notes/team/on-call.md").read_text()
    assert "coffer_curated_at" not in settled and "Primary on-call" in settled
    assert "coffer_curated_at" not in (knowledge / "work/runbook.md").read_text()
    curation = json.loads((legacy.coffer / "local" / "curation.json").read_text())["documents"]
    assert set(curation) == {"notes/team/on-call.md"}, "the edited runbook is still pending"


@pytest.mark.acceptance(
    spec="vault-storage", scenario="the report says carried secrets wait for approval"
)
def test_the_report_names_links_and_the_remote(legacy: LegacyHome) -> None:
    report = _migrate(legacy)
    notes = "\n".join(report.notices)
    assert ".claude/projects/p/memory" in notes
    assert "empty branch" in notes
    assert "sync/" not in notes
    # Carried secrets are not yet approved anywhere: say so, with a count only.
    assert "waits once for your approval in the Coffer app" in notes
    assert "secrets were carried over" in notes
    assert (legacy.home / ".claude/projects/p/memory").is_symlink()


@pytest.mark.acceptance(spec="vault-storage", scenario="the upgrade carries every item")
def test_the_check_expects_the_shape_the_upgrade_writes(legacy: LegacyHome) -> None:
    """The upgrade moves "which connection an agent runs on" onto the agent and
    drops ``wire_api`` and ``is_active``; the inventory it is checked against
    states the same shape, so those deliberate changes are not reported as
    differences."""
    with sqlite3.connect(legacy.db) as conn:
        for name, patch in (
            ("anthropic", {"is_active": True}),
            ("claude_code", {"wire_api": "responses"}),
        ):
            (raw,) = conn.execute(
                "SELECT config_json FROM resources WHERE name=?", (name,)
            ).fetchone()
            conn.execute(
                "UPDATE resources SET config_json=? WHERE name=?",
                (json.dumps({**json.loads(raw), **patch}), name),
            )
    inventory = take_inventory(legacy.home, upgrade_db=UPGRADE)
    report = _migrate(legacy)
    assert report.outcome == "migrated", report.lines()
    assert check(legacy.home, inventory) == []
    agent = parse_resource(
        (legacy.coffer / "local" / "resources" / "agent" / "claude_code.json").read_bytes()
    )
    assert agent.config["connection_uid"] == UIDS["anthropic"]
    assert "wire_api" not in agent.config
