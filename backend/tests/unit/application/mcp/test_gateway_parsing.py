"""Unit tests for the pure envelope-parsing helpers in gateway_parsing.py."""

from __future__ import annotations

from coffer.application.mcp.gateway_parsing import _extract_agent, _extract_cwd


def test_extract_agent_reads_meta_key():
    """Spec 001 FR-021 (amended): the shim stamps its bound agent's name into
    ``params._meta["coffer/agent"]`` at the initialize handshake."""
    assert _extract_agent({"_meta": {"coffer/agent": "claude_code"}}) == "claude_code"


def test_extract_agent_absent_meta_returns_none():
    assert _extract_agent({}) is None


def test_extract_agent_meta_present_without_agent_key_returns_none():
    assert _extract_agent({"_meta": {"coffer/cwd": "/p"}}) is None


def test_extract_agent_ignores_non_string_value():
    assert _extract_agent({"_meta": {"coffer/agent": 123}}) is None


def test_extract_agent_ignores_empty_string():
    assert _extract_agent({"_meta": {"coffer/agent": ""}}) is None


def test_extract_agent_meta_not_a_dict_returns_none():
    assert _extract_agent({"_meta": "not-a-dict"}) is None


def test_extract_cwd_and_agent_coexist_independently():
    params = {"_meta": {"coffer/cwd": "/work/repo", "coffer/agent": "codex"}}
    assert _extract_cwd(params) == "/work/repo"
    assert _extract_agent(params) == "codex"
