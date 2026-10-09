"""The validator's rule for resource files, ``resources/<kind>/<name>.json``
(spec vault-storage "Identify a resource by the uid inside its file", "Carry
a format version on every vault document", "Keep the last valid version when
a hand edit is invalid").

Every change under ``resources/`` — a person's edit found by the scanner, a
daemon write, a merge — is judged here before it may be committed:

- the bytes must be a resource document (``INVALID_DOCUMENT``), filed under
  its own kind's directory (``KIND_MISMATCH``), with a usable name;
- its ``format_version`` is compared with this build's (every kind is at 1
  today): a file this build cannot read is ``NEWER_FORMAT``, a readable newer
  one is committed with a ``NEWER_FORMAT_READ_ONLY`` warning, an edit to an
  older one waiting for its layout upgrade is ``OLDER_FORMAT_EDIT``;
- its config is validated by the kind's ``config_schema`` as the kind reads
  it — a ``${HOME}/...`` path the store wrote is expanded first — and a config key
  the schema does not declare is ``CONFIG_INVALID``, as the kinds' own models
  refuse it (``extra="forbid"``): a file written by hand or arriving in a
  merge is held to exactly what an API write is. A top-level document field
  this build does not know is an ``UNKNOWN_FIELD`` warning and is kept (ADR
  every-vault-file-carries-its-format-version: a newer build of the same
  format may add one), and so is a kind this build does not know at all (a
  newer build's kind: kept, inert);
- its name passes the framework's rule for the kind — free text for a
  provider or a channel (``Kind.free_name``), a fixed slug for the rest — and
  the kind's own ``validate_name`` (``mcp_server``'s 24-character cap and
  ``__`` separator, a skill's hyphen-only charset), on every change, so a
  merge or a hand rename is judged as a register is;
- a file with no ``uid`` is a new resource: the rule asks for a fix that
  mints one, which the writer commits as the daemon's own right after the
  person's commit;
- a uid another path held at ``HEAD`` makes the newcomer ``DUPLICATE_UID``
  (a copied file) — unless that path is going away in the same change, which
  is a move — and a name another resource of the kind already has (ignoring
  case, for a free-text name) is ``NAME_TAKEN``;
- a config flag the kind lets only one resource hold (``Kind.exclusive_flags``:
  ``provider``'s ``transcribe_default``) set while another resource holds it —
  at ``HEAD`` or in the same change — is ``CONFIG_INVALID`` on the file that
  sets it (spec provider-switching "Keep an independent speech-to-text default":
  what a partial unique index enforced in SQL).

Plain-text secrets are not detected here: the detector lives in
infrastructure (``credentials.plaintext_scan``) and this layer may not import
it.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime

from pydantic import ValidationError

from coffer.domain.resource import (
    InvalidResourceNameError,
    Kind,
    normalise_free_name,
    validate_resource_name,
)
from coffer.domain.vault.config_keys import known_keys
from coffer.domain.vault.document import DocumentInvalid, ResourceDocument, parse_resource
from coffer.domain.vault.findings import Finding, FindingCode
from coffer.domain.vault.formats import FormatSpec, FormatStatus, read
from coffer.domain.vault.layout import kind_of_resource_path
from coffer.domain.vault.portability import expand_home
from coffer.domain.vault.writes import Change, Fix, TreeReader, Validator, Verdict

#: Every kind's resource document is at format 1 today.
RESOURCE_FORMAT = FormatSpec(current=1)

#: Config keys a kind used to read and no longer does, per kind. A file that
#: still carries one (a hand edit, or a sync from a machine not yet updated) is
#: accepted and the key ignored — the schema drops it on the file's next write.
_RETIRED_CONFIG_KEYS: Mapping[str, frozenset[str]] = {
    "agent": frozenset({"effort"}),
    "provider": frozenset({"internal_default"}),
}

#: The home a file's ``${HOME}`` token is expanded against before its config is
#: validated. The store writes a path under the writing machine's home as
#: ``${HOME}/...`` and every reader expands it against its own home, so a kind
#: only ever sees an absolute path there; validating the raw token would refuse
#: every such path (a channel's ``directories``, its default ``cwd``). Any
#: absolute home gives the same verdict, and a fixed one keeps the verdict the
#: same on every machine that judges the file (a merge, a hand edit).
_STAND_IN_HOME = "/home/coffer"

#: ``{uid: (path, kind, name)}`` of every resource at ``HEAD``.
HeadOwners = Callable[[], Mapping[str, tuple[str, str, str]]]


def _config_findings(
    path: str, doc: ResourceDocument, kind_def: Kind, uid: str | None
) -> list[Finding]:
    out: list[Finding] = []
    # The config as the kind reads it: ``${HOME}`` expanded, as the store does.
    config = expand_home(doc.config, _STAND_IN_HOME)
    known = known_keys(kind_def.config_schema, config)
    subset = config
    if known is not None:
        retired = _RETIRED_CONFIG_KEYS.get(doc.kind, frozenset())
        for key in config:
            if key not in known and key not in retired:
                message = f"config: {key!r} is not a {doc.kind} setting"
                out.append(Finding(path, FindingCode.CONFIG_INVALID, message, uid))
        subset = {k: v for k, v in config.items() if k in known}
    try:
        kind_def.config_schema.model_validate(subset)
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {"msg": str(exc), "loc": ()}
        where = ".".join(str(p) for p in first.get("loc", ())) or "config"
        out.append(Finding(path, FindingCode.CONFIG_INVALID, f"{where}: {first.get('msg')}", uid))
    try:
        if kind_def.free_name:
            normalise_free_name(doc.name)
        else:
            validate_resource_name(doc.name)
        if kind_def.validate_name is not None:
            kind_def.validate_name(doc.name)
    except (InvalidResourceNameError, ValueError) as exc:
        out.append(Finding(path, FindingCode.INVALID_DOCUMENT, str(exc), uid))
    return out


def _format_findings(change: Change, doc: ResourceDocument) -> list[Finding]:
    status = read(doc.raw, RESOURCE_FORMAT).status
    path, uid = change.path, doc.uid
    if status is FormatStatus.NEWER_UNREADABLE:
        return [
            Finding(
                path,
                FindingCode.NEWER_FORMAT,
                f"written by a newer Coffer (format {doc.format_version}); "
                "update Coffer to read it",
                uid,
            )
        ]
    if status is FormatStatus.NEWER_READABLE:
        return [
            Finding(
                path,
                FindingCode.NEWER_FORMAT_READ_ONLY,
                "written by a newer Coffer; readable here, and read-only",
                uid,
            )
        ]
    if status is FormatStatus.OLDER and change.before is not None and change.before != change.data:
        return [
            Finding(
                path,
                FindingCode.OLDER_FORMAT_EDIT,
                "this file waits for its format upgrade; edit it once the owner machine has "
                "upgraded it",
                uid,
            )
        ]
    return []


def resource_rule(kinds: Mapping[str, Kind], head_owners: HeadOwners) -> Validator:
    """The rule for ``resources/``, over the live kind registry and the uids
    ``HEAD`` holds."""

    def rule(changes: Sequence[Change], _repo: TreeReader) -> Verdict:
        verdict = Verdict()
        owners = head_owners()
        touched = {c.path for c in changes}
        removed = {c.path for c in changes if c.data is None}
        claimed: dict[str, str] = {}
        names: dict[tuple[str, str], str] = {
            _name_key(kinds, kind, name): uid
            for uid, (path, kind, name) in owners.items()
            if path not in touched
        }
        for change in sorted(changes, key=lambda c: c.path):
            if change.data is None:
                continue
            found = _judge(change, kinds, owners, removed, claimed, names)
            verdict.findings.extend(found.findings)
            verdict.fixes.extend(found.fixes)
        verdict.findings.extend(_exclusive_findings(changes, kinds, _repo))
        return verdict

    return rule


def _flagged(data: bytes | None, flag: str) -> str | None:
    """The uid of the resource document ``data`` when it sets ``flag``."""
    if data is None:
        return None
    try:
        doc = parse_resource(data)
    except DocumentInvalid:
        return None
    return (doc.uid or "") if doc.config.get(flag) is True else None


def _exclusive_findings(
    changes: Sequence[Change], kinds: Mapping[str, Kind], repo: TreeReader
) -> list[Finding]:
    out: list[Finding] = []
    for kind_name, kind_def in sorted(kinds.items()):
        if not kind_def.exclusive_flags:
            continue
        prefix = f"resources/{kind_name}/"
        mine = {c.path: c.data for c in changes if c.path.startswith(prefix)}
        if not mine:
            continue
        paths = set(repo.tree("HEAD", prefix)) | set(mine)
        for flag in kind_def.exclusive_flags:
            holders: dict[str, str] = {}
            for path in sorted(paths):
                data = mine[path] if path in mine else repo.read("HEAD", path)
                uid = _flagged(data, flag)
                if uid is not None:
                    holders[path] = uid
            if len(set(holders.values())) < 2:
                continue
            for path, uid in holders.items():
                if path in mine and mine[path] is not None:
                    others = sorted(p for p, u in holders.items() if u != uid)
                    message = f"config: {flag} is already set by {', '.join(others)}"
                    out.append(Finding(path, FindingCode.CONFIG_INVALID, message, uid or None))
    return out


def _judge(
    change: Change,
    kinds: Mapping[str, Kind],
    owners: Mapping[str, tuple[str, str, str]],
    removed: set[str],
    claimed: dict[str, str],
    names: dict[tuple[str, str], str],
) -> Verdict:
    path = change.path
    assert change.data is not None
    try:
        doc = parse_resource(change.data)
    except DocumentInvalid as exc:
        return Verdict(findings=[Finding(path, FindingCode.INVALID_DOCUMENT, str(exc))])
    uid = doc.uid
    directory = kind_of_resource_path(path)
    if directory is None or path.count("/") != 2:
        message = "a resource file belongs at resources/<kind>/<name>.json"
        return Verdict(findings=[Finding(path, FindingCode.INVALID_DOCUMENT, message, uid)])
    if doc.kind != directory:
        message = f"kind {doc.kind!r} is filed under resources/{directory}/"
        return Verdict(findings=[Finding(path, FindingCode.KIND_MISMATCH, message, uid)])
    findings = _format_findings(change, doc)
    if any(f.blocking for f in findings):
        return Verdict(findings=findings)
    for key in doc.unknown_fields:
        message = f"field {key!r} is not known to this build; kept as it is"
        findings.append(Finding(path, FindingCode.UNKNOWN_FIELD, message, uid))
    kind_def = kinds.get(doc.kind)
    if kind_def is None:
        message = f"kind {doc.kind!r} is not known to this build; kept, and not used here"
        findings.append(Finding(path, FindingCode.UNKNOWN_FIELD, message, uid))
    else:
        findings.extend(_config_findings(path, doc, kind_def, uid))
    fixes: list[Fix] = []
    if uid is None:
        uid = uuid.uuid4().hex
        created = doc.created_at or datetime.now(tz=UTC).isoformat()
        minted = doc.replace(uid=uid, created_at=created)
        fixes.append(Fix(path, minted.to_bytes(), f"Gave {path} its uid"))
    else:
        held = owners.get(uid)
        if (held is not None and held[0] != path and held[0] not in removed) or uid in claimed:
            original = held[0] if held is not None else claimed[uid]
            message = f"uid {uid} is already {original}'s; a copy needs no uid of its own"
            findings.append(Finding(path, FindingCode.DUPLICATE_UID, message, uid))
            return Verdict(findings=findings)
        claimed[uid] = path
    name_key = _name_key(kinds, doc.kind, doc.name)
    holder = names.get(name_key)
    if holder is not None and holder != uid:
        message = f"another {doc.kind} is already named {doc.name!r}"
        findings.append(Finding(path, FindingCode.NAME_TAKEN, message, uid))
    else:
        names[name_key] = uid
    return Verdict(findings=findings, fixes=fixes)


def _name_key(kinds: Mapping[str, Kind], kind: str, name: str) -> tuple[str, str]:
    """What two names of ``kind`` collide on: a free-text name ignoring case,
    a fixed one exactly."""
    kind_def = kinds.get(kind)
    return (kind, name.casefold() if kind_def is not None and kind_def.free_name else name)


__all__ = ["RESOURCE_FORMAT", "HeadOwners", "resource_rule"]
