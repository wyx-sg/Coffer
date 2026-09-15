"""Startup notice for config dirs left behind by agent types Coffer dropped.

Coffer narrowed its supported agent types to ``claude_code`` + ``codex``.
Migration 0048 deletes the removed types' ``kind='agent'`` resource rows, but
nothing on disk is touched: the migration owns the database, not the user's
other tools. Whatever Coffer once wrote into those agents' config directories
(its own MCP entry, hooks, skill symlinks) stays exactly where it is.

So the daemon names the surviving paths **once** — on the first start after
the migration — and leaves the decision to clean them up with the user. A
marker file under ``~/.coffer/state/`` records that the notice went out: the
directories are the user's other tools' and may legitimately stay forever, so
repeating the warning on every boot would only teach them to ignore the log.
Deleting the marker replays the notice once.
"""

from __future__ import annotations

import logging
import os
import pathlib

_logger = logging.getLogger(__name__)

#: Home-relative marker whose presence means the notice has already been given.
NOTICE_MARKER = pathlib.Path(".coffer") / "state" / "removed-agent-notice.done"

# Home-relative config dirs of the four removed agent types. Inlined on purpose
# — these values are gone from ``AgentType``, so there is nothing left to import
# and the list must stay frozen even as the model evolves.
UNMANAGED_AGENT_CONFIG_DIRS: tuple[tuple[str, str], ...] = (
    ("opencode", ".config/opencode"),
    ("hermes", ".hermes"),
    ("cursor", ".cursor"),
    ("openclaw", ".openclaw"),
)


def _home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("HOME", "~")).expanduser()


def _mark_notified(marker: pathlib.Path) -> None:
    """Record that the notice went out. Best-effort: an unwritable marker
    means the notice repeats next boot, which is the lesser failure."""
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("notified\n", encoding="utf-8")
    except OSError:
        _logger.debug("removed_agent_type.notice_marker_unwritable", exc_info=True)


def report_removed_agent_leftovers() -> None:
    """Name the config dirs of dropped agent types that still exist on disk.

    Logs nothing at all when none of them exist, so a fresh install's startup
    output stays clean — and nothing once the notice has been given, so a
    user who keeps those tools is told once rather than on every boot.
    """
    home = _home()
    marker = home / NOTICE_MARKER
    if marker.exists():
        return
    _mark_notified(marker)
    for agent_type, relative in UNMANAGED_AGENT_CONFIG_DIRS:
        path = home / relative
        if not path.exists():
            continue
        _logger.warning(
            "removed_agent_type.config_dir_left_in_place",
            extra={
                "agent_type": agent_type,
                "path": str(path),
                "detail": (
                    f"Coffer no longer manages {agent_type} agents; files it wrote "
                    f"into {path} are left as-is. Remove them yourself if unwanted."
                ),
            },
        )
