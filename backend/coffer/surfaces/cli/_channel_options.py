"""The channel group's own options and the config they write (spec channels).

Shared by ``coffer channel add`` and the ``edit`` flags the lifecycle-verb
factory carries for this kind.
"""

from __future__ import annotations

import inspect
import os
from typing import Any

import typer

# Group gating (spec channels "Configure when the bot answers in a group"):
# tri-state, so an option left out keeps the stored value (or, at register,
# the config's own default) instead of overwriting it.
_REQUIRE_MENTION = typer.Option(
    None,
    "--require-mention/--no-require-mention",
    help="In groups, answer only when @mentioned or replied to (default: on)",
)
_IGNORE_OTHER_MENTIONS = typer.Option(
    None,
    "--ignore-other-mentions/--no-ignore-other-mentions",
    help="In groups, drop a message that @mentions anyone else (default: off)",
)


_WAIT_AFTER_TEXT = typer.Option(
    None,
    "--wait-after-text",
    min=0,
    max=60,
    help="Seconds to wait after a text message for more before answering (default: 1.5; 0 = none)",
)
# "Show a turn's working state as one status line".
_SHOW_STEPS = typer.Option(
    None,
    "--show-steps/--hide-steps",
    help="List each step under the live status line while a turn runs (default: on)",
)
# "Ping the asker when a long turn ends".
_NOTIFY_AFTER = typer.Option(
    None,
    "--notify-after",
    min=0,
    max=3600,
    help="Ping the chat when a turn runs at least this many seconds (default: 90; 0 = never)",
)
_WAIT_AFTER_FORWARD = typer.Option(
    None,
    "--wait-after-forward",
    min=0,
    max=60,
    help="Seconds to wait after a forwarded record or files with no text (default: 5; 0 = none)",
)


# The directories `/dir` may switch into (spec channels "Choose the working
# directory from chat"). Repeatable; on ``edit`` the list given REPLACES the
# stored one, and ``--no-dirs`` clears it.
_DIRS = typer.Option(
    None,
    "--dir",
    help="An absolute directory `/dir` may switch into (repeat for several; replaces the list)",
)
_NO_DIRS = typer.Option(
    False, "--no-dirs", help="Allow no directories for `/dir` (clears the list)"
)


# The channel's default working directory — where its new conversations start
# (spec channels "Choose the working directory from chat"). Stored as
# ``default_agent_config.cwd``; ``--no-default-dir`` clears it.
_DEFAULT_DIR = typer.Option(
    None,
    "--default-dir",
    help="The directory new conversations start in (default: the agent's own)",
)
_NO_DEFAULT_DIR = typer.Option(
    False, "--no-default-dir", help="Clear the default directory (the agent's own applies)"
)


def with_default_dir(
    agent_config: dict[str, Any] | None, default_dir: str | None, no_default_dir: bool
) -> dict[str, Any] | None:
    """``agent_config`` with its ``cwd`` set to ``default_dir`` (made absolute), or
    removed for ``no_default_dir``; ``None`` when neither was passed."""
    if not no_default_dir and default_dir is None:
        return None
    merged = dict(agent_config or {})
    if no_default_dir:
        merged.pop("cwd", None)
    else:
        merged["cwd"] = os.path.abspath(os.path.expanduser(str(default_dir)))
    return merged


def directories(dirs: list[str] | None, no_dirs: bool) -> list[str] | None:
    """The allow-list the user passed, or ``None`` when they passed none. Relative
    paths are made absolute against the current directory, as a shell user means."""
    if no_dirs:
        return []
    if not dirs:
        return None
    return [os.path.abspath(os.path.expanduser(d)) for d in dirs]


def _settings(
    require_mention: bool | None,
    ignore_other_mentions: bool | None,
    wait_after_text: float | None = None,
    wait_after_forward: float | None = None,
    show_steps: bool | None = None,
    notify_after: float | None = None,
) -> dict[str, bool | float]:
    """The config keys the user actually passed: group gating ("Configure when the
    bot answers in a group"), the quiet windows ("Take a burst of messages as
    one turn") and what a running turn shows ("Show a turn's working state as
    one status line")."""
    passed: dict[str, bool | float | None] = {
        "require_mention": require_mention,
        "ignore_other_mentions": ignore_other_mentions,
        "wait_after_text_seconds": wait_after_text,
        "wait_after_forward_seconds": wait_after_forward,
        "show_steps": show_steps,
        "notify_after_seconds": notify_after,
    }
    return {key: value for key, value in passed.items() if value is not None}


def settings_config(resource: dict[str, Any], values: dict[str, Any]) -> dict[str, Any] | None:
    """The stored config with only the settings given changed (``edit``)."""
    changes: dict[str, Any] = dict(
        _settings(
            values.get("require_mention"),
            values.get("ignore_other_mentions"),
            values.get("wait_after_text"),
            values.get("wait_after_forward"),
            values.get("show_steps"),
            values.get("notify_after"),
        )
    )
    dirs = directories(values.get("dirs"), bool(values.get("no_dirs")))
    if dirs is not None:
        changes["directories"] = dirs
    stored = resource.get("config") or {}
    agent_config = with_default_dir(
        stored.get("default_agent_config"),
        values.get("default_dir"),
        bool(values.get("no_default_dir")),
    )
    if agent_config is not None:
        changes["default_agent_config"] = agent_config or None
    if not changes:
        return None
    return {**(resource.get("config") or {}), **changes}


def edit_option(name: str, default: Any, annotation: Any = bool | None) -> inspect.Parameter:
    return inspect.Parameter(
        name, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=default, annotation=annotation
    )
