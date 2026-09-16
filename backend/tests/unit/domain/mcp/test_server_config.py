# backend/tests/unit/domain/mcp/test_server_config.py
import pytest
from pydantic import ValidationError

from coffer.domain.mcp.server_config import (
    HttpTransport,
    MCPServerConfig,
    StdioTransport,
)


def test_stdio_transport_minimal():
    t = StdioTransport(type="stdio", command="npx")
    assert t.type == "stdio"
    assert t.args == []
    assert t.env == {}
    assert t.credential_refs == {}


def test_stdio_transport_full():
    t = StdioTransport(
        type="stdio",
        command="npx",
        args=["-y", "@mcp/server-filesystem", "/tmp"],
        env={"LOG_LEVEL": "info"},
        credential_refs={"GITHUB_TOKEN": "github_pat_main"},
        cwd="/tmp",
    )
    assert t.args == ["-y", "@mcp/server-filesystem", "/tmp"]
    assert t.cwd == "/tmp"


def test_http_transport_minimal():
    t = HttpTransport(type="http", url="https://api.example.com/mcp")
    assert t.type == "http"
    assert t.headers == {}
    assert t.credential_refs == {}


def test_http_transport_validates_url():
    with pytest.raises(ValidationError):
        HttpTransport(type="http", url="not a url")


def test_mcp_server_config_discriminated_union_stdio():
    cfg = MCPServerConfig.model_validate(
        {
            "transport": {"type": "stdio", "command": "npx"},
        }
    )
    assert isinstance(cfg.transport, StdioTransport)


def test_mcp_server_config_discriminated_union_http():
    cfg = MCPServerConfig.model_validate(
        {
            "transport": {"type": "http", "url": "https://example.com/mcp"},
        }
    )
    assert isinstance(cfg.transport, HttpTransport)


def test_mcp_server_config_defaults():
    cfg = MCPServerConfig.model_validate({"transport": {"type": "stdio", "command": "x"}})
    assert cfg.spawn_timeout_seconds == 30
    assert cfg.request_timeout_seconds == 120


def test_mcp_server_config_ignores_retired_idle_timeout_key():
    """A vault written while ``idle_timeout_seconds`` still existed may carry
    the key in its stored ``Resource.config`` JSON. No idle GC was ever
    implemented, so the field is gone; loading such a config must ignore the
    stale key rather than reject the server. The key then disappears on the
    resource's next write, because ``_validate_config`` persists
    ``model_dump()`` of the validated model.
    """
    cfg = MCPServerConfig.model_validate(
        {"transport": {"type": "stdio", "command": "x"}, "idle_timeout_seconds": 600}
    )
    assert not hasattr(cfg, "idle_timeout_seconds")


def test_mcp_server_config_validates_timeout_ranges():
    with pytest.raises(ValidationError):
        MCPServerConfig.model_validate(
            {"transport": {"type": "stdio", "command": "x"}, "spawn_timeout_seconds": 0}
        )
    with pytest.raises(ValidationError):
        MCPServerConfig.model_validate(
            {"transport": {"type": "stdio", "command": "x"}, "spawn_timeout_seconds": 9999}
        )


def test_secret_in_env_rejected():
    """Static env values that look like API keys must be rejected.

    Secrets go through credential_refs.
    """
    with pytest.raises(ValidationError):
        StdioTransport(
            type="stdio",
            command="x",
            env={"TOKEN": "ghp_abcdefghijklmnopqrst"},
        )
    with pytest.raises(ValidationError):
        StdioTransport(
            type="stdio",
            command="x",
            env={"AUTH": "Bearer eyJhbGciOiJIUzI1NiI"},
        )


def test_secret_in_header_rejected():
    with pytest.raises(ValidationError):
        HttpTransport(
            type="http",
            url="https://example.com",
            headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiI"},
        )
