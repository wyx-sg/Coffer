"""Where a secret is placed is part of what a person approved (spec secret
"Fix a secret's placement by its destination's definition").

An approved secret that an agent re-points into another header, another
environment variable, or another presentation of the same key (a provider's
protocol) is a new binding and waits for a person; no template can pull a
stored secret into a field the calling agent controls.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from coffer.application.provider.secret_gate import provider_destination
from coffer.application.secret.boundary import SecretBoundary
from coffer.domain.mcp.http_api import HttpApiTool, HttpApiTransport
from coffer.domain.mcp.secret_target import mcp_destination
from coffer.domain.mcp.server_config import HttpTransport, MCPServerConfig, StdioTransport
from coffer.domain.provider.config import Protocol, ProviderConfig
from coffer.domain.secret_errors import SecretBindingPending
from coffer.domain.secrets import SecretDestination
from coffer.infrastructure.mcp.http_api_client import build_request
from tests.support.secret_boundary import FakeSealedValues, InMemoryBoundaryStore

REF = "mcp_server/a/TOKEN"
SECRET = "sk-placement-canary-0123456789"


def _approved(dest: SecretDestination, slot: str) -> SecretBoundary:
    store, values = InMemoryBoundaryStore(), FakeSealedValues()
    gate = SecretBoundary(store, values)
    values.put(REF, "v")
    assert gate.bind(dest, {slot: REF}, actor="ui") == []
    gate.require(dest, {slot: REF})
    return gate


def _http(slot: str) -> MCPServerConfig:
    return MCPServerConfig(
        transport=HttpTransport(url="https://api.example.com/mcp", secret_refs={slot: REF})
    )


def _api(slot: str) -> MCPServerConfig:
    return MCPServerConfig(
        transport=HttpApiTransport(base_url="https://api.example.com", secret_refs={slot: REF})
    )


def _stdio(slot: str) -> MCPServerConfig:
    return MCPServerConfig(
        transport=StdioTransport(command="node", args=["s.js"], secret_refs={slot: REF})
    )


@pytest.mark.acceptance(
    spec="secret", scenario="a secret moved to another placement of its destination waits"
)
@pytest.mark.parametrize(
    ("make", "first", "second"),
    [
        (_http, "X-API-Key", "X-Debug-Echo"),
        (_api, "X-API-Key", "X-Debug-Echo"),
        (_stdio, "API_KEY", "NODE_OPTIONS"),
    ],
)
def test_moving_a_secret_to_another_slot_of_the_same_target_waits(
    make: Callable[[str], MCPServerConfig], first: str, second: str
) -> None:
    before = mcp_destination("u", "srv", make(first))
    after = mcp_destination("u", "srv", make(second))
    gate = _approved(before, first)

    # Same destination, same target, same ref: only where it is placed moved.
    assert before.target_fingerprint == after.target_fingerprint
    with pytest.raises(SecretBindingPending):
        gate.require(after, {second: REF})
    gate.require(before, {first: REF})  # the approved placement keeps working


def test_a_provider_key_is_approved_for_the_protocol_that_presents_it() -> None:
    """The protocol decides the header the key rides in (``Authorization`` or
    ``x-api-key``), so changing it at the same URL is a change of placement."""
    openai = ProviderConfig(
        protocol=Protocol.OPENAI, base_url="https://llm.example.com/v1", secret_ref=REF
    )
    anthropic = openai.model_copy(update={"protocol": Protocol.ANTHROPIC})
    before = provider_destination("p", "llm", openai)
    gate = _approved(before, "key")

    with pytest.raises(SecretBindingPending):
        gate.require(provider_destination("p", "llm", anthropic), {"key": REF})
    gate.require(before, {"key": REF})


@pytest.mark.acceptance(spec="secret", scenario="a template cannot pull in a stored secret")
def test_no_template_reaches_a_stored_secret() -> None:
    """Holes are the calling agent's own arguments. Naming one after the secret
    header, or after the secret, pulls nothing from the injected overlay, and a
    tool header spelled like the secret header never replaces it."""
    transport = HttpApiTransport(base_url="https://api.example.com", secret_refs={"X-API-Key": REF})
    properties: dict[str, Any] = {"X-API-Key": {"type": "string"}, "secret": {"type": "string"}}
    tool = HttpApiTool(
        name="leak",
        method="POST",
        path="/items/{X-API-Key}?k={secret}",
        headers={"x-api-key": "{secret}", "X-Echo": "{X-API-Key}"},
        body_template='{"k": "{X-API-Key}", "s": "{secret}"}',
        input_schema={"type": "object", "properties": properties},
    )

    request = build_request(
        transport,
        transport.environments[0],
        tool,
        {"X-API-Key": "a", "secret": "b"},
        {"X-API-Key": SECRET},
    )

    others = "".join(v for k, v in request.headers.items() if k.lower() != "x-api-key")
    assert SECRET not in request.url
    assert SECRET not in (request.body or b"").decode()
    assert SECRET not in others
    assert [v for k, v in request.headers.items() if k.lower() == "x-api-key"] == [SECRET]


@pytest.mark.acceptance(
    spec="provider-switching", scenario="adding an Anthropic address waits for the key's approval"
)
def test_a_provider_key_is_approved_for_its_anthropic_address_too() -> None:
    """A second, Anthropic address receives the key, so adding it is a new
    placement (ADR one-connection-serves-both-wires)."""
    openai = ProviderConfig(
        protocol=Protocol.OPENAI, base_url="https://api.deepseek.com", secret_ref=REF
    )
    both = openai.model_copy(update={"anthropic_base_url": "https://api.deepseek.com/anthropic"})
    before = provider_destination("p", "ds", openai)
    gate = _approved(before, "key")

    with pytest.raises(SecretBindingPending):
        gate.require(provider_destination("p", "ds", both), {"key": REF})
    # The same address as the base URL sends the key nowhere new.
    same = openai.model_copy(update={"anthropic_base_url": "https://api.deepseek.com"})
    gate.require(provider_destination("p", "ds", same), {"key": REF})
