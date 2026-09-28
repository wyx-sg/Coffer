"""``coffer scan`` / ``adopt`` / ``discard`` over the real app.

One row of each kind — a detected agent, a hand-placed skill folder, a direct
MCP entry in an agent's own config — is listed, adopted by the ref the scan
printed, and (skill, mcp) discarded; a detected agent refuses discard.
"""

from __future__ import annotations

import json
import pathlib
import textwrap
from collections.abc import Iterator
from typing import Any

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

from coffer.surfaces.cli.main import app as cli_app

from ._real_app import audit, boot, extract_json

_runner = CliRunner()


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter

    keyring: dict[str, str] = {}
    monkeypatch.setattr(KeyringAdapter, "get", lambda self, ref: keyring.get(ref))
    monkeypatch.setattr(
        KeyringAdapter, "set", lambda self, ref, value: keyring.__setitem__(ref, value)
    )
    monkeypatch.setattr(KeyringAdapter, "delete", lambda self, ref: keyring.pop(ref, None))
    (tmp_path / ".claude").mkdir()
    yield from boot(tmp_path, monkeypatch)


def _run(*args: str, stdin: str | None = None) -> Any:
    return _runner.invoke(cli_app, list(args), input=stdin, env={"COLUMNS": "250"})


def _rows(*args: str) -> list[dict[str, Any]]:
    r = _run("scan", *args, "--json")
    assert r.exit_code == 0, r.output
    return list(extract_json(r.output)["rows"])


def _claude_code(daemon: TestClient) -> str:
    r = daemon.post("/agents", json={"type": "claude_code"})
    assert r.status_code == 201, r.text
    return str(r.json()["name"])


def _skill_folder(parent: pathlib.Path, name: str) -> pathlib.Path:
    folder = parent / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        textwrap.dedent(
            f"""\
            ---
            name: {name}
            description: A test skill named {name}.
            ---

            body
            """
        ),
        encoding="utf-8",
    )
    return folder


def _mcp_entries(home: pathlib.Path) -> pathlib.Path:
    path = home / ".claude.json"
    path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "github": {"command": "cat", "args": []},
                    "coffer": {"command": "coffer-mcp-shim", "args": ["--agent-uid", "x"]},
                }
            }
        ),
        encoding="utf-8",
    )
    return path


# --- agent rows -------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="agent-registry", scenario="adopt a discovered agent from the command line"
)
@pytest.mark.acceptance(
    spec="resource-framework", scenario="an unknown or undiscardable row is refused"
)
def test_a_detected_agent_is_adopted_and_never_discarded(
    daemon: TestClient, tmp_path: pathlib.Path
) -> None:
    (tmp_path / ".codex").mkdir()

    rows = [r for r in _rows() if r["kind"] == "agent"]
    codex = next(r for r in rows if r["ref"] == "codex")
    assert daemon.get("/resources", params={"kind": "agent"}).json()["resources"] == []

    refused = _run("discard", "agent", "codex")
    assert refused.exit_code != 0 and "cannot be discarded" in refused.output
    unknown = _run("adopt", "skill", "no-such-ref")
    assert unknown.exit_code != 0 and "names no skill row" in unknown.output
    assert daemon.get("/resources", params={"kind": "agent"}).json()["resources"] == []

    adopted = _run("adopt", "agent", "codex")
    assert adopted.exit_code == 0, adopted.output
    [agent] = daemon.get("/resources", params={"kind": "agent"}).json()["resources"]
    assert agent["name"] == codex["suggested_name"]
    assert daemon.get(f"/agents/{agent['uid']}").json()["config_dir"] == codex["config_dir"]
    assert any(e["resource_name"] == agent["name"] for e in audit(daemon, "resource_created"))
    assert "codex" not in [r["ref"] for r in _rows() if r["kind"] == "agent"]


# --- skill rows ------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="skill-manager", scenario="the command-line scan lists unmanaged skills as skill rows"
)
def test_scan_lists_a_hand_placed_skill_and_not_a_managed_link(
    daemon: TestClient, tmp_path: pathlib.Path
) -> None:
    agent = _claude_code(daemon)
    managed = _skill_folder(tmp_path / "src", "managed-one")
    assert _run("skill", "import", str(managed)).exit_code == 0
    skills_dir = tmp_path / ".claude" / "skills"
    assert (skills_dir / "managed-one").is_symlink() or (skills_dir / "managed-one").exists()
    loose = _skill_folder(skills_dir, "loose-one")

    rows = _rows("--agent", agent)
    skill_rows = [r for r in rows if r["kind"] == "skill"]
    assert [(r["ref"], r["valid"]) for r in skill_rows] == [(str(loose), True)]
    assert all(r["agent"] == agent for r in rows) and not [r for r in rows if r["kind"] == "agent"]


@pytest.mark.acceptance(
    spec="skill-manager", scenario="manage unmanaged skills with scan, adopt and discard"
)
@pytest.mark.acceptance(spec="resource-framework", scenario="a scan row is adopted by its ref")
def test_scan_adopt_and_discard_unmanaged_skills(
    daemon: TestClient, tmp_path: pathlib.Path
) -> None:
    agent = _claude_code(daemon)
    skills_dir = tmp_path / ".claude" / "skills"
    keep = _skill_folder(skills_dir, "keep-me")
    junk = _skill_folder(skills_dir, "junk-me")

    refs = {r["ref"] for r in _rows("--agent", agent) if r["kind"] == "skill"}
    assert refs == {str(keep), str(junk)}

    adopted = _run("adopt", "skill", str(keep))
    assert adopted.exit_code == 0, adopted.output
    assert "adopted: skill keep-me" in adopted.output
    assert daemon.get("/resources", params={"kind": "skill", "name": "keep-me"}).json()["resources"]
    assert audit(daemon, "resource_created")

    declined = _run("discard", "skill", str(junk), stdin="n\n")
    assert declined.exit_code == 1 and junk.exists()
    discarded = _run("discard", "skill", str(junk), stdin="y\n")
    assert discarded.exit_code == 0, discarded.output
    assert not junk.exists()
    assert [r for r in _rows("--agent", agent) if r["kind"] == "skill"] == []


# --- mcp rows ------------------------------------------------------------------------------


@pytest.mark.acceptance(spec="agent-registry", scenario="scan lists an agent's direct MCP entries")
def test_scan_lists_direct_mcp_entries_but_not_coffers_own(
    daemon: TestClient, tmp_path: pathlib.Path
) -> None:
    agent = _claude_code(daemon)
    _mcp_entries(tmp_path)
    table = _run("scan", "--agent", agent)
    assert table.exit_code == 0, table.output
    assert f"{agent}:github" in table.output
    refs = [r["ref"] for r in _rows("--agent", agent) if r["kind"] == "mcp"]
    assert refs == [f"{agent}:github"]


@pytest.mark.acceptance(
    spec="agent-registry", scenario="discard a direct MCP entry from the command line"
)
def test_discard_a_direct_mcp_entry(daemon: TestClient, tmp_path: pathlib.Path) -> None:
    agent = _claude_code(daemon)
    source = _mcp_entries(tmp_path)

    removed = _run("discard", "mcp", f"{agent}:github", "--yes")
    assert removed.exit_code == 0, removed.output
    servers = json.loads(source.read_text())["mcpServers"]
    assert "github" not in servers and "coffer" in servers
    assert list(tmp_path.glob(".claude.json*.bak")) or list(tmp_path.glob("*.bak"))
    assert audit(daemon, "agent_mcp_entry_removed")

    before = source.read_text()
    refused = _run("discard", "mcp", f"{agent}:coffer", "--yes")
    assert refused.exit_code != 0
    assert source.read_text() == before


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="adopt a direct MCP entry under a new name from the command line",
)
def test_adopt_a_direct_mcp_entry_under_a_new_name(
    daemon: TestClient, tmp_path: pathlib.Path
) -> None:
    agent = _claude_code(daemon)
    source = _mcp_entries(tmp_path)
    existing = daemon.post(
        "/resources",
        json={
            "kind": "mcp_server",
            "name": "github",
            "config": {"transport": {"type": "stdio", "command": "cat", "args": []}},
        },
    )
    assert existing.status_code == 201, existing.text

    clash = _run("adopt", "mcp", f"{agent}:github")
    assert clash.exit_code == 5, clash.output

    adopted = _run("adopt", "mcp", f"{agent}:github", "--name", "github-work")
    assert adopted.exit_code == 0, adopted.output
    assert daemon.get("/resources", params={"kind": "mcp_server", "name": "github-work"}).json()[
        "resources"
    ]
    assert "github" not in json.loads(source.read_text())["mcpServers"]
    assert audit(daemon, "agent_mcp_entry_adopted")
    assert _run("adopt", "mcp", "no-colon").exit_code == 2
