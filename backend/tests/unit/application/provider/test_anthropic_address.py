"""Which Anthropic address an existing connection is given at startup (ADR
one-connection-serves-both-wires; spec provider-switching "Fill in the
Anthropic address of an existing connection"). Pure — unit tier."""

from __future__ import annotations

from typing import Any

import pytest

from coffer.application.provider.anthropic_address import anthropic_address_for
from coffer.domain.provider.config import ProviderConfig


def _cfg(**over: Any) -> ProviderConfig:
    data: dict[str, Any] = {
        "protocol": "openai",
        "base_url": "https://gw.example/v1",
        "secret_ref": "provider/x/key",
    }
    data.update(over)
    return ProviderConfig.model_validate(data)


@pytest.mark.acceptance(
    spec="provider-switching", scenario="a gateway Claude Code runs on keeps working"
)
def test_a_gateway_claude_code_runs_on_gets_its_own_base_url() -> None:
    assert (
        anthropic_address_for(_cfg(), claude_code_on_it=True, codex_on_it=True)
        == "https://gw.example/v1"
    )


def test_a_gateway_nothing_runs_on_is_left_for_the_person() -> None:
    assert anthropic_address_for(_cfg(), claude_code_on_it=False, codex_on_it=True) is None
    assert anthropic_address_for(_cfg(), claude_code_on_it=False, codex_on_it=False) is None


@pytest.mark.acceptance(
    spec="provider-switching", scenario="a DeepSeek connection gets DeepSeek's Anthropic address"
)
def test_a_known_vendor_gets_its_anthropic_root() -> None:
    ds = _cfg(base_url="https://api.deepseek.com/")
    for claude_code in (True, False):
        assert (
            anthropic_address_for(ds, claude_code_on_it=claude_code, codex_on_it=False)
            == "https://api.deepseek.com/anthropic"
        )


def test_a_known_vendor_codex_runs_on_is_not_moved_under_it() -> None:
    # The new address waits for approval; Codex would wait with it.
    ds = _cfg(base_url="https://api.deepseek.com")
    assert anthropic_address_for(ds, claude_code_on_it=False, codex_on_it=True) is None


def test_a_connection_with_an_address_or_another_wire_is_left_alone() -> None:
    has = _cfg(anthropic_base_url="https://gw.example")
    assert anthropic_address_for(has, claude_code_on_it=True, codex_on_it=False) is None
    anthropic = _cfg(protocol="anthropic")
    assert anthropic_address_for(anthropic, claude_code_on_it=True, codex_on_it=True) is None
