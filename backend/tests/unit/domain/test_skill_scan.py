"""Unit tests for unmanaged-skill classification (domain/skill/scan.py) and
scan-location resolution (domain/agent/scan.py).

``scan_locations`` lives in ``coffer.domain.agent.scan`` — not in
``coffer.domain.skill.scan`` — because the import-linter contracts (Contract
5c in pyproject.toml) forbid ``coffer.domain.skill`` from importing
``coffer.domain.agent``.  All other symbols originate from
``coffer.domain.skill.scan``.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.agent.scan import scan_locations
from coffer.domain.agent.types import AgentType
from coffer.domain.skill.scan import ScanEntry, classify

MASTER = pathlib.Path("/home/u/.coffer/skills")


def _e(name: str, *, is_dir: bool = True, link_target: pathlib.Path | None = None) -> ScanEntry:
    return ScanEntry(
        name=name,
        path=pathlib.Path("/cfg/skills") / name,
        is_dir=is_dir,
        link_target=link_target,
    )


def test_classify_excludes_managed_and_system() -> None:
    entries = [
        _e("managed", link_target=MASTER / "managed"),
        _e(".system"),
        _e("handmade"),
        _e("foreign-link", link_target=pathlib.Path("/elsewhere/skill")),
        _e("stray-file", is_dir=False),
    ]
    out = classify(entries, master_root=MASTER)
    by = {u.name: u for u in out}
    assert set(by) == {"handmade", "foreign-link"}
    assert by["handmade"].foreign_link is False
    assert by["foreign-link"].foreign_link is True


def test_classify_nested_master_target_is_managed() -> None:
    # link to a SUBPATH of the master store still counts as managed
    out = classify([_e("deep", link_target=MASTER / "deep" / "sub")], master_root=MASTER)
    assert out == []


def test_classify_preserves_order() -> None:
    out = classify([_e("b"), _e("a")], master_root=MASTER)
    assert [u.name for u in out] == ["b", "a"]


def test_scan_locations_per_type() -> None:
    cfg = pathlib.Path("/home/u/.codex")
    locs = scan_locations(AgentType.CODEX, cfg, home=pathlib.Path("/home/u"))
    assert locs == [cfg / "skills", pathlib.Path("/home/u/.agents/skills")]
    locs2 = scan_locations(
        AgentType.CLAUDE_CODE, pathlib.Path("/home/u/.claude"), home=pathlib.Path("/home/u")
    )
    assert locs2 == [pathlib.Path("/home/u/.claude/skills")]


def test_scan_locations_defaults_home_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", "/home/envuser")
    locs = scan_locations(AgentType.CODEX, pathlib.Path("/home/envuser/.codex"))
    assert locs[-1] == pathlib.Path("/home/envuser/.agents/skills")


def test_classify_file_shaped_foreign_link_listed() -> None:
    out = classify(
        [_e("filelink", is_dir=False, link_target=pathlib.Path("/elsewhere/f"))],
        master_root=MASTER,
    )
    assert [(u.name, u.foreign_link) for u in out] == [("filelink", True)]


def test_classify_rejects_relative_paths() -> None:
    import pytest

    with pytest.raises(ValueError):
        classify([], master_root=pathlib.Path("rel"))
    with pytest.raises(ValueError):
        classify([_e("x", link_target=pathlib.Path("rel/target"))], master_root=MASTER)
