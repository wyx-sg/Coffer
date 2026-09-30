"""Local state files and the composite validator."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from coffer.application.vault.validation import VaultValidator
from coffer.domain.vault.findings import Finding, FindingCode
from coffer.domain.vault.writes import Change, TreeReader, Verdict
from coffer.infrastructure.vault.json_store import JsonStore


def test_a_missing_file_reads_empty_and_an_update_writes_it(tmp_path: Path) -> None:
    store = JsonStore(tmp_path / "local" / "reach.json")
    assert store.read() == {}
    store.update(lambda d: d.__setitem__("u1", {"enabled": False}))
    assert store.read() == {"u1": {"enabled": False}}
    assert oct((tmp_path / "local" / "reach.json").stat().st_mode & 0o777) == "0o600"


def test_an_unreadable_file_is_moved_aside_not_lost(tmp_path: Path) -> None:
    path = tmp_path / "retention.json"
    path.write_text("{broken")
    assert JsonStore(path).read() == {}
    assert (tmp_path / "retention.json.unreadable-1").read_text() == "{broken"


def test_each_change_meets_the_rule_of_its_longest_prefix() -> None:
    seen: dict[str, list[str]] = {}

    def rule(name: str):  # type: ignore[no-untyped-def]
        def judge(changes: Sequence[Change], _repo: TreeReader) -> Verdict:
            seen.setdefault(name, []).extend(c.path for c in changes)
            return Verdict(
                findings=[Finding(c.path, FindingCode.CONFIG_INVALID, name) for c in changes]
            )

        return judge

    validator = VaultValidator()
    validator.register("resources/", rule("resources"))
    validator.register("resources/skill/", rule("skill"))
    changes = [
        Change("resources/skill/a.json", b"{}", None),
        Change("resources/mcp_server/b.json", b"{}", None),
        Change("knowledge/c.md", b"x", None),
    ]
    verdict = validator(changes, None)  # type: ignore[arg-type]
    assert seen == {
        "skill": ["resources/skill/a.json"],
        "resources": ["resources/mcp_server/b.json"],
    }
    assert len(verdict.findings) == 2
