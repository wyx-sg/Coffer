"""The commands a skill says it needs (spec skill-manager "Show the commands a
skill declares it needs").

Read from the ``requires`` field of the ``SKILL.md`` frontmatter, leniently,
because the field is authored by whoever wrote the skill:

- ``requires: [jq, "gh>=2.40"]`` — a list;
- ``requires: {commands: [...]}`` — a mapping whose ``commands`` key is one;
- each entry a command name, ``name>=version``, or
  ``{command: gh, version: ">=2.40"}``.

An entry that names no command is dropped rather than failing the skill, and a
command listed twice is kept once, first spelling wins. Nothing here probes a
command: whether it is installed, which version and whether it is logged in are
the CLIs page's questions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import yaml

#: A command name as a person types it at a shell: no spaces, no path.
_COMMAND_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
_SPEC_RE = re.compile(r"^\s*([^\s<>=!~]+)\s*(?:>=|=>|~=|==)?\s*([0-9][^\s]*)?\s*$")


@dataclass(frozen=True)
class SkillRequirement:
    command: str
    min_version: str | None = None


def _one(entry: Any) -> SkillRequirement | None:
    if isinstance(entry, str):
        m = _SPEC_RE.match(entry)
        if m is None:
            return None
        command, version = m.group(1), m.group(2)
    elif isinstance(entry, dict):
        raw = entry.get("command", entry.get("name"))
        if not isinstance(raw, str):
            return None
        command = raw.strip()
        v = entry.get("version", entry.get("min_version"))
        version = None
        if isinstance(v, (str, int, float)):
            version = str(v).strip().lstrip(">=~ ") or None
    else:
        return None
    if not _COMMAND_RE.match(command):
        return None
    return SkillRequirement(command=command, min_version=version)


def parse_requires(value: Any) -> list[SkillRequirement]:
    """The requirements a frontmatter ``requires`` value declares."""
    if isinstance(value, dict):
        value = value.get("commands")
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out: list[SkillRequirement] = []
    seen: set[str] = set()
    for entry in value:
        req = _one(entry)
        if req is not None and req.command not in seen:
            seen.add(req.command)
            out.append(req)
    return out


def requires_from_skill_md(text: str) -> list[SkillRequirement]:
    """The requirements the ``SKILL.md`` text's frontmatter declares."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            try:
                data = yaml.safe_load("\n".join(lines[1:i]))
            except yaml.YAMLError:
                return []
            return parse_requires(data.get("requires")) if isinstance(data, dict) else []
    return []


__all__ = ["SkillRequirement", "parse_requires", "requires_from_skill_md"]
