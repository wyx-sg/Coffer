"""``coffer vault`` beyond ``problems`` — a file's or folder's history and restore.

Spec vault-storage "Show and restore any version of a vault file or folder".
"""

from __future__ import annotations

from coffer.surfaces.cli._route_command import Q, RouteCommand, mount

SPECS = [
    RouteCommand(
        "vault history",
        "GET",
        "/vault/history",
        "Knowledge, Skills · History tab",
        "A vault path's versions, newest first, each with its writer.",
        query=(Q("path", "A path under the vault"), Q("limit", kind=int), Q("cursor")),
    ),
    RouteCommand(
        "vault diff",
        "GET",
        "/vault/diff",
        "History tab · a version's changes",
        "One version's diff.",
        query=(Q("path"), Q("version"), Q("against", "previous or current")),
    ),
    RouteCommand(
        "vault restore",
        "POST",
        "/vault/restore",
        "History tab · Restore this version",
        "Write a version back as a new commit. Body: path, version, expected_current.",
        body=True,
    ),
]

mount(SPECS)
