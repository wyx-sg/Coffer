"""The hand-offs for skill drift no pass settles (spec skill-manager "Hand
unsettled skill drift to an agent with a prompt").

A folder in the way, a folder no skill owns and a missing master each carry a
prompt on the drift report and on the attention item, and it is the same
text on both, built from the finding alone. A drift kind a pass repairs
carries none, and the attention reason names no command.
"""

from __future__ import annotations

import pathlib
import re
import shutil

import pytest

from coffer.application.reconcile.attention_source import DriftAttentionSource
from coffer.application.skill import drift_view
from coffer.domain.skill.drift import DriftKind
from tests.support.skills import build_skill_graph, write_skill_folder

pytestmark = pytest.mark.asyncio

_COMMAND = re.compile(r"`?coffer [a-z]|\bbrew\b|in a terminal")


async def _delivered(tmp_path: pathlib.Path):
    graph = await build_skill_graph(tmp_path, hooks=False)
    _agent, skill_dir = await graph.register_agent(tmp_path, name="cur")
    await graph.import_skill(tmp_path, "s1")
    link = skill_dir / "s1"
    assert link.is_symlink()
    return graph, link


async def _attention(graph) -> dict[str, object]:
    return {i.reason_code: i for i in await DriftAttentionSource(graph.reconciler).items()}


@pytest.mark.acceptance(
    spec="skill-manager", scenario="a folder in the way is handed to an agent to compare"
)
async def test_a_folder_in_the_way_hands_the_compare_to_an_agent(tmp_path):
    graph, link = await _delivered(tmp_path)
    master = graph.store.paths_for("s1").folder
    link.unlink()
    link.mkdir()
    (link / "mine.txt").write_text("user data", encoding="utf-8")

    [entry] = (await drift_view.verify(graph.skills, graph.reconciler)).entries
    assert entry.kind is DriftKind.REPLACED_WITH_REGULAR
    prompt = entry.handoff
    assert prompt is not None
    assert str(link) in prompt and str(master) in prompt
    assert "Adopt this folder" in prompt and "Replace it with Coffer's link" in prompt
    assert "Do not move, delete or edit any folder yourself" in prompt
    # The attention item hands over the same words, and its reason is command-free.
    item = (await _attention(graph))["foreign_content"]
    assert item.handoff == prompt
    assert not _COMMAND.search(item.reason), item.reason
    # Handing it off changed nothing on disk.
    assert (link / "mine.txt").read_text(encoding="utf-8") == "user data"
    await graph.dispose()


@pytest.mark.acceptance(
    spec="skill-manager", scenario="a missing master is handed to an agent to find a copy"
)
async def test_a_missing_master_hands_the_search_to_an_agent(tmp_path):
    graph, _link = await _delivered(tmp_path)
    master = graph.store.paths_for("s1").folder
    shutil.rmtree(master)

    entries = (await drift_view.verify(graph.skills, graph.reconciler)).entries
    [entry] = [e for e in entries if e.kind is DriftKind.MISSING_MASTER]
    prompt = entry.handoff
    assert prompt is not None
    assert str(master) in prompt
    assert str(master.parent.parent / "backup" / "skills") in prompt
    assert "coffer skill show s1 --json" in prompt
    assert "copy (don't move)" in prompt
    item = (await _attention(graph))[DriftKind.MISSING_MASTER.value]
    assert item.handoff == prompt
    assert not _COMMAND.search(item.reason), item.reason
    await graph.dispose()


async def test_an_orphan_folder_hands_the_look_to_an_agent(tmp_path):
    graph = await build_skill_graph(tmp_path, hooks=False)
    src = write_skill_folder(tmp_path / "orphan-src", name="orphan")
    graph.store.copy_in(src=src, name="orphan", meta={"name": "orphan"})
    folder = graph.store.paths_for("orphan").folder

    [entry] = (await drift_view.verify(graph.skills, graph.reconciler)).entries
    assert entry.kind is DriftKind.ORPHAN_MASTER
    assert entry.handoff is not None
    assert str(folder) in entry.handoff and "Add to library" in entry.handoff
    item = (await _attention(graph))[DriftKind.ORPHAN_MASTER.value]
    assert item.handoff == entry.handoff
    assert not _COMMAND.search(item.reason), item.reason
    await graph.dispose()


async def test_a_missing_link_is_not_handed_off(tmp_path):
    graph, link = await _delivered(tmp_path)
    link.unlink()

    [entry] = (await drift_view.verify(graph.skills, graph.reconciler)).entries
    assert (entry.kind, entry.handoff) == (DriftKind.MISSING_LINK, None)
    await graph.dispose()
