"""HTTP coverage for instructions delivery (spec 004 item 1).

Master hub document at /api/v1/instructions and per-agent delivery at
/api/v1/agents/{name}/instructions[/adopt].
"""

from __future__ import annotations

import pathlib

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-instr"

# spec-007 memory-projection markers (owned by the memory feature) — used to
# prove the two managed blocks coexist.
MEM_START = "<!-- coffer:memory:start (managed, do not edit) -->"
MEM_END = "<!-- coffer:memory:end -->"
INSTR_START = "<!-- coffer:instructions:start (managed, do not edit) -->"
INSTR_END = "<!-- coffer:instructions:end -->"


def _app(tmp_path: pathlib.Path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    return create_app()


def _client(app) -> TestClient:
    set_active_token(TOKEN)
    return TestClient(app, headers={"X-Coffer-Token": TOKEN})


def _register(c: TestClient, agent_type: str, subpath: str, tmp_path: pathlib.Path) -> None:
    """Register an agent whose config dir exists (so registration is accepted)."""
    (tmp_path / subpath).mkdir(parents=True, exist_ok=True)
    r = c.post("/api/v1/agents", json={"type": agent_type})
    assert r.status_code == 201, r.text


def _claude_md(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / ".claude" / "CLAUDE.md"


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="read and write the master instructions"
)
def test_master_read_write_and_stale_409(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59700)
    with _client(app) as c:
        # Empty on a fresh install; the read never creates the file.
        r = c.get("/api/v1/instructions")
        assert r.status_code == 200, r.text
        assert r.json()["content"] == ""
        assert not (tmp_path / ".coffer" / "instructions" / "AGENTS.md").exists()

        # Write, then it reads back with a fresh fingerprint.
        w = c.put("/api/v1/instructions", json={"content": "house rules\n"})
        assert w.status_code == 200, w.text
        fp = w.json()["fingerprint"]
        assert fp
        assert c.get("/api/v1/instructions").json()["content"] == "house rules\n"

        # A write carrying an outdated fingerprint is rejected (409).
        stale = c.put(
            "/api/v1/instructions",
            json={"content": "other", "expected_fingerprint": "deadbeef"},
        )
        assert stale.status_code == 409, stale.text
        assert stale.json()["error"]["code"] == "INSTRUCTIONS_MASTER_STALE"
        # The current fingerprint is accepted.
        ok = c.put(
            "/api/v1/instructions",
            json={"content": "v2\n", "expected_fingerprint": fp},
        )
        assert ok.status_code == 200, ok.text


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="deliver master instructions to an agent"
)
def test_deliver_writes_block_preserving_existing_content(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59701)
    with _client(app) as c:
        _register(c, "claude_code", ".claude", tmp_path)
        _claude_md(tmp_path).write_text("# My own notes\n", encoding="utf-8")
        c.put("/api/v1/instructions", json={"content": "MASTER BODY\n"})

        r = c.post("/api/v1/agents/claude-code/instructions")
        assert r.status_code == 200, r.text
        assert r.json() == {"delivered": True, "in_sync": True}

        text = _claude_md(tmp_path).read_text(encoding="utf-8")
        assert INSTR_START in text and INSTR_END in text
        assert "MASTER BODY" in text
        # Pre-existing content outside the block is preserved.
        assert "# My own notes" in text
        # A .bak of the prior content was kept.
        assert (tmp_path / ".claude" / "CLAUDE.md.bak").exists()


@pytest.mark.acceptance(
    spec="004-agent-registry",
    scenario="instructions delivery is idempotent and re-delivers on master change",
)
def test_redeliver_updates_block_in_place(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59702)
    with _client(app) as c:
        _register(c, "claude_code", ".claude", tmp_path)
        c.put("/api/v1/instructions", json={"content": "v1\n"})
        c.post("/api/v1/agents/claude-code/instructions")
        c.put("/api/v1/instructions", json={"content": "v2-updated\n"})
        c.post("/api/v1/agents/claude-code/instructions")

        text = _claude_md(tmp_path).read_text(encoding="utf-8")
        assert text.count(INSTR_START) == 1  # never duplicated
        assert "v2-updated" in text and "v1" not in text


@pytest.mark.acceptance(
    spec="004-agent-registry",
    scenario="instructions delivery coexists with the memory-projection block",
)
def test_coexists_with_memory_block(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59703)
    with _client(app) as c:
        _register(c, "claude_code", ".claude", tmp_path)
        # Seed a spec-007 memory block.
        _claude_md(tmp_path).write_text(
            f"{MEM_START}\n- a remembered fact\n{MEM_END}\n", encoding="utf-8"
        )
        c.put("/api/v1/instructions", json={"content": "instr body\n"})
        c.post("/api/v1/agents/claude-code/instructions")

        text = _claude_md(tmp_path).read_text(encoding="utf-8")
        assert MEM_START in text and "a remembered fact" in text  # memory untouched
        assert INSTR_START in text and "instr body" in text

        # Removing instructions leaves the memory block intact.
        c.delete("/api/v1/agents/claude-code/instructions")
        text2 = _claude_md(tmp_path).read_text(encoding="utf-8")
        assert MEM_START in text2 and "a remembered fact" in text2
        assert INSTR_START not in text2


@pytest.mark.acceptance(spec="004-agent-registry", scenario="report instructions delivery status")
def test_status_absent_in_sync_and_drifted(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59704)
    with _client(app) as c:
        _register(c, "claude_code", ".claude", tmp_path)
        c.put("/api/v1/instructions", json={"content": "the master\n"})

        # Absent before delivery.
        assert c.get("/api/v1/agents/claude-code/instructions").json() == {
            "delivered": False,
            "in_sync": False,
        }
        # In sync right after delivery.
        c.post("/api/v1/agents/claude-code/instructions")
        assert c.get("/api/v1/agents/claude-code/instructions").json() == {
            "delivered": True,
            "in_sync": True,
        }
        # Drifted once the master changes (block not yet re-delivered).
        c.put("/api/v1/instructions", json={"content": "the master CHANGED\n"})
        body = c.get("/api/v1/agents/claude-code/instructions").json()
        assert body == {"delivered": True, "in_sync": False}


@pytest.mark.acceptance(spec="004-agent-registry", scenario="remove delivered instructions")
def test_remove_strips_block_and_is_idempotent(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59705)
    with _client(app) as c:
        _register(c, "claude_code", ".claude", tmp_path)
        _claude_md(tmp_path).write_text("keep me\n", encoding="utf-8")
        c.put("/api/v1/instructions", json={"content": "body\n"})
        c.post("/api/v1/agents/claude-code/instructions")

        r = c.delete("/api/v1/agents/claude-code/instructions")
        assert r.status_code == 200, r.text
        assert r.json() == {"delivered": False, "in_sync": False}
        text = _claude_md(tmp_path).read_text(encoding="utf-8")
        assert INSTR_START not in text and "keep me" in text

        # Removing again is a no-op success.
        again = c.delete("/api/v1/agents/claude-code/instructions")
        assert again.status_code == 200, again.text
        assert again.json()["delivered"] is False


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="adopt an agent's instructions into the master"
)
def test_adopt_block_then_whole_file(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59706)
    with _client(app) as c:
        _register(c, "claude_code", ".claude", tmp_path)

        # No block present → the whole file is adopted.
        _claude_md(tmp_path).write_text("whole-file instructions\n", encoding="utf-8")
        r = c.post("/api/v1/agents/claude-code/instructions/adopt")
        assert r.status_code == 200, r.text
        assert r.json()["content"] == "whole-file instructions\n"
        assert c.get("/api/v1/instructions").json()["content"] == "whole-file instructions\n"
        # The agent's own file is untouched by adoption.
        assert _claude_md(tmp_path).read_text(encoding="utf-8") == "whole-file instructions\n"

        # With a delivered block, the block body (not the surroundings) is adopted.
        c.put("/api/v1/instructions", json={"content": "from-master\n"})
        c.post("/api/v1/agents/claude-code/instructions")
        _claude_md(tmp_path).write_text(
            _claude_md(tmp_path)
            .read_text(encoding="utf-8")
            .replace("from-master", "edited-in-block"),
            encoding="utf-8",
        )
        c.post("/api/v1/agents/claude-code/instructions/adopt")
        assert c.get("/api/v1/instructions").json()["content"] == "edited-in-block"


@pytest.mark.acceptance(
    spec="004-agent-registry",
    scenario="reject instructions delivery for an agent without an instructions file",
)
def test_reject_for_agent_without_instructions_file(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59707)
    with _client(app) as c:
        _register(c, "openclaw", ".openclaw", tmp_path)
        for call in (
            lambda: c.get("/api/v1/agents/openclaw/instructions"),
            lambda: c.post("/api/v1/agents/openclaw/instructions"),
            lambda: c.post("/api/v1/agents/openclaw/instructions/adopt"),
        ):
            r = call()
            assert r.status_code == 422, r.text
            assert r.json()["error"]["code"] == "INSTRUCTIONS_UNSUPPORTED"
