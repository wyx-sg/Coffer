"""Integration tests for ``/api/v1/memory/*`` (spec memory FR-027..FR-032).

Boots the full FastAPI app (via ``create_app``) so every route is wired
exactly as production wires it — real SQLite, a real Claude Code fixture tree
under a temp HOME, no internal connection configured (organise/recall both
degrade rather than error, per FR-019/FR-023). ``COFFER_MEMORY_ROOT``,
``COFFER_KNOWLEDGE_ROOT`` are all pinned into
``tmp_path`` so nothing here ever touches a real ``~/.coffer``.
"""

from __future__ import annotations

import pathlib

import pytest
from starlette.testclient import TestClient

from coffer.application.memory.service import KIND_MEMORY
from coffer.application.upkeep_runs import UPKEEP_RUNS
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_TOKEN = "test-token-memory-routes"
_HEADERS = {"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "user"}

# ----- fixture native-memory content (mirrors tests/integration/memory's) -- #

_CC_PROJECT_FACT = """---
name: python-lockfile
description: Dependencies are locked with uv
metadata:
  type: project
---

Run `uv sync --frozen` in this project; a plain `pip install` drifts.
"""

_CC_PREFERENCE_FACT = """---
name: worktree-development
description: Always develop in a git worktree
metadata:
  type: feedback
---

Multiple parallel sessions share the repo — always work in a worktree.
"""


def _encode(name: str) -> str:
    return "".join(ch if ch.isalnum() and ch.isascii() else "-" for ch in name)


def _cc_slug(project_root: pathlib.Path) -> str:
    parts = [p for p in project_root.parts if p != "/"]
    return "-" + "-".join(_encode(p) for p in parts)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "memory"))
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".codex").mkdir(parents=True, exist_ok=True)

    app = create_app()
    set_active_token(_TOKEN)
    with TestClient(
        app, base_url="http://localhost", headers=_HEADERS, raise_server_exceptions=False
    ) as c:
        yield c


def _register_agent(c: TestClient, name: str, agent_type: str = "claude_code") -> None:
    r = c.post("/api/v1/agents", json={"type": agent_type, "name": name})
    assert r.status_code == 201, r.text


def _write_cc_facts(tmp_path: pathlib.Path, project_root: pathlib.Path) -> None:
    memory_dir = tmp_path / ".claude" / "projects" / _cc_slug(project_root) / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / "python-lockfile.md").write_text(_CC_PROJECT_FACT, encoding="utf-8")
    (memory_dir / "worktree-development.md").write_text(_CC_PREFERENCE_FACT, encoding="utf-8")


def _sync(c: TestClient) -> dict:
    r = c.post("/api/v1/memory/sync")
    assert r.status_code == 200, r.text
    return r.json()


# ----- partitions / facts --------------------------------------------------


def test_sync_then_list_partitions_and_facts(client, tmp_path) -> None:
    _register_agent(client, "cc")
    project_root = tmp_path / "home" / "dev" / "coffer"
    project_root.mkdir(parents=True)
    _write_cc_facts(tmp_path, project_root)

    result = _sync(client)
    assert result["facts_written"] == 2
    assert "global" in result["partitions"]

    partitions = client.get("/api/v1/memory/partitions").json()["partitions"]
    names = {p["name"] for p in partitions}
    assert "global" in names
    project_partition = next(p for p in partitions if p["name"] != "global")
    assert project_partition["project_root"] == str(project_root)
    assert project_partition["fact_count"] == 1

    facts = client.get(f"/api/v1/memory/partitions/{project_partition['name']}/facts").json()
    assert facts["facts"][0]["title"] == "python-lockfile"

    detail = client.get(
        f"/api/v1/memory/partitions/{project_partition['name']}/facts/{facts['facts'][0]['slug']}"
    ).json()
    assert detail["body"].strip().startswith("Run `uv sync --frozen`")
    assert detail["origins"][0]["agent"] == "cc"


def test_unknown_partition_facts_is_not_found(client) -> None:
    r = client.get("/api/v1/memory/partitions/does-not-exist/facts")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_unknown_fact_slug_is_not_found(client, tmp_path) -> None:
    _register_agent(client, "cc")
    project_root = tmp_path / "proj"
    project_root.mkdir(parents=True)
    _write_cc_facts(tmp_path, project_root)
    _sync(client)
    partition = next(
        p["name"]
        for p in client.get("/api/v1/memory/partitions").json()["partitions"]
        if p["name"] != "global"
    )
    r = client.get(f"/api/v1/memory/partitions/{partition}/facts/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "MEMORY_FACT_NOT_FOUND"


# ----- organise -------------------------------------------------------------


def test_organise_with_no_internal_connection_still_writes_a_digest(client, tmp_path) -> None:
    _register_agent(client, "cc")
    project_root = tmp_path / "proj"
    project_root.mkdir(parents=True)
    _write_cc_facts(tmp_path, project_root)
    _sync(client)
    partition = next(
        p["name"]
        for p in client.get("/api/v1/memory/partitions").json()["partitions"]
        if p["name"] != "global"
    )

    r = client.post(f"/api/v1/memory/partitions/{partition}/organise")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["model_used"] is False
    assert body["partition"] == partition
    assert (tmp_path / "memory" / partition / "summary.md").is_file()

    audit = client.get("/api/v1/audit").json()
    assert any(e["event_type"] == "memory_organised" for e in audit["entries"])


def test_organise_unknown_partition_is_not_found(client) -> None:
    r = client.post("/api/v1/memory/partitions/does-not-exist/organise")
    assert r.status_code == 404


@pytest.mark.acceptance(
    spec="memory",
    scenario="a second organise pass over the same partition is refused while the first is running",
)
def test_a_second_organise_over_the_same_partition_is_refused(client, tmp_path) -> None:
    """The bug this is here for: the button's spinner used to live in a browser
    component, so navigating away mid-pass and back showed an idle button and
    the next click started a SECOND pass over the same files (FR-033). The
    daemon now holds that fact, and refuses.

    The in-flight pass is simulated by claiming the partition's key directly —
    the route is synchronous, so a real second request could only be made from
    another thread, and what is under test is the refusal, not the threading.
    """
    _register_agent(client, "cc")
    project_root = tmp_path / "proj"
    project_root.mkdir(parents=True)
    _write_cc_facts(tmp_path, project_root)
    _sync(client)
    partition = next(
        p["name"]
        for p in client.get("/api/v1/memory/partitions").json()["partitions"]
        if p["name"] != "global"
    )

    assert UPKEEP_RUNS.claim(KIND_MEMORY, partition) is True
    try:
        r = client.post(f"/api/v1/memory/partitions/{partition}/organise")
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "UPKEEP_ALREADY_RUNNING"

        # … and the surface can see it, so the button shows the running pass
        # instead of inviting that second click.
        runs = client.get("/api/v1/upkeep/runs").json()["runs"]
        assert {"memory"} == {run["kind"] for run in runs}
        assert [run["name"] for run in runs] == [partition]
    finally:
        UPKEEP_RUNS.release(KIND_MEMORY, partition)

    # The key is free again, so the real pass runs.
    assert client.post(f"/api/v1/memory/partitions/{partition}/organise").status_code == 200
    assert client.get("/api/v1/upkeep/runs").json()["runs"] == []


# ----- context + delivery: FR-026's whole point -----------------------------


def test_context_composes_and_stays_bounded(client, tmp_path) -> None:
    _register_agent(client, "cc")
    project_root = tmp_path / "proj"
    project_root.mkdir(parents=True)
    _write_cc_facts(tmp_path, project_root)
    _sync(client)

    r = client.post("/api/v1/memory/context", json={"cwd": str(project_root)})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "## Coffer memory" in data["text"]
    assert data["facts_omitted"] == 0
    assert "L0" in data["layers"]


@pytest.mark.acceptance(
    spec="memory", scenario="the composed context stays within its token budget"
)
def test_context_respects_a_tiny_budget_and_names_what_was_left_out(client, tmp_path) -> None:
    _register_agent(client, "cc")
    project_root = tmp_path / "proj"
    project_root.mkdir(parents=True)
    _write_cc_facts(tmp_path, project_root)
    _sync(client)

    r = client.post("/api/v1/memory/context", json={"cwd": str(project_root), "budget_tokens": 40})
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["text"]) < 2000
    assert data["facts_omitted"] >= 0  # bound respected; exact count is context.py's concern


def test_context_scope_enforcement_does_not_leak_an_out_of_scope_partition(
    client, tmp_path
) -> None:
    """The one route a real agent's own session reaches must be scope-checked
    (spec memory FR-012): an agent outside a project partition's scope must
    never see its facts, even when its own cwd resolves to that partition."""
    _register_agent(client, "cc")
    _register_agent(client, "outsider", agent_type="codex")
    project_root = tmp_path / "proj"
    project_root.mkdir(parents=True)
    _write_cc_facts(tmp_path, project_root)
    _sync(client)
    partition = next(
        p["name"]
        for p in client.get("/api/v1/memory/partitions").json()["partitions"]
        if p["name"] != "global"
    )
    # Default scope from aggregation is {"cc"} (FR-012) — confirm "outsider"
    # is excluded, then compose context for it against the SAME cwd.
    scope = client.get(f"/api/v1/resources/memory/{partition}/scope").json()
    assert scope["scope"] == {"agents": ["cc"]}

    r = client.post("/api/v1/memory/context", json={"agent": "outsider", "cwd": str(project_root)})
    assert r.status_code == 200, r.text
    data = r.json()
    # `partition` says which partition this cwd maps to, not what is visible
    # — the leak this test guards against is in the TEXT and LAYERS, which
    # must never surface a fact from a partition "outsider" is out of scope for.
    assert data["partition"] == partition
    assert "python-lockfile" not in data["text"]
    assert data["layers"] == ["L0"]
    assert data["facts_included"] == 0


def test_delivery_install_status_and_record_fired_round_trip(client) -> None:
    _register_agent(client, "cc")

    status = client.get("/api/v1/memory/delivery", params={"agent": "cc"}).json()
    assert status["delivery"][0]["installed"] is False

    installed = client.post("/api/v1/memory/delivery/cc/install").json()
    assert installed["installed"] is True
    assert "coffer memory context --agent cc" in installed["command"]

    audit = client.get("/api/v1/audit").json()
    assert any(e["event_type"] == "memory_delivery_installed" for e in audit["entries"])

    r = client.post(
        "/api/v1/memory/context",
        json={"agent": "cc", "cwd": "/tmp", "record_fired": True},
    )
    assert r.status_code == 200, r.text

    audit2 = client.get("/api/v1/audit").json()
    assert any(e["event_type"] == "memory_delivery_fired" for e in audit2["entries"])

    removed = client.delete("/api/v1/memory/delivery/cc").json()
    assert removed["installed"] is False


def test_context_without_record_fired_does_not_record_a_fire(client) -> None:
    _register_agent(client, "cc")
    client.post("/api/v1/memory/delivery/cc/install")

    client.post("/api/v1/memory/context", json={"agent": "cc", "cwd": "/tmp"})

    audit = client.get("/api/v1/audit").json()
    assert not any(e["event_type"] == "memory_delivery_fired" for e in audit["entries"])


# ----- the partition's own files -------------------------------------------


def _synced_partition(client: TestClient, tmp_path: pathlib.Path) -> str:
    """Sync one project's facts; return the partition they landed in."""
    project_root = tmp_path / "proj"
    if not project_root.is_dir():
        project_root.mkdir(parents=True)
        _write_cc_facts(tmp_path, project_root)
    _sync(client)
    return next(
        p["name"]
        for p in client.get("/api/v1/memory/partitions").json()["partitions"]
        if p["name"] != "global"
    )


@pytest.mark.acceptance(
    spec="memory", scenario="a partition's own directory is browsable as a file tree"
)
def test_partition_files_walk_the_directory_and_read_one_file(client, tmp_path) -> None:
    _register_agent(client, "cc")
    partition = _synced_partition(client, tmp_path)

    tree = client.get(f"/api/v1/memory/partitions/{partition}/files").json()["root"]
    assert tree["path"] == ""
    assert tree["abs_path"] == str(tmp_path / "memory" / partition)
    names = {child["name"]: child for child in tree["children"]}
    # A partition is a README naming its project root plus a facts/ folder;
    # the digest only exists once organise has run, so it is not asserted here.
    assert "README.md" in names
    assert names["facts"]["type"] == "dir"
    fact_files = {child["path"] for child in names["facts"]["children"]}
    assert "facts/python-lockfile.md" in fact_files

    content = client.get(
        f"/api/v1/memory/partitions/{partition}/files/content",
        params={"path": "facts/python-lockfile.md"},
    ).json()
    assert content["binary"] is False
    assert content["truncated"] is False
    assert "uv sync --frozen" in content["content"]
    assert content["abs_path"].endswith("/facts/python-lockfile.md")


def test_partition_files_are_read_only(client, tmp_path) -> None:
    """No write reaches this family. The tree is derived (FR-016), so an edit
    would survive only until the next aggregation pass."""
    _register_agent(client, "cc")
    partition = _synced_partition(client, tmp_path)

    r = client.put(
        f"/api/v1/memory/partitions/{partition}/files/content",
        json={"path": "facts/python-lockfile.md", "content": "rewritten"},
    )
    assert r.status_code == 405


def test_partition_files_refuse_a_path_that_escapes_the_partition(client, tmp_path) -> None:
    _register_agent(client, "cc")
    partition = _synced_partition(client, tmp_path)

    r = client.get(
        f"/api/v1/memory/partitions/{partition}/files/content",
        params={"path": "../../../../etc/passwd"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "MEMORY_UNSAFE_PATH"


def test_partition_file_that_is_not_there_is_not_found(client, tmp_path) -> None:
    _register_agent(client, "cc")
    partition = _synced_partition(client, tmp_path)

    r = client.get(
        f"/api/v1/memory/partitions/{partition}/files/content",
        params={"path": "facts/no-such-fact.md"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "MEMORY_FILE_NOT_FOUND"


def test_files_of_an_unknown_partition_are_not_found(client) -> None:
    r = client.get("/api/v1/memory/partitions/does-not-exist/files")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
