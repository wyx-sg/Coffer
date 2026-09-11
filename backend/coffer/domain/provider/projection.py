"""Pure text transforms that project a provider profile into native agent config.

No filesystem access — the application layer reads the agent's native config
file, calls one of these to produce new text, and writes it back through the
atomic store (``ConfigFileStore.write_text_atomic`` → atomic + ``.bak``). This
mirrors ``domain/agent/mcp_install.py``'s ``apply_install``.

Coffer supports exactly two agent types, and BOTH are projection targets — one
transform pair (apply/remove) per agent (``ollama`` is the only wire that
projects into none: it is internal-only, used by Coffer's own engine):

- Claude Code → ``~/.claude/settings.json`` (JSON): top-level ``apiKeyHelper``
  (the key is fetched on demand, never written) plus ``env.ANTHROPIC_BASE_URL`` /
  ``ANTHROPIC_MODEL`` / ``ANTHROPIC_SMALL_FAST_MODEL``.
- Codex → ``~/.codex/config.toml`` (TOML): top-level ``model`` +
  ``model_provider`` plus a ``[model_providers.coffer]`` table whose ``env_key``
  names the env var Codex reads the key from (also never written here), and —
  when the connection curates a model set — ``model_catalog_json`` pointing at a
  Coffer-owned catalogue file so Codex's OWN model picker lists the endpoint's
  models rather than OpenAI's. The catalogue's CONTENT is built here
  (``codex_model_catalog_json``); writing and deleting the file is the
  application layer's job, like every other projection write.

Both write ONLY Coffer-managed keys, merging into the user's existing file so
unrelated content is preserved.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import MutableMapping, Sequence
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

#: Filename of the model catalogue Coffer writes next to an agent's
#: ``config.toml``, and what ``model_catalog_json`` is pointed at. The name also
#: doubles as the OWNERSHIP MARKER: de-projection drops ``model_catalog_json``
#: iff the path it holds ends in this filename, exactly as it drops
#: ``apiKeyHelper`` iff it starts with ``MANAGED_API_KEY_HELPER_PREFIX``. So a
#: catalogue the user wrote themselves is never removed, while one Coffer wrote
#: always is — including one written into a relocated config dir, since the match
#: is on the name, not on a path this module would have to re-derive.
CODEX_MODEL_CATALOG_FILENAME = "coffer-model-catalog.json"

#: Codex's TOML key that points at a model catalogue file.
CODEX_MODEL_CATALOG_KEY = "model_catalog_json"

#: How much of a TOOL RESULT Codex keeps before truncating it. NOT a context
#: window: Codex's own built-in catalogue pairs ``{"mode": "tokens", "limit":
#: 10000}`` with a ``context_window`` of 272000, so this bound describes Codex's
#: harness rather than the endpoint — which is why Coffer can mirror the built-in
#: value here instead of guessing one for a third-party endpoint.
CODEX_CATALOG_TRUNCATION_LIMIT = 10_000

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
}


def target_for(wire: Protocol) -> ProjectionTarget | None:
    """The projection target for ``wire`` (which agent + native config file), or
    ``None`` for internal-only wires (``ollama``) that project into no agent."""
    return _TARGETS.get(wire)


def wire_for_agent(agent_type: AgentType) -> Protocol | None:
    """The wire whose ``deactivate`` covers ``agent_type`` — the inverse of the
    wire→agent correspondence ``_TARGETS`` encodes. ``None`` for a type no wire
    maps onto, so callers stay total.
    """
    for wire, target in _TARGETS.items():
        if target.agent_type is agent_type:
            return wire
    return None


def target_for_agent(agent_type: AgentType) -> ProjectionTarget | None:
    """The native-config target for an agent TYPE (the file + format its writer
    touches). Every SUPPORTED agent type is a projection target, so this returns
    a target for every member of ``AgentType``; the optional return is kept only
    so callers stay total against a hand-built/unknown value."""
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


def codex_model_catalog_path(config_dir: pathlib.Path) -> pathlib.Path:
    """Where Coffer's catalogue lives for an agent whose config dir is
    ``config_dir`` — next to that agent's ``config.toml``, under the
    Coffer-owned filename. ``model_catalog_json`` must be absolute, so the
    caller must hand in an absolute config dir (``AgentConfig`` guarantees it)."""
    return config_dir / CODEX_MODEL_CATALOG_FILENAME


def codex_model_catalog_json(models: Sequence[str]) -> str | None:
    """The ``model_catalog_json`` document for a connection's curated models — or
    ``None`` when there is nothing honest to write.

    ``model_catalog_json`` REPLACES Codex's built-in model list; it does not add
    to it (verified against Codex 0.139.0: with a one-model catalogue, ``model/
    list`` returns exactly that model). So a catalogue may only be written when
    the user has curated a model set on the connection (``ProviderConfig.models``
    — the ids ticked on its detail page). An EMPTY set means "no restriction",
    and Coffer does not know what a third-party endpoint serves without a network
    call it does not make here: a catalogue built from a guess would replace
    Codex's own picker with that guess. ``None`` therefore means "write no
    catalogue, and remove any stale one".

    Every field emitted below is REQUIRED by Codex's parser — this file is a wire
    contract with another program. Omitting one does not merely lose the
    catalogue: Codex reports ``failed to parse model_catalog_json`` and falls back
    to its built-in list, so the projection silently does not take effect.
    """
    if not models:
        return None
    entries: list[dict[str, object]] = [
        {
            "slug": model,
            # The id IS the display name. Coffer authors no model names of its own
            # (the 2026-09-09 amendment: catalogues are read back from agents and
            # endpoints, never written down here), and the id is what the user
            # ticked, so it is what they will recognise in Codex's picker.
            # Prettifying it would mean maintaining a vendor-label table that goes
            # stale the moment an endpoint adds a model.
            "display_name": model,
            # Codex's built-ins are ordered by ascending priority with the
            # preferred model at 0 (gpt-5.5→0, gpt-5.4→2, … gpt-5.2→10), so the
            # curated order is reproduced by the index. Ordering only.
            "priority": index,
            # The catalogue exists to put these models in Codex's picker.
            "visibility": "list",
            # The user curated these ids for an API endpoint, so they are
            # API-usable by construction — not a guess.
            "supported_in_api": True,
            # --- values Coffer CANNOT derive for a third-party endpoint --------
            # Coffer knows an endpoint's base URL and the ids the user ticked.
            # Nothing below is discoverable from that, so each takes the value
            # that claims the LEAST, and the cost of each being wrong is noted.
            #
            # No reasoning-effort presets claimed: Codex then sends no
            # ``reasoning`` field at all (verified on a captured request). Claiming
            # presets an endpoint does not implement would put an unknown
            # parameter on every request — a hard 400 on a strict gateway. Cost of
            # being conservative: a model that does support effort levels cannot
            # be driven at a chosen effort from Codex.
            "supported_reasoning_levels": [],
            # Same argument for the two other request-shaping capabilities:
            # unsupported => the parameter is never sent.
            "supports_reasoning_summaries": False,
            "support_verbosity": False,
            # Sequential tool calls work everywhere; parallel ones are an opt-in
            # capability. Cost of being conservative: a capable model runs its
            # tool calls one at a time, i.e. slower, never broken.
            "supports_parallel_tool_calls": False,
            # No experimental tools assumed.
            "experimental_supported_tools": [],
            # The enum's least-committal value. Codex's own models opt into
            # "shell_command"; on 0.139.0 both values produced an identical tool
            # set on the wire, so this is the safe default rather than a bet on
            # what a third-party model was trained to drive.
            "shell_type": "default",
            # Harness-level tool-output bound, not an endpoint property — see
            # CODEX_CATALOG_TRUNCATION_LIMIT.
            "truncation_policy": {"mode": "tokens", "limit": CODEX_CATALOG_TRUNCATION_LIMIT},
            # Codex's own catalogue puts its ENTIRE agent system prompt here, and
            # the field is required. Empty means Codex sends no ``instructions``
            # (verified on a captured request) — it still sends its permissions,
            # skills and environment developer messages and the full tool set, so
            # the agent works, but without Codex's persona prompt. The
            # alternative, copying OpenAI's prompt into a Coffer-written file,
            # would pin one Codex version's prompt and silently override every
            # later one; Coffer does not author another product's system prompt.
            "base_instructions": "",
        }
        for index, model in enumerate(models)
    ]
    return json.dumps({"models": entries}, indent=2, ensure_ascii=False) + "\n"


def _pop_managed_catalog(doc: MutableMapping[str, object]) -> None:
    """Drop ``model_catalog_json`` iff it points at a COFFER-owned catalogue —
    the same ownership discipline ``remove_anthropic_settings`` applies to
    ``apiKeyHelper``. A user's own catalogue (any other filename) is left alone.
    Compared as a POSIX basename: Coffer only ever writes posix paths here, and
    parsing the value as a native path would make a pure transform
    platform-dependent."""
    value = doc.get(CODEX_MODEL_CATALOG_KEY)
    if isinstance(value, str) and pathlib.PurePosixPath(value).name == (
        CODEX_MODEL_CATALOG_FILENAME
    ):
        doc.pop(CODEX_MODEL_CATALOG_KEY, None)


def apply_codex_provider(
    text: str,
    *,
    base_url: str,
    model: str | None,
    wire_api: str,
    display_name: str,
    provider_id: str = CODEX_PROVIDER_ID,
    env_key: str = CODEX_ENV_KEY,
    catalog_path: pathlib.Path | None = None,
) -> str:
    """Return new ``config.toml`` text with Coffer's openai provider block.

    Merges into the user's existing TOML via tomlkit (comments / ordering /
    unrelated keys preserved). Sets top-level ``model`` + ``model_provider`` and
    the ``[model_providers.<provider_id>]`` table. When ``model`` is ``None`` (an
    unbound agent) the top-level ``model`` is omitted so Codex uses its default.

    ``catalog_path`` points ``model_catalog_json`` at the Coffer-owned catalogue
    (see :func:`codex_model_catalog_json`) so Codex's OWN model picker offers the
    endpoint's models instead of OpenAI's. ``None`` means this connection curates
    no model set: Codex's built-in list is left alone, and a catalogue pointer
    Coffer wrote earlier is dropped.
    """
    doc = tomlkit.parse(text) if text.strip() else tomlkit.document()
    if model:
        doc["model"] = model
    else:
        doc.pop("model", None)
    doc["model_provider"] = provider_id
    if catalog_path is None:
        _pop_managed_catalog(doc)
    else:
        if not catalog_path.is_absolute():
            # Codex resolves this key as an absolute path; a relative one would
            # silently resolve against whatever cwd the agent was started in.
            raise ValueError(f"{CODEX_MODEL_CATALOG_KEY} must be absolute, got {catalog_path}")
        doc[CODEX_MODEL_CATALOG_KEY] = str(catalog_path)
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
    points at Coffer (a user-selected provider is left untouched). A
    ``model_catalog_json`` pointing at the Coffer-owned catalogue is dropped too,
    so Codex's own model list comes back; one pointing anywhere else is the user's
    and stays. Unrelated keys are preserved."""
    if not text.strip():
        return ""
    doc = tomlkit.parse(text)
    _pop_managed_catalog(doc)
    providers = doc.get("model_providers")
    if isinstance(providers, MutableMapping):
        providers.pop(provider_id, None)
        if not providers:
            doc.pop("model_providers", None)
    if doc.get("model_provider") == provider_id:
        doc.pop("model_provider", None)
        doc.pop("model", None)
    return tomlkit.dumps(doc)
