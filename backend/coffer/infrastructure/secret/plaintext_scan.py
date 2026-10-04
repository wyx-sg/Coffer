"""Find plaintext secrets in text, and the secret references skill files cite.

Spec vault-sync "Refuse to push a plaintext secret" reads a file's text for an
assignment whose name says secret (``DB_PASSWORD=…``, ``api_key: …``) or a
well-known token shape. A finding names where the value is, **never the value**.

``skills_citing_secrets`` is a literal search of the skill master store for
``coffer://secret/<name>`` references.
"""

from __future__ import annotations

import pathlib
import re

from coffer.domain.secrets import SECRET_URI_PREFIX, cited_secret_names

SECRET_KEY = re.compile(
    r"(?i)(password|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|private[_-]?key)"
)
#: ``NAME = value`` / ``name: value`` with a secret-sounding name and a value
#: of at least eight non-space characters that is not already a reference or
#: an interpolation.
_ASSIGNMENT = re.compile(
    r"""(?P<key>[A-Za-z_][A-Za-z0-9_.-]*)\s*[:=]\s*(?P<q>["']?)(?P<value>[^\s"'#`]{8,})(?P=q)"""
)
TOKEN_SHAPES = re.compile(
    r"\b(?P<value>(?:ghp|gho|ghu|ghs)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|"
    r"sk-[A-Za-z0-9_-]{20,}|xox[abpr]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16})\b"
)
#: An unquoted value holding call, index or list punctuation is code
#: (``token = m.group(0)``, ``password=password,``), never a literal secret.
_CODE = re.compile(r"[()\[\],;]")
PLACEHOLDER = re.compile(r"(?i)^(x{3,}|\*{3,}|<.*>|your[-_].*|changeme|example.*|placeholder.*)$")
SKILL_SUFFIXES = {".md", ".sh", ".py", ".env", ".json", ".yaml", ".yml", ".toml", ".txt"}
MAX_BYTES = 1_000_000


def usable(value: str) -> bool:
    v = value.strip()
    return bool(v) and not v.startswith((SECRET_URI_PREFIX, "$", "{{")) and not PLACEHOLDER.match(v)


def line_hits(raw: str) -> list[tuple[str, str, int, int]]:
    """``(key, value, start, end)`` for each plaintext value on one line: an
    assignment whose name says secret, or a well-known token shape."""
    if "coffer run" in raw:
        # `--secret ENV=NAME` names a secret; it is not one.
        return []
    out: list[tuple[str, str, int, int]] = []
    seen: list[tuple[int, int]] = []
    for m in _ASSIGNMENT.finditer(raw):
        key, value = m.group("key"), m.group("value")
        if not SECRET_KEY.search(key) or not usable(value):
            continue
        if not m.group("q") and _CODE.search(value):
            continue
        span = (m.start("value"), m.end("value"))
        seen.append(span)
        out.append((key, value, *span))
    for m in TOKEN_SHAPES.finditer(raw):
        span = (m.start("value"), m.end("value"))
        if any(s <= span[0] < e for s, e in seen):
            continue
        out.append(("", m.group("value"), *span))
    return out


def find_in_text(text: str) -> list[tuple[int, str]]:
    """``(line, key)`` for each plaintext value in ``text``, never the value.
    A token found by its shape alone is keyed ``token``. For vault sync's check
    before a push (spec vault-sync "Refuse to push a plaintext secret")."""
    return [
        (n, key or "token")
        for n, raw in enumerate(text.splitlines(), start=1)
        for key, _value, _s, _e in line_hits(raw)
    ]


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
            or path.suffix not in SKILL_SUFFIXES
            or any(part.startswith(".") for part in rel.parts)
            or path.stat().st_size > MAX_BYTES
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for name in cited_secret_names(text):
            out.setdefault(name, set()).add(rel.parts[0])
    return out
