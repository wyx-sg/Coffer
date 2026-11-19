"""Which keys of an agent's MCP entry hold secrets, and the entry's other keys
with those withheld — the adopt-time pattern the dialogs and the import plan
share."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

_SECRET_KEY_RE = re.compile(
    r"(TOKEN|SECRET|PASSWORD|PASSWD|API_?KEY|CREDENTIAL|AUTHORIZATION)", re.IGNORECASE
)


def secret_env_keys(env: dict[str, str]) -> list[str]:
    """Return sorted list of env keys whose names look like secrets.

    A key is considered secret if its value is non-empty and its name matches
    TOKEN|SECRET|PASSWORD|PASSWD|API_?KEY|CREDENTIAL|AUTHORIZATION (case-insensitive).
    """
    return sorted(k for k, v in env.items() if v and _SECRET_KEY_RE.search(k))


def looks_secret(key: str) -> bool:
    """Whether a key NAME looks like it holds a secret (the adopt-time pattern)."""
    return bool(_SECRET_KEY_RE.search(key))


def _holds_secret(value: Any) -> bool:
    """Whether a nested mapping/list carries a secret-looking key anywhere in it."""
    if isinstance(value, dict):
        return any(looks_secret(k) or _holds_secret(v) for k, v in value.items())
    if isinstance(value, list):
        return any(_holds_secret(v) for v in value)
    return False


@dataclass(frozen=True)
class ExtraField:
    """One of an entry's other keys, ready to show: ``value`` is ``None`` when masked."""

    key: str
    value: str | None
    masked: bool


def masked_extra(extra: dict[str, Any]) -> list[ExtraField]:
    """The entry's other keys, sorted, with anything secret-looking withheld.

    A key whose own name looks secret (and whose value is non-empty), or whose
    value nests a secret-looking key at any depth, is masked whole: its value
    never leaves this function. Everything else is rendered as text — strings
    as themselves, other values as compact JSON.
    """
    out: list[ExtraField] = []
    for key in sorted(extra):
        value = extra[key]
        if (looks_secret(key) and value not in (None, "")) or _holds_secret(value):
            out.append(ExtraField(key=key, value=None, masked=True))
            continue
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        out.append(ExtraField(key=key, value=text, masked=False))
    return out
