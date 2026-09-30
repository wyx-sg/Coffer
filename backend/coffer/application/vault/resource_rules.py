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
- its config is validated by the kind's ``config_schema`` over **the keys the
  schema knows**: a key it does not know is an ``UNKNOWN_FIELD`` warning,
  never a refusal — to this build a newer build's key and a typo look the same
  — and so is a top-level field, and a kind this build does not know at all
  (a newer build's kind: kept, inert);
- a file with no ``uid`` is a new resource: the rule asks for a fix that
  mints one, which the writer commits as the daemon's own right after the
  person's commit;
- a uid another path held at ``HEAD`` makes the newcomer ``DUPLICATE_UID``
  (a copied file) — unless that path is going away in the same change, which
  is a move — and a name another resource of the kind already has is
  ``NAME_TAKEN``;
- a config flag the kind lets only one resource hold (``Kind.exclusive_flags``:
  ``provider``'s ``internal_default``) set while another resource holds it —
  at ``HEAD`` or in the same change — is ``CONFIG_INVALID`` on the file that
  sets it (spec provider-switching "Keep at most one internal default connection":
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

from coffer.domain.resource import InvalidResourceNameError, Kind, validate_resource_name
from coffer.domain.vault.config_keys import known_keys
from coffer.domain.vault.document import DocumentInvalid, ResourceDocument, parse_resource
from coffer.domain.vault.findings import Finding, FindingCode
from coffer.domain.vault.formats import FormatSpec, FormatStatus, read
from coffer.domain.vault.layout import kind_of_resource_path
from coffer.domain.vault.writes import Change, Fix, TreeReader, Validator, Verdict

#: Every kind's resource document is at format 1 today.
RESOURCE_FORMAT = FormatSpec(current=1)

#: ``{uid: (path, kind, name)}`` of every resource at ``HEAD``.
HeadOwners = Callable[[], Mapping[str, tuple[str, str, str]]]


def _config_findings(
    path: str, doc: ResourceDocument, kind_def: Kind, uid: str | None
) -> list[Finding]:
    out: list[Finding] = []
    known = known_keys(kind_def.config_schema, doc.config)
    subset = doc.config
    if known is not None:
        for key in doc.config:
            if key not in known:
                out.append(
                    Finding(
                        path,
                        FindingCode.UNKNOWN_FIELD,
                        f"config key {key!r} is not known to this build; kept as it is",
                        uid,
                    )
                )
        subset = {k: v for k, v in doc.config.items() if k in known}
    try:
        kind_def.config_schema.model_validate(subset)
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {"msg": str(exc), "loc": ()}
        where = ".".join(str(p) for p in first.get("loc", ())) or "config"
        out.append(Finding(path, FindingCode.CONFIG_INVALID, f"{where}: {first.get('msg')}", uid))
    try:
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
            (kind, name): uid for uid, (path, kind, name) in owners.items() if path not in touched
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
    holder = names.get((doc.kind, doc.name))
    if holder is not None and holder != uid:
        message = f"another {doc.kind} is already named {doc.name!r}"
        findings.append(Finding(path, FindingCode.NAME_TAKEN, message, uid))
    else:
        names[(doc.kind, doc.name)] = uid
    return Verdict(findings=findings, fixes=fixes)


__all__ = ["RESOURCE_FORMAT", "HeadOwners", "resource_rule"]
