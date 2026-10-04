"""The 1.0 freeze of every string Coffer writes into an agent's own config.

These lines live in files Coffer does not own — Claude Code's ``settings.json``
and ``.claude.json``, Codex's ``config.toml`` and ``hooks.json`` — and outlast
the build that wrote them: an agent runs them, de-projection and the
reconciler recognise them, and a later build has to clean them up. Changing
one silently has already cost months of broken delivery once (a renamed flag
left every installed hook calling a command that no longer parsed). So the
exact text each surface writes from an empty file is pinned here, with fixed
fake paths and uids.

A failure here is not a formatting nit. Changing any of these strings is a
change to a public surface: it needs an OpenSpec change, a plan for the lines
already on users' disks, and then an edit to the expected text below.
"""

from __future__ import annotations

import json
import pathlib
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.provider.projector import projection_request
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import spec_for
from coffer.domain.agent.descriptor import descriptor_for
from coffer.domain.agent.mcp_install import apply_install
from coffer.domain.agent.types import AgentType
from coffer.domain.memory.delivery import DeliveryAdapter
from coffer.domain.model_proxy.state import DEFAULT_PROXY_PORT, proxy_root
from coffer.domain.provider.agent_projection import (
    ClaudeCodeProviderProjection,
    CodexProviderProjection,
)
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.resource import Resource
from coffer.domain.usage.records import Wire
from coffer.infrastructure.memory.delivery.claude_code import ClaudeCodeDelivery
from coffer.infrastructure.memory.delivery.codex import CodexDelivery

_NOW = datetime(2026, 9, 30, tzinfo=UTC)
_CLI = "/Users/me/.coffer/bin/coffer"
_SHIM = "/Users/me/.coffer/bin/coffer-mcp-shim"
_AGENT_UID = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
_CONNECTION_UID = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"
_CONNECTION = {
    "protocol": "anthropic",
    "base_url": "https://gw.example",
    "secret_ref": "gw-key",
}

#: The one command every memory hook entry runs, marker first.
_HOOK_COMMAND = f': coffer-memory; {_CLI} memory hook --agent-uid {_AGENT_UID} --cwd "$PWD"'


def _resource(kind: str, name: str, config: dict[str, Any], uid: str) -> Resource:
    return Resource(
        uid=uid,
        kind=kind,
        name=name,
        description=None,
        config=config,
        enabled=True,
        created_at=_NOW,
        updated_at=_NOW,
        scope=None,
    )


def _provider_text(agent_type: AgentType, config_file: str, wire: Wire) -> str:
    """What switching an unbound agent onto a connection writes into an empty
    native config, built the way the projector builds it."""
    agent_cfg = {"type": agent_type.value, "config_dir": str(pathlib.Path(config_file).parent)}
    request = projection_request(
        _resource("provider", "gw", _CONNECTION, _CONNECTION_UID),
        ProviderConfig.model_validate(_CONNECTION),
        _resource("agent", agent_type.value, agent_cfg, _AGENT_UID),
        AgentConfig.model_validate(agent_cfg),
        coffer_cli=_CLI,
        proxy_root=proxy_root(DEFAULT_PROXY_PORT),
        wire=wire,
    )
    facet = (
        ClaudeCodeProviderProjection()
        if agent_type is AgentType.CLAUDE_CODE
        else CodexProviderProjection()
    )
    return facet.apply("", request, pathlib.Path(config_file)).text


def _mcp_text(agent_type: AgentType, config_dir: str) -> str:
    """What connecting the agent writes into its empty MCP config file."""
    injection = descriptor_for(agent_type).mcp
    assert injection is not None
    spec = spec_for(agent_type, injection.config_key, pathlib.Path(config_dir))
    return apply_install(
        spec.format,
        "",
        _SHIM,
        container_key=injection.container_key,
        entry_style=injection.entry_style,
        agent_uid=_AGENT_UID,
        extras=injection.entry_extras,
    )


def test_claude_code_provider_projection_is_frozen() -> None:
    assert _provider_text(AgentType.CLAUDE_CODE, "/h/.claude/settings.json", Wire.ANTHROPIC) == (
        "{\n"
        f'  "apiKeyHelper": "{_CLI} proxy token --agent-uid {_AGENT_UID}",\n'
        '  "env": {\n'
        '    "ANTHROPIC_BASE_URL": "http://127.0.0.1:38471/anthropic",\n'
        '    "NO_PROXY": "127.0.0.1,localhost"\n'
        "  }\n"
        "}\n"
    )


def test_codex_provider_block_is_frozen() -> None:
    assert _provider_text(AgentType.CODEX, "/h/.codex/config.toml", Wire.OPENAI) == (
        'model_provider = "coffer"\n'
        "\n"
        "[model_providers.coffer]\n"
        'name = "Coffer (gw)"\n'
        'base_url = "http://127.0.0.1:38471/openai/v1"\n'
        'wire_api = "responses"\n'
        "supports_websockets = false\n"
        "requires_openai_auth = false\n"
        f'auth = {{command = "{_CLI}", '
        f'args = ["proxy", "token", "--agent-uid", "{_AGENT_UID}"], timeout_ms = 30000}}\n'
    )


def test_claude_code_mcp_entry_is_frozen() -> None:
    assert _mcp_text(AgentType.CLAUDE_CODE, "/h/.claude") == (
        "{\n"
        '  "mcpServers": {\n'
        '    "coffer": {\n'
        f'      "command": "{_SHIM}",\n'
        '      "args": [\n'
        '        "--agent-uid",\n'
        f'        "{_AGENT_UID}"\n'
        "      ]\n"
        "    }\n"
        "  }\n"
        "}\n"
    )


def test_codex_mcp_entry_is_frozen() -> None:
    assert _mcp_text(AgentType.CODEX, "/h/.codex") == (
        f'[mcp_servers.coffer]\ncommand = "{_SHIM}"\nargs = ["--agent-uid", "{_AGENT_UID}"]\n'
        'env_vars = ["COFFER_TURN_TOKEN"]\ntool_timeout_sec = 86400\n'
    )


def _entry(matcher: str | None, timeout: int) -> dict[str, Any]:
    leaf = {"type": "command", "command": _HOOK_COMMAND, "timeout": timeout}
    return {"matcher": matcher, "hooks": [leaf]} if matcher else {"hooks": [leaf]}


#: Both agents carry the same two entries, in this order.
_FROZEN_HOOKS = {
    "hooks": {
        "SessionStart": [_entry("startup|resume|clear|compact", 10)],
        "UserPromptSubmit": [_entry(None, 5)],
    }
}


@pytest.mark.parametrize(
    "adapter",
    [ClaudeCodeDelivery(cli=_CLI), CodexDelivery(cli=_CLI)],
    ids=lambda a: a.agent_type,
)
def test_memory_hook_entries_are_frozen(adapter: DeliveryAdapter) -> None:
    text = adapter.install("", _AGENT_UID)
    assert adapter.command_for(_AGENT_UID) == _HOOK_COMMAND
    doc = json.loads(text)
    assert doc == _FROZEN_HOOKS
    assert list(doc["hooks"]) == list(_FROZEN_HOOKS["hooks"])
