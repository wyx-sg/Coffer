"""``coffer memory hook`` — the one command of the memory group.

The installed memory hook entries in an agent's own settings file run it, so it
stays on the command line, hidden because nobody types it. Notes, partitions
and what was delivered are the Memory page's job (spec resource-framework
"Keep the command line to what needs it").
"""

from __future__ import annotations

import typer

from coffer.surfaces.cli import memory_hook_cmd

app = typer.Typer(help="Memory hook entry point", hidden=True)

app.command("hook", hidden=True)(memory_hook_cmd.hook)
