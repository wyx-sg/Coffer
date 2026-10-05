"""Find plaintext secrets in managed skills and MCP servers, and rewrite a skill file.

Spec secret "Move plaintext secrets in managed resources into the store",
detecting with the bundled rules (spec secret "Detect plaintext secrets with
the bundled rules").

* A **skill** is read as files: :func:`detector.detect` runs over each whole
  file, so a value that spans lines (a PEM private key) is one finding on the
  line it starts on, and :func:`rewrite_file` replaces it whole.
* An **MCP server** is read as config: a stdio ``env`` value, an HTTP
  ``headers`` value or an HTTP API ``headers`` value is a finding when
  :func:`detector.detect_setting` names a rule for it. A reference
  (``coffer://secret/…``), an interpolation, a placeholder or a short value
  is not.

A finding names where a value is and which rule found it, **never the value**.
Its id is a hash of the location, so a dry run and the import after it agree.
"""

from __future__ import annotations

import errno
import hashlib
import os
import pathlib
import re
import tempfile
from collections.abc import Iterable
from typing import Any

from coffer.application.secret.plaintext_move import Finding, Hit
from coffer.domain.secrets import is_valid_secret_name, secret_uri
from coffer.infrastructure.secret.detector import Lines, detect, detect_setting
from coffer.infrastructure.secret.plaintext_scan import MAX_BYTES, SKILL_SUFFIXES


def _name(*parts: str) -> str:
    raw = ".".join(p for p in parts if p)
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip(".-")[:64]
    return cleaned if is_valid_secret_name(cleaned) else "imported"


def _finding_id(*parts: object) -> str:
    return hashlib.sha256("\0".join(str(p) for p in parts).encode()).hexdigest()[:16]


def _read(path: pathlib.Path) -> str | None:
    """The file's text with its line endings kept, so offsets match the bytes."""
    try:
        with open(path, encoding="utf-8", newline="") as f:
            return f.read()
    except UnicodeDecodeError:
        return None


def _skill_hits(path: pathlib.Path, skill: str, rel: str) -> list[Hit]:
    text = _read(path)
    if text is None:
        return []
    lines = Lines(text)
    hits: list[Hit] = []
    for d in detect(text, rel):
        n = lines.number(d.start)
        if d.key:
            key = d.key
            name = _name(skill, key.lower())
        else:
            key = f"token-{n}"
            name = _name(skill, key)
        finding = Finding(
            id=_finding_id("skill", path, d.start, d.rule),
            source="skill",
            resource=skill,
            resource_uid=None,
            path=str(path),
            line=n,
            field=None,
            key=key,
            proposed_name=name,
            rule=d.rule,
        )
        hits.append(Hit(finding, text[d.start : d.end], d.start, d.end))
    return hits


def scan_skills(
    skills_root: pathlib.Path, skip: frozenset[str] = frozenset()
) -> tuple[list[Hit], int]:
    """Hits in every text file of the skill master store, and how many files were read.
    ``skip`` names skills that are Coffer's own rendering (its guide), which
    quote commands like ``coffer run --secret PGPASSWORD=orders-db`` on purpose."""
    hits: list[Hit] = []
    checked = 0
    if not skills_root.is_dir():
        return hits, checked
    for path in sorted(skills_root.rglob("*")):
        rel = path.relative_to(skills_root)
        if (
            not path.is_file()
            or path.is_symlink()
            or path.suffix not in SKILL_SUFFIXES
            or any(part.startswith(".") for part in rel.parts)
            or path.stat().st_size > MAX_BYTES
            or rel.parts[0] in skip
        ):
            continue
        hits += _skill_hits(path, rel.parts[0], rel.as_posix())
        checked += 1
    return hits, checked


def scan_server(uid: str, name: str, config: dict[str, Any]) -> list[Hit]:
    """Hits in one MCP server's static ``env`` / ``headers`` (any transport)."""
    transport = config.get("transport")
    if not isinstance(transport, dict):
        return []
    hits: list[Hit] = []
    for bucket, field in (("env", "env"), ("headers", "header")):
        values = transport.get(bucket)
        if not isinstance(values, dict):
            continue
        for key, value in values.items():
            if not isinstance(value, str):
                continue
            rule = detect_setting(str(key), value)
            if rule is None:
                continue
            finding = Finding(
                id=_finding_id("mcp_server", uid, field, key),
                source="mcp_server",
                resource=name,
                resource_uid=uid,
                path=None,
                line=None,
                field=field,
                key=str(key),
                proposed_name=None,
                rule=rule,
            )
            hits.append(Hit(finding, value, config=config))
    return hits


def scan_servers(servers: Iterable[tuple[str, str, dict[str, Any]]]) -> tuple[list[Hit], int]:
    """Hits in every ``(uid, name, config)`` server, and how many were read."""
    hits: list[Hit] = []
    checked = 0
    for uid, name, config in servers:
        hits += scan_server(uid, name, config)
        checked += 1
    return hits, checked


def rewrite_file(path: str, hits: list[Hit], names: dict[str, str]) -> None:
    """Replace each moved value with its reference, atomically, keeping the mode."""
    target = pathlib.Path(path)
    text = _read(target)
    if text is None:
        raise OSError(errno.EILSEQ, "not valid UTF-8")
    for h in sorted(hits, key=lambda h: -h.start):
        text = text[: h.start] + secret_uri(names[h.finding.id]) + text[h.end :]
    mode = target.stat().st_mode & 0o777
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, target)
    except BaseException:
        pathlib.Path(tmp).unlink(missing_ok=True)
        raise
