"""Pure text transforms that project a connection into OpenCode's
``opencode.json`` (spec provider-switching "Project into OpenCode config without
overwriting it"; ADR opencode-reads-its-proxy-token-from-a-file).

OpenCode gets one custom provider, ``provider.coffer``, in the shape both
OpenCode 1.x and 2.x read: the ``@ai-sdk/openai`` package, so requests go to the
Responses API the local model proxy serves, ``options.baseURL`` at the proxy's
OpenAI route, and ``options.apiKey`` as a ``{file:…}`` reference to the agent's
proxy token file. OpenCode runs no command for a key, so the token sits in a
file of its own under Coffer's folder rather than in ``opencode.json``. The
connection's curated models become the provider's ``models``, and the bound
model becomes the top-level ``model`` (``coffer/<id>``).

De-projection removes ``provider.coffer`` and a top-level ``model`` that points
into it; every other key is the user's and stays.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Sequence
from typing import Any

from coffer.domain.errors import ConfigFileFormatInvalid
from coffer.domain.provider.model_binding import ProjectedModel

#: The ``provider`` key Coffer owns, and the prefix of a model it selects.
OPENCODE_PROVIDER_ID = "coffer"
#: The AI SDK package OpenCode loads for the provider: it speaks the Responses
#: API, the one OpenAI route the model proxy relays.
OPENCODE_PROVIDER_PACKAGE = "@ai-sdk/openai"
#: OpenCode 1.x requires ``limit.output`` beside ``limit.context``; this is
#: OpenCode's own cap on a reply, so writing it changes nothing it would do.
OPENCODE_OUTPUT_LIMIT = 32_000

_PREFIX = OPENCODE_PROVIDER_ID + "/"


def _load(text: str) -> dict[str, Any]:
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except ValueError as e:
        raise ConfigFileFormatInvalid("json", str(e)) from e
    if not isinstance(data, dict):
        raise ConfigFileFormatInvalid("json", "top-level value must be an object")
    return data


def _dump(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def token_reference(token_file: pathlib.Path) -> str:
    """The ``apiKey`` value: OpenCode reads the file's text at startup."""
    return "{file:" + str(token_file) + "}"


def _model_entry(model_id: str, window: int | None) -> dict[str, Any]:
    entry: dict[str, Any] = {"name": model_id}
    if window:
        entry["limit"] = {"context": window, "output": min(OPENCODE_OUTPUT_LIMIT, window)}
    return entry


def provider_block(
    *,
    display_name: str,
    base_url: str,
    token_file: pathlib.Path,
    models: Sequence[ProjectedModel],
    model: str | None,
    context_window: int | None = None,
) -> dict[str, Any]:
    """``provider.coffer``: the connection's models, plus the bound model
    when the connection curates none (an unrestricted connection)."""
    entries = {m.id: _model_entry(m.id, m.context_window) for m in models}
    if model and model not in entries:
        entries[model] = _model_entry(model, context_window)
    return {
        "npm": OPENCODE_PROVIDER_PACKAGE,
        "name": display_name,
        "options": {"baseURL": base_url, "apiKey": token_reference(token_file)},
        "models": entries,
    }


def apply_opencode_provider(
    text: str,
    *,
    display_name: str,
    base_url: str,
    token_file: pathlib.Path,
    models: Sequence[ProjectedModel],
    model: str | None,
    context_window: int | None = None,
) -> str:
    """``text`` with ``provider.coffer`` written and, when the agent has a
    bound model, the top-level ``model`` pointing at it. Without a binding a
    ``model`` of Coffer's is dropped, so OpenCode never selects a model the
    provider no longer lists; the user's own ``model`` stays."""
    data = _load(text)
    providers = data.get("provider")
    if not isinstance(providers, dict):
        providers = {}
        data["provider"] = providers
    providers[OPENCODE_PROVIDER_ID] = provider_block(
        display_name=display_name,
        base_url=base_url,
        token_file=token_file,
        models=models,
        model=model,
        context_window=context_window,
    )
    if model:
        data["model"] = _PREFIX + model
    elif _is_coffer_model(data.get("model")):
        del data["model"]
    return _dump(data)


def _is_coffer_model(value: object) -> bool:
    return isinstance(value, str) and value.startswith(_PREFIX)


def remove_opencode_provider(text: str) -> str:
    """``text`` without ``provider.coffer`` and without a top-level ``model``
    that selects it. An empty ``provider`` table Coffer leaves behind goes too."""
    data = _load(text)
    providers = data.get("provider")
    if isinstance(providers, dict) and OPENCODE_PROVIDER_ID in providers:
        del providers[OPENCODE_PROVIDER_ID]
        if not providers:
            del data["provider"]
    if _is_coffer_model(data.get("model")):
        del data["model"]
    if not text.strip() and not data:
        return text
    return _dump(data)


def opencode_provider_present(text: str) -> bool:
    """Whether ``text`` holds any key Coffer's projection writes."""
    data = _load(text)
    providers = data.get("provider")
    return (isinstance(providers, dict) and OPENCODE_PROVIDER_ID in providers) or (
        _is_coffer_model(data.get("model"))
    )


def set_opencode_model(text: str, model: str | None) -> str:
    """``text`` with the top-level ``model`` set to ``model`` as written
    (``provider/model``), or removed for ``None``."""
    data = _load(text)
    if model:
        data["model"] = model
    else:
        data.pop("model", None)
    return _dump(data)


__all__ = [
    "OPENCODE_OUTPUT_LIMIT",
    "OPENCODE_PROVIDER_ID",
    "OPENCODE_PROVIDER_PACKAGE",
    "apply_opencode_provider",
    "opencode_provider_present",
    "provider_block",
    "remove_opencode_provider",
    "set_opencode_model",
    "token_reference",
]
