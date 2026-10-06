"""``coffer secret`` beyond ``list`` and ``set`` — the Secrets page.

Spec secret "List every stored and cited secret with what uses it" and
"Import a master key after showing whose key it is". No command prints a value
or the master key: revealing one is ``coffer secret reveal``, which shows it in
the desktop app after the person's presence check, and importing a key is
``coffer secret import-key``, which opens the app's own import.
"""

from __future__ import annotations

from coffer.surfaces.cli._route_command import RouteCommand, mount

_UI = "Secrets · "
_KEY = "Settings · Security · master key · "

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
    RouteCommand(
        "secret key-fingerprint",
        "GET",
        "/secrets/key/fingerprint",
        _KEY + "fingerprint",
        "This machine's master key fingerprint (never the key).",
    ),
    RouteCommand(
        "secret key-preview",
        "POST",
        "/secrets/key/import/preview",
        _KEY + "import (review)",
        "Whose key a key backup holds, beside this machine's; changes nothing. Body: "
        "material (read from a file with --data @backup.json).",
        body=True,
    ),
    RouteCommand(
        "secret key-install",
        "POST",
        "/secrets/key/import",
        _KEY + "import (the app's request)",
        "The request the Coffer app sends to install a key backup. Body: material, "
        "passphrase, nonce, signature, where nonce and signature are the presence grant "
        "the app signs after its own Touch ID check; the command line cannot get one, "
        "and without it nothing is installed. To import a key, run "
        "`coffer secret import-key`, which opens the import in the app.",
        body=True,
    ),
]

mount(SPECS)
