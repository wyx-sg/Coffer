"""``coffer secret`` beyond ``list`` and ``set`` — the Secrets page.

Spec secret "List every stored and cited secret with what uses it". No command
prints a value: revealing one is ``coffer secret reveal``, which shows it in
the desktop app after the person's presence check.
"""

from __future__ import annotations

from coffer.surfaces.cli._route_command import RouteCommand, mount

_UI = "Secrets · "

SPECS = [
    RouteCommand(
        "secret delete",
        "DELETE",
        "/secrets/{ref}",
        _UI + "Delete",
        "Delete a secret nothing uses any more.",
    ),
    RouteCommand(
        "secret describe",
        "PUT",
        "/secrets/notes",
        _UI + "Edit label and description",
        "Label and describe a secret. Body: ref, label, description.",
        body=True,
    ),
    RouteCommand(
        "secret scan",
        "POST",
        "/secrets/scan",
        _UI + "Find plaintext secrets",
        "Find plaintext secrets in skills and MCP servers (values are never shown).",
    ),
    RouteCommand(
        "secret import",
        "POST",
        "/secrets/import",
        _UI + "Move into the store",
        "Move found plaintext secrets into the store. Body: ids, dry_run.",
        body=True,
    ),
    RouteCommand(
        "secret ignore",
        "POST",
        "/secrets/scan/ignore",
        _UI + "Not a secret",
        "Remember found values as not secrets, so scans stop reporting them. Body: ids.",
        body=True,
    ),
    RouteCommand(
        "secret unignore",
        "POST",
        "/secrets/scan/unignore",
        _UI + "Report again",
        "Forget values remembered as not secrets. Body: ids.",
        body=True,
    ),
    RouteCommand(
        "secret local-access request",
        "POST",
        "/secrets/local-access/request",
        _UI + "Allow local programs (coffer run)",
        "Ask to hand a secret to programs coffer run starts; waits for approval. Body: name.",
        body=True,
        pending=True,
    ),
    RouteCommand(
        "secret local-access revoke",
        "POST",
        "/secrets/local-access/revoke",
        _UI + "Stop allowing local programs",
        "Withdraw the grant. Body: name.",
        body=True,
    ),
]

mount(SPECS)
