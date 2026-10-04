"""A join's differing file shows what taking the other side changes here
(spec vault-sync "Join a new machine by taking the union"; board 6.5.19)."""

from __future__ import annotations

from pathlib import Path

from .harness import fleet

DOC = "knowledge/team/x.md"


def test_a_join_choice_has_the_take_theirs_diff(tmp_path: Path) -> None:
    mac, mini = fleet(tmp_path, "Mac", "Mini")
    mac.put(DOC, "Escalate after 15 min.\n")
    mac.run(mac.service.join())
    mini.put(DOC, "Escalate after 30 min.\n")
    mini.run(mini.service.join())
    assert [c.path for c in mini.run(mini.service.join_choices())] == [DOC]
    found = mini.run(mini.service.file_versions(DOC))
    assert found is not None
    assert (found.ours, found.theirs) == ("Escalate after 30 min.\n", "Escalate after 15 min.\n")
    assert "-Escalate after 30 min." in found.take_theirs
    assert "+Escalate after 15 min." in found.take_theirs
    assert mini.run(mini.service.file_versions("knowledge/team/none.md")) is None
