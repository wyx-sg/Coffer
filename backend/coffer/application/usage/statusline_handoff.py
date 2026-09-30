"""The prompt for opting in to the Claude Code statusline wrapper (spec
provider-switching "Offer an opt-in statusline wrapper").

Coffer never installs the wrapper: it wraps the person's own ``statusLine``
command, which differs per person, in a settings file that is Claude Code's.
So the edit is handed to the person's agent (``domain/handoff.py``), with the
file, the wrapper's exact form and how it treats its argument — one argument
is run as a shell command line, which is what ``statusLine.command`` holds.
The prompt asks for no secret and no quota endpoint: the wrapper forwards
only the ``rate_limits`` Claude Code already writes to the status line.
"""

from __future__ import annotations

import pathlib

from coffer.domain.handoff import Handoff, render_handoff

#: The wrapper's command line, before the person's own command.
WRAPPER = "coffer usage statusline"


def statusline_handoff(config_dir: pathlib.Path) -> str:
    """The opt-in prompt for the Claude Code whose settings live in ``config_dir``."""
    settings = config_dir / "settings.json"
    return render_handoff(
        Handoff(
            task=(
                f"Please set up Coffer's status line wrapper for Claude Code in {settings}, "
                "so Coffer can show my subscription quota."
            ),
            facts=(
                f"Claude Code's settings file: {settings}. The status line is its "
                '`statusLine` setting, `{"type": "command", "command": "..."}`.',
                f"The wrapper is `{WRAPPER} -- <my own statusLine command>`. It passes "
                "the rate limits Claude Code writes to the status line on to Coffer, then "
                "runs my own command with the same input and prints what it prints, even "
                "when Coffer is not running.",
                "Given one argument after `--`, the wrapper runs it as a shell command line, "
                "so my current command goes in as one quoted argument.",
                f"With no command after it, `{WRAPPER}` prints nothing, which leaves the "
                "status line empty.",
                "Claude Code must find `coffer` on the PATH it runs the status line with; "
                "if it does not, use the full path of `coffer`.",
            ),
            steps=(
                "Read the file. If `statusLine.command` is set, wrap it as "
                f"`{WRAPPER} -- '<it>'` with the quoting that keeps it one argument; if "
                "there is no `statusLine`, add one whose command is "
                f"`{WRAPPER}` alone.",
                "Keep every other setting exactly as it is, and show me the diff before "
                "you save it. Touch no other file in that folder.",
                "Afterwards, tell me the quota appears on Coffer's Usage page once I "
                "next use Claude Code in a terminal.",
            ),
        )
    )


__all__ = ["WRAPPER", "statusline_handoff"]
