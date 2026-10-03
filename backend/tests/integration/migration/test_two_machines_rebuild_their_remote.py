"""Two machines that synced on the previous build, upgraded one after the
other: the old remote is never converted — the first upgraded machine's vault
replaces it (the old history stays in git) — and the second joins the
replaced remote as new, and both end with every resource byte-identical and
nothing lost (plan q9, user rule "no remote conversion")."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

from coffer.application.sync.round_answers import choose_join
from coffer.application.sync.round_join import join, preview
from coffer.domain.sync.joins import JoinKind
from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.rounds import RoundStatus
from coffer.domain.sync.stops import Answer
from coffer.infrastructure.vault.migration.run import migrate
from tests.integration.sync_thin.machines import Machine, bare_remote

from .conftest import UPGRADE
from .legacy_home import AT, UIDS, LegacyHome, build_legacy_home

#: The bundle schema every build before the vault layout read, and refused
#: anything above (ADR every-vault-file-carries-its-format-version).
PREVIOUS_BUILD_SCHEMA = 2


def _old_layout_remote(tmp: Path) -> SyncRemote:
    """The previous build's sync tree: manifest schema 2, a document per uid."""
    remote = bare_remote(tmp / "old")
    work = tmp / "old-work"
    work.mkdir()
    files = {
        "manifest.json": json.dumps({"schema_version": 2}) + "\n",
        f"resources/mcp_server/{UIDS['github']}.yaml": "kind: mcp_server\nname: github\n",
        "machines/machine-a.yaml": "machine_id: machine-a\npointer: abc\n",
        "machines/machine-b.yaml": "machine_id: machine-b\npointer: abc\n",
        "state/channel-peers/tg.yaml": "peers: []\n",
    }
    for rel, text in files.items():
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_text(text)
    git = ["git", "-C", str(work), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "init", "-q", "-b", "main"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "layout 2"], check=True)
    subprocess.run([*git, "push", "-q", str(remote), "main"], check=True)
    return SyncRemote(url=str(remote))


def _home(tmp: Path, name: str, monkeypatch: pytest.MonkeyPatch) -> LegacyHome:
    home = tmp / name
    home.mkdir()
    (home / ".gitconfig").write_text("[user]\n\tname = t\n\temail = t@t\n")
    monkeypatch.setenv("HOME", str(home))
    return build_legacy_home(home)


def _resources(machine: Machine) -> dict[str, bytes]:
    root = machine.repo.root
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.glob("resources/*/*")}


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="two machines upgrade and keep syncing through the replaced remote",
)
def test_the_old_remote_is_replaced_then_the_second_machine_joins_as_new(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _old_layout_remote(tmp_path)
    a = _home(tmp_path, "a", monkeypatch)
    # Machine B has what B alone had written: its own version of one document,
    # a document A never saw, and a provider A does not have.
    b = _home(tmp_path, "b", monkeypatch)
    (b.coffer / "knowledge/work/runbook.md").write_text("B's runbook\n")
    (b.coffer / "knowledge/notes/b-only.md").write_text("only on B\n")
    with sqlite3.connect(b.db) as conn:
        conn.execute(
            "INSERT INTO resources (id, uid, kind, name, config_json, enabled, created_at,"
            " updated_at, rev) VALUES (40, ?, 'provider', 'b-only', ?, 1, ?, ?, 1)",
            ("b9" * 16, json.dumps({"protocol": "openai", "base_url": "https://x"}), AT, AT),
        )

    monkeypatch.setenv("HOME", str(a.home))
    migrate(a.home, upgrade_db=UPGRADE, build="test")
    mac = Machine(a.coffer, "A", old)
    old_tip = subprocess.run(
        ["git", "--git-dir", old.url, "rev-parse", "main"], capture_output=True, text=True
    ).stdout.strip()
    assert preview(mac.engine, old, None).kind is JoinKind.REPLACE
    replaced = join(mac.engine, old, None)
    assert replaced.status is RoundStatus.PUSHED and replaced.join == "replace"
    shown = subprocess.run(
        ["git", "--git-dir", old.url, "show", "main:manifest.json"], capture_output=True, text=True
    ).stdout
    # Machine B, still on the previous build, reads only this number and
    # refuses the replaced remote rather than misreading it.
    assert json.loads(shown)["schema_version"] > PREVIOUS_BUILD_SCHEMA
    assert (
        subprocess.run(
            ["git", "--git-dir", old.url, "merge-base", "--is-ancestor", old_tip, "main"],
            check=False,
        ).returncode
        == 0
    ), "the old history stays in the remote"
    new = old
    mac = Machine(a.coffer, "A", new)

    monkeypatch.setenv("HOME", str(b.home))
    migrate(b.home, upgrade_db=UPGRADE, build="test")
    mini = Machine(b.coffer, "B", new)
    seen = preview(mini.engine, new, None)
    assert seen.kind is JoinKind.NEW
    assert seen.differ == ("knowledge/work/runbook.md",), "every resource is byte-identical"
    assert join(mini.engine, new, None).status is RoundStatus.JOINED
    choose_join(mini.engine, "knowledge/work/runbook.md", Answer.MINE, actor="user")
    mini.round()
    mac.round()
    mini.round()

    assert _resources(mac) == _resources(mini)
    assert "resources/provider/b-only.json" in _resources(mac)
    for machine in (mac, mini):
        assert machine.disk("knowledge/notes/b-only.md") == b"only on B\n"
        assert machine.disk("knowledge/work/runbook.md") == b"B's runbook\n"
        assert machine.disk("knowledge/notes/team/on-call.md") is not None
        assert machine.disk("skills/writing-tests/SKILL.md") is not None
    mac.round()

    def content(machine: Machine) -> dict[str, str]:
        tree = machine.repo.tree("HEAD")
        return {p: b for p, b in tree.items() if not p.startswith("machines/")}

    assert content(mac) == content(mini), "both converged on one vault"
