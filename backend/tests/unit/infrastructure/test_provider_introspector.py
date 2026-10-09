"""Provider introspector: protocol-keyed defaults + the loopback SSRF exemption.

No network. The adapter's ``provider`` argument is a DETECTED WIRE PROTOCOL
(``domain.provider.config.Protocol``), never a vendor id — every caller reaches
it through ``POST /api/v1/models/*``, whose ``provider`` field the connection
editors fill from the connection's ``protocol``. These tests lock both halves of
that: the default base URL is keyed by protocol, and a loopback base URL stays
exempt from the SSRF guard (which would otherwise break every local-model
connection) while the exemption follows the URL, never the declared protocol.
"""

from __future__ import annotations

import pytest

from coffer.domain.provider.config import Protocol
from coffer.infrastructure.provider.introspector import (
    PROTOCOL_BASE_URLS,
    ProviderIntrospector,
)


def test_base_url_defaults_are_keyed_by_protocol() -> None:
    # Every key is a real Protocol value, so no entry is unreachable.
    assert set(PROTOCOL_BASE_URLS) <= {p.value for p in Protocol}
    intro = ProviderIntrospector()
    assert intro._base_url("anthropic", None) == "https://api.anthropic.com"
    assert intro._base_url("ollama", None) is None  # retired: no default of its own
    assert intro._base_url("openai", None) is None  # the SDK's own default
    # An inconclusive probe has no default: the user's URL is the only truth.
    assert intro._base_url("unknown", None) is None
    # An explicit base URL always wins over the protocol default.
    assert intro._base_url("openai", "http://127.0.0.1:9999/v1") == "http://127.0.0.1:9999/v1"


async def test_a_loopback_runtime_is_exempt_from_the_ssrf_guard() -> None:
    """The regression this file exists for: a local-model connection must work.

    A local runtime's base URL is loopback, which the guard blocks outright, so the
    guard must not run for it — otherwise every local-model connection fails to
    list models or test.
    """
    intro = ProviderIntrospector()
    # A hand-typed loopback URL passes without raising.
    await intro._guard("openai", "http://localhost:11434/v1")
    await intro._guard("openai", "http://127.0.0.1:11434/v1")


async def test_the_exemption_follows_the_url_not_the_declared_protocol() -> None:
    """``provider`` is whatever the caller sent: labelling a metadata or LAN
    address as a local runtime must not switch the guard off."""
    intro = ProviderIntrospector()
    for url in ("http://169.254.169.254/latest", "http://10.0.0.5:11434/v1"):
        for provider in ("openai", ""):
            with pytest.raises(ValueError, match="SSRF"):
                await intro._guard(provider, url)


async def test_guard_is_a_no_op_without_a_url() -> None:
    # `_base_url` returns None for openai (SDK default); there is nothing to check.
    await ProviderIntrospector()._guard("openai", None)


def test_the_openai_client_answers_once_without_retrying() -> None:
    # A probe is waited on with a spinner: the SDK's default retries turned one
    # slow model into three timeouts back to back.
    client = ProviderIntrospector()._openai_client("https://api.example.com/v1", "k")
    assert client.max_retries == 0
    assert client.timeout == 30.0


@pytest.mark.acceptance(spec="provider-switching", scenario="a window the endpoint reports is kept")
def test_a_models_entry_reports_its_window_in_any_common_spelling() -> None:
    from coffer.infrastructure.provider.introspector import reported_window

    assert reported_window({"id": "claude-x", "max_input_tokens": 1_000_000}) == 1_000_000
    assert reported_window({"id": "or/x", "context_length": 163_840}) == 163_840
    assert reported_window({"id": "or/y", "top_provider": {"context_length": 65_536}}) == 65_536
    assert reported_window({"id": "vllm", "max_model_len": 32_768}) == 32_768
    # Nothing said, or nothing plausible: no window, never a guess.
    assert reported_window({"id": "gpt-x"}) is None
    assert reported_window({"id": "z", "context_length": "lots"}) is None
    assert reported_window({"id": "z", "context_length": True}) is None
    assert reported_window(None) is None
