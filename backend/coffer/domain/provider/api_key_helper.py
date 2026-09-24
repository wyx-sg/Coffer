"""The ``apiKeyHelper`` line Coffer projects into Claude Code's ``settings.json``.

Building it and recognising it are two halves of one fact — what Coffer writes
and what de-projection may therefore remove — so they live together, apart from
the settings/TOML transforms in :mod:`coffer.domain.provider.projection` that
use them. Pure: no filesystem access.
"""

from __future__ import annotations

import pathlib
import shlex

#: The words every Coffer-managed ``apiKeyHelper`` runs: the ``coffer`` CLI's
#: ``provider key`` command. Coffer writes the CLI as an absolute path
#: (``/Users/me/.coffer/bin/coffer provider key --connection-uid <uid>``); files
#: on disk still hold the older bare form (``coffer provider key ...``) and, before
#: the uid existed, the name form (``--connection <name>``) and the wire form
#: (``--wire anthropic``). :func:`is_managed_api_key_helper` recognises all of
#: them, so de-projection never clobbers a user-owned helper but always reverts
#: ours — including one this machine wrote before any of those changes.
#: Recognising those on the way OUT is not a compatibility shim: nothing reads
#: them, and a file Coffer wrote is a file Coffer has to be able to clean up.
_CLI_NAME = "coffer"
_KEY_COMMAND = ["provider", "key"]


def anthropic_api_key_helper(connection_uid: str, *, coffer_cli: str) -> str:
    """The ``apiKeyHelper`` Coffer projects for Claude Code: fetch one specific
    connection's key on demand (so the raw key is never written to disk).

    ``coffer_cli`` is the CLI to run, resolved by the caller — an absolute path,
    because Claude Code launched from the Dock or Finder does not get the login
    shell's ``PATH`` and a bare ``coffer`` would not be found. Claude Code runs
    the helper through a shell, so a path holding a space is quoted.

    Keyed by the connection's UID, not its name and not its wire. The wire could
    not say which connection's key to fetch at all; the name could, until the
    user renamed the connection and left the agent shelling out to something
    that no longer resolved — which is why a rename used to have to rewrite
    this file, and why it no longer has to
    (ADR resource-identity-is-an-immutable-uid). A uid never changes, so the
    line stays true for the life of the connection.
    """
    return f"{shlex.quote(coffer_cli)} provider key --connection-uid {connection_uid}"


def is_managed_api_key_helper(helper: object) -> bool:
    """Whether ``helper`` is an ``apiKeyHelper`` Coffer wrote: a command whose
    program is the ``coffer`` CLI (bare, or by any path, quoted or not) and
    whose first two arguments are ``provider key``."""
    if not isinstance(helper, str):
        return False
    try:
        argv = shlex.split(helper)
    except ValueError:  # unbalanced quotes: not a line Coffer wrote
        return False
    return (
        len(argv) >= 3 and pathlib.PurePath(argv[0]).name == _CLI_NAME and argv[1:3] == _KEY_COMMAND
    )
