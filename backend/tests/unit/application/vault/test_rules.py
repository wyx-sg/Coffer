"""The validator's rules for resource files and state documents
(coffer.application.vault.resource_rules / state_rules)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from coffer.application.vault.resource_rules import resource_rule
from coffer.application.vault.state_rules import state_rule
from coffer.domain.resource import Kind
from coffer.domain.vault.findings import FindingCode, Severity
from coffer.domain.vault.writes import Change


class _Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    colour: str


KINDS = {"widget": Kind(name="widget", display_name="Widget", config_schema=_Config)}


class _Tree:
    def __init__(self, files: dict[str, bytes] | None = None) -> None:
        self.files = files or {}

    def read(self, ref: str, path: str) -> bytes | None:
        return self.files.get(path)

    def tree(self, ref: str = "HEAD", prefix: str = "") -> dict[str, str]:
        return {p: "blob" for p in self.files if p.startswith(prefix)}


def _doc(**fields: Any) -> bytes:
    base: dict[str, Any] = {"uid": "u1", "kind": "widget", "name": "w", "config": {"colour": "b"}}
    base.update(fields)
    return (json.dumps({k: v for k, v in base.items() if v is not None}) + "\n").encode()


def _judge(changes: list[Change], owners: dict[str, tuple[str, str, str]] | None = None):  # type: ignore[no-untyped-def]
    rule = resource_rule(KINDS, lambda: owners or {})
    return rule(changes, _Tree())


def test_a_valid_resource_file_has_no_findings() -> None:
    verdict = _judge([Change("resources/widget/w.json", _doc(), None)])
    assert verdict.findings == [] and verdict.fixes == []


def test_the_kind_must_match_its_directory() -> None:
    verdict = _judge([Change("resources/other/w.json", _doc(), None)])
    assert [f.code for f in verdict.findings] == [FindingCode.KIND_MISMATCH]


def test_unknown_fields_and_config_keys_are_warnings_not_refusals() -> None:
    data = _doc(extra=1, config={"colour": "b", "shade": "x"})
    verdict = _judge([Change("resources/widget/w.json", data, None)])
    assert {f.code for f in verdict.findings} == {FindingCode.UNKNOWN_FIELD}
    assert all(f.severity is Severity.WARNING for f in verdict.findings)


def test_an_unknown_kind_is_kept_with_a_warning() -> None:
    data = _doc(kind="newkind")
    verdict = _judge([Change("resources/newkind/w.json", data, None)])
    assert [f.severity for f in verdict.findings] == [Severity.WARNING]


def test_a_uid_held_elsewhere_is_a_duplicate_unless_that_path_goes_away() -> None:
    owners = {"u1": ("resources/widget/w.json", "widget", "w")}
    copy = Change("resources/widget/copy.json", _doc(name="copy"), None)
    assert [f.code for f in _judge([copy], owners).findings] == [FindingCode.DUPLICATE_UID]
    moved = [copy, Change("resources/widget/w.json", None, _doc())]
    assert _judge(moved, owners).findings == []


def test_a_name_another_resource_has_is_taken() -> None:
    owners = {"u9": ("resources/widget/w.json", "widget", "w")}
    change = Change("resources/widget/w2.json", _doc(uid="u1"), None)
    assert [f.code for f in _judge([change], owners).findings] == [FindingCode.NAME_TAKEN]


def test_a_file_without_a_uid_asks_for_one() -> None:
    verdict = _judge([Change("resources/widget/w.json", _doc(uid=None), None)])
    assert verdict.findings == []
    minted = json.loads(verdict.fixes[0].data)
    assert len(minted["uid"]) == 32 and minted["created_at"]


def test_a_newer_unreadable_format_is_refused_and_a_readable_one_warned() -> None:
    newer = _doc(format_version=3)
    assert [f.code for f in _judge([Change("resources/widget/w.json", newer, None)]).findings] == [
        FindingCode.NEWER_FORMAT
    ]
    readable = _doc(format_version=3, format_compat=1)
    codes = [f.code for f in _judge([Change("resources/widget/w.json", readable, None)]).findings]
    assert codes == [FindingCode.NEWER_FORMAT_READ_ONLY]


def test_an_invalid_config_is_refused() -> None:
    verdict = _judge([Change("resources/widget/w.json", _doc(config={"colour": 1}), None)])
    assert [f.code for f in verdict.findings] == [FindingCode.CONFIG_INVALID]


def test_state_documents_are_checked_for_their_shape_and_their_owner() -> None:
    rule = state_rule()
    good = b'{"server_uid": "s1", "format_version": 1, "disabled": {"tool": ["a"]}}'
    assert rule([Change("state/mcp-preferences/gh.json", good, None)], _Tree()).findings == []
    bad = b'{"server_uid": "s1", "disabled": {"tool": "a"}}'
    codes = [
        f.code for f in rule([Change("state/mcp-preferences/gh.json", bad, None)], _Tree()).findings
    ]
    assert codes == [FindingCode.INVALID_DOCUMENT]
    missing = b'{"peers": []}'
    codes = [
        f.code
        for f in rule([Change("state/channel-peers/c.json", missing, None)], _Tree()).findings
    ]
    assert codes == [FindingCode.MISSING_FIELD]
    tree = _Tree({"state/mcp-preferences/gh.json": good})
    second = Change("state/mcp-preferences/gh-2.json", good, None)
    assert [f.code for f in rule([second], tree).findings] == [FindingCode.DUPLICATE_UID]
    unknown_area = Change("state/elsewhere/x.json", b'{"anything": 1}', None)
    assert rule([unknown_area], _Tree()).findings == []


class _Flagged(BaseModel):
    flag: bool = False


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a file flagging a second internal default is refused by the vault",
)
def test_an_exclusive_flag_held_elsewhere_refuses_only_the_newcomer() -> None:
    kinds = {
        "thing": Kind(
            name="thing",
            display_name="Thing",
            config_schema=_Flagged,
            exclusive_flags=("flag",),
        )
    }
    held = _doc(kind="thing", uid="a", name="a", config={"flag": True})
    tree = _Tree({"resources/thing/a.json": held})
    rule = resource_rule(kinds, lambda: {"a": ("resources/thing/a.json", "thing", "a")})
    second = _doc(kind="thing", uid="b", name="b", config={"flag": True})
    verdict = rule([Change("resources/thing/b.json", second, None)], tree)
    assert [(f.path, f.code) for f in verdict.findings] == [
        ("resources/thing/b.json", FindingCode.CONFIG_INVALID)
    ]
    # Moving the flag in one change (clear a, set b) leaves one holder.
    cleared = _doc(kind="thing", uid="a", name="a", config={"flag": False})
    moved = rule(
        [
            Change("resources/thing/a.json", cleared, held),
            Change("resources/thing/b.json", second, None),
        ],
        tree,
    )
    assert moved.findings == []
