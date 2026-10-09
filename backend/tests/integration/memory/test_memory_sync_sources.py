"""What the sync reads from (spec memory "Read no transcripts or rollouts",
"Read only registered agents' memory", "Skip unchanged sources").

Real agent directories, real readers and a real vault under the test's
``HOME``.
"""

from __future__ import annotations

import json
import os
import pathlib

import pytest

from coffer.application.memory.sync_report import SyncReport
from coffer.application.memory.sync_service import SYNC_RUN
from coffer.application.upkeep_runs import UPKEEP_RUNS
from coffer.infrastructure.memory.readers import MEMORY_READERS
from coffer.infrastructure.memory.readers.claude_code import ClaudeCodeMemoryReader
from coffer.infrastructure.memory.readers.codex import CodexMemoryReader
from tests.integration.memory._sync_harness import (
    Machine,
    cc_file,
    cc_project,
    codex_dir,
    codex_memory,
    hub_files,
)
from tests.integration.memory.conftest import init_repository


def _vault() -> pathlib.Path:
    return pathlib.Path(os.environ["HOME"]) / ".coffer" / "vault"


def _fact(title: str) -> str:
    return cc_file(title, f"{title}, briefly", "feedback", f"{title}.")


@pytest.fixture
def payments(tmp_path: pathlib.Path) -> pathlib.Path:
    return init_repository(tmp_path / "src" / "payments", remote="git@github.com:acme/payments.git")


@pytest.mark.acceptance(spec="memory", scenario="list no transcript or rollout as a source")
def test_no_transcript_or_rollout_is_listed_as_a_source(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    claude = tmp_path / "claude"
    # ``cc_project`` lays a session transcript beside the memory directory.
    memory = cc_project(claude, payments, {"feedback_a.md": _fact("Fact A")})
    assert list(memory.parent.glob("*.jsonl"))
    codex = codex_dir(
        tmp_path / "codex", codex_memory([("Payments", str(payments), ["Run make test"])])
    )
    rollouts = codex / "sessions" / "2026" / "10" / "09"
    rollouts.mkdir(parents=True)
    (rollouts / "rollout-2026-10-09T06-00-00.jsonl").write_text(
        json.dumps({"type": "session_meta"}) + "\n", encoding="utf-8"
    )
    (codex / "memories" / "raw_memories.md").write_text("- raw capture\n", encoding="utf-8")

    listed = [
        *(s.path for s in ClaudeCodeMemoryReader().sources(str(claude))),
        *(s.path for s in CodexMemoryReader().sources(str(codex))),
    ]

    assert listed
    assert not [p for p in listed if p.endswith(".jsonl") or "raw_memories" in p]
    assert all(pathlib.Path(p).name != "MEMORY.md" or "codex" in p for p in listed)


@pytest.mark.acceptance(spec="memory", scenario="read nothing from an unregistered agent")
async def test_an_unregistered_directory_is_never_read(
    tmp_path: pathlib.Path, payments: pathlib.Path
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    cc_project(a.claude(), payments, {"feedback_kept.md": _fact("Registered fact")})
    stray = tmp_path / "a" / "claude-unregistered"
    cc_project(stray, payments, {"feedback_stray.md": _fact("Stray fact")})

    await a.sync()

    titles = [p.read_text(encoding="utf-8") for p in hub_files(_vault())]
    assert len(titles) == 1
    assert "Registered fact" in titles[0]
    assert not any(str(stray) in path for path in a.service.ledger.load().sources)


@pytest.mark.acceptance(
    spec="memory", scenario="an unchanged source file is skipped on the next sync"
)
async def test_an_unchanged_source_is_not_read_again(
    tmp_path: pathlib.Path, payments: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = Machine("machine-a", tmp_path / "a")
    cc_project(a.claude(), payments, {"feedback_a.md": _fact("Fact A")})
    first = await a.sync()
    assert isinstance(first, SyncReport) and first.sources_read == 1
    before = hub_files(_vault())

    reader = next(r for r in MEMORY_READERS if r.agent_type == "claude_code")

    def _never(source: object) -> object:
        raise AssertionError("an unchanged source was read again")

    monkeypatch.setattr(reader, "read", _never)
    second = await a.sync()

    assert isinstance(second, SyncReport)
    assert (second.sources_read, second.sources_skipped, second.failures) == (0, 1, [])
    assert hub_files(_vault()) == before


async def test_a_running_sync_is_listed_among_the_passes_in_flight(
    tmp_path: pathlib.Path, payments: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``coffer daemon status`` reads the daemon's table of passes in flight
    (spec resource-framework "Report the passes in flight in one cross-kind
    read"): a sync is in it while it runs and gone once it ends."""
    a = Machine("machine-a", tmp_path / "a")
    cc_project(a.claude(), payments, {"feedback_a.md": _fact("Fact A")})
    reader = next(r for r in MEMORY_READERS if r.agent_type == "claude_code")
    seen: list[object] = []
    real = reader.sources

    def _sources(config_dir: str):  # type: ignore[no-untyped-def]
        seen.append(UPKEEP_RUNS.running(*SYNC_RUN))
        return real(config_dir)

    monkeypatch.setattr(reader, "sources", _sources)
    await a.sync()

    assert seen and all(run is not None for run in seen)
    assert UPKEEP_RUNS.running(*SYNC_RUN) is None
