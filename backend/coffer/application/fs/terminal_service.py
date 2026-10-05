"""Open an agent's session in a terminal window on the host.

Spec daemon "Open an agent session in a terminal", "List the terminals installed
on this host". The web UI's hand-off and session rows ask the loopback daemon,
which is always on the user's own machine, to start the terminal.

Safety: the daemon builds the command from validated fields and starts the
launcher with an **argument vector** — never a shell string of its own. A new
session's prompt is written to a private file (mode 0600) that the command reads
and removes, so the prompt's text never appears on a command line or in shell
history.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from coffer.application.fs import terminal_command as cmd
from coffer.application.platform_port import PlatformPort, TerminalLaunch
from coffer.domain.fs_terminal_errors import FsTerminalFailed, FsTerminalInvalid


@dataclass(frozen=True)
class TerminalOption:
    """One detected terminal: a human ``label`` and the launcher ``value``."""

    label: str
    value: str


@dataclass(frozen=True)
class _Terminal:
    label: str
    app_bundle: str | None  # .app bundle name (None: not a macOS app)
    command: str | None  # executable on PATH (None: macOS-only)


# Display order.
_KNOWN: tuple[_Terminal, ...] = (
    _Terminal("Terminal", "Terminal", None),
    _Terminal("iTerm", "iTerm", None),
    _Terminal("Warp", "Warp", None),
    _Terminal("Orca", "Orca", "orca"),
    _Terminal("GNOME Terminal", None, "gnome-terminal"),
    _Terminal("Konsole", None, "konsole"),
    _Terminal("x-terminal-emulator", None, "x-terminal-emulator"),
)


class TerminalDetectService:
    """Enumerate the installed terminals of the current host (stateless)."""

    def __init__(self, platform: PlatformPort) -> None:
        self._platform = platform

    def list_terminals(self) -> list[TerminalOption]:
        options: list[TerminalOption] = []
        for t in _KNOWN:
            value = self._platform.terminal_launch_value(app_bundle=t.app_bundle, command=t.command)
            if value is not None:
                options.append(TerminalOption(label=t.label, value=value))
        return options


class TerminalService:
    """Validate, build the command, start the terminal."""

    def __init__(
        self,
        platform: PlatformPort,
        *,
        default_workspace: Callable[[], str],
        handoff_dir: Callable[[], Path],
    ) -> None:
        self._platform = platform
        self._default_workspace = default_workspace
        self._handoff_dir = handoff_dir

    def open_session(
        self,
        *,
        terminal: str | None,
        agent: str,
        cwd: str | None,
        resume: str | None,
        prompt: str | None,
    ) -> None:
        """Start ``agent``'s session in ``terminal``: ``resume`` an existing one,
        or begin a new one with ``prompt``. Raises ``FsTerminalInvalid`` before
        anything is started and ``FsTerminalFailed`` when the launcher cannot be."""
        cmd.program_for(agent)
        if (resume is None) == (prompt is None):
            raise FsTerminalInvalid("give exactly one of resume and prompt")
        if resume is not None:
            cmd.check_session_id(resume)
        if prompt is not None and not prompt.strip():
            raise FsTerminalInvalid("the prompt is empty")
        directory = self._directory(cwd)
        template = (terminal or "").strip()

        prompt_file: Path | None = None
        if resume is not None:
            command = cmd.resume_command(agent, resume, directory)
        else:
            assert prompt is not None
            prompt_file = self._handoff_dir() / f"{uuid.uuid4().hex}.txt"
            command = cmd.prompt_command(agent, prompt_file, directory)
        launch = (
            TerminalLaunch(cmd.template_argv(template, command=command, cwd=directory))
            if cmd.is_template(template)
            else self._platform.terminal_launch(template or None, command=command, cwd=directory)
        )
        written: list[Path] = []
        try:
            if prompt_file is not None:
                assert prompt is not None
                _write_private(prompt_file, cmd.prompt_file_text(prompt))
                written.append(prompt_file)
            for path, text in launch.files:
                _write_private(path, text)
                written.append(path)
            _spawn(launch.argv)
        except (OSError, FsTerminalFailed) as e:
            for path in written:
                path.unlink(missing_ok=True)
            if isinstance(e, FsTerminalFailed):
                raise
            raise FsTerminalFailed(str(e)) from e

    def _directory(self, cwd: str | None) -> str:
        """The directory to open in: ``cwd`` when it is an existing absolute
        directory, else Coffer's default workspace. A relative path is refused."""
        if cwd is None or not cwd.strip():
            return self._default_workspace()
        if not Path(cwd).is_absolute():
            raise FsTerminalInvalid("cwd must be an absolute path")
        return cwd if Path(cwd).is_dir() else self._default_workspace()


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    path.chmod(0o600)


def _spawn(argv: list[str]) -> None:
    # Fire-and-forget like FsOpenService: the launcher returns at once or is a
    # long-lived terminal that must outlive the request; only a failed spawn is
    # an error.
    try:
        subprocess.Popen(
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as e:
        raise FsTerminalFailed(f"{argv[0]}: {e}") from e
