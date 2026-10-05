"""The validator's rule for state documents, ``state/<area>/<name>.json``
(spec vault-storage).

A state document is a JSON object at a format version this build can read.
The areas this build writes are checked for their shape: an MCP server's
capability switches (``mcp-preferences``: ``server_uid``, a ``disabled``
map of capability type to key lists and a ``tool_exposure`` map of tool to
``listed`` / ``search``), a channel's pairings
(``channel-peers``: ``channel_uid`` and a ``peers`` list naming each chat),
the command-line tools a person added by hand (``cli-tools``: a ``tools`` list,
each entry naming its ``command``), what a person said about a secret
(``secret-notes``: a ``notes`` map keyed by ref),
and Coffer's own settings (``settings``). Only one document per owner is
admitted: a second path claiming an owner ``HEAD`` already files elsewhere is
``DUPLICATE_UID``. A key this build does not know is a warning; an area it
does not know is accepted as it is.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from coffer.domain.vault.document import DocumentInvalid, decode
from coffer.domain.vault.findings import Finding, FindingCode
from coffer.domain.vault.formats import (
    FORMAT_COMPAT_KEY,
    FORMAT_VERSION_KEY,
    FormatSpec,
    FormatStatus,
    read,
)
from coffer.domain.vault.layout import STATE
from coffer.domain.vault.writes import Change, TreeReader, Validator, Verdict

STATE_FORMAT = FormatSpec(current=1)

#: area -> (owner field, the document's own keys).
AREAS: dict[str, tuple[str | None, frozenset[str]]] = {
    "mcp-preferences": ("server_uid", frozenset({"server_uid", "disabled", "tool_exposure"})),
    "channel-peers": ("channel_uid", frozenset({"channel_uid", "peers"})),
    "cli-tools": (None, frozenset({"tools"})),
    "secret-notes": (None, frozenset({"notes"})),
    # ``model``, ``curate_owner_machine_id`` and ``model_timeout_s`` are keys an
    # older build wrote; they are accepted and ignored, and the next write of
    # the document drops them.
    "settings": (
        None,
        frozenset(
            {"model", "curate_owner_machine_id", "model_timeout_s", "transcribe_model", "upkeep"}
        ),
    ),
}
_COMMON = frozenset({FORMAT_VERSION_KEY, FORMAT_COMPAT_KEY})


def _shape_error(area: str, doc: dict[str, Any]) -> str | None:
    if area == "mcp-preferences":
        disabled = doc.get("disabled", {})
        if not isinstance(disabled, dict) or not all(
            isinstance(keys, list) and all(isinstance(k, str) for k in keys)
            for keys in disabled.values()
        ):
            return "disabled must map a capability type to a list of keys"
        exposure = doc.get("tool_exposure", {})
        if not isinstance(exposure, dict) or not all(
            v in ("listed", "search") for v in exposure.values()
        ):
            return "tool_exposure must map a tool name to listed or search"
    if area == "channel-peers":
        peers = doc.get("peers", [])
        if not isinstance(peers, list) or not all(
            isinstance(p, dict) and isinstance(p.get("chat_id"), str) for p in peers
        ):
            return "peers must be a list of objects, each naming its chat_id"
    if area == "cli-tools":
        tools = doc.get("tools", [])
        if not isinstance(tools, list) or not all(
            isinstance(t, dict) and isinstance(t.get("command"), str) and t["command"]
            for t in tools
        ):
            return "tools must be a list of objects, each naming its command"
        commands = [t["command"] for t in tools]
        if len(set(commands)) != len(commands):
            return "a command is listed twice"
    if area == "secret-notes":
        notes = doc.get("notes", {})
        if not isinstance(notes, dict) or not all(
            isinstance(entry, dict)
            and isinstance(entry.get("label", ""), str)
            and isinstance(entry.get("description", ""), str)
            and isinstance(entry.get("created_for", ""), str)
            and isinstance(entry.get("origin", ""), str)
            for entry in notes.values()
        ):
            return "notes must map a ref to an object with a label and a description"
    if area == "settings" and "upkeep" in doc and not isinstance(doc["upkeep"], dict):
        return "upkeep must be an object"
    return None


def _owner_elsewhere(
    repo: TreeReader, area: str, field: str, owner: str, path: str, touched: set[str]
) -> str | None:
    for other in repo.tree("HEAD", f"{STATE}/{area}/"):
        if other == path or other in touched:
            continue
        data = repo.read("HEAD", other)
        try:
            if data is not None and decode(data).get(field) == owner:
                return other
        except DocumentInvalid:
            continue
    return None


def _judge(change: Change, repo: TreeReader, touched: set[str]) -> list[Finding]:
    path = change.path
    parts = path.split("/")
    area = parts[1] if len(parts) >= 3 else ""
    assert change.data is not None
    try:
        doc = decode(change.data)
    except DocumentInvalid as exc:
        return [Finding(path, FindingCode.INVALID_DOCUMENT, str(exc))]
    try:
        status = read(doc, STATE_FORMAT).status
    except ValueError as exc:
        return [Finding(path, FindingCode.INVALID_DOCUMENT, str(exc))]
    if status is FormatStatus.NEWER_UNREADABLE:
        return [Finding(path, FindingCode.NEWER_FORMAT, "written by a newer Coffer")]
    if area not in AREAS:
        return []
    field, own = AREAS[area]
    out: list[Finding] = []
    if status is FormatStatus.NEWER_READABLE:
        message = "written by a newer Coffer; readable here, and read-only"
        out.append(Finding(path, FindingCode.NEWER_FORMAT_READ_ONLY, message))
    shape = _shape_error(area, doc)
    if shape is not None:
        return [*out, Finding(path, FindingCode.INVALID_DOCUMENT, shape)]
    for key in doc:
        if key not in own and key not in _COMMON:
            message = f"field {key!r} is not known to this build; kept as it is"
            out.append(Finding(path, FindingCode.UNKNOWN_FIELD, message))
    if field is not None:
        owner = doc.get(field)
        if not isinstance(owner, str) or not owner:
            return [*out, Finding(path, FindingCode.MISSING_FIELD, f"{field} is required")]
        other = _owner_elsewhere(repo, area, field, owner, path, touched)
        if other is not None:
            message = f"{other} already holds this {field}"
            out.append(Finding(path, FindingCode.DUPLICATE_UID, message, owner))
    return out


def state_rule() -> Validator:
    def rule(changes: Sequence[Change], repo: TreeReader) -> Verdict:
        touched = {c.path for c in changes if c.data is None}
        findings: list[Finding] = []
        for change in changes:
            if change.data is not None:
                findings.extend(_judge(change, repo, touched))
        return Verdict(findings=findings)

    return rule


__all__ = ["AREAS", "STATE_FORMAT", "state_rule"]
