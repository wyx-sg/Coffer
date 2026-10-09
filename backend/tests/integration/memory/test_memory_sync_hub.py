"""The memory sync's publish half: native memory into the hub (spec memory
"Keep every agent's memories in a hub in the vault" and the requirements that
decide what is published, from where, and how).

Real git checkouts, real agent directories and a real vault under the test's
``HOME``; a :class:`Machine` is a machine id and its own agents and ledger.
"""

from __future__ import annotations

import os
import pathlib

import pytest

from coffer.infrastructure.memory.hub_store import parse_entry
from coffer.infrastructure.vault.instance import vault_repository
from tests.integration.memory._sync_harness import (
    Machine,
    cc_file,
    cc_project,
    codex_memory,
    hub_files,
)
from tests.integration.memory.conftest import git, init_repository


def _vault() -> pathlib.Path:
    return pathlib.Path(os.environ["HOME"]) / ".coffer" / "vault"


def _entries() -> list:  # type: ignore[type-arg]
    return [parse_entry(p.read_text(encoding="utf-8")) for p in hub_files(_vault())]


@pytest.fixture
def payments(tmp_path: pathlib.Path) -> pathlib.Path:
    return init_repository(tmp_path / "src" / "payments", remote="git@github.com:acme/payments.git")


@pytest.mark.acceptance(spec="memory", scenario="an agent's memory becomes one hub file")
async def test_an_agent_memory_becomes_one_hub_file(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    cc = a.claude()
    cc_project(
        cc,
        payments,
        {
            "feedback_testing.md": cc_file(
                "Integration tests hit a real database",
                "Never mock the DB in integration tests",
                "feedback",
                "A mocked run hid a broken migration.",
            )
        },
    )
    await a.sync()

    files = hub_files(_vault())
    assert [p.parent.name for p in files] == ["github.com-acme-payments"]
    entry = parse_entry(files[0].read_text(encoding="utf-8"))
    assert entry is not None
    assert entry.origin.machine == "machine-a"
    assert entry.origin.agent == "claude_code"
    assert entry.origin.source.endswith("memory/feedback_testing")
    assert entry.type == "feedback"
    assert entry.title == "Integration tests hit a real database"
    assert entry.description == "Never mock the DB in integration tests"
    assert entry.body == "A mocked run hid a broken migration."
    assert entry.project == "github.com/acme/payments"

    repo = vault_repository()
    log = git("log", "--format=%an|%s", "--", "memory", cwd=repo.root)
    assert log.splitlines() == ["Coffer (memory-sync)|Memory sync: 1 published"]


@pytest.mark.acceptance(spec="memory", scenario="a memory about the person is filed under global")
async def test_a_memory_about_the_person_is_filed_under_global(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    cc_project(
        a.claude(),
        payments,
        {
            "user_lang.md": cc_file(
                "Replies in Chinese", "The person reads Chinese", "user", "Reply in Chinese."
            )
        },
    )
    a.codex(
        memory_md="",
        summary_md="## User Profile\nA backend engineer who prefers small pull requests.\n",
    )
    await a.sync()

    folders = {p.parent.name for p in hub_files(_vault())}
    assert folders == {"global"}
    assert {e.origin.agent for e in _entries()} == {"claude_code", "codex"}


@pytest.mark.acceptance(spec="memory", scenario="two clones on two machines share one project")
async def test_two_clones_on_two_machines_share_one_project(tmp_path: pathlib.Path) -> None:
    upstream = init_repository(tmp_path / "upstream")
    one = tmp_path / "a" / "src" / "payments"
    other = tmp_path / "b" / "work" / "pay"
    git("clone", "-q", str(upstream), str(one), cwd=tmp_path)
    git("remote", "set-url", "origin", "git@github.com:acme/payments.git", cwd=one)
    git("clone", "-q", str(upstream), str(other), cwd=tmp_path)
    git("remote", "set-url", "origin", "https://github.com/acme/payments", cwd=other)

    a = Machine("machine-a", tmp_path / "ma")
    cc_project(
        a.claude(),
        one,
        {"p.md": cc_file("Ledger retries", "Retries are idempotent", "project", "x")},
    )
    b = Machine("machine-b", tmp_path / "mb")
    cc_project(
        b.claude(), other, {"q.md": cc_file("Batch size", "Batches are 500", "project", "y")}
    )
    await a.sync()
    await b.sync()

    projects = {e.project for e in _entries()}
    assert projects == {"github.com/acme/payments"}
    assert {p.parent.name for p in hub_files(_vault())} == {"github.com-acme-payments"}


@pytest.mark.acceptance(
    spec="memory", scenario="a memory from a scratch directory is not published"
)
async def test_a_memory_from_a_scratch_directory_is_not_published(tmp_path: pathlib.Path) -> None:
    scratch = tmp_path / "Documents" / "Codex" / "2026-10-01" / "topic"
    scratch.mkdir(parents=True)
    a = Machine("machine-a", tmp_path / "a")
    cc_project(a.claude(), scratch, {"p.md": cc_file("A trap", "Something", "project", "body")})
    await a.sync()
    assert hub_files(_vault()) == []


@pytest.mark.acceptance(spec="memory", scenario="a path follows the repository to another machine")
async def test_a_path_follows_the_repository_to_another_machine(tmp_path: pathlib.Path) -> None:
    upstream = init_repository(tmp_path / "upstream")
    one = tmp_path / "a-home" / "src" / "payments"
    other = tmp_path / "b-home" / "work" / "pay"
    for path, url in (
        (one, "git@github.com:acme/payments.git"),
        (other, "https://github.com/acme/payments"),
    ):
        git("clone", "-q", str(upstream), str(path), cwd=tmp_path)
        git("remote", "set-url", "origin", url, cwd=path)
    a = Machine("machine-a", tmp_path / "ma", home=str(tmp_path / "a-home"))
    body = f"See {one}/ledger/retry.py and {tmp_path / 'a-home'}/.config/tool.toml."
    cc_project(
        a.claude(),
        one,
        {"p.md": cc_file("Retry lives in ledger", "Where retry is", "project", body)},
    )
    b = Machine("machine-b", tmp_path / "mb", home=str(tmp_path / "b-home"))
    b_cc = b.claude()
    cc_project(b_cc, other, {})
    await a.sync()
    await b.sync()

    (entry,) = _entries()
    assert "<repo>/ledger/retry.py" in entry.body
    assert "~/.config/tool.toml" in entry.body
    copies = list((b_cc / "projects").rglob("coffer_*.md"))
    assert len(copies) == 1
    text = copies[0].read_text(encoding="utf-8")
    assert f"{other}/ledger/retry.py" in text
    assert f"{tmp_path / 'b-home'}/.config/tool.toml" in text


@pytest.mark.acceptance(spec="memory", scenario="a memory the agent changed updates its hub entry")
async def test_a_memory_the_agent_changed_updates_its_hub_entry(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    codex = a.codex(
        memory_md=codex_memory([("Payments", str(payments), ["Use uv sync --frozen."])])
    )
    await a.sync()
    (before,) = _entries()

    (codex / "memories" / "MEMORY.md").write_text(
        codex_memory([("Payments", str(payments), ["Use uv sync --frozen --no-dev in CI."])]),
        encoding="utf-8",
    )
    a.service._now = lambda: "2026-10-10T00:00:00Z"  # type: ignore[method-assign]
    await a.sync()
    (after,) = _entries()
    assert after.id == before.id
    assert after.body == "Use uv sync --frozen --no-dev in CI."
    assert after.updated_at != before.updated_at


@pytest.mark.acceptance(spec="memory", scenario="a memory the agent dropped leaves the hub")
async def test_a_memory_the_agent_dropped_leaves_the_hub(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    memory = cc_project(a.claude(), payments, {"p.md": cc_file("T", "D", "project", "B")})
    await a.sync()
    assert len(hub_files(_vault())) == 1
    (memory / "p.md").unlink()
    await a.sync()
    assert hub_files(_vault()) == []


@pytest.mark.acceptance(spec="memory", scenario="another machine's entry is left alone")
async def test_another_machines_entry_is_left_alone(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    cc_project(a.claude(), payments, {"p.md": cc_file("T", "D", "project", "B")})
    await a.sync()
    (path,) = hub_files(_vault())
    before = path.read_bytes()

    b = Machine("machine-b", tmp_path / "b")
    b.claude()
    await b.sync()
    assert path.read_bytes() == before


@pytest.mark.acceptance(spec="memory", scenario="a memory holding a token is withheld")
async def test_a_memory_holding_a_token_is_withheld(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    token = "sk-proj-" + "Ab3dE6gH9jK2mN5pQ8sT1vW4yZ7bC0eF3hJ6kL9nP2rS5uX8"
    memory = cc_project(
        a.claude(),
        payments,
        {"key.md": cc_file("API key", "The key", "reference", f"OPENAI_API_KEY={token}")},
    )
    await a.service.sync("user")
    assert hub_files(_vault()) == []
    ((event, _actor, details),) = a.audit.events
    assert event == "memory_synced"
    assert details["withheld"] == [{"agent": "cc", "path": str(memory / "key.md")}]
    assert token not in str(details)
