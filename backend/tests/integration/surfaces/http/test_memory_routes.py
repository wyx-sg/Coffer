"""The memory hub through the daemon: the Memory page's reads and edits, a tidy
as one commit, the hook in each agent, and the cleanup of an older build's
copies (spec memory).

Each test boots the full app under its own ``HOME`` with every feature on in
``daemon-config.json``, so the vault, the agents' folders and the hub are all
under ``tmp_path``.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import time
from collections.abc import Iterator

import pytest
from starlette.testclient import TestClient

from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.memory.legacy import BLOCK_BEGIN, BLOCK_END
from coffer.infrastructure.vault.instance import vault_writer
from coffer.surfaces.http import feature_dependencies
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from tests.support.features import enable_all_in_config

_TOKEN = "test-token-memory"
_HEADERS = {"X-Coffer-Token": _TOKEN}
_PROJECT = "github.com-acme-pay"


@pytest.fixture
def home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[pathlib.Path]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.delenv(daemon_config.FEATURES_ENV, raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    enable_all_in_config()
    (tmp_path / ".coffer").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude").mkdir()
    prior = feature_dependencies._feature_service
    yield tmp_path
    feature_dependencies._feature_service = prior


def _client() -> TestClient:
    set_active_token(_TOKEN)
    return TestClient(create_app(), base_url="http://localhost", headers=_HEADERS)


def _hub() -> pathlib.Path:
    return vault_writer().repo.root / "memory" / "projects"


def _write(name: str, body: str, *, title: str = "Testing", kind: str = "feedback") -> pathlib.Path:
    path = _hub() / _PROJECT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\ntitle: {title}\ntype: {kind}\nupdated: 2026-11-19\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return path


def _history(c: TestClient) -> list[dict[str, object]]:
    r = c.get("/api/v1/vault/history", params={"path": "memory/"})
    assert r.status_code == 200, r.text
    return list(r.json()["versions"])


@pytest.mark.acceptance(spec="memory", scenario="the Memory page lists projects and their topics")
def test_the_memory_page_lists_projects_topics_and_problems(home: pathlib.Path) -> None:
    with _client() as c:
        _write("testing.md", "Run the unit tier before pushing.")
        (_hub() / _PROJECT / "loose.md").write_text("no frontmatter\n", encoding="utf-8")

        state = c.get("/api/v1/memory").json()
        assert state["folder_path"].endswith("memory/projects")
        assert state["projects"] == [
            {"folder": _PROJECT, "topics": 2, "problems": 1, "updated": "2026-11-19"}
        ]
        assert state["tidy_running"] is False
        assert "coffer memory tidy-start" in state["tidy_handoff"]["prompt"]

        topics = c.get(f"/api/v1/memory/projects/{_PROJECT}").json()["topics"]
        assert [(t["name"], bool(t["problems"])) for t in topics] == [
            ("loose.md", True),
            ("testing.md", False),
        ]
        assert c.get(f"/api/v1/memory/projects/{_PROJECT}/gone.md").status_code == 404
        assert c.get(f"/api/v1/memory/projects/{_PROJECT}/..").status_code in {400, 404, 422}


@pytest.mark.acceptance(spec="memory", scenario="an edit from the Memory page refuses a stale file")
def test_an_edit_is_one_commit_and_refuses_a_stale_file(home: pathlib.Path) -> None:
    with _client() as c:
        _write("testing.md", "Old line.")
        url = f"/api/v1/memory/projects/{_PROJECT}/testing.md"
        read = c.get(url).json()
        text = read["text"].replace("Old line.", "New line.")

        saved = c.put(url, json={"text": text, "expected": read["digest"]})
        assert saved.status_code == 200, saved.text
        assert saved.json()["body"] == "New line."
        assert (
            c.put(url, json={"text": text, "expected": read["digest"]}).json()["error"]["code"]
            == "MEMORY_FILE_STALE"
        )

        gone = c.delete(url, params={"expected": saved.json()["digest"]})
        assert gone.status_code == 204, gone.text
        assert not (_hub() / _PROJECT / "testing.md").exists()


@pytest.mark.acceptance(spec="memory", scenario="a tidy's edits land as one commit with its report")
def test_a_tidys_edits_land_as_one_commit(home: pathlib.Path) -> None:
    with _client() as c:
        _write("a.md", "One.")
        _write("b.md", "Two.", title="Other")
        vault_writer().settle()
        before = _history(c)

        assert c.post("/api/v1/memory/tidy/start").json()["running"] is True
        (_hub() / _PROJECT / "b.md").unlink()
        _write("a.md", "One.\nTwo.")
        # Nothing commits a paused hub's edits until the tidy finishes.
        vault_writer().settle()
        assert len(_history(c)) == len(before)

        done = c.post("/api/v1/memory/tidy/finish", json={"summary": "Merged b into a."})
        assert done.status_code == 200, done.text
        assert done.json()["version"]
        after = _history(c)
        assert len(after) == len(before) + 1
        assert c.get("/api/v1/memory").json()["tidy_running"] is False
        # Finishing again with nothing open commits nothing.
        assert c.post("/api/v1/memory/tidy/finish", json={}).json()["version"] is None


def _settings(home: pathlib.Path) -> dict[str, object]:
    path = home / ".claude" / "settings.json"
    return json.loads(path.read_text()) if path.is_file() else {}  # type: ignore[no-any-return]


def _commands(home: pathlib.Path) -> list[str]:
    hooks = _settings(home).get("hooks") or {}
    return [
        h["command"]
        for g in hooks.get("SessionStart", [])  # type: ignore[union-attr]
        for h in g["hooks"]
    ]


@pytest.mark.acceptance(
    spec="memory", scenario="the hook is installed while memory is on and removed when it is off"
)
def test_the_hook_follows_the_memory_switch(home: pathlib.Path) -> None:
    (home / ".claude" / "settings.json").write_text(json.dumps({"theme": "dark"}))
    with _client() as c:
        r = c.post("/api/v1/agents", json={"type": "claude_code"})
        assert r.status_code == 201, r.text
        # The registration's hint brings the next pass forward.
        deadline = time.monotonic() + 10
        while not _commands(home) and time.monotonic() < deadline:
            time.sleep(0.05)
        commands = _commands(home)
        assert len(commands) == 1 and commands[0].endswith("memory session-start")
        assert _settings(home)["theme"] == "dark"

        assert c.put("/api/v1/daemon/features/memory", json={"enabled": False}).status_code == 200
        assert _settings(home) == {"theme": "dark"}


@pytest.mark.acceptance(
    spec="memory", scenario="upgrading removes the old copies from the agents' own memory"
)
def test_upgrading_removes_the_old_copies(home: pathlib.Path) -> None:
    index = home / ".claude" / "projects" / "-work-pay" / "memory" / "MEMORY.md"
    index.parent.mkdir(parents=True)
    index.write_text(f"- mine\n\n{BLOCK_BEGIN}\n- copied\n{BLOCK_END}\n", encoding="utf-8")
    only_ours = home / ".claude" / "projects" / "-work-x" / "memory" / "MEMORY.md"
    only_ours.parent.mkdir(parents=True)
    only_ours.write_text(f"{BLOCK_BEGIN}\n- copied\n{BLOCK_END}\n", encoding="utf-8")
    codex = home / ".codex" / "memories" / "extensions" / "coffer"
    codex.mkdir(parents=True)
    (codex / "x.md").write_text("copied", encoding="utf-8")
    (home / ".codex" / "memories" / "mine.md").write_text("mine", encoding="utf-8")
    with _client() as c:
        assert c.post("/api/v1/agents", json={"type": "claude_code"}).status_code == 201
        assert c.post("/api/v1/agents", json={"type": "codex"}).status_code == 201
    # The next start cleans every registered agent's folder.
    with _client():
        pass
    assert index.read_text(encoding="utf-8") == "- mine\n"
    assert not only_ours.exists()
    assert not codex.exists()
    assert (home / ".codex" / "memories" / "mine.md").read_text() == "mine"


@pytest.mark.acceptance(spec="memory", scenario="an older build's entries become topics")
def test_an_older_builds_entries_become_topics(home: pathlib.Path) -> None:
    with _client():
        old = _hub() / _PROJECT / "m-1.md"
        old.parent.mkdir(parents=True, exist_ok=True)
        old.write_text(
            "---\nid: m-1\ntitle: Answer in Chinese\ntype: feedback\n"
            "origin:\n  agent: claude_code\nupdated_at: 2026-10-01T10:00:00Z\n---\n\n"
            "Reply in Chinese.\n",
            encoding="utf-8",
        )
        vault_writer().settle()
    with _client() as c:
        topic = c.get(f"/api/v1/memory/projects/{_PROJECT}/m-1.md").json()
        assert topic["problems"] == []
        assert (topic["title"], topic["type"], topic["updated"]) == (
            "Answer in Chinese",
            "feedback",
            "2026-10-01",
        )
        assert "origin" not in topic["text"] and topic["body"] == "Reply in Chinese."


@pytest.mark.acceptance(spec="memory", scenario="a session outside a repository is handed nothing")
def test_the_context_follows_the_sessions_repository(
    home: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    repo = tmp_path / "work" / "pay"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "remote", "add", "origin", "git@github.com:acme/pay.git"],
        check=True,
    )
    with _client() as c:
        _write("testing.md", "Run the unit tier before pushing.")
        text = c.get("/api/v1/memory/context", params={"cwd": str(repo)}).json()["text"]
        assert '<coffer-memory project="github.com/acme/pay">' in text
        assert "Run the unit tier before pushing." in text
        outside = tmp_path / "loose"
        outside.mkdir()
        assert c.get("/api/v1/memory/context", params={"cwd": str(outside)}).json()["text"] == ""
