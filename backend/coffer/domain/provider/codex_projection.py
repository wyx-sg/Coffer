"""Pure text transforms that project a connection into Codex's ``config.toml``,
and the content of the Coffer-owned model catalogue beside it (spec
provider-switching "Project into Codex config without clobbering it").

Codex gets top-level ``model`` + ``model_provider = "coffer"`` and a
``[model_providers.coffer]`` table. Codex authenticates to that provider with
its ``auth`` command (``auth.command`` / ``auth.args``), which prints the
agent's local model-proxy token, with ``supports_websockets = false`` and
``requires_openai_auth = false`` — so a Codex the user starts in their own
terminal needs nothing exported, and no key rides its environment.

When the connection curates a model set, ``model_catalog_json`` points at a
Coffer-owned catalogue whose entries carry each model's context window, a 90%
auto-compact limit and its effort levels; ``model_reasoning_effort`` is written
only when the chosen model has levels (without them Codex sends no reasoning
effort whatever the key says).
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import MutableMapping, Sequence
from dataclasses import dataclass

import tomlkit

from coffer.domain.provider.model_binding import ProjectedModel

#: The ``model_providers`` table key Coffer manages, and the ``model_provider``
#: selector that points at it.
#: The one ``wire_api`` Codex still loads — it parses ``responses`` and refuses
#: every other spelling, the retired ``chat`` included — so it is fixed here
#: instead of being a setting.
CODEX_WIRE_API = "responses"
CODEX_PROVIDER_ID = "coffer"
#: Filename of the model catalogue Coffer writes next to an agent's
#: ``config.toml``. The name doubles as the OWNERSHIP MARKER: de-projection
#: drops ``model_catalog_json`` iff the path it holds ends in this filename.
CODEX_MODEL_CATALOG_FILENAME = "coffer-model-catalog.json"
#: Codex's TOML key that points at a model catalogue file.
CODEX_MODEL_CATALOG_KEY = "model_catalog_json"
#: How much of a TOOL RESULT Codex keeps before truncating it — Codex's own
#: built-in value, a harness bound rather than an endpoint property.
CODEX_CATALOG_TRUNCATION_LIMIT = 10_000
_EFFORT_KEY = "model_reasoning_effort"


@dataclass(frozen=True)
class CodexAuthCommand:
    """The command Codex runs for its provider bearer token."""

    command: str
    args: tuple[str, ...]


def codex_model_catalog_path(config_dir: pathlib.Path) -> pathlib.Path:
    """Where Coffer's catalogue lives for an agent whose config dir is
    ``config_dir`` (absolute, as ``AgentConfig`` guarantees)."""
    return config_dir / CODEX_MODEL_CATALOG_FILENAME


def _entry(index: int, model: ProjectedModel) -> dict[str, object]:
    entry: dict[str, object] = {
        "slug": model.id,
        # The id IS the display name: Coffer authors no model names.
        "display_name": model.id,
        # Codex orders its built-ins by ascending priority, preferred at 0.
        "priority": index,
        "visibility": "list",
        # Curated for an API endpoint, so API-usable by construction.
        "supported_in_api": True,
        # Levels the connection records for the model (spec provider-switching
        # "Record a context window and effort levels with each curated model");
        # none means Codex sends no ``reasoning`` field at all, which is the
        # right answer for a model nobody said takes one.
        "supported_reasoning_levels": [
            {"effort": level, "description": level} for level in model.effort_levels
        ],
        # Unsupported => never sent: values Coffer cannot derive claim the least.
        "supports_reasoning_summaries": False,
        "support_verbosity": False,
        "supports_parallel_tool_calls": False,
        "experimental_supported_tools": [],
        "shell_type": "default",
        "truncation_policy": {"mode": "tokens", "limit": CODEX_CATALOG_TRUNCATION_LIMIT},
        # Required, and empty so Codex sends no ``instructions``: Coffer does
        # not author another product's system prompt.
        "base_instructions": "",
    }
    if model.effort_levels:
        entry["default_reasoning_level"] = model.default_effort or model.effort_levels[0]
    if model.context_window is not None:
        # Without a window Codex falls back to 272k and a smaller endpoint
        # overflows before Codex ever compacts; an unknown one is left out
        # rather than guessed.
        entry["context_window"] = model.context_window
        entry["max_context_window"] = model.context_window
        entry["auto_compact_token_limit"] = model.auto_compact_limit
    return entry


def codex_model_catalog_json(models: Sequence[ProjectedModel | str]) -> str | None:
    """The ``model_catalog_json`` document for a connection's curated models —
    or ``None`` when there is nothing honest to write (an uncurated connection:
    the key REPLACES Codex's built-in list, so a guess would replace the picker
    with the guess). Every field Codex's parser requires is emitted: a malformed
    catalogue is not an error, Codex just falls back to its built-in list."""
    if not models:
        return None
    projected = [m if isinstance(m, ProjectedModel) else ProjectedModel(id=m) for m in models]
    entries = [_entry(i, m) for i, m in enumerate(projected)]
    return json.dumps({"models": entries}, indent=2, ensure_ascii=False) + "\n"


def _pop_managed_catalog(doc: MutableMapping[str, object]) -> None:
    """Drop ``model_catalog_json`` iff it points at a COFFER-owned catalogue
    (compared as a POSIX basename, so the transform stays platform-free)."""
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
    display_name: str,
    auth: CodexAuthCommand,
    effort: str | None = None,
    provider_id: str = CODEX_PROVIDER_ID,
    catalog_path: pathlib.Path | None = None,
) -> str:
    """Return new ``config.toml`` text with Coffer's provider block.

    The block authenticates through ``auth``. ``effort`` is written only by a
    caller that knows the model has levels. ``catalog_path`` ``None``: no
    curated set, and a catalogue pointer Coffer wrote earlier is dropped.
    """
    doc = tomlkit.parse(text) if text.strip() else tomlkit.document()
    if model:
        doc["model"] = model
    else:
        doc.pop("model", None)
    doc["model_provider"] = provider_id
    if effort:
        doc[_EFFORT_KEY] = effort
    if catalog_path is None:
        _pop_managed_catalog(doc)
    else:
        if not catalog_path.is_absolute():
            raise ValueError(f"{CODEX_MODEL_CATALOG_KEY} must be absolute, got {catalog_path}")
        doc[CODEX_MODEL_CATALOG_KEY] = str(catalog_path)
    if not isinstance(doc.get("model_providers"), MutableMapping):
        doc["model_providers"] = tomlkit.table(is_super_table=True)
    block = tomlkit.table()
    block["name"] = display_name
    block["base_url"] = base_url
    block["wire_api"] = CODEX_WIRE_API
    # WebSockets off: pointed at another base URL, Codex otherwise tries the
    # Responses WebSocket transport first and stalls.
    block["supports_websockets"] = False
    block["requires_openai_auth"] = False
    auth_table = tomlkit.inline_table()
    auth_table["command"] = auth.command
    auth_table["args"] = list(auth.args)
    block["auth"] = auth_table
    doc["model_providers"][provider_id] = block
    return tomlkit.dumps(doc)


def remove_codex_provider(
    text: str, *, provider_id: str = CODEX_PROVIDER_ID, managed_effort: str | None = None
) -> str:
    """Inverse of :func:`apply_codex_provider` — so Codex falls back to its OWN
    provider and models ("use built-in"). The provider table always goes;
    ``model_provider``, ``model`` and a ``model_reasoning_effort`` equal to
    ``managed_effort`` go only while ``model_provider`` points at Coffer (a
    user-selected provider is left untouched); a Coffer-owned catalogue pointer
    goes too."""
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
        if managed_effort is not None and doc.get(_EFFORT_KEY) == managed_effort:
            doc.pop(_EFFORT_KEY, None)
    return tomlkit.dumps(doc)


__all__ = [
    "CODEX_CATALOG_TRUNCATION_LIMIT",
    "CODEX_MODEL_CATALOG_FILENAME",
    "CODEX_MODEL_CATALOG_KEY",
    "CODEX_PROVIDER_ID",
    "CodexAuthCommand",
    "apply_codex_provider",
    "codex_model_catalog_json",
    "codex_model_catalog_path",
    "remove_codex_provider",
]
