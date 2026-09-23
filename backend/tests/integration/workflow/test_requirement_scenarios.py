"""Workflow requirement scenarios, run end to end through production wiring.

Each test here covers one ``#### Scenario:`` of ``openspec/specs/workflow/
spec.md`` that had no test, against the daemon ``requirement_harness`` builds:
real SQLite rows, the real run directory, the real node driver and context
composer, real git for a mounted repository. The only stand-in is the agent,
and it is literal — it writes what its brief tells it to write — so what these
tests observe is what the engine did, not what a fake was told to answer.
"""

from __future__ import annotations

import asyncio
import copy
import pathlib
import shutil
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ConfigValidationError, ScopeInvalidError
from coffer.domain.scope import Scope
from coffer.domain.workflow.run import (
    ApprovalStatus,
    NodeAction,
    NodeStatus,
    RunInputKind,
    RunStatus,
)
from coffer.infrastructure.knowledge import paths as knowledge_paths
from coffer.infrastructure.workflow import paths

from .requirement_harness import (
    TEMPLATE,
    Daemon,
    agent_body,
    build_daemon,
    http_client,
    tree,
)

API = "/api/v1/workflow"


@pytest.fixture
async def daemon(tmp_path: pathlib.Path) -> AsyncIterator[Daemon]:
    built, engine = await build_daemon(tmp_path)
    yield built
    await engine.dispose()


@pytest.fixture
async def client(daemon: Daemon) -> AsyncIterator[httpx.AsyncClient]:
    async for http in http_client(daemon):
        yield http


async def git(cwd: pathlib.Path, *args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git",
        "-C",
        str(cwd),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    assert proc.returncode == 0, err.decode()
    return out.decode()


async def developer_repo(root: pathlib.Path) -> pathlib.Path:
    """A git repository with a commit, a second branch and uncommitted work."""
    repo = root / "account"
    repo.mkdir()
    await git(repo, "init", "-b", "main")
    await git(repo, "config", "user.email", "dev@example.invalid")
    await git(repo, "config", "user.name", "Dev")
    (repo / "README.md").write_text("REPO-SENTINEL committed\n", encoding="utf-8")
    await git(repo, "add", "README.md")
    await git(repo, "commit", "-m", "first")
    await git(repo, "branch", "feature/login")
    (repo / "README.md").write_text("REPO-SENTINEL edited, not committed\n", encoding="utf-8")
    (repo / "scratch.txt").write_text("uncommitted work\n", encoding="utf-8")
    return repo


needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not on PATH")


# --- "Attach no behaviour to a stage key" -------------------------------------


def _with_stage_keys(first: str, second: str) -> dict[str, Any]:
    renamed = copy.deepcopy(TEMPLATE)
    renamed["stages"][0]["key"] = first
    renamed["stages"][1]["key"] = second
    return renamed


async def _trace(daemon: Daemon, template_name: str, config: dict[str, Any]) -> dict[str, Any]:
    """Everything about how a run went, with its stage keys left out."""
    template = await daemon.template(config, name=template_name)
    run = await daemon.started_run(template)
    taken = await daemon.drive_to_the_end(run.id)
    final = await daemon.run_repo.get_run(run.id)
    assert final is not None
    events = await daemon.events.list_events(run.id)
    attempts = await daemon.attempts.list_attempts(run.id)
    return {
        "taken": taken,
        "events": [(e.event_type, e.node_key) for e in events],
        "attempts": sorted((a.node_key, a.attempt, a.status) for a in attempts),
        "status": final.status,
        "current": final.current_node_key,
    }


@pytest.mark.acceptance(spec="workflow", scenario="a stage's key changes nothing about how it runs")
async def test_two_templates_differing_only_in_stage_keys_run_identically(
    daemon: Daemon,
) -> None:
    # The second pair sorts the other way round and reads like behaviour
    # ("approval", "release"): if anything ordered by, or keyed off, the stage
    # key, this is the pair that would show it.
    plain = await _trace(daemon, "plain", _with_stage_keys("design", "coding"))
    loaded = await _trace(daemon, "loaded", _with_stage_keys("release", "approval"))

    assert plain["taken"] == ["draft_td", "write_code"]
    assert loaded == plain
    assert plain["status"] == RunStatus.COMPLETED.value


# --- "Read a template's scope as the agents it may drive" ---------------------


def _one_node_on(agent: str) -> dict[str, Any]:
    return {
        "stages": [
            {
                "key": "design",
                "name": "Design",
                "nodes": [
                    {"key": "draft_td", "name": "Draft the design", "type": "ai", "agent": agent}
                ],
            }
        ]
    }


@pytest.mark.acceptance(
    spec="workflow", scenario="a node may name only an agent the template may drive"
)
async def test_a_node_naming_an_agent_outside_the_templates_scope_is_refused(
    daemon: Daemon,
) -> None:
    """Through the resource framework with the kind exactly as the composition
    root registers it, because that is the only path a template is written by.
    A scope names agents by uid and a node by key, so both agents are real
    rows here."""
    claude = await daemon.resources.register(
        "agent", "claude", {"type": "claude_code"}, "user", allow_lifecycle_kind=True
    )
    codex = await daemon.resources.register(
        "agent", "codex", {"type": "codex"}, "user", allow_lifecycle_kind=True
    )
    inside = _one_node_on("claude_code")
    template = await daemon.template(inside, name="scoped")
    await daemon.resources.update_scope(template.uid, Scope(agents=[claude.uid]), actor="user")

    # The first version — a node on the one agent in scope — is accepted.
    assert (await daemon.resources.get(template.uid)).config == inside

    outside = _one_node_on("codex")
    with pytest.raises(ConfigValidationError) as caught:
        await daemon.resources.update_config(template.uid, outside, actor="user")

    assert "stages[0].nodes[0].agent" in str(caught.value)
    assert (await daemon.resources.get(template.uid)).config == inside

    # The same rule from the other side: narrowing the scope away from the
    # agent a node already names is refused, and the scope stays as it was.
    with pytest.raises(ScopeInvalidError) as narrowed:
        await daemon.resources.update_scope(template.uid, Scope(agents=[codex.uid]), actor="user")

    assert "stages[0].nodes[0].agent" in str(narrowed.value)
    assert (await daemon.resources.get(template.uid)).scope == Scope(agents=[claude.uid])


# --- "Give each run a working directory of its own" ---------------------------


@pytest.mark.acceptance(spec="workflow", scenario="a run's working directory is Coffer's to choose")
async def test_a_run_never_works_in_a_directory_the_request_named(
    daemon: Daemon, client: httpx.AsyncClient, tmp_path: pathlib.Path
) -> None:
    template = await daemon.template(TEMPLATE)
    named = tmp_path / "a-directory-of-my-own"

    response = await client.post(
        f"{API}/runs",
        json={"template_uid": template.uid, "title": "Ship it", "workdir": str(named)},
    )

    # Refused or ignored — either way, no run works where the request said.
    assert response.status_code in (201, 422), response.text
    listed = (await client.get(f"{API}/runs")).json()["items"]
    assert all(run["workdir"] != str(named) for run in listed)
    assert not named.exists()

    created = await client.post(f"{API}/runs", json={"template_uid": template.uid, "title": "B"})
    assert created.status_code == 201, created.text
    run = created.json()
    workdir = pathlib.Path(run["workdir"])
    assert workdir == paths.workspace_dir(run["id"])
    assert workdir.is_relative_to(paths.run_dir(run["id"]))
    assert workdir.is_dir()

    # And every task's conversation is opened in it.
    signal = await client.post(
        f"{API}/runs/{run['id']}/signals", json={"version": run["version"], "signal": "start"}
    )
    assert signal.status_code == 200, signal.text
    await daemon.drive_to_the_end(run["id"])
    assert [conv["cwd"] for conv in daemon.agent.conversations] == [str(workdir)] * 2


# --- "Keep a node to seven statuses" (as the API reports them) ----------------

SEVEN = {
    "pending",
    "running",
    "waiting_review",
    "waiting_approval",
    "completed",
    "skipped",
    "failed",
}


async def _detail(client: httpx.AsyncClient, run_id: str) -> dict[str, Any]:
    response = await client.get(f"{API}/runs/{run_id}")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _statuses(detail: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    for stage in detail["stages"]:
        for node in stage["nodes"]:
            found.add(node["status"])
            if node["latest"] is not None:
                found.add(node["latest"]["status"])
    return found


@pytest.mark.acceptance(spec="workflow", scenario="a node is only ever in one of seven statuses")
async def test_every_status_the_api_reports_for_a_node_is_one_of_the_seven(
    daemon: Daemon, client: httpx.AsyncClient
) -> None:
    daemon.agent.write_deliverables = False
    run = await daemon.started_run(await daemon.template(TEMPLATE))
    seen = _statuses(await _detail(client, run.id))
    await daemon.start(run.id, "draft_td")  # stops in review: td.md never written
    seen |= _statuses(await _detail(client, run.id))
    await daemon.act(run.id, "draft_td", NodeAction.SKIP)
    seen |= _statuses(await _detail(client, run.id))
    await daemon.start(run.id, "write_code")
    seen |= _statuses(await _detail(client, run.id))
    await daemon.act(run.id, "write_code", NodeAction.COMPLETE, waive_artifacts=True)
    seen |= _statuses(await _detail(client, run.id))

    assert seen <= SEVEN
    assert {"pending", "waiting_review", "skipped", "completed"} <= seen


# --- "Accept the node actions start, feedback, complete, retry, skip and
#      restore" -----------------------------------------------------------------


@pytest.mark.acceptance(spec="workflow", scenario="a node takes exactly six actions")
async def test_a_node_knows_the_six_actions_and_refuses_any_other(
    daemon: Daemon, client: httpx.AsyncClient
) -> None:
    daemon.agent.write_deliverables = False
    run = await daemon.started_run(await daemon.template(TEMPLATE))
    url = f"{API}/runs/{run.id}/nodes/draft_td/actions"

    async def act(action: str, **extra: Any) -> httpx.Response:
        version = (await _detail(client, run.id))["run"]["version"]
        return await client.post(url, json={"version": version, "action": action, **extra})

    # Each of the six, submitted where it is legal, is applied.
    steps: list[tuple[str, dict[str, Any], str]] = [
        ("start", {}, "waiting_review"),
        ("feedback", {"feedback": "ground it in the repo"}, "waiting_review"),
        ("complete", {"waive_artifacts": True}, "completed"),
        ("retry", {}, "pending"),
        ("skip", {}, "skipped"),
        ("restore", {}, "pending"),
    ]
    for action, extra, then in steps:
        response = await act(action, **extra)
        assert response.status_code == 200, (action, response.text)
        node = (await _detail(client, run.id))["stages"][0]["nodes"][0]
        assert node["status"] == then, action

    # Anything else is refused, and nothing about the run moves.
    before = await _detail(client, run.id)
    events_before = len(await daemon.events.list_events(run.id))
    for unknown in ("approve", "reopen", "abort", "START"):
        response = await act(unknown)
        assert response.status_code == 422, (unknown, response.text)
    assert await _detail(client, run.id) == before
    assert len(await daemon.events.list_events(run.id)) == events_before


# --- "Keep every attempt when a node is retried" ------------------------------


@pytest.mark.acceptance(spec="workflow", scenario="a retry keeps the attempt before it")
async def test_retrying_appends_an_attempt_and_the_first_one_is_still_readable(
    daemon: Daemon,
) -> None:
    run = await daemon.started_run(await daemon.template(TEMPLATE))
    # First attempt: a conversation, an output, and the developer's feedback.
    daemon.agent.write_deliverables = False
    await daemon.start(run.id, "draft_td")
    await daemon.act(run.id, "draft_td", NodeAction.FEEDBACK, feedback="ground it in the repo")
    first_td = paths.artifact_path(run.id, "draft_td", 1, "td.md")
    first_td.parent.mkdir(parents=True, exist_ok=True)
    first_td.write_text("the first attempt's design\n", encoding="utf-8")
    await daemon.act(run.id, "draft_td", NodeAction.COMPLETE)
    first = await daemon.attempts.latest_attempt(run.id, "draft_td")
    assert first is not None and first.attempt == 1

    daemon.agent.write_deliverables = True
    await daemon.act(run.id, "draft_td", NodeAction.RETRY)
    await daemon.start(run.id, "draft_td")

    rows = sorted(
        (a for a in await daemon.attempts.list_attempts(run.id) if a.node_key == "draft_td"),
        key=lambda a: a.attempt,
    )
    assert [a.attempt for a in rows] == [1, 2]
    kept = rows[0]
    assert kept.id == first.id
    assert kept.status == NodeStatus.COMPLETED.value
    # Its conversation, its output and its feedback, all still there.
    assert kept.conversation_id == "conv-1"
    assert rows[1].conversation_id not in (None, "conv-1")
    assert kept.summary == first.summary and kept.summary
    assert first_td.read_text(encoding="utf-8") == "the first attempt's design\n"
    feedback = [
        e
        for e in await daemon.events.list_events(run.id)
        if e.event_type == "node.feedback_submitted"
    ]
    assert [(e.node_key, e.payload["attempt"], e.payload["feedback"]) for e in feedback] == [
        ("draft_td", 1, "ground it in the repo")
    ]


# --- "List a run's mounted inputs to every node" ------------------------------


@needs_git
@pytest.mark.acceptance(
    spec="workflow", scenario="every kind of input is listed and none is pasted"
)
async def test_all_five_kinds_of_input_are_named_in_the_opening_and_none_is_inlined(
    daemon: Daemon, tmp_path: pathlib.Path
) -> None:
    await daemon.knowledge.create_collection("prd-notes", actor="user")
    doc = knowledge_paths.collection_dir("prd-notes") / "requirements.md"
    doc.write_text("# Requirements\n\nKNOWLEDGE-SENTINEL body\n", encoding="utf-8")
    repo = await developer_repo(tmp_path)
    link = "https://example.invalid/wiki/PRD-1"

    run = await daemon.started_run(await daemon.template(TEMPLATE))
    await daemon.inputs.add_input(run.id, kind=RunInputKind.KNOWLEDGE, ref="prd-notes")
    await daemon.inputs.upload_input(run.id, filename="prd.txt", content=b"UPLOAD-SENTINEL body")
    await daemon.inputs.add_note(run.id, title="Direction", text="NOTE-SENTINEL body")
    await daemon.inputs.add_input(run.id, kind=RunInputKind.LINK, ref=link)
    mounted = await daemon.inputs.add_input(run.id, kind=RunInputKind.REPO, ref=str(repo))
    checkout = next(item.path for item in mounted if item.kind is RunInputKind.REPO)
    assert checkout is not None

    await daemon.start(run.id, "draft_td")
    attempt = await daemon.attempts.latest_attempt(run.id, "draft_td")
    assert attempt is not None
    # The task opened: its brief was composed and its turn began.
    assert daemon.agent.turns, (attempt.status, attempt.failure_reason)
    opening = daemon.agent.opening_of("conv-1")

    inputs_dir = paths.run_dir(run.id) / "inputs"
    assert "- knowledge `prd-notes`" in opening
    assert f"- file `{inputs_dir}/prd.txt`" in opening
    assert f"- note `{inputs_dir}/Direction.md`" in opening
    assert f"- link `{link}`" in opening
    assert f"- repo `{checkout}`" in opening
    # Each of those opens what it names.
    assert (inputs_dir / "prd.txt").read_bytes() == b"UPLOAD-SENTINEL body"
    assert (inputs_dir / "Direction.md").read_text(encoding="utf-8") == "NOTE-SENTINEL body"
    assert pathlib.Path(checkout, "README.md").is_file()
    for sentinel in ("KNOWLEDGE-SENTINEL", "UPLOAD-SENTINEL", "NOTE-SENTINEL", "REPO-SENTINEL"):
        assert sentinel not in opening, sentinel


# --- "Leave the source repository untouched on unmount" -----------------------


async def _repo_state(repo: pathlib.Path) -> dict[str, Any]:
    return {
        "branches": await git(repo, "branch", "--list", "--format=%(refname:short)"),
        "head": await git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
        "status": await git(repo, "status", "--porcelain"),
        # The working tree; git's own bookkeeping is compared through git.
        "files": {k: v for k, v in tree(repo).items() if not k.startswith(".git/")},
    }


def _mine(branches: str) -> list[str]:
    """The developer's own branches — the list without the one Coffer made."""
    return [b for b in branches.splitlines() if not b.startswith("coffer/")]


@needs_git
@pytest.mark.acceptance(
    spec="workflow", scenario="unmounting a repository leaves the source as it was"
)
async def test_unmounting_a_repository_gives_back_the_checkout_and_touches_nothing_else(
    daemon: Daemon, tmp_path: pathlib.Path
) -> None:
    repo = await developer_repo(tmp_path)
    before_mount = await _repo_state(repo)
    run = await daemon.started_run(await daemon.template(TEMPLATE))
    mounted = await daemon.inputs.add_input(run.id, kind=RunInputKind.REPO, ref=str(repo))
    checkout = pathlib.Path(next(i.path for i in mounted if i.kind is RunInputKind.REPO) or "")
    assert checkout.is_dir()
    # The run works in its checkout, as a run would.
    (checkout / "the-runs-work.txt").write_text("done by the run\n", encoding="utf-8")
    before_unmount = await _repo_state(repo)

    remaining = await daemon.inputs.remove_input(run.id, str(repo))

    assert remaining == ()
    assert not checkout.exists()
    after = await _repo_state(repo)
    # Working tree and uncommitted work exactly as they were before the unmount.
    assert after["files"] == before_unmount["files"]
    assert after["status"] == before_unmount["status"]
    assert after["head"] == before_unmount["head"]
    assert (repo / "scratch.txt").read_text(encoding="utf-8") == "uncommitted work\n"
    # The developer's branches as they were before the unmount; the branch
    # Coffer created for the checkout went with it, so the list is the one the
    # repository had before the run was ever given it.
    assert _mine(after["branches"]) == _mine(before_unmount["branches"])
    assert after["branches"] == before_mount["branches"]
    assert after == before_mount


# --- "Audit template, run, approval and gate events" --------------------------


@pytest.mark.acceptance(
    spec="workflow", scenario="every change to a workflow leaves an audit entry"
)
async def test_template_run_approval_and_gated_call_each_leave_an_audit_entry(
    daemon: Daemon,
) -> None:
    template = await daemon.template(TEMPLATE)
    run = await daemon.started_run(template)
    await daemon.start(run.id, "draft_td")
    attempt = await daemon.attempts.latest_attempt(run.id, "draft_td")
    assert attempt is not None

    refused = await daemon.gate.check_tool_call(
        run_context=f"{run.id}/{attempt.id}",
        tool_name="jira__create_issue",
        arguments={"project": "COF", "summary": "ship it"},
    )
    assert refused is not None and refused["isError"] is True
    [approval] = await daemon.approvals.list_for_run(run.id)
    await daemon.approvals.decide(
        approval.id, decision=ApprovalStatus.APPROVED, decided_by="user", decided_surface="web"
    )
    await daemon.drive_to_the_end(run.id)
    final = await daemon.run_repo.get_run(run.id)
    assert final is not None and final.status == RunStatus.COMPLETED.value

    template_trail = await daemon.audit.query(resource=template)
    assert [e.event_type for e in template_trail] == [AuditEventType.RESOURCE_CREATED.value]
    run_trail = [e for e in await daemon.audit.query(limit=200) if e.resource_name == run.id]
    by_type = {e.event_type: e for e in run_trail}
    for expected in (
        AuditEventType.WORKFLOW_RUN_STARTED,
        AuditEventType.WORKFLOW_TOOL_CALL_GATED,
        AuditEventType.WORKFLOW_APPROVAL_DECIDED,
        AuditEventType.WORKFLOW_RUN_FINISHED,
    ):
        assert expected.value in by_type, (expected, sorted(by_type))
    assert by_type[AuditEventType.WORKFLOW_TOOL_CALL_GATED.value].details["tool_name"] == (
        "jira__create_issue"
    )
    assert by_type[AuditEventType.WORKFLOW_APPROVAL_DECIDED.value].details["status"] == "approved"
    assert by_type[AuditEventType.WORKFLOW_RUN_FINISHED.value].details["status"] == "completed"


# --- "Never index a run's directory" ------------------------------------------


@pytest.mark.acceptance(spec="workflow", scenario="a run's files are the only copy of themselves")
async def test_a_runs_directory_holds_its_files_as_written_and_nothing_derived(
    daemon: Daemon,
) -> None:
    knowledge_before = tree(knowledge_paths.knowledge_root())
    run = await daemon.started_run(await daemon.template(TEMPLATE))
    await daemon.inputs.upload_input(run.id, filename="prd.txt", content=b"UPLOAD-SENTINEL body")
    await daemon.drive_to_the_end(run.id)
    final = await daemon.run_repo.get_run(run.id)
    assert final is not None and final.status == RunStatus.COMPLETED.value

    run_dir = paths.run_dir(run.id)
    files = tree(run_dir)
    td = paths.artifact_path(run.id, "draft_td", 1, "td.md")
    report = paths.artifact_path(run.id, "write_code", 1, "report.md")
    written = {
        str(td.relative_to(run_dir)): agent_body(td).encode(),
        str(report.relative_to(run_dir)): agent_body(report).encode(),
        "inputs/prd.txt": b"UPLOAD-SENTINEL body",
    }
    # Every file it wrote, byte for byte.
    for rel, body in written.items():
        assert files.get(rel) == body, rel
    # And beyond them only the run's generated catalogue, which names files and
    # copies none of them. No index, no chunks, no embeddings, no database.
    assert set(files) - set(written) <= {paths.CATALOG_NAME}, sorted(set(files) - set(written))
    catalogue = files.get(paths.CATALOG_NAME, b"")
    for body in written.values():
        assert body.strip() not in catalogue
    assert {p.name for p in run_dir.iterdir() if p.is_dir()} <= {
        "artifacts",
        "inputs",
        "workspace",
    }
    # The knowledge root has gained nothing from them.
    assert tree(knowledge_paths.knowledge_root()) == knowledge_before
