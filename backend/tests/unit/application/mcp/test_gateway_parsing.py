"""Unit tests for the pure envelope-parsing helpers in gateway_parsing.py."""

from __future__ import annotations

from coffer.application.mcp.gateway_parsing import _extract_agent_uid, _extract_cwd

# A uid is an opaque uuid4 hex; spelled out here so the assertions read like the
# wire does rather than like a name.
_UID = "9f2c41a0b7d94e6a8c1f35b2d07ae914"


def test_extract_agent_uid_reads_meta_key():
    """MCP Gateway FR-013 (amended): the shim stamps its bound agent's UID into
    ``params._meta["coffer/agent-uid"]`` at the initialize handshake."""
    assert _extract_agent_uid({"_meta": {"coffer/agent-uid": _UID}}) == _UID


def test_extract_agent_uid_absent_meta_returns_none():
    assert _extract_agent_uid({}) is None


def test_extract_agent_uid_meta_present_without_agent_key_returns_none():
    assert _extract_agent_uid({"_meta": {"coffer/cwd": "/p"}}) is None


def test_extract_agent_uid_ignores_the_retired_name_shaped_key():
    """A shim installed by an older Coffer stamps ``coffer/agent`` with a NAME.
    There is no fallback to it (ADR resource-identity-is-an-immutable-uid): the
    scope it would be compared against holds uids, so honouring the old key
    could only match the wrong thing or nothing. Such a session is unidentified,
    which means it sees strictly less, never more."""
    assert _extract_agent_uid({"_meta": {"coffer/agent": "claude_code"}}) is None


def test_extract_agent_uid_ignores_non_string_value():
    assert _extract_agent_uid({"_meta": {"coffer/agent-uid": 123}}) is None


def test_extract_agent_uid_ignores_empty_string():
    assert _extract_agent_uid({"_meta": {"coffer/agent-uid": ""}}) is None


def test_extract_agent_uid_meta_not_a_dict_returns_none():
    assert _extract_agent_uid({"_meta": "not-a-dict"}) is None


def test_extract_cwd_and_agent_uid_coexist_independently():
    params = {"_meta": {"coffer/cwd": "/work/repo", "coffer/agent-uid": _UID}}
    assert _extract_cwd(params) == "/work/repo"
    assert _extract_agent_uid(params) == _UID
