"""Pure text transforms that project a provider profile into native agent config.

No filesystem access — the application layer reads the agent's native config
file, calls one of these to produce new text, and writes it back through the
atomic store (``ConfigFileStore.write_text_atomic`` → atomic + ``.bak``). This
mirrors ``domain/agent/mcp_install.py``'s ``apply_install``.

Two wire formats project into an agent's native config (``ollama`` projects into
none — it is internal-only, used by Coffer's own engine):

- ``anthropic`` → Claude Code ``~/.claude/settings.json`` (JSON): top-level
  ``apiKeyHelper`` (the key is fetched on demand, never written) plus
  ``env.ANTHROPIC_BASE_URL`` / ``ANTHROPIC_MODEL`` / ``ANTHROPIC_SMALL_FAST_MODEL``.
- ``openai`` → Codex ``~/.codex/config.toml`` (TOML): top-level ``model`` +
  ``model_provider`` plus a ``[model_providers.coffer]`` table whose ``env_key``
  names the env var Codex reads the key from (also never written here).

Both write ONLY Coffer-managed keys, merging into the user's existing file so
unrelated content is preserved.
"""

from __future__ import annotations

import json
from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import Any

import tomlkit

from coffer.domain.agent.config_files import ConfigFileFormat
from coffer.domain.agent.mcp_entries import _dump_yaml, _parse_yaml
from coffer.domain.agent.types import AgentType
from coffer.domain.provider.config import Protocol

# --- Codex provider-block identity --------------------------------------------

#: The ``model_providers`` table key Coffer manages, and the ``model_provider``
#: selector that points at it.
CODEX_PROVIDER_ID = "coffer"
#: The env var Codex reads the API key from (``model_providers.coffer.env_key``).
#: The raw key is materialized into this var at runtime, never written to disk.
CODEX_ENV_KEY = "COFFER_PROVIDER_KEY"

#: Prefix of every Coffer-managed ``apiKeyHelper`` — both the per-connection form
#: (``coffer provider key --connection <name>``) and the legacy wire form
#: (``--wire anthropic``). De-projection removes a helper iff it starts with this,
#: so it never clobbers a user-owned helper but always reverts ours.
MANAGED_API_KEY_HELPER_PREFIX = "coffer provider key"

#: Legacy wire-keyed helper kept for back-compat (older ``settings.json`` files);
#: resolution falls back to the connection active for the wire's agent.
ANTHROPIC_API_KEY_HELPER = f"{MANAGED_API_KEY_HELPER_PREFIX} --wire anthropic"


def anthropic_api_key_helper(connection: str) -> str:
    """The ``apiKeyHelper`` Coffer projects for Claude Code: fetch the named
    connection's key on demand (so the raw key is never written to disk). Keyed
    by CONNECTION, not wire, so the projected agent always reads exactly the key
    of the connection that was activated — no silent wire+active mismatch."""
    return f"{MANAGED_API_KEY_HELPER_PREFIX} --connection {connection}"


@dataclass(frozen=True)
class ProjectionTarget:
    """Where a connection projects: the agent type + its native config file."""

    agent_type: AgentType
    config_key: str
    format: ConfigFileFormat


_TARGETS: dict[Protocol, ProjectionTarget] = {
    Protocol.ANTHROPIC: ProjectionTarget(AgentType.CLAUDE_CODE, "settings", ConfigFileFormat.JSON),
    Protocol.OPENAI: ProjectionTarget(AgentType.CODEX, "config", ConfigFileFormat.TOML),
}

#: The native-config target per AGENT type. The projection writer is chosen by
#: which agent the connection is compatible with — NOT by the connection's wire —
#: so an openai-compatible endpoint routed to Claude Code writes Claude's
#: ``settings.json`` (anthropic shape), and vice versa.
_AGENT_TARGETS: dict[AgentType, ProjectionTarget] = {
    AgentType.CLAUDE_CODE: ProjectionTarget(
        AgentType.CLAUDE_CODE, "settings", ConfigFileFormat.JSON
    ),
    AgentType.CODEX: ProjectionTarget(AgentType.CODEX, "config", ConfigFileFormat.TOML),
    # opencode projects an openai-compatible `provider` block into opencode.json.
    AgentType.OPENCODE: ProjectionTarget(AgentType.OPENCODE, "opencode", ConfigFileFormat.JSON),
    # Hermes projects a `providers.coffer` entry + model block into config.yaml.
    AgentType.HERMES: ProjectionTarget(AgentType.HERMES, "config", ConfigFileFormat.YAML),
}


def target_for(wire: Protocol) -> ProjectionTarget | None:
    """The projection target for ``wire`` (which agent + native config file), or
    ``None`` for internal-only wires (``ollama``) that project into no agent."""
    return _TARGETS.get(wire)


def target_for_agent(agent_type: AgentType) -> ProjectionTarget | None:
    """The native-config target for an agent TYPE (the file + format its writer
    touches), or ``None`` for an agent Coffer cannot project into."""
    return _AGENT_TARGETS.get(agent_type)


def apply_anthropic_settings(
    text: str,
    *,
    base_url: str,
    model: str | None,
    fast_model: str | None,
    api_key_helper: str = ANTHROPIC_API_KEY_HELPER,
) -> str:
    """Return new ``settings.json`` text with Coffer's anthropic provider keys.

    Merges into the user's existing JSON; unrelated keys are preserved. Sets the
    top-level ``apiKeyHelper`` and the ``env`` provider vars; never writes
    ``ANTHROPIC_API_KEY`` (it would override the helper). When ``model`` is
    ``None`` (an unbound agent) the ``ANTHROPIC_MODEL`` var is omitted so the
    agent runs on its OWN default model.
    """
    data = json.loads(text) if text.strip() else {}
    if not isinstance(data, dict):  # a hand-edit left a non-object root
        data = {}
    data["apiKeyHelper"] = api_key_helper
    env = data.get("env")
    if not isinstance(env, dict):
        env = {}
        data["env"] = env
    env["ANTHROPIC_BASE_URL"] = base_url
    if model:
        env["ANTHROPIC_MODEL"] = model
    else:
        env.pop("ANTHROPIC_MODEL", None)
    if fast_model:
        env["ANTHROPIC_SMALL_FAST_MODEL"] = fast_model
    else:
        env.pop("ANTHROPIC_SMALL_FAST_MODEL", None)
    # ensure_ascii=False: settings.json may hold non-ASCII user content; don't
    # rewrite it to \uXXXX on every switch.
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def apply_codex_provider(
    text: str,
    *,
    base_url: str,
    model: str | None,
    wire_api: str,
    display_name: str,
    provider_id: str = CODEX_PROVIDER_ID,
    env_key: str = CODEX_ENV_KEY,
) -> str:
    """Return new ``config.toml`` text with Coffer's openai provider block.

    Merges into the user's existing TOML via tomlkit (comments / ordering /
    unrelated keys preserved). Sets top-level ``model`` + ``model_provider`` and
    the ``[model_providers.<provider_id>]`` table. When ``model`` is ``None`` (an
    unbound agent) the top-level ``model`` is omitted so Codex uses its default.
    """
    doc = tomlkit.parse(text) if text.strip() else tomlkit.document()
    if model:
        doc["model"] = model
    else:
        doc.pop("model", None)
    doc["model_provider"] = provider_id
    # Recreate `model_providers` if absent OR if a hand-edit left a non-table
    # value there (indexing into a scalar would raise).
    if not isinstance(doc.get("model_providers"), MutableMapping):
        doc["model_providers"] = tomlkit.table(is_super_table=True)
    block = tomlkit.table()
    block["name"] = display_name
    block["base_url"] = base_url
    block["wire_api"] = wire_api
    block["env_key"] = env_key
    doc["model_providers"][provider_id] = block
    return tomlkit.dumps(doc)


def remove_anthropic_settings(text: str) -> str:
    """Inverse of :func:`apply_anthropic_settings` — strip Coffer's managed keys so
    Claude Code falls back to its OWN login ("use built-in"). Removes any
    Coffer-managed ``apiKeyHelper`` (matched by prefix, so both the per-connection
    and legacy wire forms are reverted — never a user-owned one) and the
    ``env.ANTHROPIC_BASE_URL`` / ``ANTHROPIC_MODEL`` / ``ANTHROPIC_SMALL_FAST_MODEL``
    vars; unrelated keys and env entries are preserved."""
    data = json.loads(text) if text.strip() else {}
    if not isinstance(data, dict):
        return "{}\n"
    helper = data.get("apiKeyHelper")
    if isinstance(helper, str) and helper.startswith(MANAGED_API_KEY_HELPER_PREFIX):
        data.pop("apiKeyHelper", None)
    env = data.get("env")
    if isinstance(env, dict):
        for key in ("ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL", "ANTHROPIC_SMALL_FAST_MODEL"):
            env.pop(key, None)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def remove_codex_provider(text: str, *, provider_id: str = CODEX_PROVIDER_ID) -> str:
    """Inverse of :func:`apply_codex_provider` — drop Coffer's provider block so
    Codex falls back to its OWN default provider/model ("use built-in"). The
    ``[model_providers.<provider_id>]`` table is always removed; ``model_provider``
    and the top-level ``model`` are cleared ONLY when ``model_provider`` currently
    points at Coffer (a user-selected provider is left untouched). Unrelated keys
    are preserved."""
    if not text.strip():
        return ""
    doc = tomlkit.parse(text)
    providers = doc.get("model_providers")
    if isinstance(providers, MutableMapping):
        providers.pop(provider_id, None)
        if not providers:
            doc.pop("model_providers", None)
    if doc.get("model_provider") == provider_id:
        doc.pop("model_provider", None)
        doc.pop("model", None)
    return tomlkit.dumps(doc)


def apply_opencode_provider(
    text: str,
    *,
    base_url: str,
    model: str | None,
    provider_id: str = CODEX_PROVIDER_ID,
    env_key: str = CODEX_ENV_KEY,
) -> str:
    """Return new ``opencode.json`` text with Coffer's openai-compatible provider.

    Merges into the user's existing JSON (unrelated keys preserved). Writes a
    ``provider.<provider_id>`` block using opencode's ``@ai-sdk/openai-compatible``
    npm loader whose ``apiKey`` REFERENCES the env var Coffer injects at spawn time
    (``{env:COFFER_PROVIDER_KEY}``) — the raw key is never written to disk, same as
    the Codex/Claude projections. When a ``model`` is bound, it is declared in the
    provider's ``models`` map and selected as the top-level ``model``
    (``<provider_id>/<model>``); an unbound agent leaves the top-level ``model``
    untouched so opencode uses its own default.
    """
    data = json.loads(text) if text.strip() else {}
    if not isinstance(data, dict):  # a hand-edit left a non-object root
        data = {}
    provider = data.get("provider")
    if not isinstance(provider, dict):
        provider = {}
        data["provider"] = provider
    block: dict[str, object] = {
        "npm": "@ai-sdk/openai-compatible",
        "name": "Coffer",
        "options": {"baseURL": base_url, "apiKey": f"{{env:{env_key}}}"},
    }
    if model:
        block["models"] = {model: {}}
        data["model"] = f"{provider_id}/{model}"
    else:
        # Unbound: clear a stale ``coffer/*`` selection so opencode falls back to
        # its OWN default model (parity with ``apply_codex_provider``'s
        # ``doc.pop("model")``); a user-chosen model is left untouched.
        existing = data.get("model")
        if isinstance(existing, str) and existing.startswith(f"{provider_id}/"):
            data.pop("model", None)
    provider[provider_id] = block
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def remove_opencode_provider(text: str, *, provider_id: str = CODEX_PROVIDER_ID) -> str:
    """Inverse of :func:`apply_opencode_provider` — drop Coffer's ``provider`` entry
    so opencode falls back to its OWN provider/model. The ``provider.<provider_id>``
    block is always removed (and the ``provider`` object when it becomes empty); the
    top-level ``model`` is cleared ONLY when it points at Coffer (``<provider_id>/``).
    Unrelated keys are preserved."""
    if not text.strip():
        return ""
    data = json.loads(text)
    if not isinstance(data, dict):
        return "{}\n"
    provider = data.get("provider")
    if isinstance(provider, dict):
        provider.pop(provider_id, None)
        if not provider:
            data.pop("provider", None)
    model = data.get("model")
    if isinstance(model, str) and model.startswith(f"{provider_id}/"):
        data.pop("model", None)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


#: Hermes reads a custom endpoint's key from a named env var (``key_env``) — the
#: exact analogue of Codex's ``env_key`` — so Coffer reuses ``COFFER_PROVIDER_KEY``
#: and the raw key is never written to disk.
_HERMES_API_MODE = "chat_completions"


def apply_hermes_provider(
    text: str,
    *,
    base_url: str,
    model: str | None,
    provider_id: str = CODEX_PROVIDER_ID,
    env_key: str = CODEX_ENV_KEY,
) -> str:
    """Return new ``config.yaml`` text with Coffer's provider selected for Hermes.

    Merges into the user's existing YAML via ruamel (comments/order preserved).
    Writes a named ``providers.<provider_id>`` entry (``base_url`` + ``key_env`` +
    ``api_mode``) and points the top-level ``model`` block at it. The key is
    referenced by env var (``key_env``), never written. When ``model`` is bound it
    is set as the model default; an unbound agent omits the default so Hermes uses
    the provider's own default model.
    """
    doc = _parse_yaml(text)
    model_block = doc.get("model")
    if not isinstance(model_block, MutableMapping):
        model_block = {}
        doc["model"] = model_block
    model_block["provider"] = provider_id
    model_block["base_url"] = base_url
    model_block["api_mode"] = _HERMES_API_MODE
    if model:
        model_block["default"] = model
    else:
        model_block.pop("default", None)
    providers = doc.get("providers")
    if not isinstance(providers, MutableMapping):
        providers = {}
        doc["providers"] = providers
    entry: dict[str, Any] = {
        "base_url": base_url,
        "api_mode": _HERMES_API_MODE,
        "key_env": env_key,
    }
    if model:
        entry["default_model"] = model
    providers[provider_id] = entry
    return _dump_yaml(doc)


def remove_hermes_provider(text: str, *, provider_id: str = CODEX_PROVIDER_ID) -> str:
    """Inverse of :func:`apply_hermes_provider` — drop Coffer's ``providers`` entry
    and revert the ``model`` block ONLY when it currently points at Coffer (a
    user-chosen provider is left untouched). Unrelated keys are preserved."""
    if not text.strip():
        return ""
    doc = _parse_yaml(text)
    providers = doc.get("providers")
    if isinstance(providers, MutableMapping):
        providers.pop(provider_id, None)
        if not providers:
            doc.pop("providers", None)
    model_block = doc.get("model")
    if isinstance(model_block, MutableMapping) and model_block.get("provider") == provider_id:
        for key in ("provider", "base_url", "api_mode", "default"):
            model_block.pop(key, None)
        if not model_block:
            doc.pop("model", None)
    return _dump_yaml(doc)
