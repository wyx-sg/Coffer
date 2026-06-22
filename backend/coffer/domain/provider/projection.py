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

import tomlkit

from coffer.domain.agent.config_files import ConfigFileFormat
from coffer.domain.agent.types import AgentType
from coffer.domain.provider.config import Protocol

# --- Codex provider-block identity --------------------------------------------

#: The ``model_providers`` table key Coffer manages, and the ``model_provider``
#: selector that points at it.
CODEX_PROVIDER_ID = "coffer"
#: The env var Codex reads the API key from (``model_providers.coffer.env_key``).
#: The raw key is materialized into this var at runtime, never written to disk.
CODEX_ENV_KEY = "COFFER_PROVIDER_KEY"

#: The command Claude Code runs to fetch the auth token (``apiKeyHelper``). It
#: resolves the active anthropic profile's credential from the Fernet vault and
#: prints it — so the key is never persisted in ``settings.json``.
ANTHROPIC_API_KEY_HELPER = "coffer provider key --wire anthropic"


@dataclass(frozen=True)
class ProjectionTarget:
    """Where a wire format projects: the agent type + its native config file."""

    agent_type: AgentType
    config_key: str
    format: ConfigFileFormat


_TARGETS: dict[Protocol, ProjectionTarget] = {
    Protocol.ANTHROPIC: ProjectionTarget(AgentType.CLAUDE_CODE, "settings", ConfigFileFormat.JSON),
    Protocol.OPENAI: ProjectionTarget(AgentType.CODEX, "config", ConfigFileFormat.TOML),
}


def target_for(wire: Protocol) -> ProjectionTarget | None:
    """The projection target for ``wire`` (which agent + native config file), or
    ``None`` for internal-only wires (``ollama``) that project into no agent."""
    return _TARGETS.get(wire)


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


def remove_anthropic_settings(text: str, *, api_key_helper: str = ANTHROPIC_API_KEY_HELPER) -> str:
    """Inverse of :func:`apply_anthropic_settings` — strip Coffer's managed keys so
    Claude Code falls back to its OWN login ("use built-in"). Removes the managed
    ``apiKeyHelper`` (only when it is Coffer's, never a user-owned one) and the
    ``env.ANTHROPIC_BASE_URL`` / ``ANTHROPIC_MODEL`` / ``ANTHROPIC_SMALL_FAST_MODEL``
    vars; unrelated keys and env entries are preserved."""
    data = json.loads(text) if text.strip() else {}
    if not isinstance(data, dict):
        return "{}\n"
    if data.get("apiKeyHelper") == api_key_helper:
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
