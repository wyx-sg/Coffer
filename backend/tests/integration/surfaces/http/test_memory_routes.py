"""Integration tests for ``/api/v1/memory/*`` (spec memory FR-036..FR-038).

Boots the full FastAPI app (via ``create_app``) so every route is wired
exactly as production wires it — real SQLite, a real Claude Code fixture tree
under a temp HOME, and **a real git repository**, because a partition is keyed
on a repository now and a plain directory deliberately makes none (FR-014,
FR-015). No internal connection is configured, so the distil pass takes its
mechanical path (FR-024) — which is what makes "sync, distil, then read" a
deterministic three lines here rather than a model call.

What this tier is for, as opposed to the unit and ``tests/integration/memory``
tiers that already cover the layer's behaviour: the **wire**. Field names and
error codes, the status codes a client branches on, and the two payload
promises FR-028/FR-030 make that a client can only check by reading the
response — that ``POST /context`` carries a line for *every* note plus the
absolute ``notes/`` path, and that under a binding ceiling it is ``global``
that loses lines while the repository the session is open in keeps its own.

Every route on this family is addressed by **uid**, so the helpers below take
the label a fixture created and look the uid up once — the same one round trip
the CLI makes through ``_resolve``. The tests keep naming partitions ``coffer``
and ``global`` because that is what a reader recognises; what travels on the
wire is the identity.

``COFFER_MEMORY_ROOT``, ``COFFER_KNOWLEDGE_ROOT`` and ``HOME`` are all pinned
into ``tmp_path``, so nothing here ever reaches a real ``~/.coffer`` or a real
``~/.claude``.
"""

from __future__ import annotations

import pathlib
import shutil

import pytest
from starlette.testclient import TestClient

from coffer.application.memory.service import KIND_MEMORY
from coffer.application.upkeep_runs import UPKEEP_RUNS
from coffer.domain.memory.budget import estimate_tokens
from coffer.domain.memory.retired import RetiredNote
from coffer.infrastructure.memory import paths as memory_paths
from coffer.infrastructure.memory import store as memory_store
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from tests.integration.memory.conftest import claude_code_config, init_repository

_TOKEN = "test-token-memory-routes"
_HEADERS = {"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "user"}

# ----- fixture native-memory content --------------------------------------- #
#
# One project entry and one personal entry, which is the split the layer files
# on: an entry about the repository lands in that repository's partition, and
# one about the developer lands in ``global`` whichever repository it was
# learned in (FR-011). Every test below that needs two partitions gets them
# from this pair rather than from a second fixture repository.


def _cc_memory_file(name: str, description: str, type_: str, body: str) -> str:
    return (
        f"---\nname: {name}\ndescription: {description}\n"
        f"metadata:\n  type: {type_}\n---\n\n{body}\n"
    )


_CC_PROJECT_MEMORY = _cc_memory_file(
    "python-lockfile",
    "Dependencies are locked with uv",
    "project",
    "Run `uv sync --frozen` in this project; a plain `pip install` drifts.",
)
_CC_PERSONAL_MEMORY = _cc_memory_file(
    "worktree-development",
    "Always develop in a git worktree",
    "feedback",
    "Multiple parallel sessions share the repo — always work in a worktree.",
)


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


def _register_agent(c: TestClient, name: str, agent_type: str = "claude_code") -> str:
    r = c.post("/api/v1/agents", json={"type": agent_type, "name": name})
    assert r.status_code == 201, r.text
    return str(r.json()["uid"])


def _uid(c: TestClient, kind: str, name: str) -> str:
    """The uid of the ``kind`` resource labelled ``name``.

    ``GET /resources?kind=&name=`` is the one route allowed to find a resource
    by its label, and this is the same single lookup the CLI makes before every
    command (``surfaces/cli/_resolve.py``). Doing it here keeps the tests
    readable in labels while the requests they make are spelled the way a real
    client spells them.
    """
    r = c.get("/api/v1/resources", params={"kind": kind, "name": name})
    assert r.status_code == 200, r.text
    matches = r.json()["resources"]
    assert matches, f"no {kind} named {name!r}"
    return str(matches[0]["uid"])


def _repository(tmp_path: pathlib.Path, name: str = "coffer") -> pathlib.Path:
    """A real ``git init`` — the only thing that earns a partition (FR-014)."""
    return init_repository(tmp_path / name)


def _seed(tmp_path: pathlib.Path, repository: pathlib.Path, files: dict[str, str]) -> None:
    """Put Claude Code memory files in the project directory that decodes to
    ``repository``, with the sibling transcript production reads the cwd from."""
    claude_code_config(tmp_path / ".claude", repository, files)


def _default_files() -> dict[str, str]:
    return {
        "python-lockfile.md": _CC_PROJECT_MEMORY,
        "worktree-development.md": _CC_PERSONAL_MEMORY,
    }


def _sync(c: TestClient) -> dict:
    r = c.post("/api/v1/memory/sync")
    assert r.status_code == 200, r.text
    return r.json()


def _partitions(c: TestClient) -> dict[str, dict]:
    r = c.get("/api/v1/memory/partitions")
    assert r.status_code == 200, r.text
    return {p["name"]: p for p in r.json()["partitions"]}


def _partition_uid(c: TestClient, name: str) -> str:
    """The uid of the partition labelled ``name``, read off the list route.

    Deliberately not through ``_uid``: the list is what a real surface renders
    and then acts from, so taking the uid out of the row it already has is the
    client behaviour ``PartitionOut.uid`` exists to make possible.
    """
    return str(_partitions(c)[name]["uid"])


def _distil(c: TestClient, partition: str) -> dict:
    r = c.post(f"/api/v1/memory/partitions/{_partition_uid(c, partition)}/distil")
    assert r.status_code == 200, r.text
    return r.json()


def _distilled(c: TestClient, tmp_path: pathlib.Path, files: dict[str, str] | None = None) -> str:
    """Register an agent, seed a repository, sync and distil both partitions.

    Returns the repository partition's name. Most tests below want a partition
    with real notes in it, and notes only exist after a distil pass: aggregation
    writes ``.raw/`` and nothing else (FR-008).
    """
    _register_agent(c, "cc")
    repository = _repository(tmp_path)
    _seed(tmp_path, repository, files if files is not None else _default_files())
    _sync(c)
    name = next(n for n in _partitions(c) if n != "global")
    _distil(c, name)
    _distil(c, "global")
    return name


def _lines(text: str) -> list[str]:
    return [line for line in text.split("\n") if line.startswith("- **")]


def _binding_ceiling(text: str, *, room_for: int) -> int:
    """A ceiling that fits ``text``'s scaffolding and ``room_for`` index lines.

    Measured off an untrimmed payload rather than hard-coded, because the
    scaffolding's own size moves with the absolute notes path — a long
    ``tmp_path`` here, a short ``~/.coffer/...`` in production — and both trim
    notices are reserved up front, so a literal would pin this to one machine's
    directory names.
    """
    lines = _lines(text)
    scaffolding = estimate_tokens(text) - sum(estimate_tokens(line) for line in lines)
    for partition in ("global", "coffer"):
        scaffolding += estimate_tokens(
            f"(99 older line(s) not shown — those notes are files in "
            f"{memory_paths.notes_dir(partition)})"
        )
    return scaffolding + max(estimate_tokens(line) for line in lines) * room_for


# ----- partitions and notes -------------------------------------------------


def test_sync_then_distil_lists_partitions_and_their_notes(client, tmp_path) -> None:
    _register_agent(client, "cc")
    repository = _repository(tmp_path)
    _seed(tmp_path, repository, _default_files())

    result = _sync(client)
    assert result["entries_written"] == 2
    assert result["failures"] == []
    assert sorted(result["partitions"]) == ["coffer", "global"]

    # Aggregation writes `.raw/` only — a partition has no note until a distil
    # pass has run (FR-008).
    listed = _partitions(client)
    assert listed["coffer"]["note_count"] == 0
    assert listed["coffer"]["repository_path"] == str(repository.resolve())
    assert listed["coffer"]["repository_key"] == f"path:{repository.resolve()}"
    assert listed["coffer"]["unresolvable"] is False
    # `global` is no repository, and is resolvable from everywhere regardless.
    assert listed["global"]["repository_path"] == ""
    assert listed["global"]["unresolvable"] is False
    # Each row carries the identity every other route on this family takes, so
    # a surface that has listed the partitions acts on one without looking it
    # up by label first.
    assert listed["coffer"]["uid"] and listed["coffer"]["uid"] != listed["global"]["uid"]

    distilled = _distil(client, "coffer")
    assert distilled == {
        "partition": "coffer",
        "merged": 0,
        "opened": 1,
        "retired": 0,
        "dropped": 0,
        "model_used": False,
    }
    _distil(client, "global")
    assert _partitions(client)["coffer"]["note_count"] == 1

    coffer_uid = _partition_uid(client, "coffer")
    notes = client.get(f"/api/v1/memory/partitions/{coffer_uid}/notes").json()["notes"]
    assert len(notes) == 1
    summary = notes[0]
    assert summary["title"] == "python-lockfile"
    assert summary["slug"] == "python-lockfile"
    assert summary["partition"] == "coffer"
    assert summary["type"] == "project"
    assert summary["description"] == "Dependencies are locked with uv"
    assert summary["search_terms"] == []  # Claude Code states none (FR-004)
    assert summary["created_at"] and summary["updated_at"]
    # Retirement is a file leaving `notes/` plus a line in `RETIRED.md`, never a
    # flag a client has to filter on (FR-025).
    assert "status" not in summary
    assert "superseded_by" not in summary

    detail = client.get(f"/api/v1/memory/partitions/{coffer_uid}/notes/python-lockfile").json()
    assert "uv sync --frozen" in detail["body"]
    assert detail["origins"][0]["agent"] == "cc"
    assert detail["origins"][0]["native_path"].endswith("/memory/python-lockfile.md")
    assert detail["origins"][0]["anchor"] == "python-lockfile"

    # The personal entry went to `global` whichever repository it was learned
    # in — and that is what the session is given first (FR-011).
    global_uid = _partition_uid(client, "global")
    global_notes = client.get(f"/api/v1/memory/partitions/{global_uid}/notes").json()["notes"]
    assert [n["title"] for n in global_notes] == ["worktree-development"]
    assert global_notes[0]["type"] == "feedback"


def test_unknown_partition_notes_is_not_found(client) -> None:
    """A uid nothing answers to — the only way to miss, now that the path
    carries an identity rather than a label a typo could mangle."""
    r = client.get("/api/v1/memory/partitions/no-such-uid/notes")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_unknown_note_slug_is_not_found(client, tmp_path) -> None:
    partition = _distilled(client, tmp_path)
    r = client.get(
        f"/api/v1/memory/partitions/{_partition_uid(client, partition)}/notes/does-not-exist"
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "MEMORY_NOTE_NOT_FOUND"


@pytest.mark.acceptance(
    spec="memory", scenario="a directory that is not a repository gets no partition"
)
def test_a_partition_whose_repository_is_gone_is_listed_as_unresolvable(client, tmp_path) -> None:
    """FR-016: an orphan says so on this surface rather than sitting there
    undeliverable and unmentioned. It stays listed — and therefore deletable
    through the Resource route — because only the developer can decide that
    repository is not coming back."""
    partition = _distilled(client, tmp_path)
    assert _partitions(client)[partition]["unresolvable"] is False

    shutil.rmtree(tmp_path / "coffer")

    listed = _partitions(client)
    assert listed[partition]["unresolvable"] is True
    assert listed[partition]["repository_path"] == str((tmp_path / "coffer").resolve())
    assert listed[partition]["note_count"] == 1  # its notes are still readable


# ----- retirements ----------------------------------------------------------


def test_retired_answers_from_the_partitions_retirement_record(client, tmp_path) -> None:
    """``GET /retired`` reads ``RETIRED.md`` (FR-025), newest first — the file
    is appended to, so the wire order is the file's reversed."""
    partition = _distilled(client, tmp_path)
    uid = _partition_uid(client, partition)
    assert client.get(f"/api/v1/memory/partitions/{uid}/retired").json()["retired"] == []

    memory_store.write_retired(
        partition,
        [
            RetiredNote(
                slug="hook-injection",
                title="Context injection ships",
                reason="The mechanism was removed in 2026-09.",
                replaced_by="pull-only-delivery",
                retired_at="2026-09-10T00:00:00+00:00",
                entry_ids=("cc:one",),
            ),
            RetiredNote(
                slug="",
                title="A scratch observation",
                reason="Nothing was kept from it.",
                retired_at="2026-09-12T00:00:00+00:00",
                entry_ids=("cc:two",),
            ),
        ],
    )

    retired = client.get(f"/api/v1/memory/partitions/{uid}/retired").json()["retired"]
    assert [r["title"] for r in retired] == ["A scratch observation", "Context injection ships"]
    assert retired[1] == {
        "slug": "hook-injection",
        "title": "Context injection ships",
        "reason": "The mechanism was removed in 2026-09.",
        "replaced_by": "pull-only-delivery",
        "retired_at": "2026-09-10T00:00:00+00:00",
    }
    # `entry_ids` is the next pass's exclusion list, not the reader's business.
    assert "entry_ids" not in retired[0]
    # A record for entries a pass kept nothing from carries no slug.
    assert retired[0]["slug"] == ""


def test_retired_of_an_unknown_partition_is_not_found(client) -> None:
    r = client.get("/api/v1/memory/partitions/no-such-uid/retired")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


# ----- distil ---------------------------------------------------------------


def test_distil_with_no_internal_connection_still_writes_an_index(client, tmp_path) -> None:
    """FR-024: thinner, not absent. Each raw entry becomes a note of its own and
    ``MEMORY.md`` is still written, so this installation still has a delivery."""
    _register_agent(client, "cc")
    repository = _repository(tmp_path)
    _seed(tmp_path, repository, _default_files())
    _sync(client)

    body = _distil(client, "coffer")
    assert body["model_used"] is False
    assert body["opened"] == 1

    index = client.get(
        f"/api/v1/memory/partitions/{_partition_uid(client, 'coffer')}/files/content",
        params={"path": "MEMORY.md"},
    ).json()
    assert "python-lockfile" in index["content"]
    assert str(repository.resolve()) in index["content"]

    audit = client.get("/api/v1/audit").json()["entries"]
    assert any(e["event_type"] == "memory_distilled" for e in audit)
    assert any(e["event_type"] == "memory_aggregated" for e in audit)


def test_distil_unknown_partition_is_not_found(client) -> None:
    r = client.post("/api/v1/memory/partitions/no-such-uid/distil")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.acceptance(
    spec="memory",
    scenario="a second distil pass over the same partition is refused while the first is running",
)
def test_a_second_distil_over_the_same_partition_is_refused(client, tmp_path) -> None:
    """The bug this is here for: the button's spinner used to live in a browser
    component, so navigating away mid-pass and back showed an idle button and
    the next click started a SECOND pass over the same files (FR-041). The
    daemon now holds that fact, and refuses.

    The in-flight pass is simulated by claiming the partition's key directly —
    the route is synchronous, so a real second request could only be made from
    another thread, and what is under test is the refusal, not the threading.
    """
    partition = _distilled(client, tmp_path)
    uid = _partition_uid(client, partition)

    # Claimed by UID, because that is what the route claims and what the
    # unattended sweep claims: two writers only collide if both spell the
    # partition the same way, and the label is the spelling that can move.
    assert UPKEEP_RUNS.claim(KIND_MEMORY, uid) is True
    try:
        r = client.post(f"/api/v1/memory/partitions/{uid}/distil")
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "UPKEEP_ALREADY_RUNNING"

        # … and the surface can see it, so the button shows the running pass
        # instead of inviting that second click.
        runs = client.get("/api/v1/upkeep/runs").json()["runs"]
        assert {"memory"} == {run["kind"] for run in runs}
        assert [run["name"] for run in runs] == [uid]
    finally:
        UPKEEP_RUNS.release(KIND_MEMORY, uid)

    # The key is free again, so the real pass runs.
    assert client.post(f"/api/v1/memory/partitions/{uid}/distil").status_code == 200
    assert client.get("/api/v1/upkeep/runs").json()["runs"] == []


# ----- context: the payload the whole redesign is about ---------------------


@pytest.mark.acceptance(
    spec="memory",
    scenario="the composed context carries the whole index and the path to the bodies",
)
def test_context_carries_every_note_and_the_absolute_notes_path(client, tmp_path) -> None:
    """The measured failure this route exists to fix: the old surface shipped
    8 of 189 lines and pointed at ``coffer__recall``, which was called five
    times in its life. The payload now carries a line per note and the absolute
    directory the bodies are in, and names no tool at all (FR-028)."""
    files = {
        f"project-{i}.md": _cc_memory_file(f"project-{i}", f"Project fact {i}", "project", "body")
        for i in range(4)
    }
    files.update(
        {
            f"about-{i}.md": _cc_memory_file(f"about-{i}", f"Personal fact {i}", "feedback", "body")
            for i in range(3)
        }
    )
    partition = _distilled(client, tmp_path, files)
    repository = tmp_path / "coffer"

    r = client.post(
        "/api/v1/memory/context",
        json={"agent_uid": _uid(client, "agent", "cc"), "cwd": str(repository / "backend")},
    )
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["partition"] == partition
    assert data["notes_included"] == 7
    assert data["notes_omitted"] == 0
    # A cwd deep inside the repository resolves to the repository's partition.
    for slug in [f"project-{i}" for i in range(4)] + [f"about-{i}" for i in range(3)]:
        assert data["text"].count(f"`{slug}.md`") == 1
    assert len(_lines(data["text"])) == 7

    # The path is the current repository partition's, absolute, and the payload
    # says a body is read as a file rather than naming a tool for it (FR-028).
    notes_dir = str(memory_paths.notes_dir(partition))
    assert notes_dir.startswith("/")
    assert notes_dir in data["text"]
    assert "read one as a file" in data["text"]
    for tool in ("coffer__recall", "coffer__read", "coffer__search", "MCP"):
        assert tool not in data["text"]
    # There is no `layers` field any more: delivery is not a two-tier digest.
    assert "layers" not in data


@pytest.mark.acceptance(
    spec="memory", scenario="an index too large for the ceiling is trimmed and says so"
)
def test_context_under_a_binding_ceiling_keeps_the_repository_and_drops_global(
    client, tmp_path
) -> None:
    """FR-030, and the reverse of what this layer did before. The previous
    design spent its budget on ``global`` first and delivered, on a live vault
    of 189 entries, 8 lines of which none were about the project the session
    was open in — so what is pinned here is *which* partition loses lines."""
    files = {
        f"project-{i}.md": _cc_memory_file(f"project-{i}", f"Project fact {i}", "project", "b")
        for i in range(3)
    }
    files.update(
        {
            f"about-{i}.md": _cc_memory_file(f"about-{i}", f"Personal fact {i}", "feedback", "b")
            for i in range(12)
        }
    )
    partition = _distilled(client, tmp_path, files)
    repository = tmp_path / "coffer"
    cc_uid = _uid(client, "agent", "cc")

    full = client.post(
        "/api/v1/memory/context", json={"agent_uid": cc_uid, "cwd": str(repository)}
    ).json()
    assert full["notes_omitted"] == 0, "the untrimmed payload is the baseline"

    ceiling = _binding_ceiling(full["text"], room_for=6)

    r = client.post(
        "/api/v1/memory/context",
        json={"agent_uid": cc_uid, "cwd": str(repository), "ceiling_tokens": ceiling},
    )
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["notes_omitted"] > 0
    assert estimate_tokens(data["text"]) <= ceiling
    # The repository the session is open in keeps every line it has …
    for i in range(3):
        assert f"`project-{i}.md`" in data["text"]
    # … and `global` is what gives way — some of it, not all: the ceiling was
    # sized for six lines and the repository's three were spent first.
    kept = [i for i in range(12) if f"`about-{i}.md`" in data["text"]]
    assert kept, "the ceiling left room for global lines too"
    assert len(kept) < 12
    # The trim says how many were dropped AND where those notes are, which is
    # what makes it a small loss: every line that did not fit is still a file.
    assert f"({data['notes_omitted']} older line(s) not shown" in data["text"]
    assert str(memory_paths.notes_dir("global")) in data["text"]
    assert data["notes_included"] + data["notes_omitted"] == 15
    assert data["partition"] == partition


def test_context_serves_a_partition_to_an_agent_that_contributed_nothing_to_it(
    client, tmp_path
) -> None:
    """FR-013 at the wire: the partition reaches every agent, not its sources.

    The notes here were aggregated from ``cc`` alone, and ``outsider`` — a
    Codex agent that contributed not one entry — opens a session in the same
    repository and is served the same payload. This route used to narrow by
    the partition's per-agent reach, which aggregation had defaulted to the
    agents it read from, so this exact request came back **empty**: on the
    maintainer's own vault a Codex session in the Coffer repository was served
    no project memory at all. Nobody chose that, and it defeated the point of
    aggregating several agents' memory into one place.
    """
    partition = _distilled(client, tmp_path)
    outsider_uid = _register_agent(client, "outsider", agent_type="codex")
    repository = tmp_path / "coffer"

    # The kind carries no reach any more, and the framework's own scope route
    # says so rather than reporting an empty narrowing.
    scope = client.get(f"/api/v1/resources/{_partition_uid(client, partition)}/scope").json()
    assert scope["supports_scope"] is False
    assert scope["scope"] is None

    served = client.post(
        "/api/v1/memory/context", json={"agent_uid": outsider_uid, "cwd": str(repository)}
    ).json()
    to_a_source = client.post(
        "/api/v1/memory/context",
        json={"agent_uid": _uid(client, "agent", "cc"), "cwd": str(repository)},
    ).json()

    assert served["partition"] == partition
    assert "`python-lockfile.md`" in served["text"]
    assert served["notes_included"] > 0
    # Byte-identical: who is asking decides nothing about the payload. The uid
    # travels for ``record_fired`` — who fired — and for nothing else.
    assert served["text"] == to_a_source["text"]


def test_context_for_a_directory_in_no_repository_is_global(client, tmp_path) -> None:
    _distilled(client, tmp_path)

    data = client.post(
        "/api/v1/memory/context",
        json={
            "agent_uid": _uid(client, "agent", "cc"),
            "cwd": str(tmp_path / "Documents" / "2026-09-17"),
        },
    ).json()

    assert data["partition"] == "global"
    assert "`worktree-development.md`" in data["text"]
    assert "in no repository Coffer has aggregated yet" in data["text"]


# ----- delivery -------------------------------------------------------------


def test_delivery_install_status_and_record_fired_round_trip(client) -> None:
    cc_uid = _register_agent(client, "cc")

    status = client.get("/api/v1/memory/delivery", params={"agent_uid": cc_uid}).json()
    assert status["delivery"][0]["installed"] is False
    # Both halves travel: the uid a surface acts on, the label it renders. A row
    # carrying one of the two would send every client back for the other.
    assert status["delivery"][0]["agent_uid"] == cc_uid
    assert status["delivery"][0]["agent_name"] == "cc"
    # A fire is an event, never a field on the status (FR-033, FR-039).
    assert "last_fired_at" not in status["delivery"][0]

    installed = client.post(f"/api/v1/memory/delivery/{cc_uid}/install").json()
    assert installed["installed"] is True
    # The uid goes INTO the installed command, so the entry keeps naming this
    # agent however the user relabels it — the whole reason delivery is keyed
    # on an identity rather than on a label.
    assert f"coffer memory context --agent-uid {cc_uid}" in installed["command"]

    audit = client.get("/api/v1/audit").json()
    assert any(e["event_type"] == "memory_delivery_installed" for e in audit["entries"])

    r = client.post(
        "/api/v1/memory/context",
        json={"agent_uid": cc_uid, "cwd": "/tmp", "record_fired": True},
    )
    assert r.status_code == 200, r.text

    audit2 = client.get("/api/v1/audit").json()
    assert any(e["event_type"] == "memory_delivery_fired" for e in audit2["entries"])
    # Installation is unchanged by a fire.
    assert client.get("/api/v1/memory/delivery", params={"agent_uid": cc_uid}).json()["delivery"][
        0
    ]["installed"]

    removed = client.delete(f"/api/v1/memory/delivery/{cc_uid}").json()
    assert removed["installed"] is False


def test_an_installed_hook_survives_the_agent_being_renamed(client) -> None:
    """The failure the uid removes. The hook entry is a string in somebody
    else's settings file that Coffer writes once and never revisits, so a label
    baked into it would start naming an agent nothing answers to the first time
    the user edited it — and every session's fire would go unattributed.
    """
    cc_uid = _register_agent(client, "cc")
    installed = client.post(f"/api/v1/memory/delivery/{cc_uid}/install").json()
    command = installed["command"]

    renamed = client.patch(f"/api/v1/resources/{cc_uid}", json={"name": "claude-code"})
    assert renamed.status_code == 200, renamed.text

    # The command on disk was not rewritten, and it is still recognised …
    status = client.get("/api/v1/memory/delivery", params={"agent_uid": cc_uid}).json()
    assert status["delivery"][0]["installed"] is True
    assert status["delivery"][0]["command"] == command
    # … under the agent's new label, which is what the row renders.
    assert status["delivery"][0]["agent_name"] == "claude-code"

    # And the fire it records still lands on this agent.
    r = client.post(
        "/api/v1/memory/context",
        json={"agent_uid": cc_uid, "cwd": "/tmp", "record_fired": True},
    )
    assert r.status_code == 200, r.text
    audit = client.get("/api/v1/audit").json()["entries"]
    assert any(e["event_type"] == "memory_delivery_fired" for e in audit)


def test_context_without_record_fired_does_not_record_a_fire(client) -> None:
    cc_uid = _register_agent(client, "cc")
    client.post(f"/api/v1/memory/delivery/{cc_uid}/install")

    client.post("/api/v1/memory/context", json={"agent_uid": cc_uid, "cwd": "/tmp"})

    audit = client.get("/api/v1/audit").json()
    assert not any(e["event_type"] == "memory_delivery_fired" for e in audit["entries"])


# ----- the partition's own files -------------------------------------------


@pytest.mark.acceptance(
    spec="memory", scenario="a partition's own directory is browsable as a file tree"
)
def test_partition_files_walk_the_directory_and_read_one_file(client, tmp_path) -> None:
    partition = _distilled(client, tmp_path)
    memory_store.write_retired(
        partition,
        [RetiredNote(slug="gone", title="Gone", reason="No longer true.", entry_ids=("cc:x",))],
    )

    uid = _partition_uid(client, partition)
    tree = client.get(f"/api/v1/memory/partitions/{uid}/files").json()["root"]
    assert tree["path"] == ""
    assert tree["abs_path"] == str(tmp_path / "memory" / partition)
    names = {child["name"]: child for child in tree["children"]}
    # Four things, one writer each — and nothing left of the shape this
    # replaced: no README.md, no summary.md, no facts/.
    assert set(names) == {"MEMORY.md", "notes", "RETIRED.md", ".raw"}
    assert names["notes"]["type"] == "dir"
    assert names["notes"]["derived"] is False
    assert "notes/python-lockfile.md" in {c["path"] for c in names["notes"]["children"]}
    # `.raw/` is reachable through the same tree, and marked as the verbatim
    # input rather than Coffer's own writing (FR-008, FR-037).
    assert names[".raw"]["type"] == "dir"
    assert names[".raw"]["derived"] is True
    raw_children = names[".raw"]["children"]
    assert len(raw_children) == 1

    content = client.get(
        f"/api/v1/memory/partitions/{uid}/files/content",
        params={"path": "notes/python-lockfile.md"},
    ).json()
    assert content["binary"] is False
    assert content["truncated"] is False
    assert "uv sync --frozen" in content["content"]
    assert content["abs_path"].endswith("/notes/python-lockfile.md")
    assert content["folder_abs_path"] == str(memory_paths.notes_dir(partition))

    # The hidden half reads too, verbatim: it is the distil pass's input, and
    # it is what makes a note's paraphrase checkable back against the source.
    raw = client.get(
        f"/api/v1/memory/partitions/{uid}/files/content",
        params={"path": raw_children[0]["path"]},
    ).json()
    assert "uv sync --frozen" in raw["content"]
    assert "agent: cc" in raw["content"]


def test_partition_files_are_read_only(client, tmp_path) -> None:
    """No write reaches this family. The tree is derived (FR-019), so an edit
    would survive only until the next aggregation pass."""
    partition = _distilled(client, tmp_path)

    r = client.put(
        f"/api/v1/memory/partitions/{_partition_uid(client, partition)}/files/content",
        json={"path": "notes/python-lockfile.md", "content": "rewritten"},
    )
    assert r.status_code == 405


def test_partition_files_refuse_a_path_that_escapes_the_partition(client, tmp_path) -> None:
    partition = _distilled(client, tmp_path)

    r = client.get(
        f"/api/v1/memory/partitions/{_partition_uid(client, partition)}/files/content",
        params={"path": "../../../../etc/passwd"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "MEMORY_UNSAFE_PATH"


def test_partition_file_that_is_not_there_is_not_found(client, tmp_path) -> None:
    partition = _distilled(client, tmp_path)

    r = client.get(
        f"/api/v1/memory/partitions/{_partition_uid(client, partition)}/files/content",
        params={"path": "notes/no-such-note.md"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "MEMORY_FILE_NOT_FOUND"


def test_files_of_an_unknown_partition_are_not_found(client) -> None:
    r = client.get("/api/v1/memory/partitions/no-such-uid/files")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
