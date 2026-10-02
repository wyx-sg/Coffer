"""The whole of one MCP entry as the agent's file holds it, secrets withheld.

The direct-server detail page shows the entry's complete configuration, not a
reconstructed subset. Everything that could carry a credential is replaced by
``MASK`` before the entry leaves the daemon (spec agent-registry "Show one
direct MCP entry's full configuration without its secrets"):

* every value under an ``env`` / ``environment`` / ``headers`` /
  ``http_headers`` map — their key names stay, as they do everywhere else;
* the value of any key whose NAME looks secret (token, key, secret, password,
  authorization, credential...), at any depth;
* a ``--flag=value`` argument whose flag looks secret, and the argument after a
  bare secret-looking ``--flag``;
* the password and secret-looking query values of any URL, and the credential
  of an ``Authorization``-style ``Bearer``/``Basic`` string.

Pure functions over plain Python values — no I/O.
"""

from __future__ import annotations

import re
from typing import Any

from coffer.domain.agent.mcp_entries import looks_secret

MASK = "••••••"

#: Maps whose every value is withheld (their keys stay).
_VALUE_MAPS = frozenset({"env", "environment", "headers", "http_headers", "env_http_headers"})
_KEY_NAME_RE = re.compile(r"(^|[_\-.])(KEY|PAT|PASS)$|ACCESS[_\-]?KEY|PRIVATE[_\-]?KEY", re.I)
_URL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://")
_BEARER_RE = re.compile(r"\b(Bearer|Basic)\s+\S+", re.IGNORECASE)
_FLAG_VALUE_RE = re.compile(r"^(-{1,2}[^=\s]+)=(.*)$", re.DOTALL)


def _secret_name(name: str) -> bool:
    return looks_secret(name) or bool(_KEY_NAME_RE.search(name))


def _mask_url(text: str) -> str:
    """``text`` with a URL's userinfo password and secret-looking query values withheld."""
    scheme, sep, rest = text.partition("://")
    authority, slash, tail = rest.partition("/")
    if "@" in authority:
        userinfo, _, host = authority.rpartition("@")
        user = userinfo.partition(":")[0]
        authority = f"{user}:{MASK}@{host}" if ":" in userinfo else f"{MASK}@{host}"
    path, qmark, query = tail.partition("?")
    if qmark:
        pairs = []
        for pair in query.split("&"):
            name, eq, _value = pair.partition("=")
            pairs.append(f"{name}={MASK}" if eq and _secret_name(name) else pair)
        tail = f"{path}?{'&'.join(pairs)}"
    return f"{scheme}{sep}{authority}{slash}{tail}"


def _mask_text(text: str) -> str:
    """A free string: a URL's credentials, a Bearer/Basic credential."""
    if _URL_RE.match(text):
        text = _mask_url(text)
    return _BEARER_RE.sub(lambda m: f"{m.group(1)} {MASK}", text)


def _mask_all(value: Any) -> Any:
    """Every scalar leaf of ``value`` withheld (empty strings stay empty)."""
    if isinstance(value, dict):
        return {k: _mask_all(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask_all(v) for v in value]
    if value is None or isinstance(value, bool) or value == "":
        return value
    return MASK


def _mask_args(items: list[Any]) -> list[Any]:
    out: list[Any] = []
    withhold_next = False
    for item in items:
        if not isinstance(item, str):
            out.append(_redact("", item))
            withhold_next = False
            continue
        flag = _FLAG_VALUE_RE.match(item)
        if withhold_next and not item.startswith("-"):
            out.append(MASK)
        elif flag and _secret_name(flag.group(1)):
            out.append(f"{flag.group(1)}={MASK}")
        else:
            out.append(_mask_text(item))
        withhold_next = item.startswith("-") and not flag and _secret_name(item)
    return out


def _redact(key: str, value: Any) -> Any:
    if key.lower() in _VALUE_MAPS:
        return _mask_all(value)
    if key and _secret_name(key):
        return _mask_all(value)
    if isinstance(value, dict):
        return {k: _redact(k, v) for k, v in value.items()}
    if isinstance(value, list):
        # A `command` array is the executable followed by its arguments.
        return _mask_args(value) if key in {"args", "command"} else [_redact("", v) for v in value]
    if isinstance(value, str):
        return _mask_text(value)
    return value


def redacted_config(raw: dict[str, Any]) -> dict[str, Any]:
    """The entry exactly as the file holds it, every credential-bearing value withheld."""
    return {str(k): _redact(str(k), v) for k, v in raw.items()}
