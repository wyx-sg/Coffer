"""The command line's map: every UI operation, the route it calls, its command.

Spec resource-framework "Offer every management operation on the command
line"; design align-cli-with-ui-and-add-tool-environments D1, D2. Each
management command records the web UI or desktop operation it stands for and
the REST route(s) it calls; the policy test reads :data:`OPERATIONS`, compares
it with the routes the web UI calls and the desktop shell's commands, and
fails on a gap that :data:`EXEMPT` does not explain. The coverage table in the
docs is rendered from the same rows (``scripts/cli_coverage.py``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, TypeVar

F = TypeVar("F", bound=Callable[..., object])

Category = Literal["file-content", "window", "internal"]


@dataclass(frozen=True)
class Operation:
    #: Space-separated command path, as typed after ``coffer``.
    command: str
    method: str
    #: The route under ``/api/v1``, with ``{param}`` placeholders.
    route: str
    #: The page (or desktop surface) and the action, as the coverage table reads.
    ui: str


#: Every recorded (command, route) pair, in registration order.
OPERATIONS: list[Operation] = []


def record(command: str, method: str, route: str, ui: str) -> None:
    OPERATIONS.append(Operation(command, method.upper(), route, ui))


def maps(command: str, *routes: tuple[str, str], ui: str) -> Callable[[F], F]:
    """Record a hand-written command's routes; returns the function unchanged."""

    def mark(func: F) -> F:
        for method, route in routes:
            record(command, method, route, ui)
        return func

    return mark


#: Routes the web UI calls that carry no command, each with why. Nothing else
#: may be missing (spec resource-framework "Offer every management operation on
#: the command line").
EXEMPT: dict[tuple[str, str], tuple[Category, str]] = {
    # Plain file contents an agent reads and edits with its own tools.
    ("GET", "/knowledge/file"): ("file-content", "a knowledge document is a plain file"),
    ("DELETE", "/knowledge/file"): ("file-content", "a knowledge document is a plain file"),
    ("GET", "/skills/{uid}/files/content"): ("file-content", "a skill's files are plain files"),
    ("GET", "/skills/orphans/{name}/files/content"): (
        "file-content",
        "a skill's files are plain files",
    ),
    ("GET", "/agents/{uid}/config-files/{key}/content"): (
        "file-content",
        "an agent's config file is its own plain file",
    ),
    ("GET", "/agents/{uid}/native-memory/files/content"): (
        "file-content",
        "an agent's native memory is its own plain file",
    ),
    ("GET", "/agents/{uid}/unmanaged-skills/{skill}/files/content"): (
        "file-content",
        "a skill's files are plain files",
    ),
    # Acts whose whole meaning is the window a person sits at.
    ("GET", "/channels/{uid}/people/{sender_id}/avatar"): (
        "window",
        "a paired person's picture in the owner list",
    ),
    ("GET", "/fs/browse"): ("window", "the folder picker's own listing"),
    ("GET", "/fs/editors"): ("window", "which editors the Open in… menu offers"),
    ("GET", "/fs/terminals"): ("window", "which terminals the Open in… menu offers"),
    ("POST", "/fs/open"): ("window", "opens a file in the person's editor"),
    ("POST", "/fs/reveal"): ("window", "reveals a file in Finder"),
    ("POST", "/fs/terminal"): ("window", "opens a terminal window for the person"),
    ("POST", "/fs/pick-folder"): ("window", "a native folder picker for the person"),
    ("POST", "/sync/join-choices/editor"): ("window", "opens a conflicting file in the editor"),
    ("POST", "/sync/stop/files/editor"): ("window", "opens a conflicting file in the editor"),
}

#: The desktop shell's IPC commands: the command that does the same, or why none.
SHELL_COMMANDS: dict[str, str | tuple[Category, str]] = {
    "restart_daemon": "daemon restart",
    # The offline screen opens the file with no daemon; `path logs` names that
    # file without one. `log daemon` reads through the daemon (and starts it),
    # so it is the Activity page's counterpart, not this one's.
    "show_daemon_log": "path logs",
    "get_daemon_info": ("internal", "the page's handshake with the shell"),
    "daemon_version_matches": ("internal", "the page's handshake with the shell"),
    "set_ui_language": ("window", "the window's interface language"),
    "set_attention_count": ("internal", "the menu bar's count, set by the page"),
    "reveal_secret": "secret reveal",
    "export_master_key_backup": "secret backup-key",
    "master_key_backup_closed": (
        "internal",
        "the backup dialog closing ends the command's waiting request",
    ),
    "import_master_key": "secret import-key",
    "approve_pending": "approval approve",
    "approve_pending_batch": "approval approve",
    "update_status": "app update status",
    "check_for_updates": "app update check",
    "install_update": "app update install",
    "set_update_auto_check": "app update auto-check",
    "uninstall_coffer": "uninstall",
}


__all__ = ["EXEMPT", "OPERATIONS", "SHELL_COMMANDS", "Category", "Operation", "maps", "record"]
