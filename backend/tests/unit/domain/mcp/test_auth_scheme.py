"""A secret header stores the credential alone; its slot names the scheme
(spec mcp-gateway "Support stdio and HTTP upstreams"). Every value
here is made up."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from coffer.application.mcp.custom_tools import split_headers
from coffer.application.secret.plaintext_move import Finding, Hit, _credential, _with_refs
from coffer.domain.agent.mcp_entries import McpEntry, to_transport_config
from coffer.domain.auth_scheme import header_value, split_scheme, with_schemes
from coffer.domain.mcp.http_api import HttpApiTool, HttpApiTransport
from coffer.domain.mcp.server_config import HttpTransport
from coffer.infrastructure.mcp.http_api_client import build_request

KEY = "fake-postman-key-0123456789"


def _finding(fid: str, key: str, field: str) -> Finding:
    return Finding(
        id=fid,
        source="mcp_server",
        resource="pm",
        resource_uid=None,
        path=None,
        line=None,
        field=field,
        key=key,
        proposed_name=None,
        rule="coffer-server-setting",
    )


@pytest.mark.parametrize(
    ("pasted", "expected"),
    [
        (f"Bearer {KEY}", ("Bearer", KEY)),
        (f"bearer   {KEY} ", ("Bearer", KEY)),
        (f"Token {KEY}", ("Token", KEY)),
        (KEY, (None, KEY)),
        ("Basic dXNlcjpwYXNz", (None, "Basic dXNlcjpwYXNz")),
        ("Bearer", (None, "Bearer")),
    ],
)
def test_a_pasted_value_splits_into_scheme_and_credential(
    pasted: str, expected: tuple[str | None, str]
) -> None:
    assert split_scheme(pasted) == expected


def test_a_slot_sends_its_scheme_in_front_of_the_credential() -> None:
    assert header_value("Bearer", KEY) == f"Bearer {KEY}"
    assert header_value(None, KEY) == KEY
    assert with_schemes({"Authorization": KEY, "X-Api-Key": KEY}, {"Authorization": "Bearer"}) == {
        "Authorization": f"Bearer {KEY}",
        "X-Api-Key": KEY,
    }


@pytest.mark.acceptance(spec="mcp-gateway", scenario="a secret header is sent behind its scheme")
def test_a_custom_tool_request_carries_the_scheme() -> None:
    transport = HttpApiTransport(
        base_url="https://api.example.com",  # type: ignore[arg-type]
        secret_refs={"Authorization": "secret/" + "c3" * 16},
        auth_schemes={"Authorization": "Bearer"},
        tools=[HttpApiTool(name="me", method="GET", path="/me")],
    )
    request = build_request(
        transport, transport.environments[0], transport.tools[0], {}, {"Authorization": KEY}
    )
    assert request.headers["Authorization"] == f"Bearer {KEY}"


def test_a_scheme_is_set_only_on_a_secret_header() -> None:
    with pytest.raises(ValidationError, match="only on a secret header"):
        HttpTransport(
            url="https://mcp.example.com",  # type: ignore[arg-type]
            headers={"X-Team": "a"},
            auth_schemes={"X-Team": "Bearer"},
        )
    with pytest.raises(ValidationError):
        HttpTransport(
            url="https://mcp.example.com",  # type: ignore[arg-type]
            secret_refs={"Authorization": "secret/" + "c3" * 16},
            auth_schemes={"Authorization": "Basic"},  # type: ignore[dict-item]
        )


def test_a_slot_without_a_scheme_sends_its_secret_as_is() -> None:
    """A config saved before schemes existed keeps working unchanged."""
    t = HttpTransport.model_validate(
        {"url": "https://mcp.example.com", "secret_refs": {"Authorization": "secret/" + "c3" * 16}}
    )
    assert t.auth_schemes == {}
    assert with_schemes({"Authorization": f"Bearer {KEY}"}, t.auth_schemes) == {
        "Authorization": f"Bearer {KEY}"
    }


def test_a_custom_tool_header_row_keeps_its_scheme() -> None:
    plain, refs, schemes = split_headers(
        [
            {"name": "Authorization", "secret": "c3" * 16, "scheme": "Bearer"},
            {"name": "X-Team", "value": "a"},
        ]
    )
    assert plain == {"X-Team": "a"}
    assert refs == {"Authorization": "secret/" + "c3" * 16}
    assert schemes == {"Authorization": "Bearer"}


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="an adopted Bearer header stores the key alone"
)
def test_an_adopted_bearer_header_keeps_the_scheme_on_the_slot() -> None:
    entry = McpEntry(
        name="pm",
        source="global",
        transport="http",
        url="https://mcp.example.com",
        headers={"Authorization": f"Bearer {KEY}", "X-Team": "a"},
    )
    cfg = to_transport_config(entry, {"Authorization": "mcp/x/pm/Authorization"})
    assert cfg["auth_schemes"] == {"Authorization": "Bearer"}
    assert cfg["headers"] == {"X-Team": "a"}
    assert KEY not in str(cfg)


def test_a_moved_header_keeps_its_scheme_and_an_env_value_stays_whole() -> None:
    header = Hit(
        _finding("h", "Authorization", "header"),
        value=f"Bearer {KEY}",
    )
    env = Hit(
        _finding("e", "TOKEN", "env"),
        value=f"Bearer {KEY}",
    )
    config = {
        "transport": {
            "type": "http",
            "url": "https://mcp.example.com",
            "headers": {"Authorization": f"Bearer {KEY}"},
        }
    }
    moved = _with_refs(config, [header], {"h": "secret/" + "c3" * 16})
    assert moved["transport"]["auth_schemes"] == {"Authorization": "Bearer"}
    assert moved["transport"]["headers"] == {}
    assert _credential(header) == ("Bearer", KEY)
    assert _credential(env) == (None, f"Bearer {KEY}")
