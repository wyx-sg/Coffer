"""Unit tests for the pure envelope-parsing helpers in gateway_parsing.py."""

from __future__ import annotations

from coffer.application.mcp.gateway_parsing import _extract_agent_uid, _extract_cwd

# A uid is an opaque uuid4 hex; spelled out here so the assertions read like the
# wire does rather than like a name.
_UID = "9f2c41a0b7d94e6a8c1f35b2d07ae914"


def test_extract_agent_uid_reads_meta_key():
    """MCP Gateway "Take the agent identity from the handshake": the shim
    stamps its bound agent's UID into ``params._meta["coffer/agent-uid"]`` at
    the initialize handshake."""
    assert _extract_agent_uid({"_meta": {"coffer/agent-uid": _UID}}) == _UID


def test_extract_agent_uid_absent_meta_returns_none():
    assert _extract_agent_uid({}) is None


def test_extract_agent_uid_meta_present_without_agent_key_returns_none():
    assert _extract_agent_uid({"_meta": {"coffer/cwd": "/p"}}) is None


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
