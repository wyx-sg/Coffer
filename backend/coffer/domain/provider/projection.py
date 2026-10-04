"""Pure text transforms that project a connection into Claude Code's
``settings.json`` (the Codex half is :mod:`coffer.domain.provider.codex_projection`).

No filesystem access — the application layer reads the agent's native config
file, calls one of these to produce new text, and writes it back through the
atomic store. Both halves write ONLY Coffer-managed keys, merging into the
user's existing file so unrelated content is preserved.

What Claude Code gets (spec provider-switching "Project into Claude Code
settings without clobbering them"):

- ``apiKeyHelper`` — a command Coffer names; the key is fetched on demand,
  never written.
- ``env.ANTHROPIC_BASE_URL`` — where the agent sends its requests.
- the top-level ``model`` — NOT ``env.ANTHROPIC_MODEL``,
  which outranks ``model`` and would undo the user's own ``/model`` choice at
  every launch.
- ``env.ANTHROPIC_DEFAULT_<TIER>_MODEL`` for each pinned tier — the Haiku pin
  also runs background tasks, which otherwise run on the main model behind a
  custom base URL.
- ``modelPicker`` — the connection's curated models in Claude Code's ``/model``
  picker, replacing the built-in rows on an endpoint that serves no Claude ids.
- for a local runtime, ``CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS`` (local
  runtimes reject Claude Code's beta request fields) and
  ``CLAUDE_CODE_MAX_CONTEXT_TOKENS`` (Claude Code assumes 200k for an id it
  does not know).
- ``env.NO_PROXY`` gains ``127.0.0.1,localhost`` when the base URL is the local
  model proxy, so a corporate ``HTTPS_PROXY`` never captures the loopback leg.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from coffer.domain.agent.tiers import CLAUDE_TIERS, tier_env_key
from coffer.domain.provider.api_key_helper import is_managed_api_key_helper
from coffer.domain.provider.codex_projection import (
    CODEX_CATALOG_TRUNCATION_LIMIT as CODEX_CATALOG_TRUNCATION_LIMIT,
)
from coffer.domain.provider.codex_projection import (
    CODEX_MODEL_CATALOG_FILENAME as CODEX_MODEL_CATALOG_FILENAME,
)
from coffer.domain.provider.codex_projection import (
    CODEX_MODEL_CATALOG_KEY as CODEX_MODEL_CATALOG_KEY,
)
from coffer.domain.provider.codex_projection import (
    CODEX_PROVIDER_ID as CODEX_PROVIDER_ID,
)
from coffer.domain.provider.codex_projection import (
    apply_codex_provider as apply_codex_provider,
)
from coffer.domain.provider.codex_projection import (
    codex_model_catalog_json as codex_model_catalog_json,
)
from coffer.domain.provider.codex_projection import (
    codex_model_catalog_path as codex_model_catalog_path,
)
from coffer.domain.provider.codex_projection import (
    remove_codex_provider as remove_codex_provider,
)

#: Keys written into ``env`` besides the tier pins.
_BASE_URL = "ANTHROPIC_BASE_URL"
_DISABLE_BETAS = "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS"
_MAX_CONTEXT = "CLAUDE_CODE_MAX_CONTEXT_TOKENS"
_NO_PROXY = "NO_PROXY"
#: What ``NO_PROXY`` gains while the base URL is the loopback proxy.
LOOPBACK_NO_PROXY = ("127.0.0.1", "localhost")
#: The description every ``modelPicker`` option Coffer writes carries — the
#: ownership marker de-projection reads, as the helper's command is for
#: ``apiKeyHelper``. A picker the user wrote never carries it on every row.
PICKER_MARKER = "via Coffer"


def _load(text: str) -> dict[str, Any]:
    data = json.loads(text) if text.strip() else {}
    return data if isinstance(data, dict) else {}


def _dump(data: Mapping[str, Any]) -> str:
    # ensure_ascii=False: settings.json may hold non-ASCII user content; don't
    # rewrite it to \uXXXX on every switch.
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _split(value: object) -> list[str]:
    if not isinstance(value, str):
        return []
    return [p.strip() for p in value.split(",") if p.strip()]


def _add_no_proxy(env: dict[str, Any]) -> None:
    parts = _split(env.get(_NO_PROXY))
    for host in LOOPBACK_NO_PROXY:
        if host not in parts:
            parts.append(host)
    env[_NO_PROXY] = ",".join(parts)


def _drop_no_proxy(env: dict[str, Any]) -> None:
    """Take back only what :func:`_add_no_proxy` appended: the loopback pair
    at the END of the list. A pair the user placed elsewhere is theirs."""
    parts = _split(env.get(_NO_PROXY))
    tail = list(LOOPBACK_NO_PROXY)
    if parts[-len(tail) :] != tail:
        return
    rest = parts[: -len(tail)]
    if rest:
        env[_NO_PROXY] = ",".join(rest)
    else:
        env.pop(_NO_PROXY, None)


def _is_managed_picker(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    options = value.get("options")
    return (
        isinstance(options, list)
        and bool(options)
        and all(isinstance(o, dict) and o.get("description") == PICKER_MARKER for o in options)
    )


def model_picker(models: Sequence[str], *, replace_builtin: bool) -> dict[str, Any]:
    """The ``modelPicker`` value listing ``models`` (ids as labels — Coffer
    authors no model names)."""
    return {
        "options": [{"model": m, "label": m, "description": PICKER_MARKER} for m in models],
        "replaceBuiltInOptions": replace_builtin,
    }


def apply_anthropic_settings(
    text: str,
    *,
    base_url: str,
    api_key_helper: str,
    model: str | None = None,
    tier_models: Mapping[str, str] | None = None,
    picker_models: Sequence[str] = (),
    replace_builtin_picker: bool = False,
    local_context_window: int | None = None,
    local: bool = False,
) -> str:
    """Return new ``settings.json`` text with Coffer's keys.

    ``model`` ``None`` leaves the user's own top-level key as it
    is (the agent runs on whatever it was set to); a tier missing from
    ``tier_models`` is unpinned. ``api_key_helper`` is REQUIRED and has no
    default: a caller must name what the helper resolves.
    """
    data = _load(text)
    data["apiKeyHelper"] = api_key_helper
    env = data.get("env")
    if not isinstance(env, dict):
        env = {}
        data["env"] = env
    env[_BASE_URL] = base_url
    if model:
        data["model"] = model
    pins = dict(tier_models or {})
    for tier in CLAUDE_TIERS:
        if pins.get(tier):
            env[tier_env_key(tier)] = pins[tier]
        else:
            env.pop(tier_env_key(tier), None)
    if picker_models:
        data["modelPicker"] = model_picker(picker_models, replace_builtin=replace_builtin_picker)
    elif _is_managed_picker(data.get("modelPicker")):
        data.pop("modelPicker", None)
    if local:
        env[_DISABLE_BETAS] = "1"
    else:
        env.pop(_DISABLE_BETAS, None)
    if local and local_context_window:
        env[_MAX_CONTEXT] = str(local_context_window)
    else:
        env.pop(_MAX_CONTEXT, None)
    _add_no_proxy(env)
    return _dump(data)


def remove_anthropic_settings(text: str, *, managed_model: str | None = None) -> str:
    """Inverse of :func:`apply_anthropic_settings` — strip every key Coffer
    wrote so Claude Code falls back to its OWN login ("use built-in").

    ``apiKeyHelper`` goes only when it is Coffer's (:func:`is_managed_api_key_helper`);
    the ``env`` keys (base URL, tier pins, the local-runtime pair, the
    loopback ``NO_PROXY`` tail) go only while that helper was there — with a
    helper the user wrote or none at all they are the user's own and stay;
    ``modelPicker`` only when every option carries :data:`PICKER_MARKER`, and
    the top-level ``model`` only while it still holds what Coffer projected
    (``managed_model``, the agent's binding): a model the user has since picked
    with ``/model`` is theirs and stays. Unrelated keys are preserved.
    """
    raw = json.loads(text) if text.strip() else {}
    if not isinstance(raw, dict):
        return "{}\n"
    data: dict[str, Any] = raw
    # The ownership marker for the ``env`` keys: they carry no mark of their
    # own, so they are Coffer's only while Coffer's helper is in the file.
    owned = is_managed_api_key_helper(data.get("apiKeyHelper"))
    if owned:
        data.pop("apiKeyHelper", None)
    if _is_managed_picker(data.get("modelPicker")):
        data.pop("modelPicker", None)
    if managed_model is not None and data.get("model") == managed_model:
        data.pop("model", None)
    env = data.get("env")
    if owned and isinstance(env, dict):
        for key in (_BASE_URL, _DISABLE_BETAS, _MAX_CONTEXT):
            env.pop(key, None)
        for tier in CLAUDE_TIERS:
            env.pop(tier_env_key(tier), None)
        _drop_no_proxy(env)
    return _dump(data)


__all__ = [
    "CODEX_CATALOG_TRUNCATION_LIMIT",
    "CODEX_MODEL_CATALOG_FILENAME",
    "CODEX_MODEL_CATALOG_KEY",
    "CODEX_PROVIDER_ID",
    "LOOPBACK_NO_PROXY",
    "PICKER_MARKER",
    "apply_anthropic_settings",
    "apply_codex_provider",
    "codex_model_catalog_json",
    "codex_model_catalog_path",
    "model_picker",
    "remove_anthropic_settings",
    "remove_codex_provider",
]
