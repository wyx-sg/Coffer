"""The command-line tools a skill declares it drives (SKILL.md ``requires:``).

```yaml
requires:
  - command: gh                 # required; a bare name, no path
    title: GitHub CLI           # optional display name
    min_version: "2.40"         # optional; dotted numbers
    login_check: gh auth status # optional; argv of the SAME command
    login: gh auth login        # optional; shown to copy, never run
    why: Opens and labels issues.
  - jq                          # shorthand: a command with no conditions
  - "node>=20.1"                # shorthand: a command and its minimum
```

The shorter spellings of spec skill-manager "Show the commands a skill
declares it needs" are the same list: ``requires: {commands: [...]}``, an entry
``name>=version`` (also ``==`` / ``~=``), and ``{command|name, version}``.

Only the mapping form also names the Coffer secrets a skill needs (spec
skill-manager "Declare the secrets a skill requires"):

```yaml
requires:
  commands: [gh]
  secrets: [GITHUB_TOKEN]       # names in Coffer's secret store; never values
```

The mapping form also names the MCP servers and custom-tool groups a skill
calls (spec skill-manager "Declare the tools a skill requires"), by the name each
has in Coffer; an entry may be a mapping with a ``why``:

```yaml
requires:
  tools: [github, {name: billing-api, why: Reads invoices.}]
```

A mapping key other than ``commands``, ``secrets`` and ``tools`` is refused: it
is reported as a warning and nothing under it is read. Whether a tool name is
one Coffer knows is not decided here (this module reads text only); the
requirement service skips an unknown one with a warning.

``metadata.requires`` is a different thing — the other skills this one loads —
read by :func:`required_skills_from_skill_md`.

Parsed leniently: the frontmatter is third-party, like ``allowed-tools``, so
an entry that is not understood is skipped and reported as a warning, never a
reason to refuse the skill. The rules are what keep a declaration from making
Coffer run anything but the tool it names: the command is a bare name and the
login check's first word is that command.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

from coffer.domain.secrets import is_valid_secret_name
from coffer.domain.skill.validator import parse_frontmatter

COMMAND_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
_MIN_VERSION_RE = re.compile(r"^\d+(?:\.\d+)*$")
_TEXT_MAX = 200
#: A resource name as Coffer files MCP servers and tool groups under.
_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")
#: The keys the mapping form of ``requires:`` may carry.
_MAPPING_KEYS = ("commands", "secrets", "tools")
_KEYS = frozenset(
    {"command", "name", "title", "min_version", "version", "login_check", "login", "why"}
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
    why: str | None = None


@dataclass(frozen=True)
class ToolRequirement:
    """One MCP server or custom-tool group a skill calls, by its Coffer name."""

    name: str
    why: str | None = None


@dataclass(frozen=True)
class RequirementsParse:
    requirements: tuple[CommandRequirement, ...] = ()
    #: The Coffer secret names the skill needs, in the order declared.
    secrets: tuple[str, ...] = ()
    #: The MCP servers and custom-tool groups the skill calls, in declared order.
    tools: tuple[ToolRequirement, ...] = ()
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
    each one that cannot. A command or secret named twice keeps its first entry."""
    warnings: list[str] = []
    secrets: tuple[str, ...] = ()
    tools: tuple[ToolRequirement, ...] = ()
    if isinstance(value, dict):
        unknown = sorted(str(k) for k in value if k not in _MAPPING_KEYS)
        if unknown:
            warnings.append(
                f"requires: unknown key(s) {', '.join(unknown)} refused; "
                "only commands, secrets and tools are read"
            )
        secrets = _secrets(value.get("secrets"), warnings)
        tools = _tools(value.get("tools"), warnings)
        value = value.get("commands")
    commands = _commands(value, warnings)
    return RequirementsParse(commands, secrets, tools, tuple(warnings))


def _commands(value: object, warnings: list[str]) -> tuple[CommandRequirement, ...]:
    if isinstance(value, str):
        value = [value]
    if value is None:
        return ()
    if not isinstance(value, list):
        warnings.append("requires: expected a list of commands; ignored")
        return ()
    out: list[CommandRequirement] = []
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
    return tuple(out)


def _secrets(value: object, warnings: list[str]) -> tuple[str, ...]:
    """The ``secrets:`` list of the mapping form: secret names, never values."""
    if isinstance(value, str):
        value = [value]
    if value is None:
        return ()
    if not isinstance(value, list):
        warnings.append("requires secrets: expected a list of secret names; ignored")
        return ()
    out: list[str] = []
    for index, entry in enumerate(value, start=1):
        name = entry.strip() if isinstance(entry, str) else None
        if not name or not is_valid_secret_name(name):
            warnings.append(f"requires secret {index}: {entry!r} is not a secret name; skipped")
            continue
        if name in out:
            warnings.append(f"requires secret {name}: declared twice; later entry skipped")
            continue
        out.append(name)
    return tuple(out)


def _tools(value: object, warnings: list[str]) -> tuple[ToolRequirement, ...]:
    """The ``tools:`` list of the mapping form: names, each optionally with a why."""
    if isinstance(value, str):
        value = [value]
    if value is None:
        return ()
    if not isinstance(value, list):
        warnings.append("requires tools: expected a list of tool names; ignored")
        return ()
    out: list[ToolRequirement] = []
    for index, entry in enumerate(value, start=1):
        why: str | None = None
        if isinstance(entry, dict):
            why = _text(entry.get("why"), "why", [])
            entry = entry.get("name")
        name = entry.strip() if isinstance(entry, str) else None
        if not name or not _TOOL_NAME_RE.match(name):
            warnings.append(f"requires tool {index}: {entry!r} is not a tool name; skipped")
            continue
        if any(t.name == name for t in out):
            warnings.append(f"requires tool {name}: declared twice; later entry skipped")
            continue
        out.append(ToolRequirement(name, why))
    return tuple(out)


def required_skills_from_skill_md(text: str) -> tuple[str, ...]:
    """The skills a SKILL.md says it loads (``metadata.requires``: a list of
    skill names), in declared order; empty when there are none or it is not a list."""
    data = parse_frontmatter(text)
    metadata = data.get("metadata") if data else None
    value = metadata.get("requires") if isinstance(metadata, dict) else None
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return ()
    names = [v.strip() for v in value if isinstance(v, str) and v.strip()]
    return tuple(dict.fromkeys(names))


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
    return (
        CommandRequirement(
            command=command,
            title=_text(entry.get("title"), "title", dropped),
            min_version=_min_version(entry.get("min_version", entry.get("version"))),
            login_check=login_check,
            login=_text(entry.get("login"), "login", dropped),
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
    "CommandRequirement",
    "RequirementsParse",
    "ToolRequirement",
    "parse_requires",
    "required_skills_from_skill_md",
    "requirements_from_skill_md",
]
