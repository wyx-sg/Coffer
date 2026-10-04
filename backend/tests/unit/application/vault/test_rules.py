"""The validator's rules for resource files and state documents
(coffer.application.vault.resource_rules / state_rules)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from coffer.application.mcp.kind import make_mcp_kind
from coffer.application.vault.resource_rules import resource_rule
from coffer.application.vault.state_rules import state_rule
from coffer.domain.resource import Kind
from coffer.domain.skill.frontmatter import validate_frontmatter_name
from coffer.domain.vault.findings import FindingCode, Severity
from coffer.domain.vault.writes import Change


class _Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    colour: str


class _Open(BaseModel):
    model_config = ConfigDict(extra="allow")


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


def test_an_unknown_top_level_field_is_a_warning_not_a_refusal() -> None:
    data = _doc(extra=1)
    verdict = _judge([Change("resources/widget/w.json", data, None)])
    assert [f.code for f in verdict.findings] == [FindingCode.UNKNOWN_FIELD]
    assert all(f.severity is Severity.WARNING for f in verdict.findings)


def test_a_config_key_the_schema_does_not_declare_is_refused() -> None:
    data = _doc(config={"colour": "b", "shade": "x"})
    verdict = _judge([Change("resources/widget/w.json", data, None)])
    [finding] = verdict.findings
    assert finding.code is FindingCode.CONFIG_INVALID and "'shade'" in finding.message
    assert finding.severity is Severity.ERROR


def test_a_retired_agent_config_key_is_accepted_and_ignored() -> None:
    from coffer.domain.agent.config import AgentConfig

    kinds = {"agent": Kind(name="agent", display_name="Agent", config_schema=AgentConfig)}
    rule = resource_rule(kinds, lambda: {})

    def judge(config: dict[str, Any]):  # type: ignore[no-untyped-def]
        data = _doc(kind="agent", config=config)
        return rule([Change("resources/agent/w.json", data, None)], _Tree())

    assert judge({"type": "claude_code", "effort": "high"}).findings == []
    [finding] = judge({"type": "claude_code", "shade": "x"}).findings
    assert finding.code is FindingCode.CONFIG_INVALID and "'shade'" in finding.message


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


def test_the_cli_tools_document_is_checked_for_its_shape() -> None:
    rule = state_rule()
    path = "state/cli-tools/tools.json"

    def codes(doc: bytes) -> list[FindingCode]:
        return [f.code for f in rule([Change(path, doc, None)], _Tree()).findings]

    assert codes(b'{"format_version": 1, "tools": [{"command": "jq", "title": null}]}') == []
    assert codes(b'{"tools": {"jq": 1}}') == [FindingCode.INVALID_DOCUMENT]
    assert codes(b'{"tools": [{"title": "no command"}]}') == [FindingCode.INVALID_DOCUMENT]
    assert codes(b'{"tools": [{"command": "jq"}, {"command": "jq"}]}') == [
        FindingCode.INVALID_DOCUMENT
    ]
    assert codes(b'{"tools": [], "extra": 1}') == [FindingCode.UNKNOWN_FIELD]


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


def test_a_file_is_held_to_the_kinds_own_name_rules() -> None:
    """A hand edit or a merge meets the same name rule a register does: an
    ``mcp_server`` name over 24 characters and a skill name with ``_`` are
    refused, not tolerated because the file arrived already named."""
    kinds = {
        "mcp_server": make_mcp_kind({}),
        "skill": Kind(
            name="skill",
            display_name="Skill",
            config_schema=_Open,
            validate_name=validate_frontmatter_name,
        ),
    }
    rule = resource_rule(kinds, dict)
    transport = {"transport": {"type": "stdio", "command": "x"}}
    long_name = "a" * 25
    server = _doc(kind="mcp_server", name=long_name, config=transport)
    skill = _doc(uid="u2", kind="skill", name="old_style", config={})
    verdict = rule(
        [
            Change(f"resources/mcp_server/{long_name}.json", server, None),
            Change("resources/skill/old_style.json", skill, None),
        ],
        _Tree(),
    )
    assert sorted((f.path, f.code) for f in verdict.findings) == [
        (f"resources/mcp_server/{long_name}.json", FindingCode.INVALID_DOCUMENT),
        ("resources/skill/old_style.json", FindingCode.INVALID_DOCUMENT),
    ]
    ok = _doc(kind="mcp_server", name="a" * 24, config=transport)
    assert rule([Change(f"resources/mcp_server/{'a' * 24}.json", ok, None)], _Tree()).findings == []


def test_a_title_on_a_kind_without_titles_is_refused() -> None:
    kinds = {
        "widget": Kind(name="widget", display_name="Widget", config_schema=_Config, titled=False)
    }
    rule = resource_rule(kinds, dict)
    titled = Change("resources/widget/w.json", _doc(title="Pretty"), None)
    [finding] = rule([titled], _Tree()).findings
    assert finding.code is FindingCode.INVALID_DOCUMENT and "no title" in finding.message
    assert rule([Change("resources/widget/w.json", _doc(), None)], _Tree()).findings == []
