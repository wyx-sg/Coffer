"""Path portability for synced config (spec 010 slice 5, ADR-043).

The user's machines have different usernames/home layouts, so absolute paths
inside resource configs (`config_dir`, command paths) break when synced
verbatim. Two pure mechanisms, applied in order at import:

1. ``${HOME}`` normalization — export rewrites string values whose prefix is
   the exporting machine's home directory to ``${HOME}/...``; import expands
   the token to the importing machine's home. Zero-config, covers the
   same-relative-layout case.
2. Per-machine overrides — an RFC 7386 JSON Merge Patch stored under the
   machine's own workspace dir, for values that genuinely differ (an
   Intel-vs-ARM homebrew path). Export strips the overridden keys back to the
   last shared values so a machine's local specialization never leaks into
   the medium.

Everything here is pure: homes and patches are passed in; IO lives in the
sync workspace.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

HOME_TOKEN = "${HOME}"


def _map_strings(value: Any, fn: Any) -> Any:
    if isinstance(value, str):
        return fn(value)
    if isinstance(value, Mapping):
        return {k: _map_strings(v, fn) for k, v in value.items()}
    if isinstance(value, list):
        return [_map_strings(v, fn) for v in value]
    return value


def normalize_home(config: Mapping[str, Any], home: str) -> dict[str, Any]:
    """Rewrite string values under ``home`` to portable ``${HOME}/...`` form.

    Only prefix matches at a path-boundary count: ``/Users/xing/x`` matches for
    home ``/Users/xing``, ``/Users/xingelsewhere`` does not. A value already
    containing the literal token is left as-is (documented edge)."""
    root = home.rstrip("/")
    if not root:
        return dict(config)

    def rewrite(s: str) -> str:
        if s == root:
            return HOME_TOKEN
        if s.startswith(root + "/"):
            return HOME_TOKEN + s[len(root) :]
        return s

    result: dict[str, Any] = _map_strings(dict(config), rewrite)
    return result


def expand_home(config: Mapping[str, Any], home: str) -> dict[str, Any]:
    """Expand ``${HOME}`` tokens to this machine's home directory."""
    root = home.rstrip("/")

    def rewrite(s: str) -> str:
        if s == HOME_TOKEN:
            return root
        if s.startswith(HOME_TOKEN + "/"):
            return root + s[len(HOME_TOKEN) :]
        return s

    result: dict[str, Any] = _map_strings(dict(config), rewrite)
    return result


def apply_merge_patch(target: Mapping[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    """RFC 7386 JSON Merge Patch: dicts merge recursively, ``null`` removes a
    key, anything else replaces."""
    out: dict[str, Any] = dict(target)
    for key, value in patch.items():
        if value is None:
            out.pop(key, None)
        elif isinstance(value, Mapping) and isinstance(out.get(key), Mapping):
            out[key] = apply_merge_patch(out[key], value)
        else:
            out[key] = value if not isinstance(value, Mapping) else apply_merge_patch({}, value)
    return out


def strip_overridden(
    live: Mapping[str, Any],
    patch: Mapping[str, Any],
    shared: Mapping[str, Any],
) -> dict[str, Any]:
    """Reconstruct the SHARED view of a locally-patched config for export.

    For every key the patch touches, the last shared value wins (or the key
    disappears if the shared doc never had it) — a machine's per-machine
    specialization must not leak into the medium and overwrite the fleet."""
    out: dict[str, Any] = dict(live)
    for key, value in patch.items():
        if isinstance(value, Mapping) and isinstance(out.get(key), Mapping):
            out[key] = strip_overridden(
                out[key],
                value,
                shared.get(key, {}) if isinstance(shared.get(key), Mapping) else {},
            )
        elif key in shared:
            out[key] = shared[key]
        else:
            out.pop(key, None)
    return out
