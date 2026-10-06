"""The ``coffer memory`` group, and ``coffer memory hook`` in it.

The group is visible: the Memory page's operations (partitions, notes, what
was delivered, sync, tidy) are its commands, declared in ``commands/memory.py``
(spec resource-framework "Offer every management operation on the command
line"). Only ``hook`` is hidden — the installed memory hook entries in an
agent's own settings file run it, and nobody types it.
"""

from __future__ import annotations

import typer

from coffer.surfaces.cli import memory_hook_cmd

app = typer.Typer(no_args_is_help=True)

app.command("hook", hidden=True)(memory_hook_cmd.hook)
