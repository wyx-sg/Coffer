"""Find plaintext secrets in managed skills and MCP servers, and rewrite a skill file.

Spec secret "Move plaintext secrets in managed resources into the store".

* A **skill** is read as files: the rules of :func:`plaintext_scan.line_hits`
  (an assignment whose name says secret, a well-known token shape).
* An **MCP server** is read as config: a stdio ``env`` value, an HTTP
  ``headers`` value or an HTTP API ``headers`` value is a finding when its
  key says secret / key / authorization, or its value is a token shape or a
  ``Bearer``/``Token`` credential. A reference (``coffer://secret/…``), an
  interpolation (``$VAR``, ``${VAR}``, ``{{…}}``), a placeholder or a value
  shorter than eight characters is not.

A finding names where a value is, **never the value**. Its id is a hash of the
location, so a dry run and the import after it agree.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import re
import tempfile
from collections.abc import Iterable
from typing import Any

from coffer.application.secret.plaintext_move import Finding, Hit
from coffer.domain.secrets import is_valid_secret_name, secret_uri
from coffer.infrastructure.secret.plaintext_scan import (
    MAX_BYTES,
    PLACEHOLDER,
    SKILL_SUFFIXES,
    TOKEN_SHAPES,
    line_hits,
)

_SERVER_KEY = re.compile(
    r"(?i)(password|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|private[_-]?key"
    r"|authorization|auth)"
)
_CREDENTIAL = re.compile(r"^(Bearer|Token)\s+\S")
_MIN_LENGTH = 8


def _name(*parts: str) -> str:
    raw = ".".join(p for p in parts if p)
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip(".-")[:64]
    return cleaned if is_valid_secret_name(cleaned) else "imported"


def _finding_id(*parts: object) -> str:
    return hashlib.sha256("\0".join(str(p) for p in parts).encode()).hexdigest()[:16]


def _skill_hits(path: pathlib.Path, skill: str) -> list[Hit]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    hits: list[Hit] = []
    for n, raw in enumerate(text.splitlines(), start=1):
        for key, value, start, end in line_hits(raw):
            if not key:
                key = f"token-{n}"
                name = _name(skill, key)
            else:
                name = _name(skill, key.lower())
            finding = Finding(
                id=_finding_id("skill", path, n, key),
                source="skill",
                resource=skill,
                resource_uid=None,
                path=str(path),
                line=n,
                field=None,
                key=key,
                proposed_name=name,
            )
            hits.append(Hit(finding, value, start, end))
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
        hits += _skill_hits(path, rel.parts[0])
        checked += 1
    return hits, checked


def _plaintext_value(key: str, value: str) -> bool:
    v = value.strip()
    if len(v) < _MIN_LENGTH or v.startswith(("coffer://secret/", "$", "{{")):
        return False
    if PLACEHOLDER.match(v):
        return False
    return bool(_SERVER_KEY.search(key) or _CREDENTIAL.match(v) or TOKEN_SHAPES.search(v))


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
            if not isinstance(value, str) or not _plaintext_value(str(key), value):
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
    lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
    for h in sorted(hits, key=lambda h: (h.finding.line or 0, -h.start)):
        i = (h.finding.line or 1) - 1
        line = lines[i]
        lines[i] = line[: h.start] + secret_uri(names[h.finding.id]) + line[h.end :]
    mode = target.stat().st_mode & 0o777
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("".join(lines))
        os.chmod(tmp, mode)
        os.replace(tmp, target)
    except BaseException:
        pathlib.Path(tmp).unlink(missing_ok=True)
        raise


def rewrite_secret_uris(
    skills_root: pathlib.Path,
    old: str,
    new: str,
    skip: frozenset[str] = frozenset(),
) -> int:
    """Replace ``coffer://secret/<old>`` with ``coffer://secret/<new>`` in every
    text file of the skill master store (Coffer's own rendered skills in ``skip``
    excepted), atomically and keeping each file's mode; how many files changed.
    A file that cannot be rewritten raises, after the others were tried."""
    pattern = re.compile(re.escape(secret_uri(old)) + r"(?![A-Za-z0-9_.-])")
    replacement = secret_uri(new)
    changed = 0
    failure: OSError | None = None
    if not skills_root.is_dir():
        return 0
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
        try:
            text = path.read_text(encoding="utf-8")
            if not pattern.search(text):
                continue
            mode = path.stat().st_mode & 0o777
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(pattern.sub(replacement, text))
                os.chmod(tmp, mode)
                os.replace(tmp, path)
            except BaseException:
                pathlib.Path(tmp).unlink(missing_ok=True)
                raise
            changed += 1
        except UnicodeDecodeError:
            continue
        except OSError as e:
            failure = e
    if failure is not None:
        raise failure
    return changed
