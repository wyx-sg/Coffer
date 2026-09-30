"""The command-line tools a skill declares it drives (SKILL.md ``requires:``).

```yaml
requires:
  - command: gh                 # required; a bare name, no path
    title: GitHub CLI           # optional display name
    min_version: "2.40"         # optional; dotted numbers
    login_check: gh auth status # optional; argv of the SAME command
    login: gh auth login        # optional; shown to copy, never run
    brew: gh                    # optional; the Homebrew formula
    why: Opens and labels issues.
  - jq                          # shorthand: a command with no conditions
  - "node>=20.1"                # shorthand: a command and its minimum
```

The shorter spellings of spec skill-manager "Show the commands a skill
declares it needs" are the same list: ``requires: {commands: [...]}``, an entry
``name>=version`` (also ``==`` / ``~=``), and ``{command|name, version}``.

Parsed leniently: the frontmatter is third-party, like ``allowed-tools``, so
an entry that is not understood is skipped and reported as a warning, never a
reason to refuse the skill. The rules are what keep a declaration from making
Coffer run anything but the tool it names: the command is a bare name, the
login check's first word is that command, and the formula is a Homebrew name.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

from coffer.domain.skill.validator import parse_frontmatter

COMMAND_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
FORMULA_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9@._+/-]{0,127}$")
_MIN_VERSION_RE = re.compile(r"^\d+(?:\.\d+)*$")
_TEXT_MAX = 200
_KEYS = frozenset(
    {"command", "name", "title", "min_version", "version", "login_check", "login", "brew", "why"}
)
#: ``gh``, ``gh>=2.40``, ``node == 20.1``, ``python3~=3.12``.
_SPEC_RE = re.compile(r"^\s*([^\s<>=!~]+)\s*(?:(?:>=|=>|~=|==)\s*([0-9][^\s]*))?\s*$")


@dataclass(frozen=True)
class CommandRequirement:
    """One command a skill needs, as the skill declared it."""

    command: str
    title: str | None = None
    min_version: str | None = None
    #: The login check's argv; its first word is ``command``.
    login_check: tuple[str, ...] | None = None
    #: Shown to the user to copy; Coffer never runs it.
    login: str | None = None
    brew: str | None = None
    why: str | None = None


@dataclass(frozen=True)
class RequirementsParse:
    requirements: tuple[CommandRequirement, ...] = ()
    #: One sentence per entry that was skipped (or field that was dropped).
    warnings: tuple[str, ...] = ()


class _SkipEntryError(ValueError):
    """An entry that cannot be used; the message says why."""


def requirements_from_skill_md(text: str) -> RequirementsParse:
    """The ``requires:`` list of a SKILL.md document; empty when there is none."""
    data = parse_frontmatter(text)
    if data is None or "requires" not in data:
        return RequirementsParse()
    return parse_requires(data["requires"])


def parse_requires(value: object) -> RequirementsParse:
    """Every entry of a ``requires:`` value that can be used, and a warning for
    each one that cannot. A command named twice keeps its first entry."""
    if isinstance(value, dict):
        value = value.get("commands")
    if isinstance(value, str):
        value = [value]
    if value is None:
        return RequirementsParse()
    if not isinstance(value, list):
        return RequirementsParse(warnings=("requires: expected a list of commands; ignored",))
    out: list[CommandRequirement] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(value, start=1):
        try:
            requirement, dropped = _entry(entry)
        except _SkipEntryError as skip:
            warnings.append(f"requires entry {index}: {skip}; skipped")
            continue
        warnings.extend(f"requires {requirement.command}: {d}" for d in dropped)
        if requirement.command in seen:
            warnings.append(f"requires {requirement.command}: declared twice; later entry skipped")
            continue
        seen.add(requirement.command)
        out.append(requirement)
    return RequirementsParse(tuple(out), tuple(warnings))


def _entry(entry: object) -> tuple[CommandRequirement, list[str]]:
    if isinstance(entry, str):
        spec = _SPEC_RE.match(entry)
        if spec is None:
            raise _SkipEntryError(f"{entry!r} is not a command name")
        return CommandRequirement(
            command=_command(spec.group(1)), min_version=_min_version(spec.group(2))
        ), []
    if not isinstance(entry, dict):
        raise _SkipEntryError("expected a command name or a mapping")
    if "command" not in entry and "name" not in entry:
        raise _SkipEntryError("no command")
    command = _command(entry.get("command", entry.get("name")))
    dropped: list[str] = []
    unknown = sorted(str(k) for k in entry if k not in _KEYS)
    if unknown:
        dropped.append(f"unknown field(s) {', '.join(unknown)} ignored")
    login_check = _login_check(command, entry.get("login_check"))
    brew = entry.get("brew")
    if brew is not None and (not isinstance(brew, str) or not FORMULA_RE.match(brew)):
        raise _SkipEntryError(f"brew {brew!r} is not a Homebrew formula name")
    return (
        CommandRequirement(
            command=command,
            title=_text(entry.get("title"), "title", dropped),
            min_version=_min_version(entry.get("min_version", entry.get("version"))),
            login_check=login_check,
            login=_text(entry.get("login"), "login", dropped),
            brew=brew,
            why=_text(entry.get("why"), "why", dropped),
        ),
        dropped,
    )


def _command(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _SkipEntryError("command must be a name")
    name = value.strip()
    if "/" in name or "\\" in name:
        raise _SkipEntryError(f"command {name!r} is a path; name the command alone")
    if not COMMAND_RE.match(name):
        raise _SkipEntryError(f"command {name!r} is not a command name")
    return name


def _login_check(command: str, value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            argv = shlex.split(value)
        except ValueError as exc:
            raise _SkipEntryError(f"login_check cannot be read ({exc})") from None
    elif isinstance(value, list) and all(isinstance(v, str) for v in value):
        argv = [str(v) for v in value]
    else:
        raise _SkipEntryError("login_check must be a command line")
    if not argv:
        raise _SkipEntryError("login_check is empty")
    if argv[0] != command:
        raise _SkipEntryError(
            f"login_check runs {argv[0]!r}, not {command!r}; it may only run the command"
        )
    return tuple(argv)


def _min_version(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (bool, float)):
        # YAML reads ``2.40`` as the float 2.4, which is a different minimum.
        raise _SkipEntryError(f'min_version {value!r} must be quoted, like "2.40"')
    text = str(value).strip().lstrip(">=~ ")
    if not _MIN_VERSION_RE.match(text):
        raise _SkipEntryError(f"min_version {text!r} is not dotted numbers")
    return text


def _text(value: object, field: str, dropped: list[str]) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        dropped.append(f"{field} is not text; ignored")
        return None
    text = " ".join(value.split())
    if not text:
        return None
    if len(text) > _TEXT_MAX:
        dropped.append(f"{field} is longer than {_TEXT_MAX} characters; shortened")
        text = text[:_TEXT_MAX]
    return text


__all__ = [
    "COMMAND_RE",
    "FORMULA_RE",
    "CommandRequirement",
    "RequirementsParse",
    "parse_requires",
    "requirements_from_skill_md",
]
