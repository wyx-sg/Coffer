"""The shell line that starts an agent's session in a terminal, and its template.

Pure: builds strings, touches nothing. The daemon builds every command itself
from validated fields (spec daemon "Open an agent session in a terminal"); a
client never sends one. Quoting is single quotes throughout, so no value can end
the quote it sits in.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from coffer.domain.fs_terminal_errors import FsTerminalInvalid

#: Agent type key -> the program a terminal runs, and the arguments that resume
#: a session (``{id}`` is the session id).
AGENT_PROGRAMS: dict[str, tuple[str, str]] = {
    "claude_code": ("claude", "--resume {id}"),
    "codex": ("codex", "resume {id}"),
}

_SESSION_ID = re.compile(r"^[A-Za-z0-9-]{1,128}$")


def quote(value: str) -> str:
    """``value`` as one single-quoted shell word."""
    return "'" + value.replace("'", "'\"'\"'") + "'"


def program_for(agent: str) -> str:
    entry = AGENT_PROGRAMS.get(agent)
    if entry is None:
        raise FsTerminalInvalid(f"unknown agent {agent!r}")
    return entry[0]


def check_session_id(session_id: str) -> str:
    if not _SESSION_ID.fullmatch(session_id):
        raise FsTerminalInvalid("not a session id (letters, digits and dashes only)")
    return session_id


def resume_command(agent: str, session_id: str, cwd: str) -> str:
    program = program_for(agent)
    check_session_id(session_id)
    args = AGENT_PROGRAMS[agent][1].format(id=session_id)
    return f"cd {quote(cwd)} && {program} {args}"


def blank_command(agent: str, cwd: str) -> str:
    """Start a new session with no first message."""
    return f"cd {quote(cwd)} && {program_for(agent)}"


def prompt_command(agent: str, prompt_file: Path, cwd: str) -> str:
    """Start a new session whose first message the command reads from, and
    removes, ``prompt_file`` — the text never appears on a command line."""
    program = program_for(agent)
    f = quote(str(prompt_file))
    return f'cd {quote(cwd)} && {program} "$(cat {f}; rm -f {f})"'


def prompt_file_text(prompt: str) -> str:
    # A first message that starts with "-" would be read as an option; a leading
    # newline survives command substitution (only trailing ones are stripped).
    return "\n" + prompt if prompt.lstrip().startswith("-") else prompt


def is_template(terminal: str) -> bool:
    return "{command}" in terminal or "{cwd}" in terminal


def template_argv(template: str, *, command: str, cwd: str) -> list[str]:
    """A custom terminal template as an argument vector (no shell)."""
    if "{command}" not in template:
        raise FsTerminalInvalid("a terminal template needs {command}")
    try:
        parts = shlex.split(template)
    except ValueError as e:
        raise FsTerminalInvalid(f"terminal template does not parse: {e}") from e
    if not parts:
        raise FsTerminalInvalid("a terminal template is empty")
    return [p.replace("{cwd}", cwd).replace("{command}", command) for p in parts]
