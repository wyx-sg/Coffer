"""A provider projection as the parameters a reconcile pass compares.

ADR one-level-triggered-reconciler-compares-parameters. Whether Coffer's keys
are *in* an agent's config (``ProviderProjection.is_present``) says nothing
about whether they are the *right* keys: a base URL, a model, an
``apiKeyHelper`` command or a model catalogue that no longer matches the
connection reads as "projected" to a presence test. These pure functions turn a
config document into the dotted keys Coffer owns in it, so two documents can be
compared parameter by parameter.

Coffer's keys in a document are the dotted keys whose value differs between
the document and what the facet's ``remove`` would leave of it. Both sides of a
comparison are measured against the same baseline — the file with Coffer's keys
taken out — so a key the projection deletes (``ANTHROPIC_API_KEY``, which would
override the helper) is owned too.

No value that could be a secret leaves this module in the clear: a key whose
name contains ``KEY`` / ``TOKEN`` / ``SECRET`` / ``PASSWORD`` is compared by
digest and rendered redacted. The ``apiKeyHelper`` is the one exception — it
is a command naming a connection by uid, never a key.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from collections.abc import Iterable, Mapping
from typing import Any

#: Formats a projected file may be in (``ConfigFileFormat`` values).
_JSON = "json"
_TOML = "toml"
_SECRET_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD")
#: Settings keys that name a command, not a secret, though the name says KEY.
_NOT_SECRET = frozenset({"apiKeyHelper"})
_REDACTED = "<redacted>"
_DIGEST_PREFIX = "sha256:"


class DocumentInvalidError(ValueError):
    """The document does not parse in its format; nothing is guessed from it."""


def parse_document(fmt: str, text: str) -> dict[str, Any]:
    """``text`` as data. An empty document is an empty mapping."""
    if not text.strip():
        return {}
    try:
        if fmt == _JSON:
            doc = json.loads(text)
        elif fmt == _TOML:
            doc = tomllib.loads(text)
        else:
            raise DocumentInvalidError(f"unsupported projection format {fmt!r}")
    except (json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        raise DocumentInvalidError(str(exc)) from exc
    if not isinstance(doc, dict):
        raise DocumentInvalidError("top level is not a mapping")
    return doc


def flatten(doc: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    """Nested mappings as dotted keys; lists and scalars are leaves. An empty
    mapping contributes nothing: the ``env`` a de-projection empties is the
    same document as one it removed."""
    out: dict[str, Any] = {}
    for key, value in doc.items():
        name = f"{prefix}{key}"
        if isinstance(value, Mapping):
            out.update(flatten(value, f"{name}."))
        else:
            out[name] = value
    return out


def owned_keys(with_coffer: Mapping[str, Any], without: Mapping[str, Any]) -> set[str]:
    """The dotted keys whose value differs between the two flattened documents."""
    names = set(with_coffer) | set(without)
    return {n for n in names if with_coffer.get(n) != without.get(n)}


def is_secret_key(name: str) -> bool:
    leaf = name.rsplit(".", 1)[-1]
    if leaf in _NOT_SECRET:
        return False
    upper = leaf.upper()
    return any(marker in upper for marker in _SECRET_MARKERS)


def digest(text: str | None) -> str | None:
    """A short content digest, or ``None`` for a file that is not there."""
    if text is None:
        return None
    return _DIGEST_PREFIX + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def params_of(flat: Mapping[str, Any], keys: Iterable[str]) -> dict[str, Any]:
    """The values of ``keys`` in ``flat`` (``None`` when absent), a secret-named
    key's value replaced by its digest so equality still holds."""
    out: dict[str, Any] = {}
    for key in sorted(keys):
        value = flat.get(key)
        if value is not None and is_secret_key(key):
            value = digest(json.dumps(value, sort_keys=True))
        out[key] = value
    return out


def render(params: Mapping[str, Any]) -> str:
    """A rendering safe to show a person: every secret-named value redacted."""
    safe = {k: (_REDACTED if v is not None and is_secret_key(k) else v) for k, v in params.items()}
    return json.dumps(safe, indent=2, sort_keys=True, default=str)


__all__ = [
    "DocumentInvalidError",
    "digest",
    "flatten",
    "is_secret_key",
    "owned_keys",
    "params_of",
    "parse_document",
    "render",
]
