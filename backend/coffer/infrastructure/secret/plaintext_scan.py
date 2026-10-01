"""Find plaintext secrets in files and move them into the encrypted store.

ADR standalone-secrets-are-named-references-injected-into-one-child, "Migration
of plaintext secret files"; spec secret "Move plaintext secret files into
the store". Two places are read:

* ``~/.coffer/secrets/*.env`` (``KEY=VALUE`` lines) and ``*.json`` (a flat map
  of strings) — the convention skills used before Coffer could hand a secret
  to a command;
* the skill master store, for assignments whose name says secret
  (``DB_PASSWORD=…``, ``api_key: …``) and for well-known token shapes, and for
  mentions of ``~/.coffer/secrets/`` that a skill's commands will have to move
  to ``coffer run``.

A scan returns where each value is and the name it would get, **never the
value**. Moving a finding stores the value under ``secret/<name>``, confirms
the stored value decrypts back to the same bytes, and only then rewrites the
file with ``coffer://secret/<name>`` in its place — atomically, keeping the
file's mode. No plaintext backup is kept: the value is in the store.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import pathlib
import re
import tempfile
from collections.abc import Callable, Iterable

from coffer.domain.secrets import (
    SECRET_URI_PREFIX,
    cited_secret_names,
    is_valid_secret_name,
    secret_uri,
)

_SECRET_KEY = re.compile(
    r"(?i)(password|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|private[_-]?key)"
)
#: ``NAME = value`` / ``name: value`` with a secret-sounding name and a value
#: of at least eight non-space characters that is not already a reference or
#: an interpolation.
_ASSIGNMENT = re.compile(
    r"""(?P<key>[A-Za-z_][A-Za-z0-9_.-]*)\s*[:=]\s*(?P<q>["']?)(?P<value>[^\s"'#`]{8,})(?P=q)"""
)
_TOKEN_SHAPES = re.compile(
    r"\b(?P<value>(?:ghp|gho|ghu|ghs)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|"
    r"sk-[A-Za-z0-9_-]{20,}|xox[abpr]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16})\b"
)
_PLACEHOLDER = re.compile(r"(?i)^(x{3,}|\*{3,}|<.*>|your[-_].*|changeme|example.*|placeholder.*)$")
_SKILL_SUFFIXES = {".md", ".sh", ".py", ".env", ".json", ".yaml", ".yml", ".toml", ".txt"}
_MAX_BYTES = 1_000_000
_SECRETS_MENTION = re.compile(r"~?/?\.coffer/secrets/[A-Za-z0-9_.-]*")


@dataclasses.dataclass(frozen=True, slots=True)
class Finding:
    """One plaintext value that could move into the store (no value inside)."""

    id: str
    path: str
    source: str  # "secrets_file" | "skill"
    key: str
    line: int
    proposed_name: str


@dataclasses.dataclass(frozen=True, slots=True)
class SkillMention:
    """A skill file that still points at a plaintext secrets file."""

    skill: str
    path: str
    line: int
    mention: str


@dataclasses.dataclass(frozen=True, slots=True)
class ScanResult:
    findings: list[Finding]
    mentions: list[SkillMention]
    #: How many files were read, so "nothing found" can say how much was looked at.
    files_checked: int = 0


@dataclasses.dataclass(frozen=True, slots=True)
class Moved:
    id: str
    path: str
    name: str


@dataclasses.dataclass(frozen=True, slots=True)
class Skipped:
    id: str
    path: str
    reason: str
    #: The value is in the store under ``name`` but the file still holds it:
    #: the file could not be rewritten.
    name: str = ""
    stored: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class ImportResult:
    moved: list[Moved]
    skipped: list[Skipped]
    dry_run: bool


@dataclasses.dataclass(frozen=True, slots=True)
class _Hit:
    finding: Finding
    value: str
    start: int  # offset of the value within its line (-1: a JSON key)
    end: int


def _name(*parts: str) -> str:
    raw = ".".join(p for p in parts if p)
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip(".-")[:64]
    return cleaned if is_valid_secret_name(cleaned) else "imported"


def _finding_id(path: pathlib.Path, line: int, key: str) -> str:
    return hashlib.sha256(f"{path}\0{line}\0{key}".encode()).hexdigest()[:16]


def _usable(value: str) -> bool:
    v = value.strip()
    return (
        bool(v) and not v.startswith((SECRET_URI_PREFIX, "$", "{{")) and not _PLACEHOLDER.match(v)
    )


def _env_hits(path: pathlib.Path) -> list[_Hit]:
    hits: list[_Hit] = []
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        m = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", raw)
        if not m:
            continue
        key, rest = m.group(1), m.group(2).rstrip()
        value = rest[1:-1] if len(rest) >= 2 and rest[0] == rest[-1] and rest[0] in "\"'" else rest
        if not _usable(value):
            continue
        start = raw.index(value, m.start(2))
        finding = Finding(
            id=_finding_id(path, n, key),
            path=str(path),
            source="secrets_file",
            key=key,
            line=n,
            proposed_name=_name(path.stem, key),
        )
        hits.append(_Hit(finding, value, start, start + len(value)))
    return hits


def _json_hits(path: pathlib.Path) -> list[_Hit]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    hits: list[_Hit] = []
    for key, value in data.items():
        if isinstance(value, str) and _usable(value):
            finding = Finding(
                id=_finding_id(path, 0, key),
                path=str(path),
                source="secrets_file",
                key=str(key),
                line=0,
                proposed_name=_name(path.stem, str(key)),
            )
            hits.append(_Hit(finding, value, -1, -1))
    return hits


def _line_hits(raw: str) -> list[tuple[str, str, int, int]]:
    """``(key, value, start, end)`` for each plaintext value on one line: an
    assignment whose name says secret, or a well-known token shape."""
    if "coffer run" in raw:
        # `--secret ENV=NAME` names a secret; it is not one.
        return []
    out: list[tuple[str, str, int, int]] = []
    seen: list[tuple[int, int]] = []
    for m in _ASSIGNMENT.finditer(raw):
        key, value = m.group("key"), m.group("value")
        if not _SECRET_KEY.search(key) or not _usable(value):
            continue
        span = (m.start("value"), m.end("value"))
        seen.append(span)
        out.append((key, value, *span))
    for m in _TOKEN_SHAPES.finditer(raw):
        span = (m.start("value"), m.end("value"))
        if any(s <= span[0] < e for s, e in seen):
            continue
        out.append(("", m.group("value"), *span))
    return out


def find_in_text(text: str) -> list[tuple[int, str]]:
    """``(line, key)`` for each plaintext value in ``text`` — the same
    detection a skill file gets, never the value. A token found by its shape
    alone is keyed ``token``. For vault sync's check before a push (spec
    vault-sync "Refuse to push a plaintext secret")."""
    return [
        (n, key or "token")
        for n, raw in enumerate(text.splitlines(), start=1)
        for key, _value, _s, _e in _line_hits(raw)
    ]


def _skill_hits(path: pathlib.Path, skill: str) -> tuple[list[_Hit], list[SkillMention]]:
    hits: list[_Hit] = []
    mentions: list[SkillMention] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [], []
    for n, raw in enumerate(text.splitlines(), start=1):
        for m in _SECRETS_MENTION.finditer(raw):
            mentions.append(SkillMention(skill, str(path), n, m.group(0)))
        for key, value, start, end in _line_hits(raw):
            if not key:
                key = f"token-{n}"
                name = _name(skill, key)
            else:
                name = _name(skill, key.lower())
            finding = Finding(
                id=_finding_id(path, n, key),
                path=str(path),
                source="skill",
                key=key,
                line=n,
                proposed_name=name,
            )
            hits.append(_Hit(finding, value, start, end))
    return hits, mentions


def _all_hits(
    secrets_dir: pathlib.Path, skills_root: pathlib.Path, skip: frozenset[str] = frozenset()
) -> tuple[list[_Hit], list[SkillMention], int]:
    hits: list[_Hit] = []
    mentions: list[SkillMention] = []
    checked = 0
    if secrets_dir.is_dir():
        for path in sorted(secrets_dir.iterdir()):
            if path.is_file() and path.suffix == ".env":
                hits += _env_hits(path)
                checked += 1
            elif path.is_file() and path.suffix == ".json":
                hits += _json_hits(path)
                checked += 1
    if skills_root.is_dir():
        for path in sorted(skills_root.rglob("*")):
            rel = path.relative_to(skills_root)
            if (
                not path.is_file()
                or path.is_symlink()
                or path.suffix not in _SKILL_SUFFIXES
                or any(part.startswith(".") for part in rel.parts)
                or path.stat().st_size > _MAX_BYTES
                or rel.parts[0] in skip
            ):
                continue
            h, m = _skill_hits(path, rel.parts[0])
            hits += h
            mentions += m
            checked += 1
    return hits, mentions, checked


def scan(
    secrets_dir: pathlib.Path, skills_root: pathlib.Path, skip: frozenset[str] = frozenset()
) -> ScanResult:
    """``skip`` names skills that are Coffer's own rendering (its guide), which
    quote commands like ``coffer run --secret PGPASSWORD=orders-db`` on purpose."""
    hits, mentions, checked = _all_hits(secrets_dir, skills_root, skip)
    return ScanResult(findings=[h.finding for h in hits], mentions=mentions, files_checked=checked)


def _rewrite(path: pathlib.Path, hits: list[_Hit], names: dict[str, str]) -> None:
    """Replace each moved value with its reference, atomically, keeping the mode."""
    if path.suffix == ".json" and all(h.start == -1 for h in hits):
        data = json.loads(path.read_text(encoding="utf-8"))
        for h in hits:
            data[h.finding.key] = secret_uri(names[h.finding.id])
        text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    else:
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        for h in sorted(hits, key=lambda h: (h.finding.line, -h.start)):
            i = h.finding.line - 1
            line = lines[i]
            lines[i] = line[: h.start] + secret_uri(names[h.finding.id]) + line[h.end :]
        text = "".join(lines)
    mode = path.stat().st_mode & 0o777
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        pathlib.Path(tmp).unlink(missing_ok=True)
        raise


def move(
    secrets_dir: pathlib.Path,
    skills_root: pathlib.Path,
    ids: Iterable[str] | None,
    *,
    store: Callable[[str, str], bool],
    dry_run: bool = False,
    skip: frozenset[str] = frozenset(),
) -> ImportResult:
    """Move the chosen findings (all, when ``ids`` is None) into the store.

    ``store(name, value)`` stores the value under ``secret/<name>`` and returns
    whether the store now decrypts that name back to exactly ``value``; a name
    already holding a different value is refused by it, and that finding is
    skipped and its file left alone. A file that cannot be rewritten (read-only,
    say) keeps its values: each of its findings is skipped as ``stored`` — the
    value is in the store, the file still holds it — and the other files are
    still rewritten. Moving the same finding again retries the file.
    """
    wanted = None if ids is None else set(ids)
    hits, _, _ = _all_hits(secrets_dir, skills_root, skip)
    chosen = [h for h in hits if wanted is None or h.finding.id in wanted]
    moved: list[Moved] = []
    skipped: list[Skipped] = []
    by_file: dict[str, list[_Hit]] = {}
    names: dict[str, str] = {}
    for h in chosen:
        name = h.finding.proposed_name
        if dry_run:
            moved.append(Moved(h.finding.id, h.finding.path, name))
            continue
        if not store(name, h.value):
            skipped.append(
                Skipped(
                    h.finding.id, h.finding.path, f"secret {name!r} already holds another value"
                )
            )
            continue
        names[h.finding.id] = name
        by_file.setdefault(h.finding.path, []).append(h)
        moved.append(Moved(h.finding.id, h.finding.path, name))
    for path, file_hits in by_file.items():
        try:
            _rewrite(pathlib.Path(path), file_hits, names)
        except OSError as e:
            failed = {h.finding.id for h in file_hits}
            moved = [m for m in moved if m.id not in failed]
            why = "it is read-only" if isinstance(e, PermissionError) else (e.strerror or str(e))
            skipped += [
                Skipped(
                    h.finding.id,
                    path,
                    f"couldn't be rewritten: {why}",
                    name=names[h.finding.id],
                    stored=True,
                )
                for h in file_hits
            ]
    return ImportResult(moved=moved, skipped=skipped, dry_run=dry_run)


def skills_citing_secrets(skills_root: pathlib.Path) -> dict[str, set[str]]:
    """``{secret name: {skill, …}}`` for every ``coffer://secret/<name>`` a skill's
    files mention — a literal search of Coffer's own skill master store."""
    out: dict[str, set[str]] = {}
    if not skills_root.is_dir():
        return out
    for path in skills_root.rglob("*"):
        rel = path.relative_to(skills_root)
        if (
            not path.is_file()
            or path.suffix not in _SKILL_SUFFIXES
            or any(part.startswith(".") for part in rel.parts)
            or path.stat().st_size > _MAX_BYTES
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for name in cited_secret_names(text):
            out.setdefault(name, set()).add(rel.parts[0])
    return out
