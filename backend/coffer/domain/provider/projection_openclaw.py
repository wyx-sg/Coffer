"""openclaw provider-projection transforms (spec 011 / ADR-043).

Pure text transforms over ``~/.openclaw/openclaw.json`` (plain JSON), split out
of ``projection.py`` for the file-size limit. Coffer projects a connection as a
``models.providers.coffer`` block and points ``agents.defaults.model.primary``
at it. Facts probe-verified on openclaw 2026.6.11:

- a custom provider MUST declare ``models`` and each entry needs BOTH ``id``
  and ``name`` (``openclaw config validate``: "custom model providers must
  declare models"; "models.0.name: Invalid input" without a name) — an empty
  ``models: []`` is valid, which is what an unbound agent projects;
- ``apiKey`` supports ``${UPPERCASE_VAR}`` env references, and a MISSING env
  var is a startup WARNING only ("Missing env var … feature using this value
  will be unavailable", exit 0, other providers unaffected) — so Coffer
  persists ``${COFFER_PROVIDER_KEY}`` and injects the key into the subprocess
  env per Coffer-driven turn; a user-run openclaw without the var degrades
  gracefully;
- model refs are ``provider/model`` (first slash); the active model is
  ``agents.defaults.model.primary`` — the user's ``fallbacks`` list is
  PRESERVED.

The ``api`` value follows the connection's wire: openclaw speaks both
``openai-completions`` and ``anthropic-messages`` (both validate), so the
projector passes the right one instead of assuming openai.
"""

from __future__ import annotations

import json
from collections.abc import MutableMapping
from typing import Any

from coffer.domain.provider.projection import CODEX_ENV_KEY, CODEX_PROVIDER_ID

#: openclaw ``models.providers.<id>.api`` values per connection wire.
OPENCLAW_API_OPENAI = "openai-completions"
OPENCLAW_API_ANTHROPIC = "anthropic-messages"


def _load(text: str) -> dict[str, Any]:
    data = json.loads(text) if text.strip() else {}
    return data if isinstance(data, dict) else {}


def _dump(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _step(node: MutableMapping[str, Any], key: str) -> MutableMapping[str, Any]:
    child = node.get(key)
    if not isinstance(child, MutableMapping):
        child = {}
        node[key] = child
    return child


def apply_openclaw_provider(
    text: str,
    *,
    base_url: str,
    model: str | None,
    api: str = OPENCLAW_API_OPENAI,
    provider_id: str = CODEX_PROVIDER_ID,
    env_key: str = CODEX_ENV_KEY,
) -> str:
    """Return new ``openclaw.json`` text with Coffer's provider block.

    Merges into the user's existing JSON (unrelated keys preserved). The
    ``apiKey`` REFERENCES the env var Coffer injects at spawn time — the raw
    key is never written to disk, same as the Codex/opencode projections. When
    a ``model`` is bound it is declared in the provider's ``models`` list
    (``{id, name}`` both required) and selected as
    ``agents.defaults.model.primary`` (``<provider_id>/<model>``); the user's
    ``fallbacks`` are left untouched. An unbound agent projects an empty
    ``models`` list and leaves ``primary`` alone (clearing only a stale
    ``coffer/…`` selection) so openclaw runs on its OWN configured model.
    """
    data = _load(text)
    providers = _step(_step(data, "models"), "providers")
    block: dict[str, Any] = {
        "api": api,
        "baseUrl": base_url,
        "apiKey": f"${{{env_key}}}",
        "models": [{"id": model, "name": model}] if model else [],
    }
    providers[provider_id] = block
    model_block = _step(_step(_step(data, "agents"), "defaults"), "model")
    if model:
        model_block["primary"] = f"{provider_id}/{model}"
    else:
        existing = model_block.get("primary")
        if isinstance(existing, str) and existing.startswith(f"{provider_id}/"):
            model_block.pop("primary", None)
    _tidy(data)
    return _dump(data)


def remove_openclaw_provider(text: str, *, provider_id: str = CODEX_PROVIDER_ID) -> str:
    """Inverse of :func:`apply_openclaw_provider` — drop Coffer's provider block
    so openclaw falls back to its OWN provider/model. ``primary`` is cleared
    ONLY when it points at Coffer (``<provider_id>/``); the user's ``fallbacks``
    and every unrelated key are preserved."""
    if not text.strip():
        return ""
    data = _load(text)
    models = data.get("models")
    if isinstance(models, MutableMapping):
        providers = models.get("providers")
        if isinstance(providers, MutableMapping):
            providers.pop(provider_id, None)
            if not providers:
                models.pop("providers", None)
        if not models:
            data.pop("models", None)
    agents = data.get("agents")
    if isinstance(agents, MutableMapping):
        defaults = agents.get("defaults")
        if isinstance(defaults, MutableMapping):
            model_block = defaults.get("model")
            if isinstance(model_block, MutableMapping):
                primary = model_block.get("primary")
                if isinstance(primary, str) and primary.startswith(f"{provider_id}/"):
                    model_block.pop("primary", None)
    _tidy(data)
    return _dump(data)


def _tidy(data: dict[str, Any]) -> None:
    """Drop ``agents.defaults.model`` / ``agents.defaults`` / ``agents``
    containers a Coffer write left empty (never touches non-empty ones —
    ``fallbacks`` or any user key keeps the chain alive)."""
    agents = data.get("agents")
    if not isinstance(agents, MutableMapping):
        return
    defaults = agents.get("defaults")
    if isinstance(defaults, MutableMapping):
        model_block = defaults.get("model")
        if isinstance(model_block, MutableMapping) and not model_block:
            defaults.pop("model", None)
        if not defaults:
            agents.pop("defaults", None)
    if not agents:
        data.pop("agents", None)


__all__ = [
    "OPENCLAW_API_ANTHROPIC",
    "OPENCLAW_API_OPENAI",
    "apply_openclaw_provider",
    "remove_openclaw_provider",
]
