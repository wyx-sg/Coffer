"""Where each piece of state lives (ADR storage-is-five-classes-by-nature).

State is stored by what it **is**: a class decides the directory, and the
directory decides whether it can travel. Only ``vault/`` is a git repository
and only ``vault/`` is ever committed or pushed, so "reach never syncs" is a
fact about where reach is stored rather than a rule a translator must
remember.

Inside the vault, every path belongs to one **area** — the unit the deletion
breaker counts in and the Sync page groups by. An area is the first path
segment, except that ``resources/<kind>/`` and ``state/<area>/`` are areas of
their own, so a mass deletion of one kind's resources is not diluted by the
others.
"""

from __future__ import annotations

import re
from enum import StrEnum


class StorageClass(StrEnum):
    """The five classes, by nature."""

    #: The user's configuration and content: always a git repository, the only
    #: copy, converges with a remote when one is configured.
    VAULT = "vault"
    #: True of this machine only (reach, the sync remote, retention, agents):
    #: never synced; can be set again.
    LOCAL = "local"
    #: The user's only copy of media and the chat workspace: not synced yet.
    CONTENT = "content"
    #: Append-only history in ``runs.db``: never synced, pruned by retention.
    RUNS = "runs"
    #: Rebuilt from other state: deleting it is always safe.
    DERIVED = "derived"


#: The top-level directories of the vault repository.
RESOURCES = "resources"
STATE = "state"
KNOWLEDGE = "knowledge"
SKILLS = "skills"
MEMORY_TRIGGERS = "memory-triggers"
SECRET = "secret"
MACHINES = "machines"
MANIFEST = "manifest.json"

#: The one bundle-wide number the vault still carries. Builds from before
#: per-file versions read only this, and ``3`` is what makes them refuse the
#: file layout rather than misread it (ADR every-vault-file-carries-its-format-version).
MANIFEST_SCHEMA_VERSION = 3

#: Every top-level directory of the vault repository. Anything else a person
#: puts there is kept and committed like any other file, but belongs to no
#: area Coffer reads.
VAULT_DIRS = (RESOURCES, STATE, KNOWLEDGE, SKILLS, MEMORY_TRIGGERS, SECRET, MACHINES)

#: The suffix of every document Coffer parses (resources, state, machines).
DOCUMENT_SUFFIX = ".json"

_SAFE_STEM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def resource_path(kind: str, name: str) -> str:
    """Where Coffer files a new resource of ``kind`` named ``name``.

    Only where it *files* one: nothing keys on the path, a person may move the
    file, and the resource is the same resource wherever it is found (ADR
    identity-is-the-uid-inside-the-file).
    """
    return f"{RESOURCES}/{kind}/{safe_stem(name)}{DOCUMENT_SUFFIX}"


def state_path(area: str, name: str) -> str:
    """Where a kind's state document for ``name`` is filed."""
    return f"{STATE}/{area}/{safe_stem(name)}{DOCUMENT_SUFFIX}"


def safe_stem(label: str) -> str:
    """``label`` as a file stem, with anything a file system or git would read
    specially replaced. Resource names are already safe; this is the fallback
    for a label that is not."""
    if _SAFE_STEM.match(label) and ".." not in label:
        return label
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip("-.") or "unnamed"
    return cleaned[:128]


def kind_of_resource_path(path: str) -> str | None:
    """The kind directory a resource document sits under, or ``None``."""
    parts = path.split("/")
    if len(parts) >= 3 and parts[0] == RESOURCES and path.endswith(DOCUMENT_SUFFIX):
        return parts[1]
    return None


def is_document(path: str) -> bool:
    """Whether Coffer parses the file at ``path`` (as opposed to carrying its
    bytes, as it does for knowledge and skill files)."""
    head = path.split("/", 1)[0]
    return path.endswith(DOCUMENT_SUFFIX) and head in (RESOURCES, STATE, MACHINES)


def area_of(path: str) -> str:
    """The area a vault-relative path belongs to (see the module docstring)."""
    parts = path.split("/")
    head = parts[0]
    if head in (RESOURCES, STATE) and len(parts) >= 3:
        return f"{head}/{parts[1]}"
    if head in VAULT_DIRS:
        return head
    if path == MANIFEST:
        return "manifest"
    return "other"


__all__ = [
    "DOCUMENT_SUFFIX",
    "KNOWLEDGE",
    "MACHINES",
    "MANIFEST",
    "MANIFEST_SCHEMA_VERSION",
    "MEMORY_TRIGGERS",
    "RESOURCES",
    "SECRET",
    "SKILLS",
    "STATE",
    "VAULT_DIRS",
    "StorageClass",
    "area_of",
    "is_document",
    "kind_of_resource_path",
    "resource_path",
    "safe_stem",
    "state_path",
]
